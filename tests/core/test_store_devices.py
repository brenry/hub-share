"""JSON documents (debounced atomic writes) and the device registry with one-time pairing codes."""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from hub.core import store
from hub.core.api import Invalid
from hub.core.devices import Devices
from hub.core.store import JsonDoc, Store


async def test_jsondoc_debounces_and_flushes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "DEBOUNCE_S", 0.05)
    path = tmp_path / "m" / "doc.json"
    doc = JsonDoc(path, {"a": 1})
    assert doc.get() == {"a": 1} and not path.exists()
    copy = doc.get()
    copy["a"] = 99
    assert doc.get() == {"a": 1}
    for i in range(5):
        doc.patch({"b": i})
    assert not path.exists()
    await asyncio.sleep(0.2)
    assert json.loads(path.read_text()) == {"a": 1, "b": 4}
    assert os.stat(path).st_mode & 0o777 == 0o600
    doc.replace({"z": 1})
    doc.flush()
    assert json.loads(path.read_text()) == {"z": 1}
    await asyncio.sleep(0.2)
    assert json.loads(path.read_text()) == {"z": 1}


def test_an_older_write_never_lands_after_a_newer_one(tmp_path: Path) -> None:
    doc = JsonDoc(tmp_path / "d.json", {})
    doc._write({"v": 2}, 2)
    doc._write({"v": 1}, 1)
    assert json.loads((tmp_path / "d.json").read_text()) == {"v": 2}


def test_store_reuses_documents_and_rejects_bad_files(tmp_path: Path) -> None:
    s = Store()
    assert s.doc(tmp_path / "x.json", {}) is s.doc(tmp_path / "x.json", {"other": 1})
    (tmp_path / "bad.json").write_text("[1,2]")
    with pytest.raises(ValueError, match="JSON object"):
        JsonDoc(tmp_path / "bad.json", {})


def test_pairing_codes_are_single_use_and_store_only_a_hash(tmp_path: Path) -> None:
    devs = Devices(tmp_path)
    code, expires = devs.mint_code("Desktop")
    assert expires > time.time() + 590 and devs.pairing_open()
    assert devs.pending() == [{"name": "Desktop", "expires": expires}]
    assert code not in "".join(p.name for p in (tmp_path / "run" / "pair").iterdir())
    device, secret = devs.redeem(code, "192.0.2.8") or (None, "")
    assert device is not None and device.id.startswith("d_")
    assert devs.redeem(code, "192.0.2.8") is None
    assert not devs.pairing_open()
    raw = (tmp_path / "devices.json").read_text()
    assert secret not in raw and "sha256:" in raw
    assert os.stat(tmp_path / "devices.json").st_mode & 0o777 == 0o600
    assert Devices(tmp_path).records() == [{"id": device.id, "name": "Desktop", "addrs": ["192.0.2.8"]}]


def test_verify_checks_secret_and_address(tmp_path: Path) -> None:
    devs = Devices(tmp_path)
    code, _ = devs.mint_code("Desk")
    device, secret = devs.redeem(code, "192.0.2.8")  # type: ignore[misc]
    token = f"{device.id}.{secret}"
    assert devs.verify(token) == device
    assert devs.verify(token[:-1] + ("A" if token[-1] != "A" else "B")) is None
    assert devs.verify(None) is None and devs.verify("nodot") is None
    assert devs.from_addr(device, "192.0.2.8") and not devs.from_addr(device, "192.0.2.9")
    assert devs.known_addr("192.0.2.8") and not devs.known_addr("192.0.2.9")


def test_expired_codes_are_refused_and_cleared(tmp_path: Path) -> None:
    devs = Devices(tmp_path)
    code, _ = devs.mint_code("Laptop")
    f = next((tmp_path / "run" / "pair").iterdir())
    rec = json.loads(f.read_text())
    rec["expires"] = time.time() - 1
    f.write_text(json.dumps(rec))
    assert devs.pending() == []
    assert not f.exists()
    code, _ = devs.mint_code("Laptop")
    f = next((tmp_path / "run" / "pair").iterdir())
    f.write_text(json.dumps({**json.loads(f.read_text()), "expires": time.time() - 1}))
    assert devs.redeem(code, "192.0.2.1") is None


def test_re_pairing_by_name_keeps_the_id_and_replaces_secret_and_address(tmp_path: Path) -> None:
    devs = Devices(tmp_path)
    d1, s1 = devs.redeem(devs.mint_code("Desk")[0], "192.0.2.8")  # type: ignore[misc]
    d2, s2 = devs.redeem(devs.mint_code("desk")[0], "192.0.2.9")  # type: ignore[misc]
    assert d1.id == d2.id and s1 != s2 and d2.addrs == ("192.0.2.9",)
    assert devs.verify(f"{d1.id}.{s1}") is None and devs.verify(f"{d2.id}.{s2}") == d2
    assert [d["id"] for d in devs.records()] == [d1.id]


def test_rename_and_remove_rules(tmp_path: Path) -> None:
    devs = Devices(tmp_path)
    a, _ = devs.redeem(devs.mint_code("Desk")[0], "192.0.2.8")  # type: ignore[misc]
    b, _ = devs.redeem(devs.mint_code("Laptop")[0], "192.0.2.9")  # type: ignore[misc]
    with pytest.raises(Invalid, match="already has"):
        devs.rename(b.id, "DESK")
    for bad in ("  ", "a\nb"):
        with pytest.raises(Invalid, match="Use a name of printable characters, not blank"):
            devs.rename(b.id, bad)
    assert devs.rename(b.id, "x" * 41).name == "x" * 41, "no length of the Hub's on a device's name"
    assert devs.rename(b.id, " Tablet ").name == "Tablet"
    with pytest.raises(Invalid, match="you are using"):
        devs.remove(a.id, current=a.id)
    devs.remove(b.id, current=a.id)
    with pytest.raises(Invalid, match="last screen"):
        devs.remove(a.id, current=None)
    with pytest.raises(Invalid, match="no longer paired"):
        devs.remove("d_00000000", current=None)


def test_a_damaged_registry_stops_with_one_line(tmp_path: Path) -> None:
    (tmp_path / "devices.json").write_text(json.dumps({"devices": [{"id": "x"}]}))
    with pytest.raises(ValueError, match="incomplete"):
        Devices(tmp_path)


def test_a_registry_from_before_gpu_nodes_were_removed_keeps_only_the_screens(tmp_path: Path) -> None:
    screen = {"id": "d_aaaaaaaa", "name": "Desk", "kind": "screen", "addrs": ["192.0.2.8"], "key_hash": "sha256:x"}
    gpu = {"id": "n_bbbbbbbb", "name": "Desk", "kind": "node", "addrs": ["192.0.2.8"], "key_hash": "sha256:y"}
    (tmp_path / "devices.json").write_text(json.dumps({"version": 1, "devices": [screen, gpu]}))
    assert Devices(tmp_path).records() == [{"id": "d_aaaaaaaa", "name": "Desk", "addrs": ["192.0.2.8"]}]
    saved = json.loads((tmp_path / "devices.json").read_text())["devices"]
    assert saved == [{"id": "d_aaaaaaaa", "name": "Desk", "addrs": ["192.0.2.8"], "key_hash": "sha256:x"}]
