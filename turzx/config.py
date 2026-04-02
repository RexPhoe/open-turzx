"""
turzx/config.py — Layout configuration management
==================================================
Layouts are JSON files that define what appears on the screen:
background, text labels, sensor readouts, images — each with
position (x, y), z-order, font, color, and format string.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ── Config directory ──

def _default_config_dir() -> Path:
    """Platform-aware config directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "turzx"


# ── Data models ──

@dataclass
class Background:
    type: str = "solid"  # "solid", "image", "video"
    color: list[int] = field(default_factory=lambda: [15, 15, 25])
    path: str = ""  # for image/video types

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Background:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class LayoutElement:
    type: str = "text"  # "text", "sensor", "image"
    x: int = 0
    y: int = 0
    z: int = 0
    # text
    text: str = ""
    # sensor
    sensor_id: str = ""
    label: str = ""
    format: str = "{label}: {value}{unit}"
    # visual
    font_size: int = 16
    color: list[int] = field(default_factory=lambda: [255, 255, 255])
    anchor: str = "lt"  # PIL text anchor

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> LayoutElement:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Layout:
    name: str = "Default"
    background: Background = field(default_factory=Background)
    refresh_rate: float = 1.0  # frames per second
    elements: list[LayoutElement] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "background": self.background.to_dict(),
            "refresh_rate": self.refresh_rate,
            "elements": [e.to_dict() for e in self.elements],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Layout:
        return cls(
            name=d.get("name", "Untitled"),
            background=Background.from_dict(d.get("background", {})),
            refresh_rate=d.get("refresh_rate", 1.0),
            elements=[LayoutElement.from_dict(e) for e in d.get("elements", [])],
        )


# ── Config manager ──

class ConfigManager:
    """Load, save, and switch between layout configurations."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or _default_config_dir()
        self.layouts_dir = self.config_dir / "layouts"
        self.layouts_dir.mkdir(parents=True, exist_ok=True)

        self._active_name: str = "default"
        self._active: Layout | None = None

        # Ensure default layout exists
        if not (self.layouts_dir / "default.json").exists():
            self.save_layout(default_layout(), "default")

        self._load_active()

    def _load_active(self) -> None:
        self._active = self.load_layout(self._active_name)

    @property
    def active_layout(self) -> Layout:
        if self._active is None:
            self._load_active()
        return self._active  # type: ignore

    def set_active(self, name: str) -> None:
        self._active_name = name
        self._load_active()

    def list_layouts(self) -> list[str]:
        return [p.stem for p in self.layouts_dir.glob("*.json")]

    def load_layout(self, name: str) -> Layout:
        path = self.layouts_dir / f"{name}.json"
        if not path.exists():
            return default_layout()
        with open(path, "r", encoding="utf-8") as f:
            return Layout.from_dict(json.load(f))

    def save_layout(self, layout: Layout, name: str | None = None) -> Path:
        fname = name or layout.name.lower().replace(" ", "_")
        path = self.layouts_dir / f"{fname}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(layout.to_dict(), f, indent=2, ensure_ascii=False)
        return path

    def delete_layout(self, name: str) -> None:
        path = self.layouts_dir / f"{name}.json"
        if path.exists() and name != "default":
            path.unlink()


# ── Default layout ──

def default_layout() -> Layout:
    """Built-in layout: system monitor with key sensors."""
    elements = [
        # Title
        LayoutElement(
            type="text", text="TURZX Monitor", x=240, y=22, z=0,
            font_size=28, color=[0, 255, 180], anchor="mt",
        ),
        # Divider position (rendered by renderer as line)
        LayoutElement(
            type="text", text="______________________________", x=240, y=48, z=0,
            font_size=12, color=[0, 120, 180], anchor="mt",
        ),
        # CPU
        LayoutElement(
            type="sensor", sensor_id="cpu.percent", x=30, y=80, z=1,
            label="CPU", font_size=20, color=[200, 220, 255],
            format="{label}: {value:.0f}{unit}",
        ),
        LayoutElement(
            type="sensor", sensor_id="cpu.freq_ghz", x=300, y=80, z=1,
            label="Freq", font_size=16, color=[140, 160, 200],
            format="{value}{unit}",
        ),
        # RAM
        LayoutElement(
            type="sensor", sensor_id="mem.percent", x=30, y=120, z=1,
            label="RAM", font_size=20, color=[200, 220, 255],
            format="{label}: {value:.0f}{unit}",
        ),
        LayoutElement(
            type="sensor", sensor_id="mem.used_gb", x=300, y=120, z=1,
            label="Used", font_size=16, color=[140, 160, 200],
            format="{value}{unit}",
        ),
        # GPU
        LayoutElement(
            type="sensor", sensor_id="gpu.percent", x=30, y=160, z=1,
            label="GPU", font_size=20, color=[200, 220, 255],
            format="{label}: {value:.0f}{unit}",
        ),
        LayoutElement(
            type="sensor", sensor_id="gpu.temp", x=300, y=160, z=1,
            label="", font_size=16, color=[140, 160, 200],
            format="{value}{unit}",
        ),
        # Disk
        LayoutElement(
            type="sensor", sensor_id="disk.percent", x=30, y=200, z=1,
            label="Disk", font_size=20, color=[200, 220, 255],
            format="{label}: {value:.0f}{unit}",
        ),
        LayoutElement(
            type="sensor", sensor_id="disk.used_gb", x=300, y=200, z=1,
            label="Used", font_size=16, color=[140, 160, 200],
            format="{value}{unit}",
        ),
        # Network
        LayoutElement(
            type="sensor", sensor_id="net.down_mbps", x=30, y=240, z=1,
            label="Down", font_size=18, color=[100, 200, 255],
            format="{label}: {value:.2f} {unit}",
        ),
        LayoutElement(
            type="sensor", sensor_id="net.up_mbps", x=300, y=240, z=1,
            label="Up", font_size=18, color=[100, 200, 255],
            format="{label}: {value:.2f} {unit}",
        ),
        # Uptime
        LayoutElement(
            type="sensor", sensor_id="sys.uptime_h", x=240, y=440, z=0,
            label="Uptime", font_size=14, color=[80, 80, 120],
            format="{label}: {value}{unit}", anchor="mb",
        ),
    ]
    return Layout(
        name="Default",
        background=Background(type="solid", color=[15, 15, 25]),
        refresh_rate=1.0,
        elements=elements,
    )
