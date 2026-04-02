"""
turzx/protocol.py — Pure protocol layer (no USB, fully cross-platform)
=======================================================================
All cryptography, packet building, and protocol logic.
No side effects, no USB I/O, easily testable.

Device: TURZX 2.8"  VID=0x1CBE  PID=0x0028  480×480px
"""

from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone
from typing import Callable

from Crypto.Cipher import DES

# ─── Protocol constants ───────────────────────────────────────────────────

VID = 0x1CBE
PID = 0x0028
EP_OUT = 0x01
EP_IN  = 0x81

DES_KEY = DES_IV = b"slv3tuzx"

MAGIC_1   = 0x1A   # header[2]
MAGIC_2   = 0x6D   # header[3]
TRAILER_1 = 0xA1   # frame[510]
TRAILER_2 = 0x1A   # frame[511]

SCREEN_W = 480
SCREEN_H = 480
JPEG_QUALITY = 95

# ─── Command IDs ─────────────────────────────────────────────────────────

CMD_QUERY            = 10
CMD_STANDBY          = 11
CMD_WAKE             = 12
CMD_BACKLIGHT_MODE   = 13   # 0=off, 2=on
CMD_BRIGHTNESS       = 14   # [8]=0-255
CMD_BACKLIGHT_RAW    = 15
CMD_STORAGE_INFO     = 17
CMD_SET_DATETIME     = 51   # [8-15] date+mode
CMD_PREPARE          = 52   # [8]=0
CMD_CONFIG_DATA      = 99
CMD_DEVICE_INFO      = 100
CMD_SEND_JPEG        = 101  # static image
CMD_SEND_FRAME       = 102  # video frame
CMD_FLUSH            = 111
CMD_CHECK_STATUS     = 112
CMD_INIT_1           = 122
CMD_INIT_2           = 123  # commit/finalize
CMD_SET_DISPLAY_CONFIG = 125  # [8-13] brightness/rotation/sleep
CMD_PRE_STANDBY      = 150
CMD_SET_RESOLUTION   = 251  # [8-16] magic+width+params
CMD_SEND_IMAGE_ALT   = 252  # data_len at offset 12 (not 8)

# ─── Crypto ──────────────────────────────────────────────────────────────


def pkcs7_pad(data: bytes) -> bytes:
    n = 8 - (len(data) % 8)
    return data + bytes([n] * n)


def des_cbc_encrypt(plaintext: bytes) -> bytes:
    cipher = DES.new(DES_KEY, DES.MODE_CBC, iv=DES_IV)
    return cipher.encrypt(pkcs7_pad(plaintext))


def des_cbc_decrypt(ciphertext: bytes) -> bytes:
    cipher = DES.new(DES_KEY, DES.MODE_CBC, iv=DES_IV)
    return cipher.decrypt(ciphertext)


# ─── Timestamp ───────────────────────────────────────────────────────────


def get_timestamp_ms() -> int:
    """Milliseconds since yesterday midnight UTC — matches C# _2A72()."""
    now = datetime.now(timezone.utc)
    yesterday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    return int((now - yesterday).total_seconds() * 1000) & 0xFFFFFFFF


# ─── Packet building ─────────────────────────────────────────────────────


def build_header(cmd: int, setup: Callable[[bytearray], None] | None = None) -> bytes:
    """Build 500-byte plaintext header."""
    h = bytearray(500)
    h[0] = cmd
    h[2] = MAGIC_1
    h[3] = MAGIC_2
    h[4:8] = struct.pack("<I", get_timestamp_ms())
    if setup:
        setup(h)
    return bytes(h)


def encrypt_header(plaintext_500: bytes) -> bytes:
    """Encrypt 500-byte header → 512-byte USB frame."""
    encrypted = des_cbc_encrypt(plaintext_500)
    frame = bytearray(512)
    frame[:len(encrypted)] = encrypted
    frame[510] = TRAILER_1
    frame[511] = TRAILER_2
    return bytes(frame)


def build_command_packet(cmd: int, setup: Callable[[bytearray], None] | None = None) -> bytes:
    """Encrypted 512-byte command packet."""
    return encrypt_header(build_header(cmd, setup))


def build_image_packet(cmd: int, jpeg_data: bytes, data_len_offset: int = 8) -> bytes:
    """Encrypted header + raw JPEG. data_len_offset=8 for CMD 101/102, 12 for CMD 252."""
    n = len(jpeg_data)

    def setup(h: bytearray):
        h[data_len_offset]     = (n >> 24) & 0xFF
        h[data_len_offset + 1] = (n >> 16) & 0xFF
        h[data_len_offset + 2] = (n >> 8)  & 0xFF
        h[data_len_offset + 3] =  n        & 0xFF

    return encrypt_header(build_header(cmd, setup)) + jpeg_data


# ─── Response parsing ─────────────────────────────────────────────────────


class Response:
    """Parsed 512-byte USB response (always unencrypted from device)."""

    def __init__(self, raw: bytes | None):
        self.raw = raw
        self.cmd_echo = raw[0]  if raw else 0
        self.status   = raw[1]  if raw else 0
        self.is_ok    = self.status == 0xC8
        self.text     = ""
        if raw and len(raw) > 8:
            tail = raw[8:]
            ni = tail.find(b"\x00")
            if ni > 0:
                self.text = tail[:ni].decode("utf-8", errors="replace")

    def __repr__(self):
        ok = "OK" if self.is_ok else "??"
        return f"[{ok}] cmd={self.cmd_echo} st=0x{self.status:02X} '{self.text}'"

    def __bool__(self):
        return bool(self.raw)

    def dump(self) -> str:
        """Full hex dump of response for debugging."""
        if not self.raw:
            return "(no response)"
        r = self.raw
        lines = [f"  cmd={r[0]} status=0x{r[1]:02X} magic={r[2]:02X}{r[3]:02X}"]
        lines.append(f"  [4-7]  {r[4]:02X} {r[5]:02X} {r[6]:02X} {r[7]:02X}")
        for off in range(8, min(48, len(r)), 4):
            chunk = r[off:off+4]
            be = struct.unpack(">I", chunk)[0]
            lines.append(f"  [{off:2d}-{off+3:2d}] {' '.join(f'{b:02X}' for b in chunk)}  (BE={be})")
        nonzero = [(i, r[i]) for i in range(48, len(r)) if r[i]]
        if nonzero:
            lines.append(f"  non-zero[48+]: {nonzero}")
        return "\n".join(lines)
