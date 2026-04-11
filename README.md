# TURZX — Dashboard for the TURZX 2.8" USB Screen

<p align="center">
  <em>Cross-platform system monitor &amp; visual editor for the 480×480 round USB display</em>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a> •
  <a href="#editor">Visual Editor</a> •
  <a href="#display-modes">Display Modes</a> •
  <a href="#sensors">Sensors</a> •
  <a href="#linux-setup">Linux Setup</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#license">License</a>
</p>

---

## What is this?

TURZX is an open-source driver and dashboard for the **TURZX 2.8" round USB screen** (480×480 px). The official software is closed-source and Windows-only; this project replaces it with a cross-platform Python application that includes:

- A **system tray daemon** that renders live sensor data on the screen.
- A **drag-and-drop layout editor** to design what the screen displays.
- **Three display modes**: static, rotative (cycle layouts on a timer), and reactive (switch layout by foreground application).
- A fully reverse-engineered **USB protocol** (DES-CBC encrypted, documented in [`DEVLOG.md`](DEVLOG.md)).

> **Device info:** VID `0x1CBE`, PID `0x0028`, firmware `turzx_0001_0024`, 480×480 px, USB 2.0 Bulk.

## Features

- **Real-time system monitoring** — CPU (with turbo frequency), GPU (NVIDIA), RAM, disk, network, battery, uptime, clock, and game FPS via RTSS.
- **Visual layout editor** — Drag-and-drop canvas that renders pixel-perfect with Pillow (same pipeline as the device). Font selection, color picker, gradients, stroke, arc/linear bars, z-order, layer locking.
- **Backgrounds** — Solid color, image, or looping video (MP4/AVI/MKV via OpenCV). Crop and position controls.
- **Display modes** — Static (fixed layout), rotative (cycle with transitions), reactive (auto-switch by foreground app).
- **Transitions** — Fade, swipe left/right/up/down between layouts.
- **Unit conversion** — Display sensor values in your preferred unit (GHz↔MHz, °C↔°F, GB↔MB, etc.).
- **Foreground app detection** — Knows which program is active (Windows: ctypes, Linux: xdotool).
- **Cross-platform** — Windows and Linux. macOS untested but structurally compatible.

## Requirements

- **Python** ≥ 3.10
- **TURZX 2.8" USB screen** connected via USB
- **libusb** (Linux: system package; Windows: bundled via `pip install libusb` or Zadig)

## Installation

### Windows

```bash
# Clone the repository
git clone https://github.com/YOUR_USER/turzx.git
cd turzx

# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install (with NVIDIA GPU support)
pip install -e ".[gpu]"

# Or with video background support too
pip install -e ".[gpu,video]"
```

> **Note:** If the device is not detected, you may need to install a WinUSB/libusb driver via [Zadig](https://zadig.akeo.ie/) or `pip install libusb`.

### Linux (Arch / Manjaro)

```bash
# System dependencies
sudo pacman -S libusb python-pyusb python-pillow python-pycryptodome python-psutil pyside6

# Clone and install
git clone https://github.com/YOUR_USER/turzx.git
cd turzx
python -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -e ".[gpu]"
```

### Linux (Debian / Ubuntu)

```bash
sudo apt install libusb-1.0-0-dev python3-venv
git clone https://github.com/YOUR_USER/turzx.git
cd turzx
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[gpu]"
```

### Optional dependencies

| Extra | Command | What it adds |
|---|---|---|
| `gpu` | `pip install -e ".[gpu]"` | NVIDIA GPU sensors (pynvml) |
| `video` | `pip install -e ".[video]"` | Video backgrounds (opencv-python) |
| `dev` | `pip install -e ".[dev]"` | IPython + pynvml for development |

## Usage

```bash
# Run the daemon (system tray icon appears)
python -m turzx

# Or, if installed via pip:
turzx
```

The application starts minimized in the **system tray**. Right-click the tray icon for:

| Action | Description |
|---|---|
| **Settings** | Open the layout editor |
| **Start / Pause** | Start or pause rendering to the device |
| **Pause Mode** | Pause auto-switching (rotative/reactive modes only) |
| **Quit** | Stop daemon and exit |

## Editor

The visual editor is a three-panel window:

- **Left panel** — Layout selector, add elements (text, sensor, image, bar, arc bar), display mode configuration, screen FPS and sensor update rate.
- **Center panel** — 480×480 drag-and-drop canvas. Shows the real PIL render (pixel-perfect to what the device displays). Elements are transparent proxies for selection and dragging.
- **Right panel** — Properties for the selected element: position, size, font, color, gradient, stroke, sensor ID, format string, unit conversion, anchor point.

### Element types

| Type | Description |
|---|---|
| `text` | Static text label |
| `sensor` | Live sensor value with format string (e.g. `{label}: {value}{unit}`) |
| `image` | PNG/JPG image overlay |
| `bar` | Linear progress bar (4 directions: right, left, up, down) |
| `arc_bar` | Circular arc progress bar |

### Backgrounds

- **Solid color** — Any RGB color.
- **Image** — PNG, JPG, BMP, GIF. Supports crop and position offsets.
- **Video** — MP4, AVI, MKV, WEBM. Loops automatically. First frame shown in editor. Requires `opencv-python`.

## Display Modes

| Mode | Behavior |
|---|---|
| **Static** | User picks one layout — it stays until changed manually. |
| **Rotative** | Cycles through selected layouts on a configurable timer (5–600 s). Supports transitions. |
| **Reactive** | Switches layout automatically based on the foreground application (e.g. `game.exe` → gaming layout). Falls back to a default layout. |

### Transitions (rotative & reactive)

`fade` · `swipe_left` · `swipe_right` · `swipe_up` · `swipe_down` · `none`

Configurable duration (0.1–3.0 s).

## Sensors

26 sensors available across 8 backends:

| Backend | Sensors | Platform |
|---|---|---|
| **CPU** | `cpu.percent`, `cpu.freq_ghz`, `cpu.freq_mhz`, `cpu.base_mhz`, `cpu.cores`, `cpu.temp` | All (turbo freq: Windows PDH; temp: Windows MAHM / Linux coretemp) |
| **Memory** | `mem.percent`, `mem.used_gb`, `mem.total_gb` | All |
| **Disk** | `disk.percent`, `disk.used_gb`, `disk.total_gb` | All |
| **Network** | `net.down_mbps`, `net.up_mbps` | All |
| **GPU** | `gpu.name`, `gpu.percent`, `gpu.temp`, `gpu.mem_gb`, `gpu.mem_total_gb`, `gpu.mem_percent`, `gpu.clock_mhz`, `gpu.mem_clock_mhz`, `gpu.fan`, `gpu.power_w` | NVIDIA (pynvml) |
| **System** | `sys.uptime_h`, `sys.clock`, `sys.date`, `sys.battery` | All |
| **Foreground** | `app.process`, `app.window_title` | Windows (ctypes); Linux partial (xdotool, X11) |
| **FPS** | `fps.current` | Windows (RTSS / MSI Afterburner shared memory) |

> `sys.clock` and `sys.date` are real-time sensors — they update every frame, not at the sensor poll rate.

## Linux Setup

### USB permissions (udev rule)

Without this rule, root access would be needed to communicate with the device:

```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="1cbe", ATTR{idProduct}=="0028", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/99-turzx.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### Platform notes

| Feature | Linux status |
|---|---|
| USB device | ✅ libusb (system package) |
| Config directory | ✅ `$XDG_CONFIG_HOME/turzx/` |
| CPU temp | ✅ `psutil.sensors_temperatures()` (coretemp / k10temp) |
| CPU turbo freq | ⚠️ Fallback to `psutil.cpu_freq()` (no PDH on Linux) |
| GPU (NVIDIA) | ✅ pynvml (requires NVIDIA driver) |
| Foreground app | ⚠️ X11 only (xdotool); Wayland not yet supported |
| FPS sensor | ❌ RTSS is Windows-only |
| System tray | ⚠️ GNOME requires [AppIndicator extension](https://extensions.gnome.org/extension/615/appindicator-support/) |

## Architecture

```
turzx/
├── protocol.py        # DES-CBC encryption, packet building (pure, no I/O)
├── device.py          # USB I/O: connect, send commands, send images
├── images.py          # Pillow helpers: JPEG encode, rotation, solid/test_pattern
├── config.py          # Layout/ModeConfig dataclasses, JSON persistence
├── renderer.py        # Two-layer compositor: video background + sensor overlay → PIL Image
├── daemon.py          # Main entry: Qt event loop, QThread render loop, device lifecycle
├── tray.py            # QSystemTrayIcon with context menu
├── modes.py           # ModeController: static / rotative / reactive switching
├── transitions.py     # Frame-to-frame transition effects (PIL)
├── i18n.py            # Translation stub (prepared for future l10n)
├── sensors/
│   ├── base.py        # SensorBackend ABC, SensorManager aggregator
│   ├── cpu.py         # CPU usage, turbo frequency (PDH), temperature (MAHM)
│   ├── gpu.py         # NVIDIA GPU metrics (pynvml)
│   ├── memory.py      # RAM usage
│   ├── disk.py        # Disk usage
│   ├── network.py     # Network throughput (delta-based)
│   ├── system.py      # Uptime, clock, date, battery
│   ├── foreground.py  # Active window title & process name
│   ├── fps.py         # Game FPS via RTSS shared memory
│   └── units.py       # Unit conversion tables
└── ui/
    ├── main_window.py # Three-panel config window (editor + properties + layout list)
    ├── editor.py       # QGraphicsScene canvas, drag-and-drop, layer lock
    └── preview.py      # (Legacy — unused, kept for reference)
```

### Render pipeline

```
Sensor poll (every 1-5s)          Video advance (60 fps)
        │                                 │
        ▼                                 ▼
  update_overlay()                 next video frame
  (text, sensors, bars → RGBA)    (or cached frame)
        │                                 │
        └──────────┬──────────────────────┘
                   ▼
            compose frame (bg + overlay + real-time clock)
                   │
                   ▼
             to_jpeg(rotate=180°)
                   │
                   ▼
         USB bulk write (CMD 101 SEND_JPEG)
```

### Protocol summary

The device uses a proprietary encrypted USB protocol (fully reverse-engineered from the official C# application):

- **Encryption:** DES-CBC, key = IV = `b"slv3tuzx"`, PKCS7 padding (500 → 504 bytes)
- **Packet:** 504 encrypted bytes + 6 zero bytes + `0xA1` + `0x1A` = 512 bytes
- **Image:** 512-byte encrypted header (CMD 101) + raw JPEG payload
- **Panel rotation:** Physically mounted 180° inverted — corrected in software
- **Working sequence:** `SET_DATETIME(2)` → `PREPARE` → `SEND_JPEG` → … → `SET_DATETIME(0)` → `COMMIT`

Full protocol documentation and development history: [`DEVLOG.md`](DEVLOG.md)

## Known Limitations

- **Device firmware freeze:** Sending more than ~5-6 commands rapidly can lock the firmware. Only recoverable via physical USB replug. The daemon uses a minimal init sequence to avoid this.
- **NVIDIA GPUs only:** AMD/Intel GPU monitoring is not implemented (stubs exist).
- **FPS sensor (Windows only):** Requires [MSI Afterburner](https://www.msi.com/Landing/afterburner) with RTSS running.
- **Wayland:** Foreground app detection requires X11 (xdotool). Wayland support is planned.
- **Single device:** Only one TURZX screen is supported at a time.

## Development

```bash
pip install -e ".[dev,gpu,video]"
python -m turzx
```

The full development history, protocol reverse-engineering notes, hardware quirks, and bug analysis are documented in [`DEVLOG.md`](DEVLOG.md).

## Third-party Licenses

TURZX depends on the following open-source libraries:

| Library | License |
|---|---|
| [PySide6](https://pyside.org) | LGPL-3.0 |
| [pyusb](https://pyusb.github.io/pyusb) | BSD-3-Clause |
| [pycryptodome](https://www.pycryptodome.org) | BSD-2-Clause / Public Domain |
| [Pillow](https://python-pillow.github.io) | MIT-CMU (HPND) |
| [psutil](https://github.com/giampaolo/psutil) | BSD-3-Clause |
| [pynvml](https://github.com/gpuopenanalytics/pynvml) | BSD-3-Clause |
| [opencv-python](https://github.com/opencv/opencv-python) | Apache-2.0 |

## License

This project is licensed under the [MIT License](LICENSE).
