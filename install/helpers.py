"""Small helpers for the Hub's installers. Standard library only; run with the system python3 -I.

    helpers.py lan [IP]                     print "<LAN IP> <LAN subnet> <interface>" (checks IP is ours when given)
    helpers.py config TEMPLATE OUT --source S --outputs O [--other-engine]
                                            write the engine app's wgp_config.json from TEMPLATE (or "-" for
                                            none): no secret, no path inside S; its own ckpts as its only checkpoint
                                            folder (never a model folder), O for outputs; --other-engine:
                                            TEMPLATE is another engine's, its OTHER_ENGINE keys left out
    helpers.py base-python ENV DEST UNDO    copy the venv's base Python (when outside /usr) to DEST and point the
                                            venv at it; UNDO records how to put it back (base-python-undo UNDO)
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys

VIRTUAL = re.compile(r"^(lo|docker|podman|virbr|br-|veth|cni|flannel|tailscale|tun|tap|wg|vnet|zt)")
# The engine config's keys that never carry over, and the values that hold whatever the old file says: no secrets,
# no plugins, no notifications, no prompt enhancer (hub/worker/wgpconfig.py, DROPPED_CONFIG and FORCED_CONFIG).
DROPPED = ("services", "llm_engines", "enabled_plugins", "installed_remote_plugins")
SAVE_KEYS = ("save_path", "image_save_path", "audio_save_path", "mesh_save_path")
# Left at upstream's own value when the config comes from another engine: HocusPocus's "compile": "transformer"
# (PyTorch compilation, upstream's "to be deprecated" choice) broke upstream 18.05's H3 clips at their last step.
OTHER_ENGINE = ("compile",)
MINIMAL = {"attention_mode": "auto", "transformer_types": [], "compile": "", "transformer_quantization": "int8",
           "text_encoder_quantization": "int8"}
CHECKS = "import ssl, sqlite3, ctypes, zlib, sys; print(sys.version.split()[0])"


class Stop(Exception):
    """One plain-English line, the installer's stop message."""


def ip_json(*args: str) -> list[dict]:
    try:
        done = subprocess.run(["ip", "-4", "-j", *args], capture_output=True, text=True)
    except OSError:
        return []
    return json.loads(done.stdout or "[]") if done.returncode == 0 else []


def addresses() -> list[tuple[str, ipaddress.IPv4Interface]]:
    """(interface, address) for every global IPv4 address of this machine."""
    found = []
    for link in ip_json("addr", "show"):
        for info in link.get("addr_info", []):
            if info.get("family") == "inet" and info.get("scope") == "global":
                found.append((link["ifname"], ipaddress.IPv4Interface(f"{info['local']}/{info['prefixlen']}")))
    return found


def lan(wanted: str | None) -> str:
    found = addresses()
    if wanted:
        ranked = [(name, a) for name, a in found if str(a.ip) == wanted]
        if not ranked:
            raise Stop(f"{wanted} is not an address of this computer")
    else:
        route_devs = [r.get("dev") for r in ip_json("route", "show", "default")]
        real = [(name, a) for name, a in found if not VIRTUAL.match(name)]
        ranked = [(name, a) for dev in route_devs for name, a in real if name == dev] + real
        if not ranked:
            raise Stop("No network address found. Connect this computer to your network, or pass --bind <IP>")
    name, chosen = ranked[0]
    return f"{chosen.ip} {chosen.network} {name}"


def inside(value: str, source: str) -> bool:
    real = os.path.realpath(source)
    return isinstance(value, str) and os.path.isabs(value) and (
        os.path.commonpath([os.path.realpath(value), real]) == real)


def config(template: str, out: str, source: str, outputs: str, other_engine: bool = False) -> None:
    """The engine app's own config, from TEMPLATE's (the old engine's, or the app's own): secrets and notifications
    gone, every path inside SOURCE gone, the app's own `ckpts` as the only checkpoint folder and upstream's default
    LoRA root (the model and LoRA folders set in Settings reach the engine from the Hub, under its hold: a run of
    upstream outside the Hub never searches them, so its import-time deletion of "deprecated" files cannot reach
    them), the outputs as every save path, the prompt enhancer off; quantization, attention and memory profiles kept."""
    loaded: object = None
    if template != "-":
        try:
            with open(template, encoding="utf-8") as f:
                loaded = json.load(f)
        except (OSError, ValueError):
            loaded = None
    cfg = dict(loaded) if isinstance(loaded, dict) else dict(MINIMAL)
    for key in list(cfg):
        value = cfg[key]
        paths = value if isinstance(value, list) else [value]
        if key in DROPPED or key.startswith("notification_") or any(inside(v, source) for v in paths):
            del cfg[key]
    cfg.pop("loras_root", None)
    for key in OTHER_ENGINE if other_engine else ():
        cfg.pop(key, None)
    cfg.update({"checkpoints_paths": ["ckpts"], "enhancer_enabled": 0, **dict.fromkeys(SAVE_KEYS, outputs)})
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
        f.write("\n")


def _links(env: str) -> dict[str, str]:
    folder = os.path.join(env, "bin")
    return {name: os.readlink(os.path.join(folder, name)) for name in sorted(os.listdir(folder))
            if name.startswith("python") and os.path.islink(os.path.join(folder, name))}


def _cfg(env: str) -> tuple[list[str], int | None, str]:
    with open(os.path.join(env, "pyvenv.cfg"), encoding="utf-8") as f:
        lines = f.read().splitlines()
    at = next((i for i, line in enumerate(lines) if line.split("=")[0].strip() == "home"), None)
    return lines, at, (lines[at].split("=", 1)[1].strip() if at is not None else "")


def base_python(env: str, dest: str, undo: str) -> str:
    """The venv's base Python copied into DEST when it lives outside /usr (uv's own folder, say), and the venv's
    `python*` links and `home` pointed at the copy; checked by running it. Returns what was done, in one line."""
    lines, at, home = _cfg(env)
    if at is None or not home:
        raise Stop(f"{env}/pyvenv.cfg names no home: this is not a Python environment the installer knows.")
    base = os.path.dirname(os.path.realpath(home))                  # the install root holding bin/
    if base == "/usr" or base.startswith("/usr/"):
        return f"The engine's Python is the system's ({home}): left as it is."
    if os.path.realpath(base) == os.path.realpath(dest):
        return f"The engine's Python is already its own ({dest})."
    if os.path.lexists(dest):
        raise Stop(f"{dest} already exists. Move it away first.")
    links = _links(env)
    with open(undo, "w", encoding="utf-8") as f:
        json.dump({"env": env, "dest": dest, "home": home, "links": links}, f)
    shutil.copytree(base, dest, symlinks=True)
    for name, target in links.items():
        path = os.path.join(env, "bin", name)
        named = os.path.join(os.path.realpath(os.path.dirname(os.path.join(env, "bin", target))),
                             os.path.basename(target))              # the folder resolved, the file as named
        if os.path.commonpath([named, base]) == base:
            os.unlink(path)
            os.symlink(os.path.join(dest, os.path.relpath(named, base)), path)
    lines[at] = f"home = {os.path.join(dest, os.path.relpath(os.path.realpath(home), base))}"
    with open(os.path.join(env, "pyvenv.cfg"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    done = subprocess.run([os.path.join(env, "bin", "python"), "-I", "-B", "-c", CHECKS], capture_output=True,
                          text=True)
    if done.returncode != 0:
        raise Stop(f"The engine's Python does not start from its copy in {dest}: "
                   f"{(done.stderr.strip().splitlines() or ['no reason given'])[-1]}")
    headers = [os.path.join(top, "Python.h") for top, _d, files in os.walk(os.path.join(dest, "include"))
               if "Python.h" in files]
    if not headers:
        raise Stop(f"The engine's Python in {dest} has no Python.h (its kernels need it).")
    return f"The engine's Python {done.stdout.strip()} is now its own copy, in {dest} (from {base})."


def base_python_undo(undo: str) -> None:
    """Put the venv's links and home back as `base_python` found them, and remove the copy."""
    with open(undo, encoding="utf-8") as f:
        record = json.load(f)
    env = record["env"]
    for name, target in record["links"].items():
        path = os.path.join(env, "bin", name)
        if os.path.lexists(path):
            os.unlink(path)
        os.symlink(target, path)
    lines, at, _home = _cfg(env)
    if at is not None:
        lines[at] = f"home = {record['home']}"
        with open(os.path.join(env, "pyvenv.cfg"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    shutil.rmtree(record["dest"], ignore_errors=True)


def option(argv: list[str], name: str) -> str:
    if name not in argv or argv.index(name) + 1 >= len(argv):
        raise Stop(f"{name} is needed")
    return argv[argv.index(name) + 1]


def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["lan"] and len(argv) <= 2:
            print(lan(argv[1] if len(argv) == 2 else None))
        elif argv[:1] == ["config"] and len(argv) in (7, 8) and (len(argv) == 7 or argv[7] == "--other-engine"):
            config(argv[1], argv[2], option(argv, "--source"), option(argv, "--outputs"), len(argv) == 8)
        elif argv[:1] == ["base-python"] and len(argv) == 4:
            print(base_python(argv[1], argv[2], argv[3]))
        elif argv[:1] == ["base-python-undo"] and len(argv) == 2:
            base_python_undo(argv[1])
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except Stop as stop:
        print(stop, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
