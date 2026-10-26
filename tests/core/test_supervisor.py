"""The worker's TMPDIR is in the Hub's `data/` (`<data>/engine-home/tmp`), so every temp file the
engine writes with `tempfile` (a clip's audio tracks, a padded line for the separator) stays there; the worker empties
it at each start like the outbox, and only that folder, never another TMPDIR."""
from __future__ import annotations

from pathlib import Path

from hub.core.supervisor import make_spawn, worker_env
from hub.worker import wgpconfig


def test_tmpdir_is_under_data(tmp_path: Path):
    data = tmp_path / "data"
    spawn = make_spawn({"python": "/env/bin/python", "root": "/engine"}, data, data / "engine" / "gpu0", "gpu0",
                       "GPU-x", passthrough=False)
    assert spawn.env["TMPDIR"] == str(data / "engine-home" / "tmp")
    assert spawn.env["HOME"] == str(data / "engine-home")
    assert worker_env(tmp_path / "home", "0")["TMPDIR"] == str(tmp_path / "home" / "tmp")


def test_the_worker_empties_its_own_tmp_only(tmp_path: Path, monkeypatch):
    home = tmp_path / "engine-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TMPDIR", str(home / "tmp"))
    assert wgpconfig.own_tmp() == [str(home / "tmp")]
    monkeypatch.setenv("TMPDIR", str(tmp_path / "elsewhere"))
    assert wgpconfig.own_tmp() == [], "a TMPDIR the controller did not set is never emptied"
    monkeypatch.delenv("TMPDIR")
    assert wgpconfig.own_tmp() == []
    shell = tmp_path / "someone"                                   # a login shell's ~/tmp: never the worker's
    monkeypatch.setenv("HOME", str(shell))
    monkeypatch.setenv("TMPDIR", str(shell / "tmp"))
    assert wgpconfig.own_tmp() == []
