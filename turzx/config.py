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

_DEFAULT_LAYOUT_VERSION = 6  # bump when default_layout() changes


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
    type: str = "text"  # "text", "sensor", "image", "shape", "bar", "arc_bar"
    x: int = 0
    y: int = 0
    z: int = 0
    w: int = 0  # width (0 = auto)
    h: int = 0  # height (0 = auto)
    # text
    text: str = ""
    # sensor
    sensor_id: str = ""
    label: str = ""
    format: str = "{label}: {value}{unit}"
    # visual
    font_size: int = 16
    font_family: str = ""  # empty = default system font
    color: list[int] = field(default_factory=lambda: [255, 255, 255])
    anchor: str = "lt"  # PIL text anchor
    # gradient fill (two-color linear gradient on text/shape fill)
    gradient: bool = False
    gradient_color: list[int] = field(default_factory=lambda: [255, 255, 255])
    gradient_angle: int = 0  # degrees: 0=left→right, 90=top→bottom, etc.
    # stroke / border
    stroke_width: int = 0  # 0 = no stroke
    stroke_color: list[int] = field(default_factory=lambda: [0, 0, 0])
    # unit conversion (sensor elements only)
    display_unit: str = ""  # empty = use sensor's native unit
    # shape
    shape: str = "rect"  # "rect", "circle", "ellipse", "line"
    fill_color: list[int] = field(default_factory=lambda: [255, 255, 255])
    fill_alpha: int = 255  # 0-255 fill opacity
    # bar / arc_bar (sensor-linked)
    bar_bg_color: list[int] = field(default_factory=lambda: [40, 40, 60])
    bar_fg_color: list[int] = field(default_factory=lambda: [0, 200, 255])
    bar_fg_gradient: bool = False
    bar_fg_color2: list[int] = field(default_factory=lambda: [255, 80, 80])
    bar_max: float = 100.0  # max value (for percentage sensors = 100)
    bar_thickness: int = 8  # line width for arc, bar height for bar
    bar_direction: str = "right"  # "right", "left", "down", "up"
    bar_start_angle: int = 135  # start angle for arc (degrees, 0=right, CCW)
    bar_sweep_angle: int = 270  # total arc sweep (degrees)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> LayoutElement:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Layout:
    name: str = "Default"
    background: Background = field(default_factory=Background)
    refresh_rate: float = 1.0  # sensor update interval in seconds (e.g. 1.0 = once/sec)
    screen_fps: int = 60  # fixed at 60 FPS for smooth video playback
    rotation: int = 180  # degrees clockwise for device output (0, 90, 180, 270)
    elements: list[LayoutElement] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "_version": _DEFAULT_LAYOUT_VERSION,
            "name": self.name,
            "background": self.background.to_dict(),
            "refresh_rate": self.refresh_rate,
            "screen_fps": self.screen_fps,
            "rotation": self.rotation,
            "elements": [e.to_dict() for e in self.elements],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Layout:
        return cls(
            name=d.get("name", "Untitled"),
            background=Background.from_dict(d.get("background", {})),
            refresh_rate=d.get("refresh_rate", 1.0),
            screen_fps=60,  # always 60 FPS
            rotation=d.get("rotation", 180),
            elements=[LayoutElement.from_dict(e) for e in d.get("elements", [])],
        )


# ── Display mode models ──


@dataclass
class ReactiveRule:
    """Maps a process name to a layout."""

    process: str = ""  # e.g. "LeagueClient.exe"
    layout: str = "default"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ReactiveRule:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RotativeConfig:
    """Settings for rotative mode: cycle through selected layouts."""

    layouts: list[str] = field(default_factory=list)
    interval: int = 30  # seconds between switches
    transition: str = "fade"
    transition_duration: float = 0.5  # seconds

    def to_dict(self) -> dict:
        return {
            "layouts": list(self.layouts),
            "interval": self.interval,
            "transition": self.transition,
            "transition_duration": self.transition_duration,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RotativeConfig:
        return cls(
            layouts=list(d.get("layouts", [])),
            interval=d.get("interval", 30),
            transition=d.get("transition", "fade"),
            transition_duration=d.get("transition_duration", 0.5),
        )


@dataclass
class ReactiveConfig:
    """Settings for reactive mode: switch layout by foreground app."""

    rules: list[ReactiveRule] = field(default_factory=list)
    fallback_layout: str = "default"
    transition: str = "fade"
    transition_duration: float = 0.5  # seconds

    def to_dict(self) -> dict:
        return {
            "rules": [r.to_dict() for r in self.rules],
            "fallback_layout": self.fallback_layout,
            "transition": self.transition,
            "transition_duration": self.transition_duration,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ReactiveConfig:
        return cls(
            rules=[ReactiveRule.from_dict(r) for r in d.get("rules", [])],
            fallback_layout=d.get("fallback_layout", "default"),
            transition=d.get("transition", "fade"),
            transition_duration=d.get("transition_duration", 0.5),
        )


@dataclass
class ModeConfig:
    """Display mode configuration: static, rotative, or reactive."""

    mode: str = "static"  # "static" | "rotative" | "reactive"
    rotative: RotativeConfig = field(default_factory=RotativeConfig)
    reactive: ReactiveConfig = field(default_factory=ReactiveConfig)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "rotative": self.rotative.to_dict(),
            "reactive": self.reactive.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> ModeConfig:
        return cls(
            mode=d.get("mode", "static"),
            rotative=RotativeConfig.from_dict(d.get("rotative", {})),
            reactive=ReactiveConfig.from_dict(d.get("reactive", {})),
        )


class ConfigManager:
    """Load, save, and switch between layout configurations."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or _default_config_dir()
        self.layouts_dir = self.config_dir / "layouts"
        self.layouts_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self.config_dir / "state.json"

        state = self._read_state()
        self._active_name: str = state.get("active_layout", "default")
        self._mode_config: ModeConfig = ModeConfig.from_dict(state.get("mode", {}))
        self._active: Layout | None = None

        # Ensure default layout exists and is up-to-date
        default_path = self.layouts_dir / "default.json"
        need_regen = not default_path.exists()
        if not need_regen:
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("_version", 0) < _DEFAULT_LAYOUT_VERSION:
                    need_regen = True
            except Exception:
                need_regen = True
        if need_regen:
            self.save_layout(default_layout(), "default")

        self._load_active()

    # ── State persistence ──

    def _read_state(self) -> dict:
        """Read full state from state file."""
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_state(self) -> None:
        """Persist active layout and mode config atomically."""
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "active_layout": self._active_name,
                        "mode": self._mode_config.to_dict(),
                    },
                    f,
                    indent=2,
                )
        except Exception:
            pass

    # ── Core API ──

    def _load_active(self) -> None:
        self._active = self.load_layout(self._active_name)

    @property
    def active_layout(self) -> Layout:
        if self._active is None:
            self._load_active()
        return self._active  # type: ignore

    @property
    def active_name(self) -> str:
        return self._active_name

    def set_active(self, name: str) -> None:
        self._active_name = name
        self._write_state()
        self._load_active()

    @property
    def mode_config(self) -> ModeConfig:
        return self._mode_config

    def save_mode_config(self, config: ModeConfig) -> None:
        self._mode_config = config
        self._write_state()

    def list_layouts(self) -> list[str]:
        return sorted(p.stem for p in self.layouts_dir.glob("*.json"))

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
            type="text",
            text="TURZX Monitor",
            x=240,
            y=22,
            z=0,
            font_size=28,
            color=[0, 255, 180],
            anchor="mt",
        ),
        # Divider position (rendered by renderer as line)
        LayoutElement(
            type="text",
            text="______________________________",
            x=240,
            y=48,
            z=0,
            font_size=12,
            color=[0, 120, 180],
            anchor="mt",
        ),
        # CPU
        LayoutElement(
            type="sensor",
            sensor_id="cpu.percent",
            x=30,
            y=80,
            z=1,
            label="CPU",
            font_size=20,
            color=[200, 220, 255],
            format="{label}: {value:.0f}{unit}",
        ),
        LayoutElement(
            type="sensor",
            sensor_id="cpu.freq_ghz",
            x=300,
            y=80,
            z=1,
            label="Freq",
            font_size=16,
            color=[140, 160, 200],
            format="{value}{unit}",
        ),
        # RAM
        LayoutElement(
            type="sensor",
            sensor_id="mem.percent",
            x=30,
            y=120,
            z=1,
            label="RAM",
            font_size=20,
            color=[200, 220, 255],
            format="{label}: {value:.0f}{unit}",
        ),
        LayoutElement(
            type="sensor",
            sensor_id="mem.used_gb",
            x=300,
            y=120,
            z=1,
            label="Used",
            font_size=16,
            color=[140, 160, 200],
            format="{value}{unit}",
        ),
        # GPU
        LayoutElement(
            type="sensor",
            sensor_id="gpu.percent",
            x=30,
            y=160,
            z=1,
            label="GPU",
            font_size=20,
            color=[200, 220, 255],
            format="{label}: {value:.0f}{unit}",
        ),
        LayoutElement(
            type="sensor",
            sensor_id="gpu.temp",
            x=300,
            y=160,
            z=1,
            label="",
            font_size=16,
            color=[140, 160, 200],
            format="{value}{unit}",
        ),
        # GPU clock + VRAM
        LayoutElement(
            type="sensor",
            sensor_id="gpu.clock_mhz",
            x=30,
            y=200,
            z=1,
            label="GPU Clock",
            font_size=16,
            color=[180, 160, 220],
            format="{label}: {value}{unit}",
        ),
        LayoutElement(
            type="sensor",
            sensor_id="gpu.mem_gb",
            x=300,
            y=200,
            z=1,
            label="VRAM",
            font_size=16,
            color=[140, 160, 200],
            format="{label}: {value}{unit}",
        ),
        # Disk
        LayoutElement(
            type="sensor",
            sensor_id="disk.percent",
            x=30,
            y=250,
            z=1,
            label="Disk",
            font_size=20,
            color=[200, 220, 255],
            format="{label}: {value:.0f}{unit}",
        ),
        LayoutElement(
            type="sensor",
            sensor_id="disk.used_gb",
            x=300,
            y=250,
            z=1,
            label="Used",
            font_size=16,
            color=[140, 160, 200],
            format="{value}{unit}",
        ),
        # Network
        LayoutElement(
            type="sensor",
            sensor_id="net.down_mbps",
            x=30,
            y=300,
            z=1,
            label="Down",
            font_size=18,
            color=[100, 200, 255],
            format="{label}: {value:.2f} {unit}",
        ),
        LayoutElement(
            type="sensor",
            sensor_id="net.up_mbps",
            x=300,
            y=300,
            z=1,
            label="Up",
            font_size=18,
            color=[100, 200, 255],
            format="{label}: {value:.2f} {unit}",
        ),
        # GPU power
        LayoutElement(
            type="sensor",
            sensor_id="gpu.power_w",
            x=30,
            y=350,
            z=1,
            label="GPU Power",
            font_size=14,
            color=[180, 140, 200],
            format="{label}: {value}{unit}",
        ),
        # Foreground app
        LayoutElement(
            type="sensor",
            sensor_id="app.process",
            x=240,
            y=400,
            z=0,
            label="App",
            font_size=14,
            color=[100, 100, 140],
            format="{value}",
            anchor="mt",
        ),
        # Uptime
        LayoutElement(
            type="sensor",
            sensor_id="sys.uptime_h",
            x=240,
            y=440,
            z=0,
            label="Uptime",
            font_size=14,
            color=[80, 80, 120],
            format="{label}: {value}{unit}",
            anchor="mb",
        ),
    ]
    return Layout(
        name="Default",
        background=Background(type="solid", color=[15, 15, 25]),
        refresh_rate=1.0,
        screen_fps=60,
        elements=elements,
    )
