#!/usr/bin/env python3
"""Create watermarked preview proofs from a photo folder hierarchy.

Recursively mirrors the folder structure of <source> into <dest>. Each image
is downsized to roughly TARGET_MEGAPIXELS, watermarked with a centered,
drop-shadowed block of text, and saved as a JPEG at JPEG_QUALITY. All outputs
are .jpg regardless of the source format.

Usage: python3 watermark_proofs.py <source> <dest>
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

IMAGE_EXTS = {'.jpg', '.jpeg', '.tif', '.tiff', '.png'}
FONT_PATH = Path.home() / 'Library/Fonts/Oswald-VariableFont_wght.ttf'
FONT_WEIGHT = 'Light'
WATERMARK_TEXT = 'FOR PREVIEW ONLY\nNOT FOR DISTRIBUTION\n© PHOTOS BY LOGAN'

TARGET_MEGAPIXELS = 3_000_000
JPEG_QUALITY = 75
WATERMARK_OPACITY = 0.10       # white text
SHADOW_OPACITY = 0.45          # black shadow, kept stronger so the faint text stays legible
MAX_TEXT_WIDTH_FRAC = 0.9      # widest line should span at most this fraction of image width


def load_font(size: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONT_PATH), size)
    try:
        font.set_variation_by_name(FONT_WEIGHT)
    except OSError:
        pass  # non-variable fallback font; used as-is
    return font


def fit_font(draw: ImageDraw.ImageDraw, canvas_width: int, max_height: int) -> ImageFont.FreeTypeFont:
    """Pick the largest font size that fits the width/height caps — scales up from
    the probe size just as readily as it scales down, rather than only ever shrinking.
    """
    longest_line = max(WATERMARK_TEXT.split('\n'), key=len)
    max_width = canvas_width * MAX_TEXT_WIDTH_FRAC

    probe_size = 100
    font = load_font(probe_size)
    width_measured = draw.textbbox((0, 0), longest_line, font=font)[2]
    height_measured = draw.multiline_textbbox((0, 0), WATERMARK_TEXT, font=font, align='center')[3]

    scale = float('inf')
    if width_measured > 0:
        scale = min(scale, max_width / width_measured)
    if height_measured > 0:
        scale = min(scale, (max_height * 0.9) / height_measured)

    size = max(12, int(probe_size * scale))
    return load_font(size)


def apply_watermark(img: Image.Image) -> Image.Image:
    base = img.convert('RGBA')
    draw = ImageDraw.Draw(base)
    band_height = base.height * 2 // 3
    center = (base.width // 2, base.height - band_height // 2)  # centered in the bottom two-thirds
    # Bound the text width by the shorter side, not the full canvas width, so it
    # doesn't stretch edge-to-edge on wide landscape photos.
    bounding_width = min(base.width, base.height)
    font = fit_font(draw, bounding_width, band_height)

    shadow_offset = max(2, font.size // 20)
    blur_radius = max(1, font.size // 25)

    # Text mask at the final (unshifted) text position — used to knock the shadow
    # out from directly behind the glyphs, so it only shows as a fringe around them
    # rather than darkening the semi-transparent white text itself.
    text_mask = Image.new('L', base.size, 0)
    ImageDraw.Draw(text_mask).multiline_text(center, WATERMARK_TEXT, font=font,
                                              fill=255, anchor='mm', align='center')

    shadow_layer = Image.new('RGBA', base.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow_layer).multiline_text(
        (center[0] + shadow_offset, center[1] + shadow_offset), WATERMARK_TEXT, font=font,
        fill=(0, 0, 0, int(255 * SHADOW_OPACITY)), anchor='mm', align='center')
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur_radius))
    shadow_layer.putalpha(ImageChops.multiply(shadow_layer.getchannel('A'), ImageOps.invert(text_mask)))
    base = Image.alpha_composite(base, shadow_layer)

    text_layer = Image.new('RGBA', base.size, (0, 0, 0, 0))
    ImageDraw.Draw(text_layer).multiline_text(
        center, WATERMARK_TEXT, font=font,
        fill=(255, 255, 255, int(255 * WATERMARK_OPACITY)), anchor='mm', align='center')
    base = Image.alpha_composite(base, text_layer)

    return base.convert('RGB')


def process_image(src: Path, dest: Path) -> None:
    with Image.open(src) as img:
        exif = img.getexif()
        # exif_transpose bakes the rotation into the pixels themselves, so the
        # orientation tag (if any) must be reset — otherwise viewers that respect
        # EXIF orientation would rotate an already-upright image a second time.
        if 274 in exif:
            exif[274] = 1

        img = ImageOps.exif_transpose(img)
        pixels = img.width * img.height
        if pixels > TARGET_MEGAPIXELS:
            scale = (TARGET_MEGAPIXELS / pixels) ** 0.5
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                              Image.LANCZOS)
        watermarked = apply_watermark(img)
        dest.parent.mkdir(parents=True, exist_ok=True)
        watermarked.save(dest, 'JPEG', quality=JPEG_QUALITY, exif=exif.tobytes())


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: watermark_proofs.py <source> <dest>")
        sys.exit(1)

    source = Path(sys.argv[1]).expanduser().resolve()
    dest = Path(sys.argv[2]).expanduser().resolve()
    if not source.exists():
        print(f"Source folder does not exist: {source}")
        sys.exit(1)
    if not FONT_PATH.exists():
        print(f"Font not found: {FONT_PATH}")
        sys.exit(1)

    files = sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    print(f"Found {len(files)} image(s) under {source}\n")

    done = failed = 0
    for src in files:
        rel = src.relative_to(source).with_suffix('.jpg')
        dest_path = dest / rel
        try:
            process_image(src, dest_path)
            print(f"  {rel}")
            done += 1
        except Exception as e:
            print(f"  FAILED: {rel} — {e}")
            failed += 1

    print(f"\nDone: {done} watermarked, {failed} failed.")


if __name__ == '__main__':
    main()
