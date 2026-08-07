"""
open_turzx/single_instance.py — Single-instance guard
=====================================================
Ensures only one Open-Turzx process runs per user session.

Uses a named local socket (``QLocalServer``/``QLocalSocket``), the same
mechanism behind QtSingleApplication.  The first process to start owns the
socket and becomes the *primary* instance; any later process detects the
live server, optionally hands off a short message (e.g. "open the settings
window"), and exits.

Why a socket instead of a PID/lock file:
    * A crashed primary leaves no live listener, so the next launch simply
      reclaims the name — no stale-PID heuristics required.
    * The same channel doubles as IPC, so ``--settings`` on an already
      running instance pops up its settings window instead of silently
      dying.

Works headless too: QtNetwork has no display dependency.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

# How long to wait for socket I/O during the short handshake (ms).
_TIMEOUT_MS = 300


def _default_key() -> str:
    """Per-user server name so distinct users never collide on a multi-seat box."""
    try:
        uid = os.getuid()
    except AttributeError:  # pragma: no cover - non-POSIX
        uid = os.environ.get("USERNAME", "user")
    return f"open-turzx-{uid}"


class SingleInstance(QObject):
    """Guard that enforces a single primary instance and relays messages to it.

    Typical use::

        guard = SingleInstance()
        if not guard.try_acquire("open-settings" if want_settings else "ping"):
            sys.exit(0)          # another instance handled it
        guard.message_received.connect(handle_message)

    A :class:`QApplication` (or any ``QCoreApplication``) must already exist
    before calling :meth:`try_acquire`, because the underlying sockets rely on
    the Qt event/notifier machinery.
    """

    #: Emitted in the primary instance with the payload sent by a later launch.
    message_received = Signal(str)

    def __init__(self, key: str | None = None) -> None:
        super().__init__()
        self._key = key or _default_key()
        self._server: QLocalServer | None = None

    @property
    def key(self) -> str:
        return self._key

    def try_acquire(self, payload: str = "") -> bool:
        """Return ``True`` if this process is the primary instance.

        If another instance is already running, send ``payload`` to it (when
        non-empty) and return ``False`` so the caller can exit.
        """
        # 1) Is a primary already listening?  If so, hand off and step aside.
        if self._notify_running(payload):
            return False

        # 2) No live listener.  Clear any socket left over from a crash and
        #    claim the name ourselves.
        QLocalServer.removeServer(self._key)
        if self._listen():
            return True

        # 3) Lost a start-up race: another process grabbed the name between our
        #    probe and our listen().  Hand off to it instead.
        if self._notify_running(payload):
            return False

        # 4) Could neither connect nor listen.  Fail open as primary so the
        #    user is never left without the app over a transient socket error.
        log.warning("Single-instance guard could not bind '%s'; running anyway", self._key)
        return True

    # ── internals ──

    def _listen(self) -> bool:
        server = QLocalServer(self)
        # Restrict the socket to the current user. A filesystem socket (vs. the
        # Linux abstract namespace) is used because removeServer() can reliably
        # clear it after a crash, giving deterministic stale-lock recovery.
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self._key):
            log.debug("listen('%s') failed: %s", self._key, server.errorString())
            return False
        server.newConnection.connect(self._on_new_connection)
        self._server = server
        return True

    def _notify_running(self, payload: str) -> bool:
        """Try to connect to an existing primary; if found, send ``payload``."""
        sock = QLocalSocket()
        sock.connectToServer(self._key)
        if not sock.waitForConnected(_TIMEOUT_MS):
            return False
        try:
            if payload:
                sock.write(payload.encode("utf-8"))
                sock.flush()
                sock.waitForBytesWritten(_TIMEOUT_MS)
        finally:
            sock.disconnectFromServer()
            if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                sock.waitForDisconnected(_TIMEOUT_MS)
        return True

    def _on_new_connection(self) -> None:
        if self._server is None:
            return
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(_TIMEOUT_MS)
        data = bytes(conn.readAll()).decode("utf-8", "ignore").strip()
        conn.disconnectFromServer()
        if data:
            self.message_received.emit(data)
