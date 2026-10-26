"""`tools/release.py` refuses a stale web/dist or one without every module's tab; the tab is
found as its registry entry, the manifest object holding the module's id and the tab's label."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "release_tool", Path(__file__).resolve().parents[2] / "tools" / "release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


REGISTRY = 'const r={"../modules/x/manifest.ts":{id:`x`,label:`Scripts`,order:30}};'
NO_TAB = "web/dist has no Scripts tab: run cd web && npm run build"


def tree(tmp_path: Path, bundle: str = REGISTRY, manifest: str = 'id="x",\n    ') -> Path:
    (tmp_path / "web/src").mkdir(parents=True)
    (tmp_path / "web/src/main.tsx").write_text("x")
    (tmp_path / "web/index.html").write_text("<html>")
    (tmp_path / "web/dist/assets").mkdir(parents=True)
    (tmp_path / "web/dist/assets/index-abc.js").write_text(bundle)
    (tmp_path / "hub/modules/x").mkdir(parents=True)
    source = f'M = Manifest(\n    {manifest}tab=Tab(label="Scripts", order=30),\n)\n'
    (tmp_path / "hub/modules/x/manifest.py").write_text(source)
    (tmp_path / "web/dist/index.html").write_text("<html>")
    old = (tmp_path / "web/dist/index.html").stat().st_mtime - 100
    for rel in ("web/src/main.tsx", "web/index.html"):
        os.utime(tmp_path / rel, (old, old))
    return tmp_path


def run(monkeypatch: pytest.MonkeyPatch, root: Path) -> list:
    monkeypatch.setattr(release, "ROOT", root)
    monkeypatch.setattr(release, "WHEELS", root / "wheels")
    for f in release.FILES:
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text("x")
    return release.release_files()


def test_a_newer_source_refuses(tmp_path, monkeypatch):
    root = tree(tmp_path)
    (root / "web/src/modules").mkdir()
    newer = root / "web/src/modules/new.ts"
    newer.write_text("y")
    later = (root / "web/dist/index.html").stat().st_mtime + 100
    os.utime(newer, (later, later))
    with pytest.raises(release.ReleaseError) as error:
        run(monkeypatch, root)
    assert str(error.value) == "web/dist is older than web/src/modules/new.ts: run cd web && npm run build"


def test_a_newer_package_json_refuses(tmp_path, monkeypatch):
    root = tree(tmp_path)
    pkg = root / "web/package.json"
    pkg.write_text("{}")
    later = (root / "web/dist/index.html").stat().st_mtime + 100
    os.utime(pkg, (later, later))
    with pytest.raises(release.ReleaseError, match="older than web/package.json: run cd web && npm run build"):
        run(monkeypatch, root)


def test_a_missing_tab_label_refuses(tmp_path, monkeypatch):
    root = tree(tmp_path, bundle='const t={label:"Edit Video"};')
    with pytest.raises(release.ReleaseError) as error:
        run(monkeypatch, root)
    assert str(error.value) == "web/dist has no Scripts tab: run cd web && npm run build"


def test_a_fresh_dist_with_every_tab_passes(tmp_path, monkeypatch):
    root = tree(tmp_path)
    rels = [rel for _, rel in run(monkeypatch, root)]
    assert "web/dist/index.html" in rels
    assert "web/dist/assets/index-abc.js" in rels


def refusal(monkeypatch: pytest.MonkeyPatch, root: Path) -> str:
    with pytest.raises(release.ReleaseError) as error:
        run(monkeypatch, root)
    return str(error.value)


def test_a_label_outside_the_registry_refuses(tmp_path, monkeypatch):
    bundle = 'const h={hoistableScripts:new Map};const m={"aria-label":`Scripts`,label:`Scripts`};'
    assert refusal(monkeypatch, tree(tmp_path, bundle=bundle)) == NO_TAB


@pytest.mark.parametrize("bundle", [
    'const r={a:{id:"x",label:"Scripts",order:30}};',
    "const r={a:{id:'x',label:'Scripts'}};",
    "const r={a:{label:`Scripts`,id:`x`}};",
    'const r={a:{"id":"x","label":"Scripts"}};',
    'const r = { a : { id : `x` , order : 30 , label : `Scripts` } };',
])
def test_the_registry_entry_passes_in_any_quote(tmp_path, monkeypatch, bundle):
    assert "web/dist/index.html" in [rel for _, rel in run(monkeypatch, tree(tmp_path, bundle=bundle))]


def test_another_modules_id_does_not_carry_the_label(tmp_path, monkeypatch):
    assert refusal(monkeypatch, tree(tmp_path, bundle="const r={a:{id:`y`,label:`Scripts`}};")) == NO_TAB


def test_a_tab_without_an_id_refuses(tmp_path, monkeypatch):
    root = tree(tmp_path, manifest="")
    assert refusal(monkeypatch, root) == "hub/modules/x/manifest.py has no id"
