"""
turzx/renderer.py — Composites a Layout + sensor values into a screen image
===========================================================================
Two-layer architecture for smooth 60 FPS video playback:

  1. **Overlay** (RGBA, transparent bg): text, sensor readouts, images.
     Rebuilt only when sensor data changes (every refresh_rate seconds).

  2. **Background frame**: video frame / static image / solid color.
     Advances every frame at 60 FPS.

Each render_frame() call: read next video frame → paste cached overlay → JPEG.
This keeps the per-frame cost minimal (~5 ms) so 60 FPS is achievable.
"""

from __future__ import annotations

import math
import os
import sys
import threading
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from .config import Layout, LayoutElement
from .images import to_jpeg
from .protocol import SCREEN_W, SCREEN_H
from .sensors.base import SensorReading
from .sensors.units import convert as convert_unit, get_strftime

# ── Font cache ──

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
_font_path_cache: dict[str, str | None] = {}  # family name -> file path

_FONT_CANDIDATES = [
    "segoeui.ttf",
    "arial.ttf",
    "DejaVuSans.ttf",
    "FreeSans.ttf",
    "LiberationSans-Regular.ttf",
]


def _find_font_file(family: str) -> str | None:
    """Resolve a font family name to its .ttf/.otf file path.

    On Windows, reads HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts
    to build a name→file mapping. On Linux, uses fc-match.
    """
    if family in _font_path_cache:
        return _font_path_cache[family]

    path: str | None = None
    family_lower = family.lower()

    if sys.platform == "win32":
        try:
            import winreg
            fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
            )
            try:
                i = 0
                while True:
                    name, data, _ = winreg.EnumValue(key, i)
                    i += 1
                    # name is like "Arial (TrueType)" or "Segoe UI (TrueType)"
                    name_clean = name.split("(")[0].strip().lower()
                    if name_clean == family_lower:
                        if os.path.isabs(data):
                            path = data
                        else:
                            path = os.path.join(fonts_dir, data)
                        break
            except OSError:
                pass
            finally:
                winreg.CloseKey(key)
        except Exception:
            pass
    else:
        # Linux: fc-match
        try:
            import subprocess
            result = subprocess.run(
                ["fc-match", "--format=%{file}", family],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip()
        except Exception:
            pass

    _font_path_cache[family] = path
    return path


def get_font(
    size: int, family: str = ""
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    key = (family, size)
    if key in _font_cache:
        return _font_cache[key]

    # Try specific family first
    if family:
        # 1) Resolve family name → file path via OS font registry
        resolved = _find_font_file(family)
        if resolved and os.path.isfile(resolved):
            try:
                font = ImageFont.truetype(resolved, size)
                _font_cache[key] = font
                return font
            except OSError:
                pass

        # 2) Try the raw name (PIL may resolve simple names like "arial")
        for suffix in ("", ".ttf", ".otf"):
            try:
                font = ImageFont.truetype(family + suffix, size)
                _font_cache[key] = font
                return font
            except OSError:
                continue

    # Fallback to system defaults
    for name in _FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(name, size)
            _font_cache[key] = font
            return font
        except OSError:
            continue
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:
        font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def _make_gradient(
    w: int, h: int, color_a: tuple, color_b: tuple, angle_deg: int
) -> Image.Image:
    """Create a w x h RGBA gradient image between two RGB colors."""
    if w < 1 or h < 1:
        return Image.new("RGBA", (max(w, 1), max(h, 1)), color_a + (255,))

    grad = Image.new("RGBA", (w, h))
    angle = math.radians(angle_deg % 360)
    cos_a, sin_a = math.cos(angle), math.sin(angle)

    # Project corners onto the gradient axis to find the range
    corners = [(0, 0), (w, 0), (w, h), (0, h)]
    projs = [x * cos_a + y * sin_a for x, y in corners]
    p_min, p_max = min(projs), max(projs)
    span = p_max - p_min if p_max != p_min else 1.0

    ra, ga, ba = color_a[:3]
    rb, gb, bb = color_b[:3]
    pixels = grad.load()
    for y in range(h):
        for x in range(w):
            t = ((x * cos_a + y * sin_a) - p_min) / span
            r = int(ra + (rb - ra) * t)
            g = int(ga + (gb - ga) * t)
            b = int(ba + (bb - ba) * t)
            pixels[x, y] = (r, g, b, 255)
    return grad


# ── Renderer ──


class Renderer:
    # Video frames advance at this rate regardless of render loop speed.
    # Prevents 24fps videos from playing 2.5x too fast at 60fps render.
    VIDEO_FPS_CAP = 24

    def __init__(self, width: int = SCREEN_W, height: int = SCREEN_H) -> None:
        self.width = width
        self.height = height

        # Video state (thread-safe)
        self._video_cap = None
        self._video_path: str | None = None
        self._video_lock = threading.Lock()
        self._video_frame: Image.Image | None = None  # cached last frame
        self._video_frame_time: float = 0.0  # when we last advanced

        # Cached overlay — rebuilt only at sensor_rate
        self._overlay: Image.Image | None = None
        self._realtime_elements: list[LayoutElement] = []

        # Cached static background (for image type — no need to re-open every frame)
        self._static_bg: Image.Image | None = None
        self._static_bg_path: str | None = None

    # ── Public API ──

    # IDs of sensors that must be drawn every frame (not cached in overlay)
    _REALTIME_SENSORS = frozenset(("sys.clock", "sys.date"))

    def update_overlay(
        self, layout: Layout, sensor_values: dict[str, SensorReading]
    ) -> None:
        """Rebuild the element overlay (call at sensor_rate, NOT every frame).

        Renders text, sensor readouts, and image elements onto a transparent
        RGBA image that gets composited on top of the background each frame.
        Real-time sensors (clock, date) are skipped here — drawn in render_frame.
        """
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for element in sorted(layout.elements, key=lambda e: e.z):
            # Skip real-time sensors — rendered per-frame instead
            if element.type == "sensor" and element.sensor_id in self._REALTIME_SENSORS:
                continue
            if element.type == "text":
                self._draw_text(overlay, draw, element)
            elif element.type == "sensor":
                self._draw_sensor(overlay, draw, element, sensor_values)
            elif element.type == "image":
                self._draw_image(overlay, element)
            elif element.type == "shape":
                self._draw_shape(overlay, draw, element)
            elif element.type == "bar":
                self._draw_bar(overlay, draw, element, sensor_values)
            elif element.type == "arc_bar":
                self._draw_arc_bar(overlay, draw, element, sensor_values)

        # Cache which elements need per-frame rendering
        self._realtime_elements = [
            el for el in layout.elements
            if el.type == "sensor" and el.sensor_id in self._REALTIME_SENSORS
        ]
        self._overlay = overlay

    def render_frame(self, layout: Layout) -> bytes:
        """Produce one JPEG frame for the device (call at 60 FPS).

        Reads the next video frame (or static bg), composites the cached
        overlay on top, draws real-time sensors (clock/date), rotates,
        and encodes to JPEG.
        """
        img = self._compose_frame(layout)
        return to_jpeg(img, self.width, self.height, rotate=layout.rotation)

    def _compose_frame(self, layout: Layout) -> Image.Image:
        """Compose one frame as a PIL Image (pre-JPEG, pre-rotation)."""
        bg = self._get_background(layout).copy()
        if self._overlay is not None:
            bg.paste(self._overlay, (0, 0), self._overlay)

        # Draw real-time sensors directly each frame
        if self._realtime_elements:
            draw = ImageDraw.Draw(bg)
            now = datetime.now()
            for el in self._realtime_elements:
                if el.sensor_id == "sys.clock":
                    fmt = get_strftime("sys.clock", el.display_unit) or "%H:%M:%S"
                    val = now.strftime(fmt)
                elif el.sensor_id == "sys.date":
                    fmt = get_strftime("sys.date", el.display_unit) or "%Y-%m-%d"
                    val = now.strftime(fmt)
                else:
                    continue
                try:
                    text = el.format.format(label=el.label or el.sensor_id, value=val, unit="")
                except (KeyError, ValueError):
                    text = val
                self._render_text_on(bg, draw, text, el)

        return bg

    def render_image(
        self, layout: Layout, sensor_values: dict[str, SensorReading]
    ) -> Image.Image:
        """Full compose into a PIL Image (for editor canvas).

        This is the all-in-one path used by the editor canvas timer
        which runs at ~5-10 FPS.  NOT used in the device render loop.
        """
        bg = self._get_background(layout).copy()
        draw = ImageDraw.Draw(bg)

        for element in sorted(layout.elements, key=lambda e: e.z):
            if element.type == "text":
                self._draw_text(bg, draw, element)
            elif element.type == "sensor":
                self._draw_sensor(bg, draw, element, sensor_values)
            elif element.type == "image":
                self._draw_image(bg, element)
            elif element.type == "shape":
                self._draw_shape(bg, draw, element)
            elif element.type == "bar":
                self._draw_bar(bg, draw, element, sensor_values)
            elif element.type == "arc_bar":
                self._draw_arc_bar(bg, draw, element, sensor_values)

        return bg

    def cleanup(self) -> None:
        """Release video resources."""
        with self._video_lock:
            if self._video_cap is not None:
                self._video_cap.release()
                self._video_cap = None
                self._video_path = None
            self._video_frame = None
            self._video_frame_time = 0.0
        self._overlay = None
        self._static_bg = None
        self._static_bg_path = None

    # ── Background ──

    def _get_background(self, layout: Layout) -> Image.Image:
        """Return the current background frame (advances video by one frame)."""
        bg = layout.background

        if bg.type == "solid":
            return Image.new("RGB", (self.width, self.height), tuple(bg.color))

        elif bg.type == "image" and bg.path:
            return self._get_static_bg(bg)

        elif bg.type == "video" and bg.path:
            frame = self._read_video_frame(bg.path)
            if frame is not None:
                return self._place_bg_media(frame, bg)

        # Default fallback
        return Image.new("RGB", (self.width, self.height), (15, 15, 25))

    def _place_bg_media(self, src: Image.Image, bg) -> Image.Image:
        """Resize source to target rect preserving aspect ratio, paste on canvas."""
        tw = bg.crop_w if bg.crop_w > 0 else self.width
        th = bg.crop_h if bg.crop_h > 0 else self.height

        if tw == self.width and th == self.height and bg.crop_x == 0 and bg.crop_y == 0:
            # Full screen — stretch to fill (legacy behaviour)
            return src.resize((self.width, self.height), Image.BILINEAR)

        # Fit within target rect preserving aspect ratio
        sw, sh = src.size
        scale = min(tw / sw, th / sh)
        nw, nh = int(sw * scale), int(sh * scale)
        resized = src.resize((nw, nh), Image.BILINEAR)

        canvas = Image.new("RGB", (self.width, self.height), tuple(bg.color))
        # Center within the target rect
        ox = bg.crop_x + (tw - nw) // 2
        oy = bg.crop_y + (th - nh) // 2
        canvas.paste(resized, (ox, oy))
        return canvas

    def _get_static_bg(self, bg) -> Image.Image:
        """Load and cache a static image background."""
        path = bg.path
        fallback_color = bg.color
        # Invalidate cache if path or crop changed
        cache_key = (path, bg.crop_x, bg.crop_y, bg.crop_w, bg.crop_h)
        if self._static_bg_path != cache_key or self._static_bg is None:
            try:
                img = Image.open(path).convert("RGB")
                self._static_bg = self._place_bg_media(img, bg)
                self._static_bg_path = cache_key
            except Exception:
                self._static_bg = None
                self._static_bg_path = None
                return Image.new(
                    "RGB", (self.width, self.height), tuple(fallback_color)
                )
        # Return a COPY so callers can draw on it without corrupting the cache
        return self._static_bg.copy()

    def _read_video_frame(self, path: str) -> Image.Image | None:
        """Read the next video frame at VIDEO_FPS_CAP rate (thread-safe).

        Between advances the last decoded frame is returned from cache,
        so the render loop can run at 60 FPS while the video plays at
        its natural rate (capped at 24 FPS).
        """
        try:
            import cv2
        except ImportError:
            return None

        now = time.monotonic()
        frame_interval = 1.0 / self.VIDEO_FPS_CAP

        with self._video_lock:
            try:
                path = path.replace("\\", "/")

                # (Re)open if path changed
                if self._video_path != path:
                    if self._video_cap is not None:
                        self._video_cap.release()
                    self._video_cap = cv2.VideoCapture(path)
                    self._video_path = path
                    self._video_frame = None
                    self._video_frame_time = 0.0

                if self._video_cap is None or not self._video_cap.isOpened():
                    return self._video_frame  # return last good frame if any

                # If not enough time has passed, return cached frame
                if self._video_frame is not None and (now - self._video_frame_time) < frame_interval:
                    return self._video_frame

                # Advance to next frame
                ret, frame = self._video_cap.read()
                if not ret:
                    # Loop back to start — try seek first
                    self._video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self._video_cap.read()
                if not ret:
                    # Seek failed (H.265, VP9, etc.) — reopen from scratch
                    self._video_cap.release()
                    self._video_cap = cv2.VideoCapture(path)
                    if self._video_cap.isOpened():
                        ret, frame = self._video_cap.read()
                if not ret:
                    return self._video_frame  # return last good frame

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                self._video_frame = img
                self._video_frame_time = now
                return self._video_frame
            except Exception:
                return self._video_frame

    # ── Elements ──

    def _render_text_on(
        self,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        text: str,
        el: LayoutElement,
    ) -> None:
        """Draw text with optional stroke and gradient fill."""
        font = get_font(el.font_size, el.font_family)
        fill = tuple(el.color)

        # Stroke (border)
        stroke_w = el.stroke_width
        stroke_fill = tuple(el.stroke_color) if stroke_w > 0 else None

        if el.gradient:
            # Gradient fill: render text as mask, create gradient, paste through mask
            bbox = draw.textbbox(
                (el.x, el.y), text, font=font, anchor=el.anchor,
                stroke_width=stroke_w,
            )
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            if tw > 0 and th > 0:
                # Draw stroke first (underneath) if requested
                if stroke_w > 0:
                    draw.text(
                        (el.x, el.y), text, font=font, anchor=el.anchor,
                        fill=stroke_fill, stroke_width=stroke_w,
                        stroke_fill=stroke_fill,
                    )
                # Create gradient patch
                grad = _make_gradient(
                    tw, th,
                    tuple(el.color), tuple(el.gradient_color),
                    el.gradient_angle,
                )
                # Create text mask
                mask = Image.new("L", (tw, th), 0)
                mask_draw = ImageDraw.Draw(mask)
                # Draw text at local origin (offset from bbox)
                mask_draw.text(
                    (el.x - bbox[0], el.y - bbox[1]),
                    text, font=font, anchor=el.anchor, fill=255,
                )
                canvas.paste(grad, (bbox[0], bbox[1]), mask)
        else:
            # Simple solid-color text (with optional stroke)
            draw.text(
                (el.x, el.y), text, fill=fill, font=font, anchor=el.anchor,
                stroke_width=stroke_w, stroke_fill=stroke_fill,
            )

    def _draw_text(self, canvas: Image.Image, draw: ImageDraw.ImageDraw, el: LayoutElement) -> None:
        self._render_text_on(canvas, draw, el.text, el)

    def _draw_sensor(
        self,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        el: LayoutElement,
        values: dict[str, SensorReading],
    ) -> None:
        reading = values.get(el.sensor_id)
        if reading is None:
            return

        # Real-time override: clock/date always use current time
        # so they update every frame regardless of sensor poll rate.
        value = reading.value
        unit = reading.unit
        if el.sensor_id == "sys.clock":
            fmt = get_strftime("sys.clock", el.display_unit) or "%H:%M:%S"
            value = datetime.now().strftime(fmt)
        elif el.sensor_id == "sys.date":
            fmt = get_strftime("sys.date", el.display_unit) or "%Y-%m-%d"
            value = datetime.now().strftime(fmt)

        # Apply unit conversion if the user chose a different display unit
        elif el.display_unit and isinstance(value, (int, float)):
            value, unit = convert_unit(value, reading.unit, el.display_unit)

        try:
            text = el.format.format(
                label=el.label or reading.name,
                value=value,
                unit=unit,
            )
        except (KeyError, ValueError):
            text = f"{el.label}: {value}{unit}"

        self._render_text_on(canvas, draw, text, el)

    def _draw_image(self, canvas: Image.Image, el: LayoutElement) -> None:
        try:
            overlay = Image.open(el.text).convert("RGBA")
            if el.w and el.h:
                overlay = overlay.resize((el.w, el.h), Image.LANCZOS)
            canvas.paste(overlay, (el.x, el.y), overlay)
        except Exception:
            pass

    # ── Shapes ──

    def _shape_fill(self, el: LayoutElement, w: int, h: int) -> tuple | Image.Image:
        """Return a fill color tuple or gradient image for shape fill."""
        if el.gradient and w > 0 and h > 0:
            return _make_gradient(w, h, tuple(el.fill_color), tuple(el.gradient_color), el.gradient_angle)
        return tuple(el.fill_color[:3]) + (el.fill_alpha,)

    def _draw_shape(
        self, canvas: Image.Image, draw: ImageDraw.ImageDraw, el: LayoutElement
    ) -> None:
        """Draw a basic shape (rect, circle, ellipse, line)."""
        w = max(el.w, 1)
        h = max(el.h, 1)
        x1, y1 = el.x, el.y
        x2, y2 = x1 + w, y1 + h
        outline = tuple(el.stroke_color) if el.stroke_width > 0 else None
        sw = el.stroke_width

        if el.shape == "line":
            draw.line(
                [(x1, y1), (x2, y2)],
                fill=tuple(el.fill_color[:3]) + (el.fill_alpha,),
                width=max(sw, 1),
            )
            return

        # For filled shapes with gradient, compose onto a temp layer
        if el.gradient:
            layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            grad = _make_gradient(w, h, tuple(el.fill_color), tuple(el.gradient_color), el.gradient_angle)
            # Create shape mask
            mask = Image.new("L", (w, h), 0)
            md = ImageDraw.Draw(mask)
            if el.shape == "circle":
                s = min(w, h)
                md.ellipse([0, 0, s - 1, s - 1], fill=255)
            elif el.shape == "ellipse":
                md.ellipse([0, 0, w - 1, h - 1], fill=255)
            else:  # rect
                md.rectangle([0, 0, w - 1, h - 1], fill=255)
            # Apply gradient through mask
            layer.paste(grad, (0, 0), mask)
            # Draw outline on layer
            if outline:
                if el.shape in ("circle", "ellipse"):
                    s = min(w, h) if el.shape == "circle" else None
                    if s:
                        ld.ellipse([0, 0, s - 1, s - 1], outline=outline, width=sw)
                    else:
                        ld.ellipse([0, 0, w - 1, h - 1], outline=outline, width=sw)
                else:
                    ld.rectangle([0, 0, w - 1, h - 1], outline=outline, width=sw)
            canvas.paste(layer, (x1, y1), layer)
        else:
            fill = tuple(el.fill_color[:3]) + (el.fill_alpha,)
            if el.shape == "circle":
                s = min(w, h)
                draw.ellipse([x1, y1, x1 + s - 1, y1 + s - 1], fill=fill, outline=outline, width=sw)
            elif el.shape == "ellipse":
                draw.ellipse([x1, y1, x2 - 1, y2 - 1], fill=fill, outline=outline, width=sw)
            else:  # rect
                draw.rectangle([x1, y1, x2 - 1, y2 - 1], fill=fill, outline=outline, width=sw)

    # ── Bars (sensor-linked) ──

    def _get_sensor_pct(
        self, el: LayoutElement, values: dict[str, SensorReading]
    ) -> float:
        """Return sensor value as 0.0-1.0 fraction of bar_max."""
        reading = values.get(el.sensor_id)
        if reading is None:
            return 0.0
        try:
            val = float(reading.value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, val / el.bar_max)) if el.bar_max > 0 else 0.0

    def _draw_bar(
        self,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        el: LayoutElement,
        values: dict[str, SensorReading],
    ) -> None:
        """Draw a progress bar linked to a sensor (supports 4 directions)."""
        w = max(el.w, 10)
        h = max(el.h, 4)
        pct = self._get_sensor_pct(el, values)
        direction = el.bar_direction or "right"

        # Background
        bg_col = tuple(el.bar_bg_color[:3]) + (255,)
        draw.rectangle([el.x, el.y, el.x + w - 1, el.y + h - 1], fill=bg_col)

        # Foreground (filled portion)
        if direction == "right":
            fw = int(w * pct)
            if fw > 0:
                fx, fy = el.x, el.y
                fx2, fy2 = el.x + fw - 1, el.y + h - 1
                grad_angle = 0
        elif direction == "left":
            fw = int(w * pct)
            if fw > 0:
                fx, fy = el.x + w - fw, el.y
                fx2, fy2 = el.x + w - 1, el.y + h - 1
                grad_angle = 180
            else:
                fw = 0
        elif direction == "down":
            fh = int(h * pct)
            if fh > 0:
                fx, fy = el.x, el.y
                fx2, fy2 = el.x + w - 1, el.y + fh - 1
                fw = fh  # reuse as nonzero flag
                grad_angle = 90
            else:
                fw = 0
        elif direction == "up":
            fh = int(h * pct)
            if fh > 0:
                fx, fy = el.x, el.y + h - fh
                fx2, fy2 = el.x + w - 1, el.y + h - 1
                fw = fh
                grad_angle = 270
            else:
                fw = 0
        else:
            fw = int(w * pct)
            if fw > 0:
                fx, fy = el.x, el.y
                fx2, fy2 = el.x + fw - 1, el.y + h - 1
                grad_angle = 0

        if fw > 0:
            if el.bar_fg_gradient:
                gw = fx2 - fx + 1
                gh = fy2 - fy + 1
                if gw > 0 and gh > 0:
                    fg = _make_gradient(
                        gw, gh,
                        tuple(el.bar_fg_color), tuple(el.bar_fg_color2),
                        grad_angle,
                    )
                    canvas.paste(fg, (fx, fy), fg)
            else:
                fg_col = tuple(el.bar_fg_color[:3]) + (255,)
                draw.rectangle([fx, fy, fx2, fy2], fill=fg_col)

        # Border
        if el.stroke_width > 0:
            draw.rectangle(
                [el.x, el.y, el.x + w - 1, el.y + h - 1],
                outline=tuple(el.stroke_color), width=el.stroke_width,
            )

    def _draw_arc_bar(
        self,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        el: LayoutElement,
        values: dict[str, SensorReading],
    ) -> None:
        """Draw a circular arc bar linked to a sensor."""
        w = max(el.w, 20)
        h = max(el.h, 20)
        pct = self._get_sensor_pct(el, values)
        thickness = max(el.bar_thickness, 2)

        bbox = [el.x, el.y, el.x + w - 1, el.y + h - 1]

        # Background arc (full sweep)
        bg_col = tuple(el.bar_bg_color[:3])
        draw.arc(bbox, el.bar_start_angle, el.bar_start_angle + el.bar_sweep_angle,
                 fill=bg_col, width=thickness)

        # Foreground arc (proportional to value)
        fg_sweep = int(el.bar_sweep_angle * pct)
        if fg_sweep > 0:
            fg_col = tuple(el.bar_fg_color[:3])
            draw.arc(bbox, el.bar_start_angle, el.bar_start_angle + fg_sweep,
                     fill=fg_col, width=thickness)
