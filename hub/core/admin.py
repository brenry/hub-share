"""Network admin: the server's addresses (read-only), the device registry and pairing links.

Core data, enforced by core; the Network card is only a view over it. The bind addresses change only on the
server terminal (`hub network set|reset`). The port can also be changed from the Assistant card
(`PATCH /api/assistant/port`): it is saved, then the hub restarts on the new port; `hub network reset` on the
server undoes it.
"""
from __future__ import annotations

from collections.abc import Callable

from hub.core.api import CardStatus
from hub.core.devices import Devices
from hub.settings import hosts, link_base


class NetworkAdmin:
    def __init__(self, devices: Devices, settings: Callable[[], dict], port: int, bound: list[str],
                 missing: list[str], set_port: Callable[[int], None] = lambda port: None) -> None:
        self.devices, self.settings, self.port = devices, settings, port
        self.bound, self.missing = list(bound), list(missing)
        self.set_port = set_port

    def server(self) -> dict:
        s = self.settings()
        return {"bind": list(s["server"]["bind"]), "port": self.port, "listening": list(self.bound),
                "missing": list(self.missing), "hosts": sorted(hosts(s, self.port))}

    def view(self, current: str | None) -> dict:
        counts = self.devices.counts()
        devices = [{**d, "connected": counts.get(d["id"], 0), "you": d["id"] == current}
                   for d in self.devices.records()]
        return {"server": self.server(), "devices": devices, "pairing": self.devices.pending()}

    def rename(self, device_id: str, name: str) -> dict:
        d = self.devices.rename(device_id, name)
        return {"id": d.id, "name": d.name}

    def remove(self, device_id: str, current: str | None) -> None:
        self.devices.remove(device_id, current)

    def pair_link(self, name: str) -> dict:
        code, expires = self.devices.mint_code(name)
        return {"link": f"{link_base(self.settings(), self.port)}/pair#c={code}", "expires": expires}

    def card(self) -> tuple[str, CardStatus]:
        if self.missing:
            return f"{self.missing[0]} not found on this server", "error"
        pending = self.devices.pending()
        if pending:
            return f'Pairing open for "{pending[0]["name"]}"', "attention"
        n = sum(1 for d in self.devices.records() if self.devices.online(d["id"]))
        return f"Port {self.port} · {n} device{'' if n == 1 else 's'} connected", "ok"
