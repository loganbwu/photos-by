#!/usr/bin/env python3
"""Denoise a video, or every video in a folder (recursively), using HandBrakeCLI
with the hqdn3d filter and an x265_10bit encode — the settings from a manual
HandBrake CLI run that worked much better than an earlier ffmpeg-based version
of this script.

By default each video is left untouched — output is written alongside it as
<name>_denoised<ext> (skipped if that file already exists). If the input is a
folder, pass an output folder as a second argument to instead write into that
folder under each file's original name (no _denoised suffix), mirroring the
input's subfolder structure. If the input is a single file, pass an output
file path as a second argument to write there instead. With --overwrite
(mutually exclusive with an output folder/file), each source file is replaced
in place instead: encoded to a temp file next to it first, then swapped in
once the encode succeeds.

Files are processed one at a time, in HandBrakeCLI's own default order — no
progress bar of our own; HandBrakeCLI already prints live "Encoding: ..." and
"Muxing: ..." lines.

Usage: python3 denoise_videos.py <folder-or-file> [output_folder-or-file] [--quality Q] [--overwrite]

Requires HandBrakeCLI on PATH (brew install handbrake).
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.mts', '.m2ts', '.wmv', '.flv', '.webm'}

# Containers HandBrake can write directly; anything else (.avi, .mts, ...) gets
# remuxed to .mp4 — HandBrake silently falls back to MP4 for an unrecognized
# output extension anyway, so pick it explicitly rather than leave a mislabeled
# file behind.
FORMAT_BY_EXT = {'.mp4': 'av_mp4', '.m4v': 'av_mp4', '.mov': 'av_mov',
                  '.mkv': 'av_mkv', '.webm': 'av_webm'}

HQDN3D = 'y-spatial=4:cb-spatial=3:cr-spatial=3:y-temporal=6:cb-temporal=4.5:cr-temporal=4.5'
QUALITY_DEFAULT = 16.0


def discover_videos(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.rglob('*')
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and not p.stem.endswith('_denoised')
    )


def output_ext(source_ext: str) -> str:
    return source_ext if source_ext.lower() in FORMAT_BY_EXT else '.mp4'


def final_path_for(video: Path, input_folder: Path, output_folder: Path | None, overwrite: bool) -> Path:
    ext = output_ext(video.suffix)
    if overwrite:
        return video if video.suffix.lower() in FORMAT_BY_EXT else video.with_suffix(ext)
    if output_folder is not None:
        return output_folder / video.relative_to(input_folder).with_suffix(ext)
    return video.parent / f"{video.stem}_denoised{ext}"


def denoise(source: Path, dest: Path, quality: float) -> bool:
    cmd = ['HandBrakeCLI', '-i', str(source), '-o', str(dest),
           '-f', FORMAT_BY_EXT.get(dest.suffix.lower(), 'av_mp4'),
           f'--hqdn3d={HQDN3D}',
           '-e', 'x265_10bit', '--encoder-preset', 'slow', '--encoder-profile', 'main422-10',
           '-q', str(quality), '--color-range', 'full', '-E', 'copy', '--crop-mode', 'none']
    result = subprocess.run(cmd)
    return result.returncode == 0 and dest.exists() and dest.stat().st_size > 0


def process(source: Path, final_path: Path, quality: float, overwrite: bool) -> bool:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    working_path = source.with_name(f".{source.stem}.denoising.tmp{final_path.suffix}") \
        if overwrite else final_path

    print(f"=== {source.name} ===")
    ok = denoise(source, working_path, quality)
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


def run(input_path: Path, output: Path | None, quality: float, overwrite: bool) -> None:
    if not shutil.which('HandBrakeCLI'):
        print("HandBrakeCLI not found on PATH. Install with: brew install handbrake")
        sys.exit(1)

    if input_path.is_file():
        jobs = [(input_path, output if output is not None else
                 final_path_for(input_path, input_path.parent, None, overwrite))]
    else:
        if output is not None and not overwrite:
            output.mkdir(parents=True, exist_ok=True)
        files = discover_videos(input_path)
        print(f"Found {len(files)} video file(s) in {input_path}\n")
        jobs = [(f, final_path_for(f, input_path, output, overwrite)) for f in files]

    succeeded = failed = skipped = 0
    for source, final_path in jobs:
        if not overwrite and final_path.exists():
            print(f"SKIP (already denoised): {source.name}")
            skipped += 1
            continue
        if process(source, final_path, quality, overwrite):
            succeeded += 1
        else:
            failed += 1

    print(f"\nDone: {succeeded} denoised, {failed} failed, {skipped} skipped.")
    if failed:
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input', type=Path,
                        help='A single video file, or a folder to recursively scan for video files')
    parser.add_argument('output', type=Path, nargs='?', default=None,
                        help='If input is a folder: folder to write denoised videos into, '
                             'mirroring the input\'s subfolder structure, under their original '
                             'filenames (no _denoised suffix); created if it doesn\'t exist. '
                             'If input is a single file: the exact output file path to write to. '
                             'Default: write <name>_denoised<ext> alongside each source file instead.')
    parser.add_argument('--quality', type=float, default=QUALITY_DEFAULT,
                        help=f'HandBrake constant-quality value for -q; lower is higher quality '
                             f'(default: {QUALITY_DEFAULT})')
    parser.add_argument('--overwrite', action='store_true',
                        help='Replace each source file in place instead of writing a '
                             '_denoised copy alongside it. Cannot be combined with an output folder/file.')
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

    output = args.output.expanduser().resolve() if args.output is not None else None
    if output is not None and input_path.is_file() and output.is_dir():
        parser.error(f"argument output: {output} is a directory, but input is a single file — "
                      "pass the exact output file path instead")

    run(input_path, output, args.quality, args.overwrite)


if __name__ == '__main__':
    main()
