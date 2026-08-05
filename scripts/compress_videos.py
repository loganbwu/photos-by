#!/usr/bin/env python3
"""Compress every video in a folder (recursively) with ffmpeg/libx265 for long-term
archival, while keeping the output editable in DaVinci Resolve.

Each file is encoded with:

    ffmpeg -i input -c:v libx265 -pix_fmt yuv420p10le -crf CRF -preset PRESET \
           -tag:v hvc1 -c:a copy output.mp4

- CRF (quality-based, not a target bitrate) keeps detail where it matters and
  compresses hard where it doesn't, which suits archival better than a fixed
  bitrate.
- 10-bit 4:2:0 output reduces banding and compresses better with x265 even from
  8-bit sources.
- The `hvc1` tag (rather than the default `hev1`) is what makes QuickTime,
  Final Cut, and Resolve recognise the HEVC stream and read it back correctly;
  without it some of those tools misdetect the codec.
- Audio is stream-copied, not re-encoded, so there's no quality loss or A/V
  drift, and the source's timecode track (if any) is preserved so the clip
  still lines up on Resolve's timeline.

Every output is always an .mp4, mirroring the input's subfolder structure
under the output folder (so no name collision with the source, and hvc1 is
only ever written into a container that supports it). A file is skipped if
its corresponding output already exists.

Each video is encoded in a single ffmpeg pass. An overall progress bar tracks
files completed across the whole batch, with ETA, plus one progress bar per
file currently being encoded, updated continuously from ffmpeg's own progress
stream rather than only jumping when a file finishes.

If the run looks likely to push disk usage past 90%, you'll be warned and
asked to confirm.

Usage: python3 compress_videos.py <input_folder> <output_folder> [--crf CRF] [--preset PRESET]

Requires ffmpeg on PATH.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

VIDEO_EXTS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.mts', '.m2ts', '.wmv', '.flv', '.webm'}

WORKERS = max(1, (os.cpu_count() or 2) - 1)  # max files encoded concurrently; leave one core free
DISK_WARN_PCT = 90

DEFAULT_CRF = 20
DEFAULT_PRESET = 'slow'

# Run ffmpeg at the lowest scheduling/I/O priority so it only uses spare capacity
# and gets out of the way of foreground work. On macOS, `taskpolicy -b -d throttle`
# lowers CPU scheduling priority (PRIO_DARWIN_BG) and this process's own disk I/O
# priority.
if platform.system() == 'Darwin' and shutil.which('taskpolicy'):
    BACKGROUND_PREFIX = ['taskpolicy', '-b', '-d', 'throttle']
elif shutil.which('nice'):
    BACKGROUND_PREFIX = ['nice', '-n', '19']
else:
    BACKGROUND_PREFIX = []


@dataclass
class FileJob:
    index: int
    path: Path
    final_path: Path
    duration: float
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


def get_timecode(path: Path) -> str | None:
    return _probe(path, 'stream_tags=timecode', select_streams='d') or None


def is_valid_video(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0 and get_duration(path) is not None


def discover_videos(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.rglob('*')
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
        and not p.name.startswith('.')  # skip our own leftover .*.compressing.tmp* files
    )


def cleanup_stale_temp_files(folder: Path) -> None:
    """Remove .*.compressing.tmp* files left behind by a previous run that got interrupted."""
    for p in folder.rglob('.*.compressing.tmp*'):
        if p.is_file():
            print(f"  Removing stale temp file from an interrupted run: {p.name}")
            p.unlink(missing_ok=True)


def final_path_for(video: Path, input_folder: Path) -> Path:
    rel = video.relative_to(input_folder).with_suffix('.mp4')
    return rel


def build_jobs(files: list[Path], input_folder: Path, output_folder: Path) -> list[FileJob]:
    jobs = []
    for i, video in enumerate(files):
        final_path = output_folder / final_path_for(video, input_folder)
        if final_path.exists():
            print(f"  SKIP (already compressed): {video.name}")
            continue

        duration = get_duration(video)
        if duration is None:
            print(f"  SKIP (unreadable): {video.name}")
            continue

        jobs.append(FileJob(
            index=i,
            path=video,
            final_path=final_path,
            duration=duration,
            timecode=get_timecode(video),
        ))
    return jobs


def disk_usage_pct(folder: Path, extra_bytes: int) -> float:
    usage = shutil.disk_usage(folder)
    return (usage.used + extra_bytes) / usage.total * 100


def confirm_disk_space(output_folder: Path, jobs: list[FileJob]) -> None:
    # CRF-based encoding has no predictable target size, so fall back to
    # assuming each output is roughly the size of its source (a conservative
    # over-estimate for archival compression, which should shrink most files).
    peak_extra = sum(j.path.stat().st_size for j in jobs)

    projected = disk_usage_pct(output_folder, peak_extra)
    if projected <= DISK_WARN_PCT:
        return

    print(f"\nWARNING: this run is projected to push disk usage to about {projected:.0f}% "
          f"(threshold {DISK_WARN_PCT}%).")
    answer = input("Continue anyway? [y/N]: ").strip().lower()
    if answer != 'y':
        print("Aborted.")
        sys.exit(1)


def _run_with_progress(cmd: list[str], duration_hint: float, pbars: list[tqdm],
                        lock: threading.Lock) -> tuple[int, str]:
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
    with lock:
        for pbar in pbars:
            pbar.update(1.0 - last_frac)
    return proc.returncode, ''.join(stderr_chunks)


def encode_file(job: FileJob, tmp_dir: Path, crf: int, preset: str,
                 pbars: list[tqdm], lock: threading.Lock) -> Path | None:
    tmp_out = tmp_dir / f"{job.index:04d}.mp4"

    cmd = [*BACKGROUND_PREFIX, 'ffmpeg', '-y', '-nostdin', '-loglevel', 'error',
           '-progress', 'pipe:1', '-nostats', '-i', str(job.path),
           '-c:v', 'libx265', '-pix_fmt', 'yuv420p10le', '-crf', str(crf), '-preset', preset,
           '-tag:v', 'hvc1']
    if job.timecode:
        cmd += ['-timecode', job.timecode]
    cmd += ['-c:a', 'copy', str(tmp_out)]

    returncode, stderr = _run_with_progress(cmd, job.duration, pbars, lock)

    if returncode != 0 or not is_valid_video(tmp_out):
        tqdm.write(f"  ERROR encoding {job.path.name}:\n{stderr.strip()[-500:]}")
        tmp_out.unlink(missing_ok=True)
        return None
    return tmp_out


def finalize(job: FileJob, tmp_out: Path | None) -> bool:
    if tmp_out is None:
        tqdm.write(f"  FAILED: {job.path.name}")
        return False

    job.final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp_out), str(job.final_path))

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


def process_file(job: FileJob, tmp_dir: Path, crf: int, preset: str,
                  overall_pbar: tqdm, file_bars: FileBarPool, lock: threading.Lock) -> bool:
    file_pbar = file_bars.acquire(job)
    tmp_out = encode_file(job, tmp_dir, crf, preset, [overall_pbar, file_pbar], lock)
    return finalize(job, tmp_out)


def run(input_folder: Path, output_folder: Path, crf: int, preset: str) -> None:
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        print("ffmpeg/ffprobe not found on PATH. Install with: brew install ffmpeg")
        sys.exit(1)

    if output_folder.exists():
        cleanup_stale_temp_files(output_folder)

    output_folder.mkdir(parents=True, exist_ok=True)

    files = discover_videos(input_folder)
    print(f"Found {len(files)} video file(s) in {input_folder}\n")
    if not files:
        sys.exit(0)

    jobs = build_jobs(files, input_folder, output_folder)
    if not jobs:
        print("\nNothing to do.")
        sys.exit(0)

    # Smallest files first, so quick wins land early instead of queuing behind
    # whatever huge file happened to sort alphabetically first.
    jobs.sort(key=lambda j: j.path.stat().st_size)

    confirm_disk_space(output_folder, jobs)

    print(f"Encoder: libx265 (crf {crf}, preset {preset})")
    print(f"{len(jobs)} file(s) to compress\n")

    succeeded = failed = 0
    lock = threading.Lock()
    with tempfile.TemporaryDirectory(prefix='.compress_videos_', dir=output_folder) as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        bar_format = "{l_bar}{bar}| {n:.1f}/{total} [{elapsed}<{remaining}, {rate_fmt}{postfix}]"
        with tqdm(total=len(jobs), desc="Total", unit="file", position=0, bar_format=bar_format) as pbar:
            n_slots = min(WORKERS, len(jobs))
            file_bars = FileBarPool(n_slots, base_position=1)
            try:
                with ThreadPoolExecutor(max_workers=n_slots) as pool:
                    futures = [pool.submit(process_file, job, tmp_dir, crf, preset, pbar, file_bars, lock)
                               for job in jobs]
                    for future in as_completed(futures):
                        if future.result():
                            succeeded += 1
                        else:
                            failed += 1
            finally:
                file_bars.close()

    print(f"\nDone: {succeeded} compressed, {failed} failed.")
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input', type=Path, help='Folder to recursively scan for video files')
    parser.add_argument('output', type=Path,
                        help='Folder to write compressed videos into, mirroring the input\'s '
                             'subfolder structure (always as .mp4). Created if it doesn\'t exist.')
    parser.add_argument('--crf', type=int, default=DEFAULT_CRF,
                        help=f'x265 constant-rate-factor quality level, lower is higher quality '
                             f'and larger files (default: {DEFAULT_CRF})')
    parser.add_argument('--preset', default=DEFAULT_PRESET,
                        help=f'x265 encoding preset, trading encode time for compression '
                             f'efficiency (default: {DEFAULT_PRESET})')
    args = parser.parse_args()

    input_folder = args.input.expanduser().resolve()
    if not input_folder.exists():
        print(f"Folder does not exist: {input_folder}")
        sys.exit(1)

    output_folder = args.output.expanduser().resolve()

    run(input_folder, output_folder, args.crf, args.preset)


if __name__ == '__main__':
    main()
