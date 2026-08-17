#!/usr/bin/env python3
"""Compress a video, or every video in a folder (recursively), with HandBrakeCLI's
x265_10bit encoder for long-term archival, while keeping the output editable in
DaVinci Resolve — the same HandBrakeCLI settings denoise_videos.py uses, minus
the hqdn3d denoise filter.

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

Every output is always an .mp4. By default (no output argument), a folder
input is compressed into a new sibling folder named <input>_compressed,
mirroring the input's subfolder structure; a single file is compressed
alongside itself as <name>_compress.mp4. Pass an output folder/file as a
second argument to write there instead. A file is skipped if its
corresponding output already exists. With --overwrite (mutually exclusive
with an output argument), each source file is replaced in place instead:
encoded to a temp file next to it first, then swapped in once the encode
succeeds.

Files are processed one at a time, in the order they're discovered — no
progress bar of our own; HandBrakeCLI already prints live "Encoding: ..." and
"Muxing: ..." lines. Running multiple HandBrakeCLI jobs at once was tried and
dropped: a single --encoder-preset slow x265 job already saturates every core,
so concurrency only added contention, not throughput.

When scanning a folder, files that already carry a container-level "encoder"
tag are skipped as already processed — Canon cameras (both the R line and the
Cinema line) leave this tag unset on their originals, while ffmpeg, HandBrake,
and DaVinci Resolve all stamp one in when they write a file. This mainly
matters for --overwrite, where a processed file keeps its original name and so
can't be recognised by the "output already exists" check. Pass --force to
compress everything regardless, bypassing both this check and the "output
already exists" check.

If the run looks likely to push disk usage past 90%, you'll be warned and
asked to confirm.

Usage: python3 compress_videos.py <folder-or-file> [output_folder-or-file] [--crf CRF] [--preset PRESET] [--overwrite] [--force]

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


def already_processed(path: Path) -> bool:
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format_tags=encoder',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        capture_output=True, text=True)
    return bool(result.stdout.strip())


def default_output_for(input_path: Path) -> Path:
    if input_path.is_dir():
        return input_path.parent / f"{input_path.name}_compressed"
    return input_path.with_name(f"{input_path.stem}_compress.mp4")


def final_path_for(video: Path, input_folder: Path, output_folder: Path, overwrite: bool) -> Path:
    if overwrite:
        return video.with_suffix('.mp4')
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


def process(source: Path, final_path: Path, crf: int, preset: str, overwrite: bool) -> bool:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    working_path = source.with_name(f".{source.stem}.compressing.tmp{final_path.suffix}") \
        if overwrite else final_path

    print(f"=== {source.name} ===")
    ok = compress(source, working_path, crf, preset)
    if not ok:
        print(f"  FAILED: {source.name}")
        working_path.unlink(missing_ok=True)
        return False

    if overwrite:
        working_path.replace(final_path)
        if final_path != source:
            source.unlink(missing_ok=True)

    size_mb = final_path.stat().st_size / 1_048_576
    print(f"  Saved: {final_path.name}  ({size_mb:.0f} MB)")
    return True


def run(input_path: Path, output: Path | None, crf: int, preset: str,
        overwrite: bool, force: bool) -> None:
    if not shutil.which('HandBrakeCLI'):
        print("HandBrakeCLI not found on PATH. Install with: brew install handbrake")
        sys.exit(1)
    if not shutil.which('ffprobe'):
        print("ffprobe not found on PATH. Install with: brew install ffmpeg")
        sys.exit(1)

    # Only skip already-processed files when scanning a folder — a single
    # file passed explicitly is compressed regardless of its encoder tag.
    if input_path.is_file():
        final_path = input_path.with_suffix('.mp4') if overwrite else output
        if not overwrite:
            final_path.parent.mkdir(parents=True, exist_ok=True)
        jobs_all = [(input_path, final_path, False)]
    else:
        if not overwrite:
            output.mkdir(parents=True, exist_ok=True)
        files = discover_videos(input_path)
        print(f"Found {len(files)} video file(s) in {input_path}\n")
        jobs_all = [(f, final_path_for(f, input_path, output, overwrite), True) for f in files]

    jobs = []
    skipped = 0
    for video, final_path, check_processed in jobs_all:
        if not force and not overwrite and final_path.exists():
            print(f"SKIP (already compressed): {video.name}")
            skipped += 1
            continue
        if not force and check_processed and already_processed(video):
            print(f"SKIP (already processed — has encoder tag): {video.name}")
            skipped += 1
            continue
        jobs.append((video, final_path))

    if not jobs:
        print("\nNothing to do.")
        sys.exit(0)

    if overwrite:
        check_dir = input_path if input_path.is_dir() else input_path.parent
    else:
        check_dir = output if input_path.is_dir() else output.parent
    confirm_disk_space(check_dir, jobs)

    succeeded = failed = 0
    for source, final_path in jobs:
        if process(source, final_path, crf, preset, overwrite):
            succeeded += 1
        else:
            failed += 1

    print(f"\nDone: {succeeded} compressed, {failed} failed, {skipped} skipped.")
    if failed:
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input', type=Path,
                        help='A single video file, or a folder to recursively scan for video files')
    parser.add_argument('output', type=Path, nargs='?', default=None,
                        help='If input is a folder: folder to write compressed videos into, '
                             'mirroring the input\'s subfolder structure (always as .mp4); created '
                             'if it doesn\'t exist. Default: <input>_compressed alongside the input '
                             'folder. If input is a single file: the exact output file path to '
                             'write to. Default: <name>_compress.mp4 alongside the source file.')
    parser.add_argument('--crf', type=int, default=DEFAULT_CRF,
                        help=f'HandBrake constant-quality value for -q; lower is higher quality '
                             f'(default: {DEFAULT_CRF})')
    parser.add_argument('--preset', default=DEFAULT_PRESET,
                        help=f'HandBrake encoder preset, trading encode time for compression '
                             f'efficiency (default: {DEFAULT_PRESET})')
    parser.add_argument('--overwrite', action='store_true',
                        help='Replace each source file in place instead of writing a compressed '
                             'copy elsewhere. Cannot be combined with an output folder/file.')
    parser.add_argument('--force', action='store_true',
                        help='Compress every matching file even if it looks already done — '
                             'skips both the "output already exists" check and the '
                             '"already has an encoder tag" check.')
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.output is not None and args.overwrite:
        parser.error("argument output: not allowed with argument --overwrite")

    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        print(f"Path does not exist: {input_path}")
        sys.exit(1)

    if args.overwrite:
        output = None
    elif args.output is not None:
        output = args.output.expanduser().resolve()
        if input_path.is_file() and output.is_dir():
            parser.error(f"argument output: {output} is a directory, but input is a single file — "
                          "pass the exact output file path instead")
    else:
        output = default_output_for(input_path)

    run(input_path, output, args.crf, args.preset, args.overwrite, args.force)


if __name__ == '__main__':
    main()
