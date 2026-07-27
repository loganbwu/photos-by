#!/usr/bin/env python3
"""Copy the earliest-captured photo for each IPTC keyword tag into a subfolder.

For every image under <folder> (searched recursively), reads its IPTC
keywords (same convention as sort_by_tag.py) and EXIF capture date. For each
distinct keyword found across all images, writes the earliest-captured image
bearing that keyword into the output folder, named after the keyword (e.g.
keyword "40" -> "40.jpg"). The output folder itself is flat, regardless of
how deep the matching source images were nested. Thumbnails are downsized to
roughly TARGET_MEGAPIXELS and saved as JPEG at JPEG_QUALITY, regardless of
the source format.

Usage: python3 first_by_tag.py <folder> [output_folder]
Default output_folder: <folder>/thumbnails
"""

import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from sort_by_tag import IMAGE_EXTS, get_tagged_keywords
from timelapse import get_capture_time

TARGET_MEGAPIXELS = 300_000
JPEG_QUALITY = 75


def save_thumbnail(src: Path, dest: Path) -> None:
    with Image.open(src) as img:
        img = ImageOps.exif_transpose(img)
        pixels = img.width * img.height
        if pixels > TARGET_MEGAPIXELS:
            scale = (TARGET_MEGAPIXELS / pixels) ** 0.5
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                              Image.LANCZOS)
        img.convert('RGB').save(dest, 'JPEG', quality=JPEG_QUALITY)


def main():
    if len(sys.argv) < 2:
        print("Usage: first_by_tag.py <folder> [output_folder]")
        sys.exit(1)

    folder = Path(sys.argv[1]).expanduser().resolve()
    if not folder.exists():
        print(f"Folder does not exist: {folder}")
        sys.exit(1)

    output_folder = (Path(sys.argv[2]).expanduser().resolve()
                      if len(sys.argv) > 2 else folder / "thumbnails")

    files = sorted(p for p in folder.rglob('*')
                   if p.is_file() and p.suffix.lower() in IMAGE_EXTS
                   and output_folder != p and output_folder not in p.parents)
    print(f"Found {len(files)} image(s) under {folder}\n")

    earliest: dict[str, tuple[datetime, Path]] = {}
    untagged = no_timestamp = 0

    for photo in files:
        keywords = get_tagged_keywords(photo)
        if not keywords:
            untagged += 1
            continue

        capture_time = get_capture_time(photo)
        if capture_time is None:
            print(f"  WARN: no capture date, skipping — {photo.name}")
            no_timestamp += 1
            continue

        for tag in keywords:
            current = earliest.get(tag)
            if current is None or capture_time < current[0]:
                earliest[tag] = (capture_time, photo)

    if not earliest:
        print("No tagged, timestamped images found.")
        sys.exit(1)

    print(f"Found {len(earliest)} distinct tag(s)\n")

    output_folder.mkdir(parents=True, exist_ok=True)
    for tag in sorted(earliest):
        capture_time, photo = earliest[tag]
        dest = output_folder / f"{tag}.jpg"
        save_thumbnail(photo, dest)
        print(f"  {tag:>6}  <-  {photo.name}  ({capture_time})  ->  {dest.name}")

    print(f"\nDone: {len(earliest)} thumbnail(s) written to {output_folder}")
    if untagged:
        print(f"  ({untagged} image(s) had no tags)")
    if no_timestamp:
        print(f"  ({no_timestamp} tagged image(s) had no readable capture date)")


if __name__ == "__main__":
    main()
