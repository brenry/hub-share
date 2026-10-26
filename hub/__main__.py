"""hub command line. The network seatbelt is installed before anything else runs."""
# ruff: noqa: E402
from __future__ import annotations

from hub.core import netlock

netlock.install()

import argparse
import copy
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from hub import engineset, pathrules
from hub.core.api import Invalid
from hub.core.devices import Devices
from hub.core.probes import Probes
from hub.core.store import write_json
from hub.settings import (
    DEFAULTS,
    LOOPBACK,
    PORT,
    SettingsError,
    check_bind,
    host_entry,
    link_base,
    load,
    save,
    validate,
)

UNIT = "hub.service"
VIRTUAL = ("lo", "docker", "br-", "veth", "virbr", "podman", "cni", "tailscale", "wg", "tun", "tap")
EPILOG = """commands:
  serve                                run the hub (the hub.service unit runs this)
  init --bind IP [--engine-root P --engine-python P] [--lora-folder P]... [--port N] [--gpu N]
                                       write the first settings (127.0.0.1 is always added)
  engine set --root P --python P [--cc P] [--cxx P] [--before FILE] [--args JSON]
                                       point the hub at an engine (the engine installer runs this)
  engine restore --before FILE         put back the engine settings `engine set` replaced
  engine clear                         no engine (its folder and Python empty)
  pair --name NAME                     print a one-time pairing link for a screen (10 minutes, single use)
  network show                         print addresses, port and paired devices
  network set [--bind IP[,IP]] [--port N]  change where the hub listens, then restart it
  network reset                        listen on this machine's LAN address + 127.0.0.1, port 42010
  restart                              restart the hub service; screens reconnect by themselves

Every command takes --data DIR (default: the HUB_DATA environment variable)."""


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data", type=Path, help="the hub's data folder (default: $HUB_DATA)")
    p = argparse.ArgumentParser(prog="hub", description="Hub: a private, LAN-only creative server.",
                                epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="command")
    sub.add_parser("serve", parents=[common], help="run the hub")
    init = sub.add_parser("init", parents=[common], help="write the first settings")
    init.add_argument("--bind", required=True, help="this server's LAN address")
    init.add_argument("--engine-root", type=Path, help="the engine folder (Wan2GP); none: set it later")
    init.add_argument("--engine-python", type=Path, help="the engine's own python")
    init.add_argument("--lora-folder", action="append", default=[], type=Path, help="a LoRA folder (repeatable)")
    init.add_argument("--port", type=int, default=PORT, help=f"port (default {PORT})")
    init.add_argument("--gpu", type=int, default=0, help="GPU index for the image engine (default 0)")
    pair = sub.add_parser("pair", parents=[common], help="print a one-time pairing link")
    pair.add_argument("--name", required=True, help="the device's name, e.g. Desktop")
    net = sub.add_parser("network", help="show or change where the hub listens")
    nsub = net.add_subparsers(dest="action", required=True, metavar="action")
    nsub.add_parser("show", parents=[common], help="print addresses, port and devices")
    nset = nsub.add_parser("set", parents=[common], help="change bind addresses and/or port")
    nset.add_argument("--bind", help="address(es), comma-separated (127.0.0.1 is always added)")
    nset.add_argument("--port", type=int, help="new port")
    nsub.add_parser("reset", parents=[common], help="LAN address + 127.0.0.1, default port")
    sub.add_parser("restart", parents=[common], help="restart the hub service")
    eng = sub.add_parser("engine", help="change the engine settings (the engine installer)")
    esub = eng.add_subparsers(dest="action", required=True, metavar="action")
    eset = esub.add_parser("set", parents=[common], help="point the hub at an engine")
    eset.add_argument("--root", required=True, help="the engine folder (with wgp.py)")
    eset.add_argument("--python", required=True, help="the engine's own python")
    eset.add_argument("--cc", default="", help="the C compiler its kernels build with (full path)")
    eset.add_argument("--cxx", default="", help="the C++ compiler (full path)")
    eset.add_argument("--before", type=Path, help="write the settings this replaces to FILE")
    eset.add_argument("--args", help="the engine's arguments, as a JSON list (default: unchanged)")
    erestore = esub.add_parser("restore", parents=[common], help="put back the settings `engine set` replaced")
    erestore.add_argument("--before", type=Path, required=True, help="the file `engine set --before` wrote")
    esub.add_parser("clear", parents=[common], help="no engine")
    return p


def _data(args: argparse.Namespace) -> Path:
    raw = args.data or os.environ.get("HUB_DATA")
    if not raw:
        raise SystemExit("hub: give --data DIR or set HUB_DATA")
    return Path(raw).expanduser().absolute()


def _with_loopback(addrs: list[str]) -> list[str]:
    return addrs if LOOPBACK in addrs else [*addrs, LOOPBACK]


def _check_local(addrs: list[str]) -> None:
    for addr in addrs:
        with socket.socket(socket.AF_INET6 if ":" in addr else socket.AF_INET) as s:
            try:
                s.bind((addr, 0))
            except OSError:
                raise SystemExit(f"hub: {addr} is not an address of this server") from None


def lan_address() -> str | None:
    """The first global IPv4 address on a physical-looking interface (`ip -j -4 addr`)."""
    try:
        out = subprocess.run(["ip", "-j", "-4", "addr", "show", "scope", "global"], capture_output=True,
                             text=True, timeout=5, check=True).stdout
        links = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    for link in links:
        if str(link.get("ifname", "")).startswith(VIRTUAL) or link.get("operstate") == "DOWN":
            continue
        for info in link.get("addr_info", []):
            if info.get("family") == "inet" and info.get("local"):
                return str(info["local"])
    return None


def _systemctl(*args: str) -> int:
    try:
        return subprocess.run(["systemctl", "--user", *args, UNIT], check=False).returncode
    except OSError:
        return 127


def _restart(data: Path, only_if_running: bool = True) -> int:
    if only_if_running and _systemctl("is-active", "--quiet") != 0:
        print("Saved. Start the hub to use it.")
        return 0
    (data / "run").mkdir(parents=True, exist_ok=True)
    (data / "run" / "restart").touch()
    if _systemctl("restart") != 0:
        (data / "run" / "restart").unlink(missing_ok=True)
        print("hub: the restart did not work; run: systemctl --user restart hub", file=sys.stderr)
        return 1
    print("Restarting the hub.")
    return 0


def cmd_init(args: argparse.Namespace, data: Path) -> int:
    try:
        s = load(data) if (data / "settings.json").exists() else copy.deepcopy(DEFAULTS)
        s["server"]["bind"] = check_bind(_with_loopback([args.bind]), False)
    except SettingsError as e:
        raise SystemExit(f"hub: {e}") from None
    s["server"]["port"] = args.port
    given = [p.expanduser().absolute() for p in (args.engine_root, args.engine_python) if p is not None]
    if len(given) == 2:
        root, python = given
        s["engine"].update(root=str(root), python=str(python))
        ckpts = (root / "ckpts").resolve()                       # a link's folder, never the link beside it
        if ckpts.is_dir() and str(ckpts) not in s["engine"]["model_folders"]:
            s["engine"]["model_folders"].append(str(ckpts))
    elif given:
        raise SystemExit("hub: give --engine-root and --engine-python together, or neither")
    if args.lora_folder:
        folders = [str(f.expanduser().absolute()) for f in args.lora_folder]
        s["modules"].setdefault("loras", {})["folders"] = folders
    gpus = Probes().gpus() or []
    uuid = next((g["uuid"] for g in gpus if g["index"] == args.gpu), None)
    s["gpus"] = [{"id": f"gpu{args.gpu}", "index": args.gpu, "uuid": uuid, "engine": True}]
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        save(data, validate(s))
    except SettingsError as e:
        raise SystemExit(f"hub: {e}") from None
    for path in given:
        if not path.exists():
            print(f"Note: {path} does not exist yet", file=sys.stderr)
    print(f"Settings written to {data / 'settings.json'}")
    return 0


def cmd_engine(args: argparse.Namespace, data: Path) -> int:
    """The engine installer's change of the engine settings (`engineset`); saved, never restarted here."""
    s = load(data)
    try:
        if args.action == "set":
            engine_args = None if args.args is None else json.loads(args.args)
            new = engineset.engine_set(s, root=args.root, python=args.python, cc=args.cc, cxx=args.cxx,
                                       engine_args=engine_args)
            if args.before is not None:
                write_json(args.before, engineset.before(s))
        elif args.action == "restore":
            new = engineset.restore(s, json.loads(args.before.read_text(encoding="utf-8")))
        else:
            new = engineset.clear(s)
    except pathrules.Refused as e:
        raise SystemExit(f"hub: {e.field}: {e.text}") from None
    save(data, new)
    print(f"Engine settings saved: {new['engine']['root'] or 'none'}")
    return 0


def cmd_network(args: argparse.Namespace, data: Path) -> int:
    s = load(data)
    if args.action == "show":
        port = s["server"]["port"]
        print("Bind: " + ", ".join(s["server"]["bind"]))
        print(f"Port: {port}")
        print("Addresses: " + " ".join(f"http://{host_entry(a, port)}" for a in s["server"]["bind"]))
        print("Devices:" if Devices(data).records() else "Devices: none paired")
        for d in Devices(data).records():
            print(f"  {d['name']} {', '.join(d['addrs'])}")
        return 0
    if args.action == "set":
        if args.bind is None and args.port is None:
            raise SystemExit("hub: give --bind, --port or both")
        if args.bind is not None:
            addrs = _with_loopback([a.strip() for a in args.bind.split(",") if a.strip()])
            check_bind(addrs, s["server"]["allow_any_interface"])
            _check_local(addrs)
            s["server"]["bind"] = addrs
        if args.port is not None:
            s["server"]["port"] = args.port
    else:
        lan = lan_address()
        if lan is None:
            print("hub: no LAN address found; listening on 127.0.0.1 only", file=sys.stderr)
        s["server"].update(bind=_with_loopback([lan] if lan else []), port=PORT, extra_hosts=[],
                           allow_any_interface=False)
    save(data, s)
    print(f"Listening on: {', '.join(s['server']['bind'])} port {s['server']['port']}")
    return _restart(data)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data = _data(args)
    try:
        if args.cmd == "serve":
            from hub.server import run

            return run(data)
        if args.cmd == "init":
            return cmd_init(args, data)
        if args.cmd == "pair":
            settings = load(data)
            code, _ = Devices(data).mint_code(args.name)
            print(f"{link_base(settings)}/pair#c={code}")
            return 0
        if args.cmd == "network":
            return cmd_network(args, data)
        if args.cmd == "engine":
            return cmd_engine(args, data)
        return _restart(data, only_if_running=False)
    except Invalid as e:
        print(f"hub: {e.text}", file=sys.stderr)
        return 1
    except SettingsError as e:
        print(f"hub: {e}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as e:
        print(f"hub: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
