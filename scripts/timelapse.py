#!/usr/bin/env python3
"""Create an MP4 from a folder of images, each held for a fixed interval.

Images are sorted by EXIF capture date (DateTimeOriginal). Each photo is
displayed for the given interval in decimal seconds.

Usage: python3 timelapse.py <folder> [output.mp4] (--interval SECONDS | --duration SECONDS | --bpm BPM)

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

LAST_HOLD_SECONDS = 3.0

_EXIF_IFD   = 0x8769
_TAG_DTO    = 36867
_TAG_DTD    = 36868
_TAG_DT     = 306
_TAG_SSDTO  = 37521
_TAG_SSDTD  = 37522


def _parse_subsec(raw: str | None) -> int:
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


_TAG_ORIENTATION = 274


def get_orientation(path: Path) -> str:
    with Image.open(path) as img:
        w, h = img.size
        if img.getexif().get(_TAG_ORIENTATION) in (5, 6, 7, 8):
            w, h = h, w
    if w > h:
        return 'landscape'
    if h > w:
        return 'portrait'
    return 'square'


def _pick_encoder() -> list[str]:
    result = subprocess.run(['ffmpeg', '-encoders', '-v', 'quiet'],
                            capture_output=True, text=True)
    if 'h264_videotoolbox' in result.stdout:
        print("Encoder: h264_videotoolbox (hardware)")
        return ['-c:v', 'h264_videotoolbox', '-q:v', '65']
    print("Encoder: libx264 ultrafast (software)")
    return ['-c:v', 'libx264', '-preset', 'ultrafast']


def make_timelapse(folder: Path, output: Path, width: int, height: int,
                    interval: float | None = None, duration: float | None = None,
                    bpm: float | None = None,
                    limit: int | None = None, match_orientation: bool = False) -> None:
    if not shutil.which('ffmpeg'):
        print("ffmpeg not found on PATH. Install it with: brew install ffmpeg")
        sys.exit(1)

    files = sorted(p for p in folder.rglob('*') if p.suffix.lower() in IMAGE_EXTS)
    if not files:
        print("No images found.")
        sys.exit(1)

    print(f"Found {len(files)} image(s) in {folder}\n")

    entries: list[tuple[datetime, Path]] = []
    skipped = 0
    for f in files:
        ts = get_capture_time(f)
        if ts is None:
            skipped += 1
        else:
            entries.append((ts, f))

    if skipped:
        print(f"  Skipped {skipped} image(s) with no readable timestamp\n")

    if not entries:
        print("No images with readable timestamps.")
        sys.exit(1)

    if match_orientation:
        target = 'landscape' if width > height else 'portrait' if height > width else 'square'
        matched, excluded = [], 0
        for ts, path in entries:
            if get_orientation(path) in (target, 'square'):
                matched.append((ts, path))
            else:
                excluded += 1
        if excluded:
            print(f"  Excluded {excluded} image(s) not matching {target} orientation\n")
        entries = matched
        if not entries:
            print(f"No images matching {target} orientation.")
            sys.exit(1)

    entries.sort(key=lambda x: x[0])

    if limit is not None:
        entries = entries[:limit]
        print(f"(--test: using first {len(entries)} images)\n")

    if bpm is not None:
        interval = 60.0 / bpm

    if duration is not None:
        interval = duration / (len(entries) - 1) if len(entries) > 1 else 0.0

    total = (len(entries) - 1) * interval + LAST_HOLD_SECONDS
    print(f"Images: {len(entries)}  |  Interval: {interval}s  |  Last hold: {LAST_HOLD_SECONDS}s  |  Total: {total:.1f}s\n")

    concat_file = Path(tempfile.mktemp(suffix='.txt'))
    try:
        with concat_file.open('w') as f:
            f.write("ffconcat version 1.0\n")
            for i, (_, img_path) in enumerate(entries):
                f.write(f"file '{img_path.resolve()}'\n")
                duration = LAST_HOLD_SECONDS if i == len(entries) - 1 else interval
                f.write(f"duration {duration:.3f}\n")
            f.write(f"file '{entries[-1][1].resolve()}'\n")

        encoder = _pick_encoder()
        cmd = [
            'ffmpeg', '-y',
            '-hide_banner', '-loglevel', 'error', '-stats',
            '-f', 'concat', '-safe', '0', '-i', str(concat_file),
            '-vf', f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=yuv420p',
            '-r', '30000/1001',   # CFR 29.97fps — matches DaVinci Resolve timeline
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
                        help='Output MP4 path (default: <folder>_timelapse.mp4)')
    duration_group = parser.add_mutually_exclusive_group(required=True)
    duration_group.add_argument('--interval', type=float,
                        help='Hold duration per image in seconds (e.g. 0.5)')
    duration_group.add_argument('--duration', type=float,
                        help='Total runtime of the main sequence in seconds, excluding the '
                             'final hold — interval is computed as duration / (num_photos - 1)')
    duration_group.add_argument('--bpm', type=float,
                        help='Beats per minute — one image per beat, interval computed as 60 / bpm')
    parser.add_argument('--size', default='1080x1350',
                        help='Output WIDTHxHEIGHT, e.g. 1080x1350 for 4:5 (default) or 1080x1080 for 1:1')
    parser.add_argument('--match-orientation', action='store_true',
                        help='Only include photos whose orientation (portrait/landscape) matches '
                             'the output size — square photos are always included')
    parser.add_argument('--test', action='store_true',
                        help='Stop after the first 10 images')
    args = parser.parse_args()

    folder = args.folder.expanduser().resolve()
    if not folder.exists():
        print(f"Folder does not exist: {folder}")
        sys.exit(1)

    try:
        width, height = (int(x) for x in args.size.lower().split('x'))
    except ValueError:
        print(f"Invalid --size {args.size!r}, expected WIDTHxHEIGHT e.g. 1080x1350")
        sys.exit(1)

    output = args.output or folder.parent / (folder.name + '_timelapse.mp4')
    make_timelapse(folder, output, width, height, interval=args.interval, duration=args.duration,
                    bpm=args.bpm, limit=10 if args.test else None, match_orientation=args.match_orientation)


if __name__ == '__main__':
    main()
