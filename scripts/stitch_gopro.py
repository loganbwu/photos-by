#!/usr/bin/env python3
"""Stitch GoPro chapter files into continuous videos.

GoPro cameras split long recordings into ~4 GB chapter files. This script
detects groups of consecutive chapters and concatenates each group into a
single output file using ffmpeg's concat demuxer (stream copy, no re-encoding).

Supports both naming conventions:
  Older (HERO5 and earlier): GOPR0001.MP4, GP010001.MP4, GP020001.MP4, ...
  Newer (HERO6+):            GH010001.MP4, GH020001.MP4, ... (H.264)
                             GX010001.MP4, GX020001.MP4, ... (H.265)

Usage: python3 stitch_gopro.py <folder> [output_folder]

Requires ffmpeg on PATH (brew install ffmpeg).
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_NEW_PATTERN = re.compile(r'^(G[HXS])(\d{2})(\d{4})\.(mp4)$', re.IGNORECASE)
_OLD_FIRST   = re.compile(r'^(GOPR)(\d{4})\.(mp4)$', re.IGNORECASE)
_OLD_CONT    = re.compile(r'^(GP)(\d{2})(\d{4})\.(mp4)$', re.IGNORECASE)


def classify(path: Path) -> tuple[str, int] | None:
    """Return (clip_id, chapter_num) for a GoPro chapter file, or None."""
    name = path.name

    m = _NEW_PATTERN.match(name)
    if m:
        prefix, chapter, clip = m.group(1).upper(), int(m.group(2)), m.group(3)
        return (f"{prefix}_{clip}", chapter)

    m = _OLD_FIRST.match(name)
    if m:
        clip = m.group(2)
        return (f"OLD_{clip}", 0)

    m = _OLD_CONT.match(name)
    if m:
        chapter, clip = int(m.group(2)), m.group(3)
        return (f"OLD_{clip}", chapter)

    return None


def find_groups(folder: Path) -> dict[str, list[Path]]:
    """Return groups of chapter files keyed by clip ID, sorted by chapter."""
    raw: dict[str, list[tuple[int, Path]]] = {}
    for path in folder.iterdir():
        if not path.is_file():
            continue
        result = classify(path)
        if result is None:
            continue
        clip_id, chapter = result
        raw.setdefault(clip_id, []).append((chapter, path))

    return {
        clip_id: [p for _, p in sorted(chapters)]
        for clip_id, chapters in sorted(raw.items())
        if len(chapters) > 1
    }


def stitch(files: list[Path], output: Path) -> bool:
    concat_file = Path(tempfile.mktemp(suffix='.txt'))
    try:
        with concat_file.open('w') as f:
            f.write("ffconcat version 1.0\n")
            for p in files:
                f.write(f"file '{p.resolve()}'\n")

        cmd = [
            'ffmpeg', '-y',
            '-hide_banner', '-loglevel', 'error', '-stats',
            '-f', 'concat', '-safe', '0', '-i', str(concat_file),
            '-c', 'copy',
            str(output),
        ]
        result = subprocess.run(cmd)
    finally:
        concat_file.unlink(missing_ok=True)

    return result.returncode == 0


def output_name(files: list[Path]) -> str:
    first = files[0]
    m = _NEW_PATTERN.match(first.name)
    if m:
        return f"{m.group(1).upper()}{m.group(3)}{first.suffix.upper()}"
    return first.stem + '_stitched' + first.suffix.upper()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder', type=Path, help='Folder containing GoPro files')
    parser.add_argument('output_folder', type=Path, nargs='?', default=None,
                        help='Destination folder (default: <folder>/stitched)')
    args = parser.parse_args()

    folder = args.folder.expanduser().resolve()
    if not folder.exists():
        print(f"Folder does not exist: {folder}")
        sys.exit(1)

    if not shutil.which('ffmpeg'):
        print("ffmpeg not found on PATH. Install it with: brew install ffmpeg")
        sys.exit(1)

    groups = find_groups(folder)

    if not groups:
        print("No multi-chapter GoPro recordings found.")
        sys.exit(0)

    print(f"Found {len(groups)} multi-chapter recording(s):\n")
    for clip_id, files in groups.items():
        print(f"  {clip_id}  ({len(files)} chapters)")
        for f in files:
            size_mb = f.stat().st_size / 1_048_576
            print(f"    {f.name}  ({size_mb:.0f} MB)")
    print()

    out_dir = (args.output_folder or folder / 'stitched').expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    failed = []
    for clip_id, files in groups.items():
        name = output_name(files)
        output = out_dir / name
        print(f"Stitching {clip_id} -> {name}")
        if stitch(files, output):
            size_mb = output.stat().st_size / 1_048_576
            print(f"  Saved: {output}  ({size_mb:.0f} MB)\n")
        else:
            print(f"  ERROR: ffmpeg failed for {name}\n")
            failed.append(clip_id)

    if failed:
        print(f"Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
