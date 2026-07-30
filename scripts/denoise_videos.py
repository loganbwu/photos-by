#!/usr/bin/env python3
"""Denoise every video in a folder (recursively) using ffmpeg's vaguedenoiser filter.

By default each video is left untouched — output is written alongside it as
<name>_denoised<ext> (skipped if that file already exists). With --overwrite,
each source file is replaced in place instead (there's no way to transcode a
video into its own bytes, so this still encodes to a temp file first and
swaps it in once validated — but only one file's worth of extra space is
ever in use at a time, and files are processed one at a time rather than in
parallel, instead of the whole batch's worth of extra space at once).

Each video is encoded in a single ffmpeg pass — never split into chunks.
An earlier version chunked long videos and encoded the chunks of a single
file in parallel, then reassembled them; that was producing ~1/3 second
audio glitches at some chunk boundaries, so chunking was removed entirely
rather than just serialized, to rule out any splice-related cause along
with the concurrency itself. Parallelism instead comes from encoding
multiple files at once (in default mode only; --overwrite still processes
one file at a time to bound extra disk usage).

An overall progress bar tracks files completed across the whole batch, with
ETA, plus one progress bar per file currently being encoded (in default mode).
All bars are updated continuously from ffmpeg's own progress stream as each
file encodes, not just when it finishes, so they won't look stalled on heavy
footage.

If the run looks likely to push disk usage past 90%, you'll be warned and
asked to confirm, with a suggestion to use --overwrite if you aren't already.

Usage: python3 denoise_videos.py <folder> [--mbps MBPS] [--overwrite]

Requires ffmpeg on PATH. Uses hevc_videotoolbox hardware encoding when
available (Apple Silicon), falling back to libx265.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

VIDEO_EXTS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.mts', '.m2ts', '.wmv', '.flv', '.webm'}
CONTAINER_PASSTHROUGH_EXTS = {'.mp4', '.mov', '.m4v', '.mts', '.m2ts'}  # can hold HEVC as-is

WORKERS = max(1, (os.cpu_count() or 2) - 1)  # max files encoded concurrently; leave one core free
DISK_WARN_PCT = 90

# The VideoToolbox media-encode engine only supports a couple of concurrent
# hardware HEVC sessions (far fewer than the CPU core count, and it varies by
# chip) — asking for more doesn't queue, it fails outright with "Could not open
# encoder before EOF". Cap concurrent hardware-encode sessions well below
# WORKERS regardless of how many cores are free.
HARDWARE_ENCODE_CONCURRENCY = min(WORKERS, 2)
HARDWARE_ENCODER_BUSY_MARKERS = ('Could not open encoder before EOF',)
HARDWARE_ENCODER_MAX_ATTEMPTS = 4

# Run ffmpeg at the lowest scheduling/I/O priority so it only uses spare capacity
# and gets out of the way of foreground work. On macOS, `taskpolicy -b -d throttle`
# lowers CPU scheduling priority (PRIO_DARWIN_BG) and this process's own disk I/O
# priority. Deliberately NOT `-c background` (a QoS clamp): that gates access to
# shared hardware like the VideoToolbox media-encode engine, and a QoS-clamped
# process can get starved indefinitely whenever anything else on the system wants
# that hardware too — it stalls completely rather than just running slower.
if platform.system() == 'Darwin' and shutil.which('taskpolicy'):
    BACKGROUND_PREFIX = ['taskpolicy', '-b', '-d', 'throttle']
elif shutil.which('nice'):
    BACKGROUND_PREFIX = ['nice', '-n', '19']
else:
    BACKGROUND_PREFIX = []

# vaguedenoiser: wavelet-based denoiser. These are "moderate" settings — enough
# to clean sensor noise without visibly softening detail.
DENOISE_FILTER = 'vaguedenoiser=threshold=2:method=soft:nsteps=6:percent=85'


@dataclass
class FileJob:
    index: int
    path: Path
    output: Path      # working path ffmpeg actually writes to
    final_path: Path  # where `output` ends up once validated (== path itself when overwriting)
    duration: float
    bit_rate: int | None
    pix_fmt: str | None
    timecode: str | None


def _probe(path: Path, *entries: str, select_streams: str | None = None) -> str:
    cmd = ['ffprobe', '-v', 'error']
    if select_streams:
        cmd += ['-select_streams', select_streams]
    cmd += ['-show_entries', *entries, '-of', 'default=noprint_wrappers=1:nokey=1', str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()


def get_duration(path: Path) -> float | None:
    raw = _probe(path, 'format=duration')
    try:
        return float(raw)
    except ValueError:
        return None


def get_bit_rate(path: Path) -> int | None:
    raw = _probe(path, 'stream=bit_rate', select_streams='v:0')
    return int(raw) if raw.isdigit() else None


def get_pix_fmt(path: Path) -> str | None:
    return _probe(path, 'stream=pix_fmt', select_streams='v:0') or None


def get_timecode(path: Path) -> str | None:
    return _probe(path, 'stream_tags=timecode', select_streams='d') or None


def is_valid_video(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0 and get_duration(path) is not None


def pick_encoder() -> list[str]:
    result = subprocess.run(['ffmpeg', '-encoders', '-v', 'quiet'], capture_output=True, text=True)
    if 'hevc_videotoolbox' in result.stdout:
        print("Encoder: hevc_videotoolbox (hardware)")
        return ['-c:v', 'hevc_videotoolbox']
    print("Encoder: libx265 (software)")
    return ['-c:v', 'libx265', '-preset', 'medium']


def pixel_args(pix_fmt: str | None, hardware: bool) -> tuple[str, list[str]]:
    """Return (extra vf format filter, profile args) matching the source's bit depth/chroma.

    Only meaningful for the videotoolbox hardware path — libx265 handles arbitrary
    pixel formats on its own.
    """
    if not hardware or not pix_fmt:
        return '', []
    if '422' in pix_fmt:
        return 'format=p210le', ['-profile:v', 'main42210']
    if '10' in pix_fmt:
        return 'format=p010le', ['-profile:v', 'main10']
    return 'format=nv12', ['-profile:v', 'main']


def bitrate_args(mbps: float | None, source_bit_rate: int | None) -> list[str]:
    if mbps is not None:
        return ['-b:v', str(int(mbps * 1_000_000))]
    if source_bit_rate:
        return ['-b:v', str(source_bit_rate)]
    return []


def discover_videos(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.rglob('*')
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
        and not p.stem.endswith('_denoised')
        and not p.name.startswith('.')  # skip our own leftover .*.denoising.tmp* files
    )


def cleanup_stale_temp_files(folder: Path) -> None:
    """Remove .*.denoising.tmp* files left behind by a previous run that got interrupted."""
    for p in folder.rglob('.*.denoising.tmp*'):
        if p.is_file():
            print(f"  Removing stale temp file from an interrupted run: {p.name}")
            p.unlink(missing_ok=True)


def final_path_for(video: Path, overwrite: bool) -> Path:
    if overwrite:
        # Same container extensions can hold HEVC as-is and get replaced under
        # their original name; anything else (e.g. .avi) gets swapped to .mp4 —
        # the old file is still deleted, just under a different final name.
        if video.suffix.lower() in CONTAINER_PASSTHROUGH_EXTS:
            return video
        return video.with_suffix('.mp4')
    ext = video.suffix if video.suffix.lower() in CONTAINER_PASSTHROUGH_EXTS else '.mp4'
    return video.parent / f"{video.stem}_denoised{ext}"


def working_path_for(video: Path, final: Path, overwrite: bool) -> Path:
    if not overwrite:
        return final  # no name collision with the source, safe to encode directly into it
    # Dot-prefixed temp name next to the source, guaranteeing the same filesystem
    # so the final swap is an instant rename rather than a second copy.
    return video.with_name(f".{video.stem}.denoising.tmp{final.suffix}")


def estimate_output_bytes(duration: float, bit_rate: int | None, mbps: float | None, path: Path) -> int:
    if mbps is not None:
        return int(duration * mbps * 1_000_000 / 8)
    if bit_rate:
        return int(duration * bit_rate / 8)
    return path.stat().st_size  # best-effort fallback: assume similar size to the source


def build_jobs(files: list[Path], overwrite: bool) -> list[FileJob]:
    jobs = []
    for i, video in enumerate(files):
        final_path = final_path_for(video, overwrite)
        if not overwrite and final_path.exists():
            print(f"  SKIP (already denoised): {video.name}")
            continue

        duration = get_duration(video)
        if duration is None:
            print(f"  SKIP (unreadable): {video.name}")
            continue

        jobs.append(FileJob(
            index=i,
            path=video,
            output=working_path_for(video, final_path, overwrite),
            final_path=final_path,
            duration=duration,
            bit_rate=get_bit_rate(video),
            pix_fmt=get_pix_fmt(video),
            timecode=get_timecode(video),
        ))
    return jobs


def disk_usage_pct(folder: Path, extra_bytes: int) -> float:
    usage = shutil.disk_usage(folder)
    return (usage.used + extra_bytes) / usage.total * 100


def confirm_disk_space(folder: Path, jobs: list[FileJob], mbps: float | None, overwrite: bool) -> None:
    estimates = [estimate_output_bytes(j.duration, j.bit_rate, mbps, j.path) for j in jobs]
    # Overwrite mode processes one file at a time and frees each original before
    # starting the next, so the peak extra usage is one file's worth, not the batch's.
    peak_extra = max(estimates, default=0) if overwrite else sum(estimates)

    projected = disk_usage_pct(folder, peak_extra)
    if projected <= DISK_WARN_PCT:
        return

    print(f"\nWARNING: this run is projected to push disk usage to about {projected:.0f}% "
          f"(threshold {DISK_WARN_PCT}%).")
    if not overwrite:
        print("Re-run with --overwrite to replace each source file in place instead of "
              "keeping both the original and the denoised copy — that needs roughly one "
              "file's worth of extra space at a time instead of the whole batch's.")
    answer = input("Continue anyway? [y/N]: ").strip().lower()
    if answer != 'y':
        print("Aborted.")
        sys.exit(1)


_hardware_encode_slots = threading.Semaphore(HARDWARE_ENCODE_CONCURRENCY)


def _run_with_progress(cmd: list[str], duration_hint: float, pbars: list[tqdm],
                        lock: threading.Lock) -> tuple[int, str, float]:
    """Run ffmpeg, nudging pbars continuously (by fraction of the file's duration) as
    -progress reports how far into duration_hint seconds of output it's gotten — rather
    than only once the whole file finishes, which can otherwise leave the bars looking
    stalled for a long time on heavy footage. Returns (returncode, stderr, fraction of
    pbar credit already given) — the caller tops up the remaining fraction itself, once,
    after any retries, so a retried attempt doesn't get double-counted.
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    stderr_chunks: list[str] = []
    def _drain_stderr() -> None:
        for chunk in proc.stderr:
            stderr_chunks.append(chunk)
    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    last_frac = 0.0
    for line in proc.stdout:
        if not line.startswith('out_time_ms='):
            continue
        raw = line.strip().split('=', 1)[1]
        if raw in ('N/A', ''):
            continue
        frac = min(int(raw) / 1_000_000 / duration_hint, 1.0) if duration_hint > 0 else 1.0
        if frac > last_frac:
            with lock:
                for pbar in pbars:
                    pbar.update(frac - last_frac)
            last_frac = frac

    proc.wait()
    stderr_thread.join()
    return proc.returncode, ''.join(stderr_chunks), last_frac


def encode_file(job: FileJob, tmp_dir: Path, encoder: list[str], hardware: bool,
                 mbps: float | None, pbars: list[tqdm], lock: threading.Lock) -> Path | None:
    fmt, profile = pixel_args(job.pix_fmt, hardware)
    vf = f"{DENOISE_FILTER},{fmt}" if fmt else DENOISE_FILTER

    tmp_out = tmp_dir / f"{job.index:04d}.mp4"

    # Hardware (VideoToolbox) encode sessions are highly sensitive to the calling
    # process's scheduling priority: macOS treats the media-encode engine as a
    # foreground-only resource and all but freezes a backgrounded/niced client's
    # access to it (measured ~0.02x realtime vs 30x+ unthrottled) rather than just
    # slowing it down proportionally. Software encoding doesn't have this problem,
    # so only nice/background that path.
    prefix = [] if hardware else BACKGROUND_PREFIX
    cmd = [*prefix, 'ffmpeg', '-y', '-nostdin', '-loglevel', 'error',
           '-progress', 'pipe:1', '-nostats', '-i', str(job.path),
           '-vf', vf, *encoder, *profile, *bitrate_args(mbps, job.bit_rate)]
    if job.timecode:
        cmd += ['-timecode', job.timecode]
    cmd += ['-c:a', 'copy', str(tmp_out)]

    max_attempts = HARDWARE_ENCODER_MAX_ATTEMPTS if hardware else 1
    returncode, stderr, last_frac = -1, '', 0.0
    for attempt in range(1, max_attempts + 1):
        if hardware:
            with _hardware_encode_slots:
                returncode, stderr, last_frac = _run_with_progress(cmd, job.duration, pbars, lock)
        else:
            returncode, stderr, last_frac = _run_with_progress(cmd, job.duration, pbars, lock)

        if returncode == 0 and is_valid_video(tmp_out):
            break
        # The hardware encoder only supports a couple of concurrent sessions
        # system-wide (shared with any other app using it, not just this script),
        # so "no free session" can still happen even under our own concurrency
        # cap — retry with backoff rather than failing the file outright.
        busy = hardware and any(marker in stderr for marker in HARDWARE_ENCODER_BUSY_MARKERS)
        if busy and attempt < max_attempts:
            tqdm.write(f"  Hardware encoder busy, retrying {job.path.name}, "
                       f"attempt {attempt + 1}/{max_attempts}...")
            time.sleep(attempt * 3)
            continue
        break

    with lock:
        for pbar in pbars:
            pbar.update(1.0 - last_frac)

    if returncode != 0 or not is_valid_video(tmp_out):
        tqdm.write(f"  ERROR encoding {job.path.name}:\n{stderr.strip()[-500:]}")
        tmp_out.unlink(missing_ok=True)
        return None
    return tmp_out


def finalize(job: FileJob, tmp_out: Path | None, overwrite: bool) -> bool:
    if tmp_out is None:
        tqdm.write(f"  FAILED: {job.path.name}")
        return False

    shutil.move(str(tmp_out), str(job.output))

    if overwrite:
        # Atomic rename on the same filesystem — overwrites final_path if it already
        # exists (the same-name case), and is a directory-entry swap, not a copy.
        job.output.replace(job.final_path)
        if job.final_path != job.path:
            job.path.unlink(missing_ok=True)

    size_mb = job.final_path.stat().st_size / 1_048_576
    tqdm.write(f"  Saved: {job.final_path.name}  ({size_mb:.0f} MB)")
    return True


class FileBarPool:
    """A fixed set of per-file progress bars, one per concurrently-processing file slot.

    Worker threads are long-lived (a ThreadPoolExecutor reuses them across jobs), so
    each thread claims one slot the first time it processes a file and keeps it for
    its lifetime — reset() and set_description() just repoint that same bar at
    whatever file the thread picks up next.
    """

    def __init__(self, n: int, base_position: int):
        bar_format = "  {desc}: {bar}| {percentage:3.0f}% [{elapsed}<{remaining}]"
        self._bars = [tqdm(total=1, position=base_position + i, leave=False, bar_format=bar_format)
                      for i in range(n)]
        self._free = list(range(n))
        self._lock = threading.Lock()
        self._local = threading.local()

    def acquire(self, job: 'FileJob') -> tqdm:
        if not hasattr(self._local, 'slot'):
            with self._lock:
                self._local.slot = self._free.pop()
        bar = self._bars[self._local.slot]
        bar.reset(total=1)
        bar.set_description(job.path.name[:40])
        return bar

    def close(self) -> None:
        for bar in self._bars:
            bar.close()


def process_file(job: FileJob, tmp_dir: Path, encoder: list[str], hardware: bool, mbps: float | None,
                  overall_pbar: tqdm, file_bars: FileBarPool, lock: threading.Lock,
                  overwrite: bool) -> bool:
    file_pbar = file_bars.acquire(job)
    tmp_out = encode_file(job, tmp_dir, encoder, hardware, mbps, [overall_pbar, file_pbar], lock)
    return finalize(job, tmp_out, overwrite)


def run(folder: Path, mbps: float | None, overwrite: bool) -> None:
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        print("ffmpeg/ffprobe not found on PATH. Install with: brew install ffmpeg")
        sys.exit(1)

    cleanup_stale_temp_files(folder)

    files = discover_videos(folder)
    print(f"Found {len(files)} video file(s) in {folder}\n")
    if not files:
        sys.exit(0)

    jobs = build_jobs(files, overwrite)
    if not jobs:
        print("\nNothing to do.")
        sys.exit(0)

    # Smallest files first, so quick wins land early instead of queuing behind
    # whatever huge file happened to sort alphabetically first.
    jobs.sort(key=lambda j: j.path.stat().st_size)

    confirm_disk_space(folder, jobs, mbps, overwrite)

    encoder = pick_encoder()
    hardware = encoder[1] == 'hevc_videotoolbox'
    print(f"{len(jobs)} file(s) to denoise\n")

    succeeded = failed = skipped = 0
    lock = threading.Lock()
    with tempfile.TemporaryDirectory(prefix='.denoise_videos_', dir=folder) as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        bar_format = "{l_bar}{bar}| {n:.1f}/{total} [{elapsed}<{remaining}, {rate_fmt}{postfix}]"
        with tqdm(total=len(jobs), desc="Total", unit="file", position=0, bar_format=bar_format) as pbar:

            if overwrite:
                # One file at a time, so at most one extra file's worth of disk
                # space is ever in use. A single file-progress bar is enough since
                # only one file is ever active.
                file_bars = FileBarPool(1, base_position=1)
                try:
                    for job in jobs:
                        needed = estimate_output_bytes(job.duration, job.bit_rate, mbps, job.path)
                        if disk_usage_pct(job.path.parent, needed) > DISK_WARN_PCT:
                            tqdm.write(f"  SKIP (would exceed {DISK_WARN_PCT}% disk usage): {job.path.name}")
                            pbar.update(1)
                            skipped += 1
                            continue

                        if process_file(job, tmp_dir, encoder, hardware, mbps, pbar, file_bars, lock, overwrite):
                            succeeded += 1
                        else:
                            failed += 1
                finally:
                    file_bars.close()
            else:
                # Files run in parallel, one progress bar each.
                n_slots = min(WORKERS, len(jobs))
                file_bars = FileBarPool(n_slots, base_position=1)
                try:
                    with ThreadPoolExecutor(max_workers=n_slots) as pool:
                        futures = [pool.submit(process_file, job, tmp_dir, encoder, hardware, mbps,
                                                pbar, file_bars, lock, overwrite)
                                   for job in jobs]
                        for future in as_completed(futures):
                            if future.result():
                                succeeded += 1
                            else:
                                failed += 1
                finally:
                    file_bars.close()

    summary = f"\nDone: {succeeded} denoised, {failed} failed"
    if skipped:
        summary += f", {skipped} skipped (disk space)"
    print(summary + '.')
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder', type=Path, help='Folder to recursively scan for video files')
    parser.add_argument('--mbps', type=float, default=None,
                        help='Target video bitrate in Mbps (default: match each source file\'s own bitrate)')
    parser.add_argument('--overwrite', action='store_true',
                        help='Replace each source file in place instead of writing a '
                             '_denoised copy alongside it')
    args = parser.parse_args()

    folder = args.folder.expanduser().resolve()
    if not folder.exists():
        print(f"Folder does not exist: {folder}")
        sys.exit(1)

    run(folder, args.mbps, args.overwrite)


if __name__ == '__main__':
    main()
