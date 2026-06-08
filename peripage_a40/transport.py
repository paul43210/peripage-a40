"""RFCOMM (Bluetooth Classic SPP) transport for the A40 -- pure stdlib.

Uses Python's built-in AF_BLUETOOTH socket, so there is no PyBluez/libbluetooth
dependency. Requires a Linux host whose Python was built with Bluetooth support
and a Classic-capable adapter (the HA box's Sena UD100-G03) in range.
"""
from __future__ import annotations
import socket
import time
import errno


class PrinterAsleep(Exception):
    """Printer is off or asleep (RFCOMM connect refused / host down)."""


class TransportError(Exception):
    pass


DEFAULT_CHANNEL = 1
_ASLEEP_ERRNOS = {errno.EHOSTDOWN, errno.ETIMEDOUT, errno.ECONNREFUSED,
                  getattr(errno, "EHOSTUNREACH", 113), 112}


class RfcommTransport:
    def __init__(self, mac: str, channel: int = DEFAULT_CHANNEL,
                 chunk: int = 180, delay: float = 0.02,
                 connect_timeout: float = 10.0, send_timeout: float = 30.0):
        self.mac = mac
        self.channel = channel
        self.chunk = chunk
        self.delay = delay
        self.connect_timeout = connect_timeout
        self.send_timeout = send_timeout
        self.sock = None

    def connect(self) -> None:
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                          socket.BTPROTO_RFCOMM)
        s.settimeout(self.connect_timeout)
        try:
            s.connect((self.mac, self.channel))
        except (socket.timeout, TimeoutError) as e:
            # On some adapters (e.g. the Sena UD100) an off/asleep printer makes
            # connect() hang to the socket timeout (errno None) instead of
            # refusing fast. Treat that as "asleep", not a transport error.
            s.close()
            raise PrinterAsleep(
                "Printer is off or asleep -- press its power/feed button "
                "to wake it, then try again.") from e
        except OSError as e:
            s.close()
            if e.errno in _ASLEEP_ERRNOS:
                raise PrinterAsleep(
                    "Printer is off or asleep -- press its power/feed button "
                    "to wake it, then try again.") from e
            raise TransportError(f"RFCOMM connect failed: {e}") from e
        s.settimeout(self.send_timeout)
        self.sock = s

    def send(self, data: bytes) -> None:
        if self.sock is None:
            raise TransportError("not connected")
        mv = memoryview(data)
        try:
            for i in range(0, len(mv), self.chunk):
                self.sock.sendall(mv[i:i + self.chunk])
                if self.delay:
                    time.sleep(self.delay)
        except (socket.timeout, TimeoutError) as e:
            raise TransportError(
                "Printer stopped accepting data (out of paper or jammed?).") from e

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()
