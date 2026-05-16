"""
turzx/transitions.py — Layout transition effects
=================================================
Pure PIL-based blending functions.  Each receives the old and new
frames (``Image.Image``, same size) and a progress float 0→1,
and returns the blended result.

All operations are cross-platform (Linux/Windows).
"""

from __future__ import annotations

import random

from PIL import Image

# Available transition names (for UI combos)
TRANSITIONS = [
    "none",
    "random",
    "fade",
    "dissolve",
    "zoom_in",
    "zoom_out",
    "swipe_left",
    "swipe_right",
    "swipe_up",
    "swipe_down",
    "wipe_left",
    "wipe_right",
    "wipe_up",
    "wipe_down",
    "iris_circle",
    "iris_box",
    "blinds_horizontal",
    "blinds_vertical",
    "checkerboard",
]

_RANDOM_TRANSITIONS = [name for name in TRANSITIONS if name not in ("none", "random")]
_DISSOLVE_MASKS: dict[tuple[int, int], Image.Image] = {}


def resolve(kind: str) -> str:
    """Return the concrete transition to use for a new layout switch."""
    if kind == "random":
        return random.choice(_RANDOM_TRANSITIONS)
    return kind


def apply(
    old: Image.Image, new: Image.Image, progress: float, kind: str
) -> Image.Image:
    """Blend *old* → *new* at *progress* (0.0 = all old, 1.0 = all new)."""
    progress = max(0.0, min(1.0, progress))
    if progress >= 1.0 or kind == "none":
        return new
    if progress <= 0.0:
        return old

    fn = _DISPATCH.get(kind, _fade)
    return fn(old, new, progress)


# ── Effects ──────────────────────────────────────────────────


def _fade(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    return Image.blend(old.convert("RGB"), new.convert("RGB"), p)


def _dissolve(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    old_rgb = old.convert("RGB")
    new_rgb = new.convert("RGB")
    threshold = int(p * 255)
    mask = _dissolve_mask(old.size).point(lambda v: 255 if v <= threshold else 0)
    return Image.composite(new_rgb, old_rgb, mask)


def _dissolve_mask(size: tuple[int, int]) -> Image.Image:
    mask = _DISSOLVE_MASKS.get(size)
    if mask is None:
        w, h = size
        data = bytearray(w * h)
        for y in range(h):
            for x in range(w):
                data[y * w + x] = ((x * 73_856_093) ^ (y * 19_349_663)) & 0xFF
        mask = Image.frombytes("L", size, bytes(data))
        _DISSOLVE_MASKS[size] = mask
    return mask


def _zoom_in(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    """New frame grows from center over the old frame."""
    old_rgb = old.convert("RGB")
    new_rgb = new.convert("RGB")
    w, h = old.size
    scale = max(p, 0.01)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    patch = new_rgb.resize((nw, nh), Image.BILINEAR)
    result = old_rgb.copy()
    result.paste(patch, ((w - nw) // 2, (h - nh) // 2))
    return result


def _zoom_out(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    """Old frame shrinks away, revealing the new frame underneath."""
    old_rgb = old.convert("RGB")
    new_rgb = new.convert("RGB")
    w, h = old.size
    scale = max(1.0 - p, 0.01)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    patch = old_rgb.resize((nw, nh), Image.BILINEAR)
    result = new_rgb.copy()
    result.paste(patch, ((w - nw) // 2, (h - nh) // 2))
    return result


def _swipe_left(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    """Old slides out left, new slides in from right."""
    w = old.width
    offset = int(p * w)
    result = Image.new("RGB", old.size, (0, 0, 0))
    result.paste(old.convert("RGB"), (-offset, 0))
    result.paste(new.convert("RGB"), (w - offset, 0))
    return result


def _swipe_right(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    """Old slides out right, new slides in from left."""
    w = old.width
    offset = int(p * w)
    result = Image.new("RGB", old.size, (0, 0, 0))
    result.paste(old.convert("RGB"), (offset, 0))
    result.paste(new.convert("RGB"), (offset - w, 0))
    return result


def _swipe_up(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    """Old slides out up, new slides in from bottom."""
    h = old.height
    offset = int(p * h)
    result = Image.new("RGB", old.size, (0, 0, 0))
    result.paste(old.convert("RGB"), (0, -offset))
    result.paste(new.convert("RGB"), (0, h - offset))
    return result


def _swipe_down(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    """Old slides out down, new slides in from top."""
    h = old.height
    offset = int(p * h)
    result = Image.new("RGB", old.size, (0, 0, 0))
    result.paste(old.convert("RGB"), (0, offset))
    result.paste(new.convert("RGB"), (0, offset - h))
    return result


def _wipe_left(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    w, h = old.size
    reveal = int(p * w)
    result = old.convert("RGB")
    if reveal > 0:
        result.paste(new.convert("RGB").crop((w - reveal, 0, w, h)), (w - reveal, 0))
    return result


def _wipe_right(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    w, h = old.size
    reveal = int(p * w)
    result = old.convert("RGB")
    if reveal > 0:
        result.paste(new.convert("RGB").crop((0, 0, reveal, h)), (0, 0))
    return result


def _wipe_up(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    w, h = old.size
    reveal = int(p * h)
    result = old.convert("RGB")
    if reveal > 0:
        result.paste(new.convert("RGB").crop((0, h - reveal, w, h)), (0, h - reveal))
    return result


def _wipe_down(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    w, h = old.size
    reveal = int(p * h)
    result = old.convert("RGB")
    if reveal > 0:
        result.paste(new.convert("RGB").crop((0, 0, w, reveal)), (0, 0))
    return result


def _iris_circle(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    from PIL import ImageDraw

    w, h = old.size
    radius = int(((w * w + h * h) ** 0.5 / 2) * p)
    cx, cy = w // 2, h // 2
    mask = Image.new("L", old.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=255)
    return Image.composite(new.convert("RGB"), old.convert("RGB"), mask)


def _iris_box(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    w, h = old.size
    rw, rh = int(w * p), int(h * p)
    left = (w - rw) // 2
    top = (h - rh) // 2
    mask = Image.new("L", old.size, 0)
    if rw > 0 and rh > 0:
        mask.paste(255, (left, top, left + rw, top + rh))
    return Image.composite(new.convert("RGB"), old.convert("RGB"), mask)


def _blinds_horizontal(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    w, h = old.size
    stripe_h = 24
    reveal = int(stripe_h * p)
    result = old.convert("RGB")
    new_rgb = new.convert("RGB")
    for y in range(0, h, stripe_h):
        if reveal > 0:
            result.paste(new_rgb.crop((0, y, w, min(y + reveal, h))), (0, y))
    return result


def _blinds_vertical(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    w, h = old.size
    stripe_w = 24
    reveal = int(stripe_w * p)
    result = old.convert("RGB")
    new_rgb = new.convert("RGB")
    for x in range(0, w, stripe_w):
        if reveal > 0:
            result.paste(new_rgb.crop((x, 0, min(x + reveal, w), h)), (x, 0))
    return result


def _checkerboard(old: Image.Image, new: Image.Image, p: float) -> Image.Image:
    w, h = old.size
    cell = 40
    steps = 12
    level = int(p * steps)
    result = old.convert("RGB")
    new_rgb = new.convert("RGB")
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            order = ((x // cell) + (y // cell) * 3) % steps
            if order <= level:
                tile = new_rgb.crop((x, y, min(x + cell, w), min(y + cell, h)))
                result.paste(tile, (x, y))
    return result


_DISPATCH = {
    "none": lambda o, n, p: n,
    "fade": _fade,
    "dissolve": _dissolve,
    "zoom_in": _zoom_in,
    "zoom_out": _zoom_out,
    "swipe_left": _swipe_left,
    "swipe_right": _swipe_right,
    "swipe_up": _swipe_up,
    "swipe_down": _swipe_down,
    "wipe_left": _wipe_left,
    "wipe_right": _wipe_right,
    "wipe_up": _wipe_up,
    "wipe_down": _wipe_down,
    "iris_circle": _iris_circle,
    "iris_box": _iris_box,
    "blinds_horizontal": _blinds_horizontal,
    "blinds_vertical": _blinds_vertical,
    "checkerboard": _checkerboard,
}
