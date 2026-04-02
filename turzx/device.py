"""
turzx/device.py — USB I/O layer (Linux/Arch first, Windows fallback)
=====================================================================
Handles USB connection, read/write, and all high-level commands.
Uses system libusb on Linux — no DLL path required.

Linux setup:
    pacman -S libusb
    # udev rule (run once):
    echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="1cbe", ATTR{idProduct}=="0028", MODE="0666"' \
        | sudo tee /etc/udev/rules.d/99-turzx.rules
    sudo udevadm control --reload-rules && sudo udevadm trigger
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Callable

import usb.backend.libusb1
import usb.core
import usb.util

from .protocol import (
    VID,
    PID,
    EP_OUT,
    EP_IN,
    Response,
    build_command_packet,
    build_image_packet,
    CMD_QUERY,
    CMD_STANDBY,
    CMD_WAKE,
    CMD_BACKLIGHT_MODE,
    CMD_BRIGHTNESS,
    CMD_SET_DATETIME,
    CMD_PREPARE,
    CMD_DEVICE_INFO,
    CMD_SEND_JPEG,
    CMD_SEND_FRAME,
    CMD_CHECK_STATUS,
    CMD_INIT_1,
    CMD_INIT_2,
    CMD_SET_DISPLAY_CONFIG,
    CMD_PRE_STANDBY,
    CMD_SET_RESOLUTION,
    CMD_SEND_IMAGE_ALT,
    CMD_STORAGE_INFO,
)

# ─── Timeouts (ms) ────────────────────────────────────────────────────────

WRITE_TIMEOUT = 5_000
READ_TIMEOUT = 3_000
IMAGE_WRITE_TIMEOUT = 10_000


# ─── Backend detection ───────────────────────────────────────────────────


def _get_backend():
    """
    On Linux: libusb is a system library — discovered automatically.
    On Windows: falls back to searching common libusb DLL locations.
    """
    if sys.platform.startswith("linux"):
        return usb.backend.libusb1.get_backend()

    # Windows fallback: try common locations
    import os

    candidates = [
        # libusb package in venv (pip install libusb)
        os.path.join(
            sys.prefix,
            "Lib",
            "site-packages",
            "libusb",
            "_platform",
            "windows",
            "x86_64",
            "libusb-1.0.dll",
        ),
        # System PATH
        "libusb-1.0.dll",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return usb.backend.libusb1.get_backend(find_library=lambda _: path)
    return usb.backend.libusb1.get_backend()


# ─── TurzxDevice ─────────────────────────────────────────────────────────


class TurzxDevice:
    """
    Low/mid-level interface to the TURZX 2.8" USB screen.

    Usage:
        with TurzxDevice() as dev:
            dev.init_sequence()
            dev.prepare()
            dev.send_frame(jpeg_bytes)   # uses CMD 101
    """

    def __init__(self, vid: int = VID, pid: int = PID, verbose: bool = True):
        self.vid = vid
        self.pid = pid
        self.verbose = verbose
        self._dev = None

    # ── Context manager ──

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    # ── Connection ──

    def connect(self):
        backend = _get_backend()
        dev = usb.core.find(idVendor=self.vid, idProduct=self.pid, backend=backend)
        if dev is None:
            raise RuntimeError(
                f"Device {self.vid:#06x}:{self.pid:#06x} not found.\n"
                "  • Close the official TURZX software if running.\n"
                "  • On Linux: check udev rule and run `sudo udevadm trigger`."
            )
        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except (usb.core.USBError, NotImplementedError):
            pass
        dev.set_configuration()
        usb.util.claim_interface(dev, 0)
        self._dev = dev
        self._log("[connected]")

    def disconnect(self):
        if self._dev:
            try:
                usb.util.release_interface(self._dev, 0)
            except Exception:
                pass
            try:
                usb.util.dispose_resources(self._dev)
            except Exception:
                pass
            self._dev = None
            self._log("[disconnected]")

    # ── Low-level I/O ──

    def drain(self, max_reads: int = 20, timeout: int = 30):
        """Flush pending data from IN endpoint."""
        for _ in range(max_reads):
            try:
                self._dev.read(EP_IN, 512, timeout=timeout)
            except Exception:
                break

    def write(self, data: bytes, timeout: int = WRITE_TIMEOUT) -> int:
        return self._dev.write(EP_OUT, data, timeout=timeout)

    def read(self, timeout: int = READ_TIMEOUT) -> bytes | None:
        try:
            return bytes(self._dev.read(EP_IN, 512, timeout=timeout))
        except usb.core.USBTimeoutError:
            return None

    def transact(
        self,
        data: bytes,
        label: str = "",
        write_timeout: int = WRITE_TIMEOUT,
        read_timeout: int = READ_TIMEOUT,
    ) -> Response | None:
        """Write data, read response, drain after read (matches C# ReadFlush)."""
        try:
            n = self.write(data, timeout=write_timeout)
        except usb.core.USBError as e:
            self._log(f"  [{label}] WRITE ERROR: {e}")
            return None
        raw = self.read(timeout=read_timeout)
        self.drain()  # ReadFlush: clear residual data AFTER read, like C#
        if raw is None:
            self._log(f"  [{label}] wrote {n}B -> READ TIMEOUT")
            return None
        resp = Response(raw)
        self._log(f"  [{label}] {resp}")
        return resp

    # ── Commands ──

    def send_cmd(
        self,
        cmd: int,
        setup: Callable[[bytearray], None] | None = None,
        label: str = "",
        read_timeout: int = READ_TIMEOUT,
    ) -> Response | None:
        pkt = build_command_packet(cmd, setup)
        return self.transact(pkt, label=label or f"CMD{cmd}", read_timeout=read_timeout)

    def send_image(
        self,
        cmd: int,
        jpeg: bytes,
        label: str = "",
        data_len_offset: int = 8,
    ) -> Response | None:
        pkt = build_image_packet(cmd, jpeg, data_len_offset)
        return self.transact(
            pkt, label=label or f"IMG{cmd}", write_timeout=IMAGE_WRITE_TIMEOUT
        )

    # ── High-level operations ──

    def query(self) -> str | None:
        resp = self.send_cmd(CMD_QUERY, label="QUERY")
        if resp and resp.text:
            self._log(f"  -> {resp.text}")
            return resp.text
        return None

    def set_datetime(self, mode: int = 2) -> Response | None:
        now = datetime.now()

        def setup(h):
            h[8] = (now.year >> 8) & 0xFF
            h[9] = now.year & 0xFF
            h[10] = now.month
            h[11] = now.day
            h[12] = now.hour
            h[13] = now.minute
            h[14] = now.second
            h[15] = mode

        return self.send_cmd(CMD_SET_DATETIME, setup, f"SET_DATETIME(mode={mode})")

    def prepare(self) -> Response | None:
        return self.send_cmd(CMD_PREPARE, lambda h: h.__setitem__(8, 0), "PREPARE")

    def commit(self) -> Response | None:
        return self.send_cmd(CMD_INIT_2, label="COMMIT")

    def set_brightness(self, value: int) -> Response | None:
        return self.send_cmd(
            CMD_BRIGHTNESS, lambda h: h.__setitem__(8, value & 0xFF), "BRIGHTNESS"
        )

    def set_backlight(self, on: bool = True) -> Response | None:
        return self.send_cmd(
            CMD_BACKLIGHT_MODE, lambda h: h.__setitem__(8, 2 if on else 0), "BACKLIGHT"
        )

    def set_display_config(
        self,
        brightness: int = 255,
        start_mode: int = 0,
        rotation: int = 0,
        sleep_delay: int = 0,
        offline_mode: int = 0,
    ) -> Response | None:
        def setup(h):
            h[8] = brightness & 0xFF
            h[9] = start_mode & 0xFF
            h[10] = 0
            h[11] = rotation & 0xFF
            h[12] = sleep_delay & 0xFF
            h[13] = offline_mode & 0xFF

        return self.send_cmd(CMD_SET_DISPLAY_CONFIG, setup, "DISPLAY_CONFIG")

    def set_resolution(
        self, width: int = 480, rotation: int = 0, param_a: int = 0, param_b: int = 0
    ) -> Response | None:
        def setup(h):
            h[8] = 0xFF
            h[9] = 0x0F
            h[10] = 0xA1
            h[11] = 0x00
            h[12] = (width >> 8) & 0xFF
            h[13] = width & 0xFF
            h[14] = rotation & 0xFF
            h[15] = param_a & 0xFF
            h[16] = param_b & 0xFF

        return self.send_cmd(CMD_SET_RESOLUTION, setup, "SET_RESOLUTION")

    def wake(self) -> Response | None:
        return self.send_cmd(CMD_WAKE, label="WAKE")

    def standby(self) -> Response | None:
        self.send_cmd(CMD_PRE_STANDBY, label="PRE_STANDBY")
        return self.send_cmd(CMD_STANDBY, label="STANDBY")

    def check_status(self) -> Response | None:
        return self.send_cmd(CMD_CHECK_STATUS, label="CHECK_STATUS")

    def get_device_info(self) -> Response | None:
        return self.send_cmd(CMD_DEVICE_INFO, label="DEVICE_INFO")

    def get_storage_info(self) -> Response | None:
        return self.send_cmd(CMD_STORAGE_INFO, label="STORAGE_INFO")

    def send_frame(self, jpeg: bytes) -> Response | None:
        """Send image using CMD 101 (SEND_JPEG). CMD 102 is accepted but does NOT render."""
        return self.send_image(CMD_SEND_JPEG, jpeg, "FRAME")

    def send_frame_102(self, jpeg: bytes) -> Response | None:
        """CMD 102 — device accepts but does NOT render on this model."""
        return self.send_image(CMD_SEND_FRAME, jpeg, "FRAME_102")

    def send_image_alt(self, jpeg: bytes) -> Response | None:
        return self.send_image(CMD_SEND_IMAGE_ALT, jpeg, "IMG_ALT", data_len_offset=12)

    # ── Composite sequences ──

    def init_sequence(self):
        """Minimal init matching C# _220E: just SET_DATETIME(2)."""
        self._log("\n=== INIT ===")
        self.set_datetime(2)
        time.sleep(0.1)
        self._log("=== INIT DONE ===\n")

    def shutdown(self):
        self.set_datetime(mode=0)
        time.sleep(0.1)
        self.commit()

    # ── Utility ──

    def _log(self, msg: str):
        if self.verbose:
            print(msg)
