"""
turzx/transitions.py — Layout transition effects
=================================================
Pure PIL-based blending functions.  Each receives the old and new
frames (``Image.Image``, same size) and a progress float 0→1,
and returns the blended result.

All operations are cross-platform (Linux/Windows).
"""

from __future__ import annotations

from PIL import Image

# Available transition names (for UI combos)
TRANSITIONS = ["none", "fade", "swipe_left", "swipe_right", "swipe_up", "swipe_down"]


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


_DISPATCH = {
    "none": lambda o, n, p: n,
    "fade": _fade,
    "swipe_left": _swipe_left,
    "swipe_right": _swipe_right,
    "swipe_up": _swipe_up,
    "swipe_down": _swipe_down,
}
