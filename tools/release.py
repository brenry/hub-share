"""Build the Hub release zip and keep the hash-pinned locks and offline wheels in step.

    python tools/release.py          verify wheels (download if needed), then write dist/hub-release-<date>-<time>.zip
    python tools/release.py wheels   download and verify the offline wheels only
    python tools/release.py lock     re-resolve requirements/*.lock (needs `uv` on PATH and network)

Every lock is for CPython 3.13 and 3.14 on Linux x86_64. It lists only the hashes of the wheels that ship,
so the wheels folder and the controller lock must agree exactly; the installer installs with --require-hashes.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "requirements"
WHEELS = ROOT / "wheels"
DIST = ROOT / "dist"
TOP_LEVEL = {
    "controller": ("starlette", "uvicorn", "websockets", "nvidia-ml-py", "pillow"),
    "dev": ("pytest", "pytest-asyncio", "ruff"),
}
SHIPPED = ("controller",)
PYTHONS = ("3.13", "3.14")
PLATFORM = "manylinux_2_28_x86_64"
PLATFORMS = [f"manylinux_2_{n}_x86_64" for n in range(28, 4, -1)] + [
    "manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64"]
LIMIT_BYTES = 28 * 1024 * 1024
TREES = ("hub", "web/dist", "install", "deploy")
FILES = ("README-INSTALL.md", "requirements/controller.lock")
REQUIRED = ("web/dist/index.html",)
SKIP_DIRS = {"__pycache__", "tests", "node_modules"}
SKIP_FILE = re.compile(r"(\.py[co]$|^test_.*\.py$|_test\.py$|^conftest\.py$)")
HASH_LINE = re.compile(r"^\s+--hash=sha256:([0-9a-f]{64})")
PIN_LINE = re.compile(r"^([A-Za-z0-9._-]+)==([^\s\\;]+)")
WEB_SOURCES = ("web/index.html", "web/package.json", "web/package-lock.json")
TAB_LABEL = re.compile(r"""Tab\(\s*label\s*=\s*(["'])(.+?)\1""")
MODULE_ID = re.compile(r"""(?<![\w.])id\s*=\s*(["'])(.+?)\1""")
OPENING = re.compile(r"\{[^{}]*")                 # an object's opening brace up to its next brace


def entry(key: str, value: str) -> re.Pattern[str]:
    """`key: <q>value<q>` in an object literal, the key bare or quoted, `<q>` one of " ' ` on both sides."""
    return re.compile(rf"""(?:^|[{{,\s])(["'`]?){key}\1\s*:\s*(["'`]){re.escape(value)}\2(?=\s*[,}}]|\s*$)""")


def registered(assets: list[str], ident: str, label: str) -> bool:
    """Some asset holds the registry's manifest object, `{id: <id>, label: <label>, …}` in either
    order, with no brace between its opening brace and either entry."""
    has_id, has_label = entry("id", ident), entry("label", label)
    return any(has_id.search(seg) and has_label.search(seg)
               for text in assets if label in text for seg in OPENING.findall(text))


class ReleaseError(Exception):
    """A plain-English reason the release cannot be built."""


def run(cmd: list[str], stdin: str | None = None) -> str:
    done = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    if done.returncode != 0:
        raise ReleaseError(f"{cmd[0]} {cmd[1] if len(cmd) > 1 else ''} failed:\n{done.stderr.strip()}")
    return done.stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_flags(python: str) -> list[str]:
    abi = "cp" + python.replace(".", "")
    flags = ["--only-binary=:all:", "--implementation", "cp", "--python-version", python, "--abi", abi]
    for platform in PLATFORMS:
        flags += ["--platform", platform]
    return flags


def pip_download(lock: Path, dest: Path, python: str, offline: bool = False) -> None:
    cmd = [sys.executable, "-m", "pip", "download", "--quiet", "--no-cache-dir", "--disable-pip-version-check",
           "--require-hashes", "-r", str(lock), "-d", str(dest), *target_flags(python)]
    if offline:
        cmd += ["--no-index", "--find-links", str(WHEELS)]
    run(cmd)


def lock_hashes(lock: Path) -> set[str]:
    return {m.group(1) for line in lock.read_text().splitlines() if (m := HASH_LINE.match(line))}


def lock_pins(text: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for line in text.splitlines() if (m := PIN_LINE.match(line))}


def keep_hashes(text: str, keep: set[str]) -> str:
    """Rewrite uv's output so each pin lists only the hashes in `keep`."""
    out: list[str] = []
    pin: str | None = None
    hashes: list[str] = []

    def flush() -> None:
        if pin is None:
            return
        if not hashes:
            raise ReleaseError(f"No Linux x86_64 wheel for CPython {' and '.join(PYTHONS)}: {pin}")
        out.append(f"{pin} \\")
        out.extend(f"    --hash=sha256:{h}" + (" \\" if i < len(hashes) - 1 else "") for i, h in enumerate(hashes))

    for line in text.splitlines():
        if m := PIN_LINE.match(line):
            flush()
            pin, hashes = f"{m.group(1)}=={m.group(2)}", []
        elif m := HASH_LINE.match(line):
            if m.group(1) in keep:
                hashes.append(m.group(1))
        else:
            flush()
            pin = None
            out.append(line)
    flush()
    return "\n".join(out).rstrip("\n") + "\n"


def write_lock(name: str) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise ReleaseError("`lock` needs uv: pip install uv")
    wanted = "\n".join(TOP_LEVEL[name]) + "\n"
    texts = {}
    for python in PYTHONS:
        texts[python] = run([uv, "pip", "compile", "-", "--quiet", "--no-header", "--generate-hashes",
                             "--python-version", python, "--python-platform", "x86_64-manylinux_2_28"], wanted)
    if lock_pins(texts[PYTHONS[0]]) != lock_pins(texts[PYTHONS[1]]):
        raise ReleaseError(f"{name}: CPython {PYTHONS[0]} and {PYTHONS[1]} resolve to different versions")
    with tempfile.TemporaryDirectory() as tmp:
        full = Path(tmp) / "full.lock"
        full.write_text(texts[PYTHONS[0]])
        for python in PYTHONS:
            pip_download(full, Path(tmp) / "w", python)
        keep = {sha256(p) for p in (Path(tmp) / "w").iterdir()}
    header = (f"# Hub {name}: hash-pinned for CPython {' and '.join(PYTHONS)} on Linux x86_64 ({PLATFORM}).\n"
              "# Only the hashes of those wheels are listed. Regenerate: python tools/release.py lock\n")
    (REQ / f"{name}.lock").write_text(header + keep_hashes(texts[PYTHONS[0]], keep))
    print(f"requirements/{name}.lock · {len(lock_pins(texts[PYTHONS[0]]))} packages")


def verify_wheels() -> None:
    allowed = set().union(*(lock_hashes(REQ / f"{name}.lock") for name in SHIPPED))
    present = sorted(WHEELS.iterdir()) if WHEELS.is_dir() else []
    for path in present:
        if path.suffix != ".whl" or sha256(path) not in allowed:
            raise ReleaseError(f"wheels/{path.name} is not in a shipped lock; delete it and run again")
    with tempfile.TemporaryDirectory() as tmp:
        for name in SHIPPED:
            for python in PYTHONS:
                try:
                    pip_download(REQ / f"{name}.lock", Path(tmp) / f"{name}{python}", python, offline=True)
                except ReleaseError as error:
                    raise ReleaseError(f"wheels/ cannot install {name}.lock on CPython {python}:\n{error}") from None
    print(f"wheels/ · {len(present)} wheels · match {' and '.join(SHIPPED)} locks on CPython {', '.join(PYTHONS)}")


def fetch_wheels() -> None:
    WHEELS.mkdir(exist_ok=True)
    for name in SHIPPED:
        for python in PYTHONS:
            pip_download(REQ / f"{name}.lock", WHEELS, python)
    verify_wheels()


def wanted(rel: Path) -> bool:
    parts = rel.parts
    return not any(p in SKIP_DIRS or p.startswith(".") for p in parts) and not SKIP_FILE.search(parts[-1])


def web_fresh(root: Path) -> None:
    """Refuse a web/dist older than its sources, or one that lacks a module's tab, found as
    its registry entry."""
    built = (root / "web/dist/index.html").stat().st_mtime
    sources = [p for p in (root / "web/src").rglob("*") if p.is_file()]
    sources += [root / f for f in WEB_SOURCES if (root / f).is_file()]
    newest = max(sources, key=lambda p: p.stat().st_mtime, default=None)
    if newest is not None and newest.stat().st_mtime > built:
        rel = newest.relative_to(root).as_posix()
        raise ReleaseError(f"web/dist is older than {rel}: run cd web && npm run build")
    assets = [p.read_text(errors="replace") for p in (root / "web/dist/assets").rglob("*") if p.is_file()]
    for manifest in sorted((root / "hub/modules").glob("*/manifest.py")):
        source = manifest.read_text()
        for match in TAB_LABEL.finditer(source):
            ident = MODULE_ID.search(source)
            if ident is None:
                raise ReleaseError(f"{manifest.relative_to(root).as_posix()} has no id")
            if not registered(assets, ident.group(2), match.group(2)):
                raise ReleaseError(f"web/dist has no {match.group(2)} tab: run cd web && npm run build")


def release_files() -> list[tuple[Path, str]]:
    missing = [p for p in REQUIRED if not (ROOT / p).is_file()]
    if missing:
        raise ReleaseError("Not ready to release, missing: " + ", ".join(missing))
    web_fresh(ROOT)
    items: list[tuple[Path, str]] = []
    for tree in TREES:
        for path in sorted((ROOT / tree).rglob("*")):
            rel = path.relative_to(ROOT)
            if path.is_file() and not path.is_symlink() and wanted(rel):
                items.append((path, rel.as_posix()))
    items += [(p, p.relative_to(ROOT).as_posix()) for p in sorted(WHEELS.glob("*.whl"))]
    items += [(ROOT / f, f) for f in FILES]
    return items


def build_zip() -> Path:
    items = release_files()
    now = datetime.datetime.now()
    today = now.date()
    name = f"hub-release-{now.strftime('%Y-%m-%d-%H%M')}"
    DIST.mkdir(exist_ok=True)
    target = DIST / f"{name}.zip"
    partial = target.with_suffix(".zip.partial")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, rel in items:
            info = zipfile.ZipInfo(f"{name}/{rel}", date_time=(today.year, today.month, today.day, 0, 0, 0))
            mode = 0o755 if path.stat().st_mode & stat.S_IXUSR else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    size = partial.stat().st_size
    if size >= LIMIT_BYTES:
        partial.unlink()
        raise ReleaseError(f"The zip would be {size / 1e6:.1f} MB; the limit is {LIMIT_BYTES / 1e6:.1f} MB")
    partial.replace(target)
    print(f"{target.relative_to(ROOT)} · {size / 1e6:.1f} MB · {len(items)} files")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("step", nargs="?", choices=("zip", "wheels", "lock"), default="zip")
    step = parser.parse_args(argv).step
    try:
        if step == "lock":
            for name in TOP_LEVEL:
                write_lock(name)
        elif step == "wheels":
            fetch_wheels()
        else:
            try:
                verify_wheels()
            except ReleaseError:
                fetch_wheels()
            build_zip()
    except ReleaseError as error:
        print(f"release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
