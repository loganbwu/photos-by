#!/usr/bin/env python3
"""Create an MP4 slideshow from a folder of images, timed by EXIF capture date.

Each image holds on screen until the next image's capture time, so the output
can be synced against a video recorded at the same event. The final image holds
for the same duration as the preceding interval, or --tail seconds if given.

Usage: python3 make_slideshow.py <folder> [output.mp4] [--tail SECONDS]

Requires ffmpeg on PATH.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image

IMAGE_EXTS = {'.jpg', '.jpeg', '.tif', '.tiff', '.png'}

# EXIF tag IDs
_EXIF_IFD = 0x8769       # pointer to the Exif sub-IFD inside the main IFD
_TAG_DTO    = 36867  # DateTimeOriginal  — original shutter time, preserved by Lightroom
_TAG_DTD    = 36868  # DateTimeDigitized
_TAG_DT     = 306    # DateTime          — may reflect Lightroom export time
_TAG_SSDTO  = 37521  # SubSecTimeOriginal
_TAG_SSDTD  = 37522  # SubSecTimeDigitized


def _parse_subsec(raw: str | None) -> int:
    """Convert a SubSec string (e.g. '980', '75') to microseconds."""
    if not raw:
        return 0
    return int(raw.ljust(6, '0')[:6])


def get_capture_time(path: Path) -> datetime | None:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            exif_ifd = exif.get_ifd(_EXIF_IFD)

        for dt_tag, subsec_tag in ((_TAG_DTO, _TAG_SSDTO), (_TAG_DTD, _TAG_SSDTD)):
            raw = exif_ifd.get(dt_tag)
            if raw:
                try:
                    dt = datetime.strptime(raw[:19], '%Y:%m:%d %H:%M:%S')
                    return dt.replace(microsecond=_parse_subsec(exif_ifd.get(subsec_tag)))
                except ValueError:
                    pass

        raw = exif.get(_TAG_DT)
        if raw:
            return datetime.strptime(raw[:19], '%Y:%m:%d %H:%M:%S')

    except Exception as e:
        print(f"  WARN: could not read EXIF from {path.name} — {e}")
    return None


def _pick_encoder() -> list[str]:
    result = subprocess.run(['ffmpeg', '-encoders', '-v', 'quiet'],
                            capture_output=True, text=True)
    if 'h264_videotoolbox' in result.stdout:
        print("Encoder: h264_videotoolbox (hardware)")
        return ['-c:v', 'h264_videotoolbox', '-q:v', '65']
    print("Encoder: libx264 ultrafast (software)")
    return ['-c:v', 'libx264', '-preset', 'ultrafast']


def make_slideshow(folder: Path, output: Path, tail: float | None, limit: int | None = None) -> None:
    if not shutil.which('ffmpeg'):
        print("ffmpeg not found on PATH. Install it with: brew install ffmpeg")
        sys.exit(1)

    files = sorted(p for p in folder.rglob('*') if p.suffix.lower() in IMAGE_EXTS)
    if not files:
        print("No images found.")
        sys.exit(1)

    print(f"Found {len(files)} image(s) in {folder}\n")

    entries: list[tuple[datetime, Path]] = []
    for f in files:
        ts = get_capture_time(f)
        if ts is None:
            print(f"  SKIP (no timestamp): {f.name}")
        else:
            print(f"  {ts.strftime('%Y-%m-%d %H:%M:%S')}.{ts.microsecond // 1000:03d}  {f.name}")
            entries.append((ts, f))

    if len(entries) < 2:
        print("\nNeed at least 2 images with readable timestamps.")
        sys.exit(1)

    entries.sort(key=lambda x: x[0])

    if limit is not None:
        entries = entries[:limit]
        print(f"(--test: using first {len(entries)} images)\n")

    durations: list[float] = []
    for i in range(len(entries) - 1):
        delta = (entries[i + 1][0] - entries[i][0]).total_seconds()
        durations.append(max(delta, 0.001))  # guard against identical timestamps

    durations.append(tail if tail is not None else durations[-1])

    print(f"\nDurations: {[f'{d:.1f}s' for d in durations]}")
    print(f"Total:     {sum(durations):.1f}s\n")

    concat_file = Path(tempfile.mktemp(suffix='.txt'))
    try:
        with concat_file.open('w') as f:
            f.write("ffconcat version 1.0\n")
            for (_, img_path), duration in zip(entries, durations):
                f.write(f"file '{img_path.resolve()}'\n")
                f.write(f"duration {duration:.3f}\n")
            # ffconcat requires the last entry repeated without a duration
            f.write(f"file '{entries[-1][1].resolve()}'\n")

        encoder = _pick_encoder()
        cmd = [
            'ffmpeg', '-y',
            '-hide_banner', '-loglevel', 'error', '-stats',
            '-f', 'concat', '-safe', '0', '-i', str(concat_file),
            '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p',
            '-pix_fmt', 'yuv420p',
            *encoder,
            str(output),
        ]
        print('Running:', ' '.join(cmd))
        result = subprocess.run(cmd)
    finally:
        concat_file.unlink(missing_ok=True)

    if result.returncode != 0:
        print("ffmpeg failed.")
        sys.exit(1)

    print(f"\nSaved: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder', type=Path, help='Folder of images')
    parser.add_argument('output', type=Path, nargs='?', default=None,
                        help='Output MP4 path (default: <folder>_slideshow.mp4)')
    parser.add_argument('--tail', type=float, default=None,
                        help='Hold duration for the final image in seconds '
                             '(default: same as the last interval)')
    parser.add_argument('--test', action='store_true',
                        help='Stop after the first 10 images')
    args = parser.parse_args()

    folder = args.folder.expanduser().resolve()
    if not folder.exists():
        print(f"Folder does not exist: {folder}")
        sys.exit(1)

    output = args.output or folder.parent / (folder.name + '_slideshow.mp4')
    make_slideshow(folder, output, args.tail, limit=10 if args.test else None)


if __name__ == '__main__':
    main()
