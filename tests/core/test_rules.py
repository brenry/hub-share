"""Static rules over `hub/`: no HTTP clients, no literal secrets, the import graph, file sizes,
and the installed controller packages compared with the hash-pinned lock."""
from __future__ import annotations

import ast
import os
import re
import sys
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "hub"
BANNED = {"httpx", "httpx2", "httpcore", "httpcore2", "requests", "urllib3", "aiohttp", "truststore",
          "urllib.request", "http.client", "ftplib", "smtplib", "websockets.client",
          "websockets.asyncio.client", "websockets.sync.client"}
TEST_TOOLS = {"pytest", "pluggy", "iniconfig", "packaging", "pygments", "pytest-asyncio", "ruff", "pip",
              "setuptools", "wheel", "hub"}


def py_files() -> list[Path]:
    return sorted(p for p in HUB.rglob("*.py") if "__pycache__" not in p.parts)


def imports(path: Path) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names += [node.module] + [f"{node.module}.{a.name}" for a in node.names]
    return names


def test_no_http_client_imports() -> None:
    bad = [f"{p.relative_to(ROOT)}: {name}" for p in py_files() for name in imports(p)
           if name in BANNED or name.split(".")[0] in {b for b in BANNED if "." not in b}]
    assert bad == []


def test_no_literal_secrets() -> None:
    hexa = re.compile(r"^[0-9a-fA-F]{32,}$")
    b64 = re.compile(r"^[A-Za-z0-9_\-]{32,}$")
    found = []
    for p in py_files():
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value
                mixed = any(c.isupper() for c in v) and any(c.islower() for c in v) and any(c.isdigit() for c in v)
                if hexa.match(v) or (b64.match(v) and mixed):
                    found.append(f"{p.relative_to(ROOT)}: {v[:12]}…")
    assert found == []


def test_modules_import_only_the_api() -> None:
    bad = []
    for p in (HUB / "modules").rglob("*.py"):
        own = f"hub.modules.{p.relative_to(HUB / 'modules').parts[0]}"
        for name in imports(p):
            if name.startswith("hub") and not (name.startswith(("hub.core.api", own)) or name == "hub.core"):
                bad.append(f"{p.relative_to(ROOT)}: {name}")
    assert bad == []


def test_core_never_imports_modules() -> None:
    bad = [f"{p.relative_to(ROOT)}: {n}" for p in [*HUB.glob("*.py"), *(HUB / "core").glob("*.py")]
           for n in imports(p) if n.startswith("hub.modules")]
    assert bad == []


def test_files_stay_small_and_typed() -> None:
    long = [f"{p.relative_to(ROOT)}: {n}" for p in py_files() if (n := len(p.read_text().splitlines())) > 300]
    assert long == []
    missing = [str(p.relative_to(ROOT)) for p in py_files()
               if p.read_text().strip() and "from __future__ import annotations" not in p.read_text()
               and len(p.read_text().splitlines()) > 3]
    assert missing == []


def _lock() -> Path | None:
    path = ROOT / "requirements" / "controller.lock"
    return path if path.is_file() else None


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@pytest.mark.skipif(_lock() is None, reason="requirements/controller.lock is not there yet (P1 creates it)")
def test_installed_packages_match_the_lock_exactly() -> None:
    """The controller venv holds exactly the locked packages (set HUB_VENV to check another venv)."""
    lock: dict[str, str] = {}
    for line in _lock().read_text().splitlines():  # type: ignore[union-attr]
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;\\]+)", line.strip())
        if m:
            lock[_norm(m.group(1))] = m.group(2)
    venv = os.environ.get("HUB_VENV")
    paths = [str(p) for p in Path(venv).glob("lib/python3.*/site-packages")] if venv else sys.path
    installed = {_norm(d.metadata["Name"]): d.version for d in metadata.distributions(path=paths)}
    if not venv:
        installed = {k: v for k, v in installed.items() if k not in {_norm(t) for t in TEST_TOOLS}}
    assert installed == lock


TEXT_NAMES = {"PngInfo", "add_itxt", "add_text"}


def _text_writes(tree: ast.AST) -> list[str]:
    """What in a parsed file could write a PNG text chunk: the PngInfo names, a `pnginfo` keyword, the plugin."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in TEXT_NAMES:
            found.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in TEXT_NAMES:
            found.append(node.attr)
        elif isinstance(node, ast.keyword) and node.arg == "pnginfo":
            found.append("pnginfo=")
        elif isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.endswith("PngImagePlugin")]
        elif isinstance(node, ast.ImportFrom):
            found += [f"{node.module}.{a.name}" for a in node.names
                      if a.name == "PngImagePlugin" or "PngImagePlugin" in (node.module or "")]
    return found


def test_only_pngtext_writes_picture_text() -> None:
    """The one text field a picture may hold is written by `hub/core/pngtext.py` alone (`named.py` decides where);
    `clean.py` names chunk types as bytes only to cut them. Tests are not walked."""
    bad = [f"{p.relative_to(ROOT)}: {name}" for p in py_files() if p != HUB / "core" / "pngtext.py"
           for name in _text_writes(ast.parse(p.read_text(), str(p)))]
    assert bad == []
    sample = ("from PIL import PngImagePlugin\nimport PIL.PngImagePlugin\ni = PngImagePlugin.PngInfo()\n"
              "i.add_text('k', 'v')\ni.add_itxt('k', 'v')\nim.save(p, pnginfo=i)\n")
    assert sorted(_text_writes(ast.parse(sample))) == sorted(
        ["PIL.PngImagePlugin", "PIL.PngImagePlugin", "PngInfo", "add_text", "add_itxt", "pnginfo="])
    assert _text_writes(ast.parse((HUB / "core" / "pngtext.py").read_text())), "the guard sees the one writer"
