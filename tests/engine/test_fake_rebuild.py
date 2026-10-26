"""`tests/engine/fake_engine/rebuild.py`: the fake engine is rebuilt from a capture (`--dump-engine`) plus the
hand-kept overlay, never edited by hand. Round trip: the fake's dump, rebuilt into an empty copy, dumps the same."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.engine.helpers import ENGINE_PYTHON, FAKE_ENGINE, FIXTURES, WORKER, make_engine_root

REBUILD = FAKE_ENGINE / "rebuild.py"
[CAPTURE] = sorted((FIXTURES / "contract").glob("fake-*/engine.json"))
FACTS = ("architecture", "family", "lora_key", "factory")


def rebuild(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(REBUILD), *args], capture_output=True, text=True, timeout=60)


def dump(root: Path, out: Path) -> dict:
    subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--dump-engine", str(out)], check=True,
                   capture_output=True, timeout=60)
    return json.loads(out.read_text())


def set_flavour(root: Path, flavour: str) -> None:
    spec = json.loads((root / "fake_engine.json").read_text())
    (root / "fake_engine.json").write_text(json.dumps({**spec, "flavour": flavour}))


def files(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text() for p in [root / "fake_engine.json", *root.glob("defaults/*")]}


@pytest.mark.parametrize("flavour", ["legacy", "upstream"])
def test_the_fake_round_trips_through_its_own_dump(tmp_path, flavour):
    first = dump(make_engine_root(tmp_path / "a", flavour), tmp_path / "a.json")
    copy = make_engine_root(tmp_path / "b", flavour)
    for path in [copy / "fake_engine.json", *(copy / "defaults").glob("*.json")]:
        path.unlink()                                                     # the copy is rebuilt from the dump alone
    result = rebuild(str(tmp_path / "a.json"), "--into", str(copy))
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    set_flavour(copy, flavour)
    second = dump(copy, tmp_path / "b.json")
    overlay = json.loads((FAKE_ENGINE / "overlay.json").read_text())
    assert set(second["models"]) == set(overlay["keep"].values()) == set(first["models"])
    for model_type, model_id in overlay["keep"].items():
        a, b = first["models"][model_type], second["models"][model_id]
        edit = overlay["edits"].get(model_id, {})
        own = set(edit.get("model", {})) | {"settings"}
        assert {k: a[k] for k in FACTS} == {k: b[k] for k in FACTS}, model_id
        assert {k: v for k, v in a["definition"].items() if k not in own} == {
            k: v for k, v in b["definition"].items() if k not in own}, model_id
        both = (a["settings"], b["settings"], a["definition"]["settings"], b["definition"]["settings"])
        assert len({json.dumps({k: v for k, v in s.items() if k not in edit.get("settings", {})}, sort_keys=True)
                    for s in both}) == 1, model_id
    assert second["generate_video"] == first["generate_video"]
    assert (second["families"], second["primary_settings"]) == (first["families"], first["primary_settings"])
    assert second["catalog"] == first["catalog"], "the catalog the Hub sees is the same"
    again = rebuild(str(tmp_path / "a.json"), "--into", str(copy), "--check")
    assert again.returncode == 1 and again.stdout.split() == ["fake_engine.json"], "only the flavour switch differs"


def test_the_checked_in_fake_is_the_rebuild_of_its_capture(tmp_path):
    result = rebuild(str(CAPTURE), "--check")
    assert (result.returncode, result.stdout, result.stderr) == (0, "", ""), "fake_engine.json or defaults/ edited"
    copy = make_engine_root(tmp_path)
    (copy / "fake_engine.json").write_text((FAKE_ENGINE / "fake_engine.json").read_text())
    spec = json.loads((copy / "defaults" / "z_image.json").read_text())
    (copy / "defaults" / "z_image.json").write_text(json.dumps({**spec, "num_inference_steps": 9}, indent=1))
    (copy / "defaults" / "stray.json").write_text("{}")
    before = files(copy)
    result = rebuild(str(CAPTURE), "--check", "--into", str(copy))
    assert result.returncode == 1 and result.stdout.split() == ["defaults/stray.json", "defaults/z_image.json"]
    assert files(copy) == before, "--check writes nothing"
    assert rebuild(str(CAPTURE), "--into", str(copy)).returncode == 0
    assert not (copy / "defaults" / "stray.json").exists()
    assert files(copy) == files(FAKE_ENGINE), "rebuilt byte for byte"
    assert rebuild(str(CAPTURE), "--check", "--into", str(copy)).returncode == 0, "a rerun changes no byte"


@pytest.mark.parametrize(("change", "line"), [
    (lambda o: o["keep"].update({"no_such_model": "no_such_model"}),
     "rebuild: overlay keep names no_such_model, which the dump does not hold"),
    (lambda o: o["edits"]["krea2_hidden"].pop("why"), "rebuild: overlay edit for krea2_hidden has no why"),
])
def test_a_bad_overlay_stops_the_tool_with_one_line(tmp_path, change, line):
    copy = make_engine_root(tmp_path)
    overlay = json.loads((copy / "overlay.json").read_text())
    change(overlay)
    (copy / "overlay.json").write_text(json.dumps(overlay))
    before = files(copy)
    result = rebuild(str(CAPTURE), "--into", str(copy))
    assert (result.returncode, result.stdout, result.stderr.splitlines()) == (2, "", [line])
    assert files(copy) == before
