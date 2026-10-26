"""Runtime seatbelt: no outbound network from this process.

An audit hook (it cannot be removed once installed) refuses connects and datagrams
to anything but Unix sockets and loopback, and refuses name lookups. The OS firewall
stays the wall; this is the seatbelt.
"""
from __future__ import annotations

import ipaddress
import socket
import sys
from typing import Any

_REVERSE = {"socket.gethostbyaddr", "socket.getnameinfo"}
_SENDS = {"socket.connect", "socket.sendto", "socket.sendmsg"}
_installed = False


def _numeric(host: Any) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    try:
        ipaddress.ip_address(str(host).split("%", 1)[0])
    except ValueError:
        return False
    return True


def _loopback(address: Any) -> bool:
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    try:
        return ipaddress.ip_address(str(host).split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _hook(event: str, args: tuple[Any, ...]) -> None:
    if not event.startswith("socket."):
        return
    if event in _SENDS:
        sock, address = args[0], args[1]
        if address is None or getattr(sock, "family", None) == socket.AF_UNIX or _loopback(address):
            return
        raise PermissionError("Outbound network is blocked in the hub")
    if event in ("socket.getaddrinfo", "socket.gethostbyname"):
        if not _numeric(args[0]):
            raise PermissionError("Name lookups are blocked in the hub")
    elif event in _REVERSE:
        target = args[0] if event == "socket.getnameinfo" else (args[0],)
        if not _loopback(target):
            raise PermissionError("Name lookups are blocked in the hub")


def install() -> None:
    """Install the hook once. Safe to call more than once."""
    global _installed
    if not _installed:
        sys.addaudithook(_hook)
        _installed = True
