"""Worker seatbelt: an audit hook that refuses outbound sockets and name lookups.

Unix sockets (the controller link) and loopback stay allowed. Native code can bypass
audit hooks; the offline environment and the OS firewall remain the wall.
"""
from __future__ import annotations

import ipaddress
import socket
import sys
from typing import Any

_SENDS = ("socket.connect", "socket.sendto", "socket.sendmsg")
_LOOKUPS = ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex")
_REVERSE = ("socket.gethostbyaddr", "socket.getnameinfo")


def _ip(host: Any) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    try:
        return ipaddress.ip_address(str(host).split("%", 1)[0])
    except ValueError:
        return None


def _hook(event: str, args: tuple[Any, ...]) -> None:
    if event in _SENDS:
        sock, address = args[0], args[1]
        if address is None or getattr(sock, "family", None) == socket.AF_UNIX:
            return
        ip = _ip(address[0]) if isinstance(address, tuple) and address else None
        if ip is None or not ip.is_loopback:
            raise PermissionError("Outbound network is blocked in the engine worker")
    elif event in _LOOKUPS and args[0] is not None and _ip(args[0]) is None:
        raise PermissionError("Name lookups are blocked in the engine worker")
    elif event in _REVERSE:
        target = args[0] if event == "socket.getnameinfo" else (args[0],)
        ip = _ip(target[0]) if isinstance(target, tuple) and target else None
        if ip is None or not ip.is_loopback:
            raise PermissionError("Name lookups are blocked in the engine worker")


def install() -> None:
    sys.addaudithook(_hook)
