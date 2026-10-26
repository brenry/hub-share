"""The audit hook blocks outbound sockets and DNS, and still allows loopback and Unix sockets."""
from __future__ import annotations

import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from hub.core import netlock

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = textwrap.dedent("""
    import socket, sys
    from hub.core import netlock
    netlock.install()
    netlock.install()   # idempotent
    results = {}
    def attempt(name, fn):
        try:
            fn()
            results[name] = "allowed"
        except PermissionError:
            results[name] = "blocked"
        except OSError:
            results[name] = "allowed"   # got past the hook; the OS refused (fine)
    attempt("tcp_out", lambda: socket.create_connection(("192.0.2.1", 80), timeout=0.2))
    attempt("dns", lambda: socket.getaddrinfo("example.com", 80))
    attempt("dns_byname", lambda: socket.gethostbyname("example.com"))
    attempt("reverse", lambda: socket.gethostbyaddr("8.8.8.8"))
    attempt("udp_out", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("192.0.2.1", 53)))
    server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen()
    attempt("loopback", lambda: socket.create_connection(server.getsockname(), timeout=1).close())
    attempt("numeric_lookup", lambda: socket.getaddrinfo("127.0.0.1", 80))
    a, b = socket.socketpair(); a.sendall(b"ok"); results["unix"] = "allowed" if b.recv(2) == b"ok" else "?"
    print(results)
""")


def test_hook_blocks_outbound_and_dns_but_not_loopback() -> None:
    out = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    results = eval(out.stdout)  # noqa: S307 - our own dict literal
    assert results["tcp_out"] == "blocked"
    assert results["dns"] == "blocked"
    assert results["dns_byname"] == "blocked"
    assert results["reverse"] == "blocked"
    assert results["udp_out"] == "blocked"
    assert results["loopback"] == "allowed"
    assert results["numeric_lookup"] == "allowed"
    assert results["unix"] == "allowed"


def test_cli_installs_the_hook_first() -> None:
    src = (ROOT / "hub" / "__main__.py").read_text()
    code = [ln for ln in src.splitlines() if ln.strip() and not ln.startswith(("#", '"""', "from __future__"))]
    assert code[0] == "from hub.core import netlock"
    assert code[1] == "netlock.install()"


class FakeSock:
    def __init__(self, family: int) -> None:
        self.family = family


@pytest.mark.parametrize("family, address, blocked", [
    (socket.AF_INET6, ("2001:db8::1", 80, 0, 0), True),
    (socket.AF_INET6, ("::1", 80, 0, 0), False),
    (socket.AF_INET, ("127.0.0.53", 53), False),
    (socket.AF_INET, ("192.168.0.11", 42010), True),
    (socket.AF_UNIX, "/run/user/1000/x.sock", False),
    (socket.AF_INET, None, False),
])
def test_hook_rules(family: int, address: object, blocked: bool) -> None:
    for event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
        if blocked:
            with pytest.raises(PermissionError):
                netlock._hook(event, (FakeSock(family), address))
        else:
            netlock._hook(event, (FakeSock(family), address))
    netlock._hook("open", ("/etc/hostname", "r", 0))
