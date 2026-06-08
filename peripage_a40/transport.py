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

# Printer control sequences (Peripage 10ff.. family).
RESET = bytes.fromhex("10fffe01" + "00" * 12)
BATTERY_QUERY = bytes.fromhex("10ff50f1")


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

    def ask(self, data: bytes, recv_size: int = 64,
            reply_timeout: float = 3.0) -> bytes:
        """Send a query and return the printer's reply bytes."""
        if self.sock is None:
            raise TransportError("not connected")
        self.sock.sendall(data)
        prev = self.sock.gettimeout()
        self.sock.settimeout(reply_timeout)
        try:
            return self.sock.recv(recv_size)
        except (socket.timeout, TimeoutError) as e:
            raise TransportError("no reply from printer") from e
        finally:
            try:
                self.sock.settimeout(prev)
            except OSError:
                pass

    def reset(self) -> None:
        """Init sequence the printer needs after connect before it replies."""
        self.send(RESET)

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


def get_battery(mac: str, channel: int = DEFAULT_CHANNEL,
                connect_timeout: float = 10.0):
    """Return the printer battery percentage (int 0-100).

    Returns ``None`` if the printer connected but gave no readable value.
    Raises ``PrinterAsleep`` if the printer is off/asleep/out of range, or
    ``TransportError`` for other connection failures.

    Protocol: after connect, send the reset/init sequence, then query
    ``10ff50f1``; the printer replies with two bytes ``{0, percent}``.
    """
    t = RfcommTransport(mac, channel=channel, connect_timeout=connect_timeout)
    t.connect()  # raises PrinterAsleep / TransportError if not connectable
    try:
        t.reset()
        time.sleep(0.1)
        resp = t.ask(BATTERY_QUERY, recv_size=16)
    except Exception:
        return None
    finally:
        t.close()
    if len(resp) >= 2 and 0 <= resp[1] <= 100:
        return int(resp[1])
    return None
