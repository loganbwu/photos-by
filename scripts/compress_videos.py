#!/usr/bin/env python3
"""Compress every video in a folder (recursively) with HandBrakeCLI's x265_10bit
encoder for long-term archival, while keeping the output editable in DaVinci
Resolve — the same HandBrakeCLI settings denoise_videos.py uses, minus the
hqdn3d denoise filter.

Each file is encoded with:

    HandBrakeCLI -i input -o output -f av_mp4 -e x265_10bit \
                 --encoder-preset PRESET --encoder-profile <matches source> \
                 -q CRF --color-range full -E copy --crop-mode none

- -q (quality-based, not a target bitrate) keeps detail where it matters and
  compresses hard where it doesn't, which suits archival better than a fixed
  bitrate.
- Chroma subsampling always matches the source (4:2:0 stays 4:2:0, 4:2:2 stays
  4:2:2, etc.) — never silently downgraded. If a source's chroma can't be
  determined, it's upgraded to 4:2:2 rather than assumed to be the lower-quality
  4:2:0. Bit depth is always upgraded to 10-bit, even from 8-bit sources, since
  that reduces banding and compresses better with x265.
- Audio is passed through with -E copy, so there's no quality loss or A/V drift.

Every output is always an .mp4, mirroring the input's subfolder structure
under the output folder. A file is skipped if its corresponding output already
exists.

Files are processed one at a time, in the order they're discovered — no
progress bar of our own; HandBrakeCLI already prints live "Encoding: ..." and
"Muxing: ..." lines. Running multiple HandBrakeCLI jobs at once was tried and
dropped: a single --encoder-preset slow x265 job already saturates every core,
so concurrency only added contention, not throughput.

If the run looks likely to push disk usage past 90%, you'll be warned and
asked to confirm.

Usage: python3 compress_videos.py <input_folder> <output_folder> [--crf CRF] [--preset PRESET]

Requires HandBrakeCLI and ffprobe (part of ffmpeg) on PATH
(brew install handbrake ffmpeg).
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.mts', '.m2ts', '.wmv', '.flv', '.webm'}

DISK_WARN_PCT = 90
DEFAULT_CRF = 20
DEFAULT_PRESET = 'slow'


def get_pix_fmt(path: Path) -> str | None:
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
         '-show_entries', 'stream=pix_fmt', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        capture_output=True, text=True)
    return result.stdout.strip() or None


def profile_for(pix_fmt: str | None) -> str:
    """Return the HandBrake --encoder-profile value that preserves the source's
    chroma subsampling while always upgrading to 10-bit. If the source's chroma
    can't be determined, upgrade to 4:2:2 rather than risk silently downgrading
    a source that might be 4:2:2 or better — better to use more space than to
    lose chroma resolution the source actually had.
    """
    if pix_fmt and '444' in pix_fmt:
        return 'main444-10'
    if pix_fmt and '422' in pix_fmt:
        return 'main422-10'
    if pix_fmt and '420' in pix_fmt:
        return 'main10'
    return 'main422-10'


def discover_videos(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.rglob('*')
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )


def final_path_for(video: Path, input_folder: Path, output_folder: Path) -> Path:
    return output_folder / video.relative_to(input_folder).with_suffix('.mp4')


def disk_usage_pct(folder: Path, extra_bytes: int) -> float:
    usage = shutil.disk_usage(folder)
    return (usage.used + extra_bytes) / usage.total * 100


def confirm_disk_space(output_folder: Path, jobs: list[tuple[Path, Path]]) -> None:
    # CRF-based encoding has no predictable target size, so fall back to
    # assuming each output is roughly the size of its source (a conservative
    # over-estimate for archival compression, which should shrink most files).
    peak_extra = sum(source.stat().st_size for source, _ in jobs)

    projected = disk_usage_pct(output_folder, peak_extra)
    if projected <= DISK_WARN_PCT:
        return

    print(f"\nWARNING: this run is projected to push disk usage to about {projected:.0f}% "
          f"(threshold {DISK_WARN_PCT}%).")
    answer = input("Continue anyway? [y/N]: ").strip().lower()
    if answer != 'y':
        print("Aborted.")
        sys.exit(1)


def compress(source: Path, dest: Path, crf: int, preset: str) -> bool:
    cmd = ['HandBrakeCLI', '-i', str(source), '-o', str(dest),
           '-f', 'av_mp4', '-e', 'x265_10bit',
           '--encoder-preset', preset, '--encoder-profile', profile_for(get_pix_fmt(source)),
           '-q', str(crf), '--color-range', 'full', '-E', 'copy', '--crop-mode', 'none']
    result = subprocess.run(cmd)
    return result.returncode == 0 and dest.exists() and dest.stat().st_size > 0


def run(input_folder: Path, output_folder: Path, crf: int, preset: str) -> None:
    if not shutil.which('HandBrakeCLI'):
        print("HandBrakeCLI not found on PATH. Install with: brew install handbrake")
        sys.exit(1)
    if not shutil.which('ffprobe'):
        print("ffprobe not found on PATH. Install with: brew install ffmpeg")
        sys.exit(1)

    output_folder.mkdir(parents=True, exist_ok=True)

    files = discover_videos(input_folder)
    print(f"Found {len(files)} video file(s) in {input_folder}\n")
    if not files:
        sys.exit(0)

    jobs = []
    for video in files:
        final_path = final_path_for(video, input_folder, output_folder)
        if final_path.exists():
            print(f"SKIP (already compressed): {video.name}")
            continue
        jobs.append((video, final_path))

    if not jobs:
        print("\nNothing to do.")
        sys.exit(0)

    confirm_disk_space(output_folder, jobs)

    succeeded = failed = 0
    for source, final_path in jobs:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"=== {source.name} ===")
        if compress(source, final_path, crf, preset):
            size_mb = final_path.stat().st_size / 1_048_576
            print(f"  Saved: {final_path.name}  ({size_mb:.0f} MB)")
            succeeded += 1
        else:
            print(f"  FAILED: {source.name}")
            final_path.unlink(missing_ok=True)
            failed += 1

    print(f"\nDone: {succeeded} compressed, {failed} failed.")
    if failed:
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input', type=Path, help='Folder to recursively scan for video files')
    parser.add_argument('output', type=Path,
                        help='Folder to write compressed videos into, mirroring the input\'s '
                             'subfolder structure (always as .mp4). Created if it doesn\'t exist.')
    parser.add_argument('--crf', type=int, default=DEFAULT_CRF,
                        help=f'HandBrake constant-quality value for -q; lower is higher quality '
                             f'(default: {DEFAULT_CRF})')
    parser.add_argument('--preset', default=DEFAULT_PRESET,
                        help=f'HandBrake encoder preset, trading encode time for compression '
                             f'efficiency (default: {DEFAULT_PRESET})')
    return parser


def main() -> None:
    args = build_parser().parse_args()

    input_folder = args.input.expanduser().resolve()
    if not input_folder.exists():
        print(f"Folder does not exist: {input_folder}")
        sys.exit(1)

    output_folder = args.output.expanduser().resolve()

    run(input_folder, output_folder, args.crf, args.preset)


if __name__ == '__main__':
    main()
