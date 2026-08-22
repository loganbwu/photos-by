#!/usr/bin/env python3
"""Denoise a video, or every video in a folder (recursively), using HandBrakeCLI
with the hqdn3d filter and an x265_10bit encode — the settings from a manual
HandBrake CLI run that worked much better than an earlier ffmpeg-based version
of this script.

By default (no output argument), a folder input is denoised into a new
sibling folder named <input>_denoised, mirroring the input's subfolder
structure; a single file is denoised alongside itself as <name>_denoised<ext>.
Pass an output folder/file as a second argument to write there instead. A
file is skipped if its corresponding output already exists. With --overwrite
(mutually exclusive with an output argument), each source file is replaced
in place instead: encoded to a temp file next to it first, then swapped in
once the encode succeeds.

Files are processed one at a time, in chronological order of file creation
date — no progress bar of our own; HandBrakeCLI already prints live
"Encoding: ..." and "Muxing: ..." lines.

Usage: python3 denoise_videos.py <folder-or-file> [output_folder-or-file] [--quality Q] [--overwrite] [--force]

When scanning a folder, files that already carry a container-level "encoder"
tag are skipped as already processed — Canon cameras (both the R line and the
Cinema line) leave this tag unset on their originals, while ffmpeg, HandBrake,
and DaVinci Resolve all stamp one in when they write a file. This mainly
matters for --overwrite, where a processed file keeps its original name and
so can't be recognised by the "output already exists" check. Pass --force to
denoise everything regardless, bypassing both this check and the "output
already exists" check.

GoPro footage is skipped outright (identified by filename, e.g. GX010001.MP4,
GH010001.MP4, GOPR0001.MP4, GP010001.MP4) — its sensor noise profile doesn't
respond well to hqdn3d, so it's left for compress_videos.py to handle instead.

Requires HandBrakeCLI and ffprobe (part of ffmpeg) on PATH
(brew install handbrake ffmpeg).
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from video_common import VIDEO_EXTS, already_processed, require_tools, swap_in

_GOPRO_PATTERNS = [
    re.compile(r'^G[HXS]\d{2}\d{4}\.mp4$', re.IGNORECASE),
    re.compile(r'^GOPR\d{4}\.mp4$', re.IGNORECASE),
    re.compile(r'^GP\d{2}\d{4}\.mp4$', re.IGNORECASE),
]


def is_gopro(path: Path) -> bool:
    return any(p.match(path.name) for p in _GOPRO_PATTERNS)


# Containers HandBrake can write directly; anything else (.avi, .mts, ...) gets
# remuxed to .mp4 — HandBrake silently falls back to MP4 for an unrecognized
# output extension anyway, so pick it explicitly rather than leave a mislabeled
# file behind.
FORMAT_BY_EXT = {'.mp4': 'av_mp4', '.m4v': 'av_mp4', '.mov': 'av_mov',
                  '.mkv': 'av_mkv', '.webm': 'av_webm'}

HQDN3D = 'y-spatial=4:cb-spatial=3:cr-spatial=3:y-temporal=6:cb-temporal=4.5:cr-temporal=4.5'
QUALITY_DEFAULT = 16.0


def creation_time(path: Path) -> float:
    stat = path.stat()
    return getattr(stat, 'st_birthtime', stat.st_ctime)


def discover_videos(folder: Path) -> list[Path]:
    files = [
        p for p in folder.rglob('*')
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS and not p.stem.endswith('_denoised')
    ]
    return sorted(files, key=creation_time)


def output_ext(source_ext: str) -> str:
    return source_ext if source_ext.lower() in FORMAT_BY_EXT else '.mp4'


def default_output_for(input_path: Path) -> Path:
    if input_path.is_dir():
        return input_path.parent / f"{input_path.name}_denoised"
    ext = output_ext(input_path.suffix)
    return input_path.parent / f"{input_path.stem}_denoised{ext}"


def final_path_for(video: Path, input_folder: Path, output_folder: Path, overwrite: bool) -> Path:
    ext = output_ext(video.suffix)
    if overwrite:
        return video if video.suffix.lower() in FORMAT_BY_EXT else video.with_suffix(ext)
    return output_folder / video.relative_to(input_folder).with_suffix(ext)


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
        swap_in(working_path, final_path, source)

    size_mb = final_path.stat().st_size / 1_048_576
    print(f"  Saved: {final_path.name}  ({size_mb:.0f} MB)")
    return True


def run(input_path: Path, output: Path | None, quality: float, overwrite: bool, force: bool) -> None:
    require_tools()

    # Only skip already-processed files when scanning a folder — a single
    # file passed explicitly is denoised regardless of its encoder tag.
    if input_path.is_file():
        final_path = final_path_for(input_path, input_path.parent, output, overwrite)
        if not overwrite:
            final_path.parent.mkdir(parents=True, exist_ok=True)
        jobs = [(input_path, final_path, False)]
    else:
        if not overwrite:
            output.mkdir(parents=True, exist_ok=True)
        files = discover_videos(input_path)
        print(f"Found {len(files)} video file(s) in {input_path}\n")
        jobs = [(f, final_path_for(f, input_path, output, overwrite), True) for f in files]

    succeeded = failed = skipped = 0
    for source, final_path, check_processed in jobs:
        if not force and is_gopro(source):
            print(f"SKIP (GoPro footage, not denoised): {source.name}")
            skipped += 1
            continue
        if not force and not overwrite and final_path.exists():
            print(f"SKIP (already denoised): {source.name}")
            skipped += 1
            continue
        if not force and check_processed and already_processed(source):
            print(f"SKIP (already processed — has encoder tag): {source.name}")
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
                             'mirroring the input\'s subfolder structure; created if it doesn\'t '
                             'exist. Default: <input>_denoised alongside the input folder. If '
                             'input is a single file: the exact output file path to write to. '
                             'Default: <name>_denoised<ext> alongside the source file.')
    parser.add_argument('--quality', type=float, default=QUALITY_DEFAULT,
                        help=f'HandBrake constant-quality value for -q; lower is higher quality '
                             f'(default: {QUALITY_DEFAULT})')
    parser.add_argument('--overwrite', action='store_true',
                        help='Replace each source file in place instead of writing a '
                             '_denoised copy alongside it. Cannot be combined with an output folder/file.')
    parser.add_argument('--force', action='store_true',
                        help='Denoise every matching file even if it looks already done — '
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

    run(input_path, output, args.quality, args.overwrite, args.force)


if __name__ == '__main__':
    main()
