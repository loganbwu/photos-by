#!/usr/bin/env python3
r"""Move exported Lightroom photos into subfolders by tag.

Tags matching ^\d{2,}_ (two or more digits, e.g. 01_ or 001_) are treated as
folder names. Tags come from IPTC keywords (JPEG/TIFF only) and from the file
name itself: a file whose name, excluding extension, matches the pattern
(e.g. 01_selects.mp4) is tagged with that name. This allows sorting files that
cannot carry keywords, such as videos. Files with exactly one distinct tag are
moved; files with zero or more than one are skipped.

Usage: python3 sort_by_tag.py <folder>
"""

import argparse
import sys
import re
from pathlib import Path

from PIL import Image
from PIL import IptcImagePlugin

TAG_PATTERN = re.compile(r'^\d{2,}_')
IMAGE_EXTS = {'.jpg', '.jpeg', '.tif', '.tiff'}


def get_tagged_keywords(path: Path) -> list[str]:
    try:
        with Image.open(path) as img:
            iptc = IptcImagePlugin.getiptcinfo(img) or {}
        keywords = iptc.get((2, 25), [])
        if isinstance(keywords, bytes):
            keywords = [keywords]
        return [k.decode('utf-8', errors='replace') for k in keywords]
    except Exception as e:
        print(f"  WARN: could not read {path.name} — {e}")
        return []


def get_tags(path: Path) -> list[str]:
    keywords = get_tagged_keywords(path) if path.suffix.lower() in IMAGE_EXTS else []
    tags = {k for k in keywords if TAG_PATTERN.match(k)}
    if TAG_PATTERN.match(path.stem):
        tags.add(path.stem)
    return sorted(tags)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder', type=Path, help='Folder of exported Lightroom photos')
    return parser


def main():
    args = build_parser().parse_args()

    folder = args.folder.expanduser().resolve()
    if not folder.exists():
        print(f"Folder does not exist: {folder}")
        sys.exit(1)

    files = sorted(p for p in folder.iterdir()
                   if p.is_file() and not p.name.startswith('.')
                   and (p.suffix.lower() in IMAGE_EXTS or TAG_PATTERN.match(p.stem)))
    print(f"Found {len(files)} file(s) in {folder}\n")

    moved = skipped_none = skipped_multi = 0

    for photo in files:
        matching = get_tags(photo)

        if len(matching) == 0:
            print(f"  Skip (no tag):      {photo.name}")
            skipped_none += 1
        elif len(matching) > 1:
            print(f"  Skip (multi-tag):   {photo.name}  {matching}")
            skipped_multi += 1
        else:
            tag = matching[0]
            dest_dir = folder / tag
            dest_dir.mkdir(exist_ok=True)
            photo.rename(dest_dir / photo.name)
            print(f"  Moved → {tag}/  {photo.name}")
            moved += 1

    print(f"\nDone: {moved} moved, {skipped_none} skipped (no tag), {skipped_multi} skipped (multiple tags).")


if __name__ == "__main__":
    main()
