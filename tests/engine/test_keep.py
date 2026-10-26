"""The engine never erases a weight file (`hub/worker/keep.py`, Stage 10): the hold, the import-time check of the
engine's `wgp.py`, the worker's open and the page run by hand (`pagerun.py`)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from hub.worker import keep, pagerun
from hub.worker.adapters import upstream
from hub.worker.faults import Unready
from tests.engine.helpers import ENGINE_PYTHON, WORKER, make_engine_root

PAGERUN = WORKER.parent / "pagerun.py"


@pytest.fixture
def weights(tmp_path):
    root = tmp_path / "weights"
    (root / "sub").mkdir(parents=True)
    for name in ("a.safetensors", "sub/b.bin"):
        (root / name).write_bytes(b"w" * 8)
    yield root
    keep.release()


def test_the_hold_keeps_every_noted_file(weights, capsys):
    assert keep.hold([str(weights), str(weights / "missing")]) == 2 and keep.holding()
    a, b = weights / "a.safetensors", weights / "sub" / "b.bin"
    os.remove(a)
    os.unlink(b)
    Path(a).unlink()
    os.rename(a, weights / "c")
    os.replace(weights / "sub" / "b.bin", weights / "d")
    (weights / "new").write_bytes(b"n")
    os.replace(weights / "new", a)                      # written over: kept, and the new file stays where it was
    assert a.read_bytes() == b.read_bytes() == b"w" * 8 and (weights / "new").exists()
    assert not (weights / "c").exists() and not (weights / "d").exists()
    fd = os.open(weights / "sub", os.O_RDONLY)
    try:
        os.unlink("b.bin", dir_fd=fd)
    finally:
        os.close(fd)
    assert b.exists()
    with pytest.raises(OSError):
        shutil.rmtree(weights / "sub")                  # the tree cannot go while a held file is in it
    assert b.exists()
    os.remove(weights / "new")                          # a file the hold did not note is free
    assert not (weights / "new").exists()
    err = capsys.readouterr().err
    assert keep.KEPT.format(a, "remove") in err and keep.KEPT.format(a, "move or replace") in err
    keep.release()
    assert not keep.holding()
    os.remove(a)
    assert not a.exists()


def test_a_downloads_working_files_are_not_held(weights):
    part = weights / ".cache" / "huggingface" / "download" / "big.safetensors.incomplete"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"p")
    (weights / "x.lock").write_bytes(b"")
    assert keep.hold([str(weights)]) == 2, "the two weights alone"
    os.replace(part, weights / "big.safetensors")             # a resumed download lands
    os.remove(weights / "x.lock")
    assert (weights / "big.safetensors").exists() and not (weights / "x.lock").exists()


def test_a_link_to_the_weights_is_held_through(tmp_path, weights):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "ckpts").symlink_to("../weights")
    keep.hold([str(tmp_path / "app" / "ckpts")])
    os.remove(tmp_path / "app" / "ckpts" / "a.safetensors")
    os.remove(weights / "a.safetensors")
    assert (weights / "a.safetensors").exists()


def test_removals_names_what_the_hold_cannot_catch():
    caught = ("import os, shutil\nfrom pathlib import Path\nfrom shutil import rmtree\nfor p in ['x']:\n"
              "    if p:\n        os.remove(p)\n    os.replace(p, p)\nPath('x').unlink()\nrmtree('t')\n"
              "def later():\n    from os import remove\n    remove('x')\n")
    assert keep.removals(caught) == []
    assert keep.removals("from os import remove as rm\nfor p in []:\n    rm(p)\n") == [], "bound while held"
    assert keep.removals("from trashlib import delete as rm\nfor p in []:\n    rm(p)\n") == ["rm at line 3"]
    assert keep.removals("from send2trash import send2trash\nsend2trash('x')\n") == ["send2trash at line 2"]
    assert keep.removals("import send2trash as s2t\nimport os\nname = 'a'.replace('a', 'b')\nos.replace('a', 'b')\n"
                         "s2t.send2trash('x')\n") == ["s2t.send2trash at line 5"]


def test_upstream_refuses_an_engine_whose_start_could_erase_past_the_hold(tmp_path):
    root = make_engine_root(tmp_path, "upstream", h3=True)
    upstream.Upstream().prepare(str(root))
    with (root / "wgp.py").open("a", encoding="utf-8") as f:
        f.write("\nfrom send2trash import send2trash as unlink\nfor _p in []:\n    unlink(_p)\n")
    lines = (root / "wgp.py").read_text().count("\n")
    with pytest.raises(Unready) as err:
        upstream.Upstream().prepare(str(root))
    assert str(err.value) == upstream.UNHELD.format(f"unlink at line {lines}")


def deprecated_root(tmp_path: Path) -> tuple[Path, Path]:
    """A fake engine root whose import removes `old.safetensors` from every checkpoint root, and a model folder
    holding that file."""
    root = make_engine_root(tmp_path, "upstream")
    spec = json.loads((root / "fake_engine.json").read_text())
    (root / "fake_engine.json").write_text(json.dumps({**spec, "deprecated": ["old.safetensors"]}))
    models = tmp_path / "models"
    models.mkdir()
    (models / "old.safetensors").write_bytes(b"w")
    return root, models


def test_the_engine_start_erases_nothing_in_the_worker(tmp_path):
    root, models = deprecated_root(tmp_path)
    config = json.loads((root / "wgp_config.json").read_text())
    (root / "wgp_config.json").write_text(json.dumps({**config, "checkpoints_paths": [str(models)]}))
    bare = subprocess.run([ENGINE_PYTHON, "-B", "-c", "import wgp"], cwd=root, capture_output=True, text=True,
                          timeout=60)
    assert bare.returncode == 0 and not (models / "old.safetensors").exists(), "the fake erases it, like upstream"
    (models / "old.safetensors").write_bytes(b"w")
    done = subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--models", str(models),
                           "--dump-catalog", str(tmp_path / "c.json")], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert (models / "old.safetensors").read_bytes() == b"w"
    assert "Kept " in done.stderr and "old.safetensors" in done.stderr


def test_with_no_model_folder_the_configs_folders_are_held(tmp_path):
    """`--dump-engine` and a bare `--check-weights` give no model folder: the engine then searches (and deletes from)
    the folders its config names, so those are held."""
    root, models = deprecated_root(tmp_path)
    config = json.loads((root / "wgp_config.json").read_text())
    (root / "wgp_config.json").write_text(json.dumps({**config, "checkpoints_paths": [str(models)]}))
    assert keep.config_roots(str(root), str(root / "wgp_config.json")) == [str(models)]
    done = subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--dump-catalog",
                           str(tmp_path / "c.json")], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert (models / "old.safetensors").exists() and "Kept " in done.stderr


def test_the_page_run_holds_the_app_configs_roots(tmp_path):
    root, models = deprecated_root(tmp_path)
    config = json.loads((root / "wgp_config.json").read_text())
    (root / "wgp_config.json").write_text(json.dumps({**config, "checkpoints_paths": [str(models), "ckpts"]}))
    assert pagerun.roots(str(root)) == [str(models), str(root / "ckpts")]
    (root / "wgp_config.json").write_text("{}")
    assert pagerun.roots(str(root)) == [str(root / "ckpts")], "upstream's defaults: ckpts, and the app is not held"
    (root / "wgp_config.json").write_text(json.dumps({**config, "checkpoints_paths": [str(models)]}))
    done = subprocess.run([ENGINE_PYTHON, "-B", str(PAGERUN), str(root)], capture_output=True, text=True,
                          timeout=60, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert (models / "old.safetensors").exists() and "Holding 1 weight files" in done.stderr
    assert subprocess.run([ENGINE_PYTHON, "-B", str(PAGERUN), str(tmp_path)], capture_output=True,
                          timeout=60).returncode == 2
