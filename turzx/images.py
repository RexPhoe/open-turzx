"""
turzx/images.py — Image helpers (PIL/Pillow)
============================================
"""

from __future__ import annotations

import io
from PIL import Image, ImageDraw

from .protocol import SCREEN_W, SCREEN_H, JPEG_QUALITY


def to_jpeg(
    img: Image.Image,
    width: int = SCREEN_W,
    height: int = SCREEN_H,
    quality: int = JPEG_QUALITY,
    rotate: int = 180,
) -> bytes:
    """Resize to screen dimensions, rotate, and encode as JPEG.

    rotate: degrees clockwise. Default 180 because the TURZX 2.8"
            panel is mounted upside-down relative to the JPEG origin.
    """
    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    if rotate:
        img = img.rotate(rotate)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def solid(color, width: int = SCREEN_W, height: int = SCREEN_H) -> bytes:
    """Solid color JPEG."""
    return to_jpeg(Image.new("RGB", (width, height), color), width, height)


def test_pattern(
    label: str = "TURZX",
    width: int = SCREEN_W,
    height: int = SCREEN_H,
) -> bytes:
    """Colorful test pattern JPEG."""
    img = Image.new("RGB", (width, height), "red")
    d = ImageDraw.Draw(img)
    for i in range(5):
        d.rectangle([i, i, width - 1 - i, height - 1 - i], outline="white")
    d.line([(0, 0), (width - 1, height - 1)], fill="yellow", width=5)
    d.line([(width - 1, 0), (0, height - 1)], fill="yellow", width=5)
    d.ellipse(
        [width // 4, height // 4, 3 * width // 4, 3 * height // 4],
        fill="lime",
        outline="white",
        width=3,
    )
    d.text((width // 3, height // 2 - 10), label, fill="black")
    d.text((10, 10), f"{width}x{height}", fill="white")
    return to_jpeg(img, width, height)


def from_file(path: str) -> bytes:
    """Load image file → JPEG bytes for screen."""
    return to_jpeg(Image.open(path))
