"""
turzx/renderer.py — Composites a Layout + sensor values into a screen JPEG
==========================================================================
Draws background, then each element sorted by z-order.
Output is a 480x480 JPEG ready for TurzxDevice.send_frame().
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from .config import Layout, LayoutElement
from .images import to_jpeg
from .protocol import SCREEN_W, SCREEN_H
from .sensors.base import SensorReading

# ── Font cache ──

_font_cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}

_FONT_CANDIDATES = [
    "segoeui.ttf",
    "arial.ttf",
    "DejaVuSans.ttf",
    "FreeSans.ttf",
    "LiberationSans-Regular.ttf",
]


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if size in _font_cache:
        return _font_cache[size]
    for name in _FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(name, size)
            _font_cache[size] = font
            return font
        except OSError:
            continue
    # Pillow 10+ supports size param; older versions don't
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:
        font = ImageFont.load_default()
    _font_cache[size] = font
    return font


# ── Renderer ──

class Renderer:
    def __init__(self, width: int = SCREEN_W, height: int = SCREEN_H) -> None:
        self.width = width
        self.height = height

    def render(self, layout: Layout, sensor_values: dict[str, SensorReading]) -> bytes:
        """Compose layout into JPEG bytes for the screen."""
        img = self._draw_background(layout)
        draw = ImageDraw.Draw(img)

        # Sort by z-order (lower z drawn first = behind)
        for element in sorted(layout.elements, key=lambda e: e.z):
            if element.type == "text":
                self._draw_text(draw, element)
            elif element.type == "sensor":
                self._draw_sensor(draw, element, sensor_values)
            elif element.type == "image":
                self._draw_image(img, element)

        return to_jpeg(img, self.width, self.height)

    def _draw_background(self, layout: Layout) -> Image.Image:
        bg = layout.background
        if bg.type == "solid":
            return Image.new("RGB", (self.width, self.height), tuple(bg.color))
        elif bg.type == "image" and bg.path:
            try:
                img = Image.open(bg.path).convert("RGB")
                return img.resize((self.width, self.height), Image.LANCZOS)
            except Exception:
                return Image.new("RGB", (self.width, self.height), (15, 15, 25))
        # Default fallback
        return Image.new("RGB", (self.width, self.height), (15, 15, 25))

    def _draw_text(self, draw: ImageDraw.ImageDraw, el: LayoutElement) -> None:
        font = get_font(el.font_size)
        draw.text(
            (el.x, el.y),
            el.text,
            fill=tuple(el.color),
            font=font,
            anchor=el.anchor,
        )

    def _draw_sensor(
        self,
        draw: ImageDraw.ImageDraw,
        el: LayoutElement,
        values: dict[str, SensorReading],
    ) -> None:
        reading = values.get(el.sensor_id)
        if reading is None:
            return  # sensor not available, skip silently

        try:
            text = el.format.format(
                label=el.label or reading.name,
                value=reading.value,
                unit=reading.unit,
            )
        except (KeyError, ValueError):
            text = f"{el.label}: {reading.value}{reading.unit}"

        font = get_font(el.font_size)
        draw.text(
            (el.x, el.y),
            text,
            fill=tuple(el.color),
            font=font,
            anchor=el.anchor,
        )

    def _draw_image(self, canvas: Image.Image, el: LayoutElement) -> None:
        try:
            overlay = Image.open(el.text).convert("RGBA")
            canvas.paste(overlay, (el.x, el.y), overlay)
        except Exception:
            pass
