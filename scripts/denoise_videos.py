#!/usr/bin/env python3
"""Denoise every video in a folder (recursively) using ffmpeg's vaguedenoiser filter.

Each video is left untouched — output is written alongside it as
<name>_denoised<ext> (skipped if that file already exists). Long videos are
split into chunks and encoded in parallel for speed, then reassembled; a
single progress bar tracks chunks completed across the whole batch, with ETA.

Usage: python3 denoise_videos.py <folder> [--mbps MBPS]

Requires ffmpeg on PATH. Uses hevc_videotoolbox hardware encoding when
available (Apple Silicon), falling back to libx265.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from tqdm import tqdm

VIDEO_EXTS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.mts', '.m2ts', '.wmv', '.flv', '.webm'}
CONTAINER_PASSTHROUGH_EXTS = {'.mp4', '.mov', '.m4v', '.mts', '.m2ts'}  # can hold HEVC as-is

SEG_LEN = 300  # seconds per chunk for large files
WORKERS = max(1, (os.cpu_count() or 2) - 1)  # leave one core free for the rest of the machine

# vaguedenoiser: wavelet-based denoiser. These are "moderate" settings — enough
# to clean sensor noise without visibly softening detail.
DENOISE_FILTER = 'vaguedenoiser=threshold=2:method=soft:nsteps=6:percent=85'


@dataclass
class FileJob:
    index: int
    path: Path
    output: Path
    duration: float
    bit_rate: int | None
    pix_fmt: str | None
    timecode: str | None
    num_segments: int
    segments_done: dict[int, Path | None] = field(default_factory=dict)


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
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and not p.stem.endswith('_denoised')
    )


def output_path_for(video: Path) -> Path:
    ext = video.suffix if video.suffix.lower() in CONTAINER_PASSTHROUGH_EXTS else '.mp4'
    return video.parent / f"{video.stem}_denoised{ext}"


def build_jobs(files: list[Path]) -> list[FileJob]:
    jobs = []
    for i, video in enumerate(files):
        output = output_path_for(video)
        if output.exists():
            print(f"  SKIP (already denoised): {video.name}")
            continue

        duration = get_duration(video)
        if duration is None:
            print(f"  SKIP (unreadable): {video.name}")
            continue

        num_segments = 1 if duration <= SEG_LEN * 2 else -(-int(duration) // SEG_LEN)
        jobs.append(FileJob(
            index=i,
            path=video,
            output=output,
            duration=duration,
            bit_rate=get_bit_rate(video),
            pix_fmt=get_pix_fmt(video),
            timecode=get_timecode(video),
            num_segments=num_segments,
        ))
    return jobs


def encode_segment(job: FileJob, seg_idx: int, tmp_dir: Path, encoder: list[str],
                    hardware: bool, mbps: float | None) -> tuple[FileJob, int, Path | None]:
    fmt, profile = pixel_args(job.pix_fmt, hardware)
    vf = f"{DENOISE_FILTER},{fmt}" if fmt else DENOISE_FILTER

    whole = job.num_segments == 1
    tmp_out = tmp_dir / f"{job.index:04d}_{seg_idx:04d}.mp4"

    cmd = ['ffmpeg', '-y', '-nostdin', '-loglevel', 'error']
    if not whole:
        cmd += ['-ss', str(seg_idx * SEG_LEN)]
    cmd += ['-i', str(job.path)]
    if not whole:
        remaining = job.duration - seg_idx * SEG_LEN
        cmd += ['-t', str(min(SEG_LEN, remaining) + (2 if remaining < SEG_LEN else 0))]
    cmd += ['-vf', vf, *encoder, *profile, *bitrate_args(mbps, job.bit_rate)]
    if whole and job.timecode:
        cmd += ['-timecode', job.timecode]
    cmd += ['-c:a', 'copy', str(tmp_out)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not is_valid_video(tmp_out):
        tqdm.write(f"  ERROR encoding {job.path.name} (segment {seg_idx}):\n{result.stderr.strip()[-500:]}")
        tmp_out.unlink(missing_ok=True)
        return job, seg_idx, None
    return job, seg_idx, tmp_out


def finalize(job: FileJob) -> bool:
    segments = [job.segments_done[i] for i in range(job.num_segments)]
    if any(s is None for s in segments):
        tqdm.write(f"  FAILED: {job.path.name} (one or more segments failed to encode)")
        for s in segments:
            if s is not None:
                s.unlink(missing_ok=True)
        return False

    if job.num_segments == 1:
        shutil.move(str(segments[0]), str(job.output))
    else:
        list_file = Path(tempfile.mktemp(suffix='.txt'))
        try:
            with list_file.open('w') as f:
                for seg in segments:
                    f.write(f"file '{seg.resolve()}'\n")
            cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
                   '-i', str(list_file)]
            if job.timecode:
                cmd += ['-timecode', job.timecode]
            cmd += ['-c', 'copy', str(job.output)]
            result = subprocess.run(cmd, capture_output=True, text=True)
        finally:
            list_file.unlink(missing_ok=True)
            for seg in segments:
                seg.unlink(missing_ok=True)

        if result.returncode != 0 or not is_valid_video(job.output):
            tqdm.write(f"  FAILED: {job.path.name} (concat failed)\n{result.stderr.strip()[-500:]}")
            job.output.unlink(missing_ok=True)
            return False

    size_mb = job.output.stat().st_size / 1_048_576
    tqdm.write(f"  Saved: {job.output.name}  ({size_mb:.0f} MB)")
    return True


def run(folder: Path, mbps: float | None) -> None:
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        print("ffmpeg/ffprobe not found on PATH. Install with: brew install ffmpeg")
        sys.exit(1)

    files = discover_videos(folder)
    print(f"Found {len(files)} video file(s) in {folder}\n")
    if not files:
        sys.exit(0)

    jobs = build_jobs(files)
    if not jobs:
        print("\nNothing to do.")
        sys.exit(0)

    encoder = pick_encoder()
    hardware = encoder[1] == 'hevc_videotoolbox'
    total_segments = sum(j.num_segments for j in jobs)
    print(f"{len(jobs)} file(s) to denoise, {total_segments} segment(s) total\n")

    succeeded = failed = 0
    with tempfile.TemporaryDirectory(prefix='denoise_videos_') as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        with tqdm(total=total_segments, desc="Denoising", unit="seg") as pbar, \
             ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [
                pool.submit(encode_segment, job, seg_idx, tmp_dir, encoder, hardware, mbps)
                for job in jobs
                for seg_idx in range(job.num_segments)
            ]
            for future in as_completed(futures):
                job, seg_idx, seg_path = future.result()
                job.segments_done[seg_idx] = seg_path
                pbar.update(1)

                if len(job.segments_done) == job.num_segments:
                    if finalize(job):
                        succeeded += 1
                    else:
                        failed += 1

    print(f"\nDone: {succeeded} denoised, {failed} failed.")
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder', type=Path, help='Folder to recursively scan for video files')
    parser.add_argument('--mbps', type=float, default=None,
                        help='Target video bitrate in Mbps (default: match each source file\'s own bitrate)')
    args = parser.parse_args()

    folder = args.folder.expanduser().resolve()
    if not folder.exists():
        print(f"Folder does not exist: {folder}")
        sys.exit(1)

    run(folder, args.mbps)


if __name__ == '__main__':
    main()
