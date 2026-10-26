"""Device registry (`<data>/devices.json`, 0600) and one-time pairing codes. Every device is a screen.

Each device has its own 32-byte secret; only its SHA-256 is stored. A screen carries
`<id>.<secret>` in a cookie. A device is accepted only from the addresses it paired from.
Codes live in `<data>/run/pair/<sha256(code)>` (written by `hub pair` or the Network card),
are single-use and expire after 10 minutes.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import os
import re
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hub.core.api import Device, Invalid
from hub.core.store import read_json, write_json

CODE_TTL_S = 600
_ID = re.compile(r"^d_[a-z0-9]{8}$")


def _hash(secret: str) -> str:
    return "sha256:" + hashlib.sha256(secret.encode()).hexdigest()


def is_loopback(addr: str) -> bool:
    try:
        return ipaddress.ip_address(addr).is_loopback
    except ValueError:
        return False


def check_name(name: Any) -> str:
    if not isinstance(name, str) or not name.strip() or not name.strip().isprintable():
        raise Invalid("name", "Use a name of printable characters, not blank")
    return name.strip()


class Devices:
    """The paired screens, pairing and admin for core and the Network card."""

    def __init__(self, data_dir: Path, on_change: Callable[[], None] = lambda: None) -> None:
        self.path = data_dir / "devices.json"
        self.codes = data_dir / "run" / "pair"
        self.on_change = on_change
        self.sockets: dict[str, set[Any]] = {}
        self._records: list[dict] = self._load()
        self._pending: tuple[int, list[dict]] = (-1, [])

    def _load(self) -> list[dict]:
        raw = read_json(self.path)
        if raw is None:
            return []
        devs = raw.get("devices") if isinstance(raw, dict) else None
        if not isinstance(devs, list):
            raise ValueError(f"{self.path}: must hold a devices list")
        older = any(isinstance(d, dict) and "kind" in d for d in devs)
        if older:  # written before GPU nodes were removed (2026-10-10): keep the screens, without the kind
            devs = [d for d in devs if not isinstance(d, dict) or d.pop("kind", "screen") == "screen"]
        for d in devs:
            ok = (isinstance(d, dict) and isinstance(d.get("id"), str) and _ID.match(d["id"])
                  and isinstance(d.get("name"), str)
                  and isinstance(d.get("addrs"), list) and isinstance(d.get("key_hash"), str))
            if not ok:
                raise ValueError(f"{self.path}: a device entry is incomplete")
        if older:
            write_json(self.path, {"version": 1, "devices": devs})
        return devs

    def _save(self) -> None:
        write_json(self.path, {"version": 1, "devices": self._records})
        self.on_change()

    # ---------------------------------------------------------------- the list
    def online(self, device_id: str) -> bool:
        return bool(self.sockets.get(device_id))

    def records(self) -> list[dict]:
        return [{k: r[k] for k in ("id", "name", "addrs")} for r in self._records]

    def _find(self, device_id: str) -> dict | None:
        return next((r for r in self._records if r["id"] == device_id), None)

    # ---------------------------------------------------------------- auth
    def known_addr(self, addr: str) -> bool:
        return any(addr in r["addrs"] for r in self._records)

    def verify(self, token: str | None) -> Device | None:
        """`<id>.<secret>` -> the device, if the secret matches."""
        if not token or "." not in token:
            return None
        device_id, _, secret = token.partition(".")
        rec = self._find(device_id)
        if rec is None:
            return None
        if not secrets.compare_digest(_hash(secret), rec["key_hash"]):
            return None
        return _device(rec)

    def from_addr(self, device: Device, addr: str) -> bool:
        rec = self._find(device.id)
        return rec is not None and addr in rec["addrs"]

    # ---------------------------------------------------------------- live sockets
    def attach(self, device_id: str, sock: Any) -> None:
        self.sockets.setdefault(device_id, set()).add(sock)

    def detach(self, device_id: str, sock: Any) -> None:
        self.sockets.get(device_id, set()).discard(sock)
        if not self.sockets.get(device_id):
            self.sockets.pop(device_id, None)

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.sockets.items() if v}

    async def disconnect(self, device_id: str) -> None:
        for sock in list(self.sockets.get(device_id, ())):
            try:
                await sock.close(4003)
            except Exception:
                pass

    # ---------------------------------------------------------------- pairing codes
    def mint_code(self, name: str) -> tuple[str, float]:
        name = check_name(name)
        code = secrets.token_hex(16)
        expires = time.time() + CODE_TTL_S
        self.codes.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_json(self.codes / hashlib.sha256(code.encode()).hexdigest(), {"name": name, "expires": expires})
        return code, expires

    def pending(self) -> list[dict]:
        """Outstanding codes: [{name, expires}] (expired ones are deleted)."""
        try:
            stamp = self.codes.stat().st_mtime_ns
        except FileNotFoundError:
            return []
        if stamp != self._pending[0]:
            found = []
            for f in self.codes.iterdir():
                try:
                    rec = read_json(f)
                except (ValueError, OSError):
                    rec = None
                if isinstance(rec, dict) and isinstance(rec.get("expires"), (int, float)):
                    found.append({"name": rec.get("name"), "expires": rec["expires"], "file": f})
            self._pending = (stamp, found)
        now = time.time()
        for rec in self._pending[1]:
            if rec["expires"] <= now:
                rec["file"].unlink(missing_ok=True)
        return [{k: r[k] for k in ("name", "expires")} for r in self._pending[1] if r["expires"] > now]

    def pairing_open(self) -> bool:
        return bool(self.pending())

    def redeem(self, code: str, addr: str) -> tuple[Device, str] | None:
        """Consume a code (single use). Creates, or replaces by name, the device."""
        if not isinstance(code, str) or not 8 <= len(code) <= 64:
            return None
        path = self.codes / hashlib.sha256(code.encode()).hexdigest()
        try:
            rec = read_json(path)
        except (OSError, ValueError):
            return None
        if not isinstance(rec, dict):
            return None
        try:
            os.unlink(path)
        except FileNotFoundError:
            return None
        if not isinstance(rec.get("expires"), (int, float)) or rec["expires"] <= time.time():
            return None
        name = check_name(rec.get("name"))
        secret = secrets.token_urlsafe(32)
        old = next((r for r in self._records if r["name"].lower() == name.lower()), None)
        if old is None:
            old = {"id": "d_" + secrets.token_hex(4), "name": name}
            self._records.append(old)
        old.update(addrs=[addr], key_hash=_hash(secret))
        self._save()
        self._drop(old["id"])
        return _device(old), secret

    # ---------------------------------------------------------------- admin (Network card)
    def rename(self, device_id: str, name: str) -> Device:
        rec = self._find(device_id)
        if rec is None:
            raise Invalid("id", "That device is no longer paired")
        name = check_name(name)
        if any(r["name"].lower() == name.lower() and r is not rec for r in self._records):
            raise Invalid("name", "Another device already has that name")
        rec["name"] = name
        self._save()
        return _device(rec)

    def remove(self, device_id: str, current: str | None) -> None:
        rec = self._find(device_id)
        if rec is None:
            raise Invalid("id", "That device is no longer paired")
        if device_id == current:
            raise Invalid("id", "This is the device you are using")
        if len(self._records) == 1:
            raise Invalid("id", "The last screen cannot be removed")
        self._records.remove(rec)
        self._save()
        self._drop(device_id)

    def _drop(self, device_id: str) -> None:
        """Close the device's open sockets (its old secret no longer counts)."""
        if self.sockets.get(device_id):
            asyncio.get_running_loop().create_task(self.disconnect(device_id))


def _device(rec: dict) -> Device:
    return Device(id=rec["id"], name=rec["name"], addrs=tuple(rec["addrs"]))
