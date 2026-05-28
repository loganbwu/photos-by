#!/usr/bin/env python3
"""Move exported Lightroom photos into subfolders by tag.

Tags matching ^\d{2}_ are treated as folder names. Photos with exactly one
such tag are moved; photos with zero or more than one are skipped.

Usage: python3 sort_by_tag.py <folder>
"""

import re
import sys
from pathlib import Path

from PIL import Image
from PIL import IptcImagePlugin

TAG_PATTERN = re.compile(r'^\d{2}_')
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


def main():
    if len(sys.argv) < 2:
        print("Usage: sort_by_tag.py <folder>")
        sys.exit(1)

    folder = Path(sys.argv[1]).expanduser().resolve()
    if not folder.exists():
        print(f"Folder does not exist: {folder}")
        sys.exit(1)

    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    print(f"Found {len(files)} image(s) in {folder}\n")

    moved = skipped_none = skipped_multi = 0

    for photo in files:
        keywords = get_tagged_keywords(photo)
        matching = [k for k in keywords if TAG_PATTERN.match(k)]

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
