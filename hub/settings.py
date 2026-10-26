"""Owner settings: `<data>/settings.json`. Schema, defaults, validation, atomic save (the Settings screen's edit:
`settings_edit`).

Nothing here names a machine: the installer (`hub init`) writes real values. The one model fact is a default
Settings can edit: how many reference images a model takes (`modules.generate-image.ref_caps`, model id prefix -> 1 to
6; the engine publishes no such number, and its own validation stays the final word). The video sizes the size menu
offers (`modules.generate-image.video_tiers`) are the engine's tier names: a list of them, or how many of the
catalog's first ones; names the catalog does not report are ignored where they are used. The longest scene a continued
clip may grow to (`modules.generate-image.continue_max_seconds`, 10 to 600 s): the engine decodes the whole source and
holds the joined file in RAM, so the scene's length bounds a continue's memory. A storyboard cell's text has no cap of
the Hub's (`pngtext.MAX` bounds what is written inside its picture). A sequence's join
encodes with libx264 at `join_crf` and `join_preset` (a trim re-encodes; whole clips may stream-copy).
A spoken line sent as turns has each join crossfaded over `modules.generate-image.speech_join_seconds` (0 to 0.14 s);
a clip's job is planned by the engine before it runs unless `modules.generate-image.plan_before_render` is false. Every
press of a clip or a line is judged inside its own job: a line by the words judge (`speech_judge`), under
`speech_words_bar` rendered again up to `speech_takes_max` takes; a clip by the face, mouth, frame and words judges
(`clip_judge`) on a scene's bars and count (`scene_takes_max`, `scene_retake_minutes`); the module settings are
checked in `settingsmods.py`, which drops the retired `clip_takes_max`, `speech_takes`, `max_cells` and `max_items`.
The C and C++ compilers the engine's kernels build with at run time (`engine.cc`, `engine.cxx`: full paths, empty for
none) are the installer's (`hub engine set`), passed to the worker as CC and CXX.
"""
from __future__ import annotations

import copy
import ipaddress
import re
from pathlib import Path
from typing import Any

from hub import settingsmods
from hub.core.store import read_json, write_json

FILE = "settings.json"
PORT = 42010
LOOPBACK = "127.0.0.1"

DEFAULTS: dict[str, Any] = {
    "version": 2, "server": {"bind": [LOOPBACK], "port": PORT, "extra_hosts": [], "allow_any_interface": False},
    "engine": {"python": "", "root": "", "args": [], "model_folders": [], "helper_folders": [], "profile": "engine",
               "profile_video": "same", "cc": "", "cxx": ""},
    "paths": {"drive": "", "characters": ""}, "gpus": [],
    "vram": {"idle_unload": True, "idle_minutes": 10, "clip_previews": False},
    "queue": {"max_waiting": 10}, "diagnostics": False,
    "modules_disabled": ["storyboard"],     # storyboards off; drop the name to turn them on
    "modules": {"generate-image": {"ref_caps": {"qwen_image_21": 6, "krea2_": 2}, "video_tiers": ["540p", "720p"],
                                   "continue_max_seconds": 60, "speech_turn_seconds": 5.0,
                                   "speech_join_seconds": 0.10, "plan_before_render": True,
                                   "speech_takes_max": 3, "speech_words_bar": 0.9,
                                   "speech_judge": True, "clip_judge": True, "clip_face_bar": 0.3,
                                   "judge_device": "cpu", "clip_lips_bar": 0.6,
                                   "frame_close": 0.3, "frame_wide": 0.12, "voice_route": "convert",
                                   "audience_level": 0.6, "audience_fade_in_ms": 100, "audience_fade_out_ms": 1000,
                                   "audience_most_ms": 4000, "scene_takes_max": 2, "scene_retake_minutes": 15,
                                   "scene_words_bar": 0.8, "scene_unscripted_seconds": 2.5},
                "storyboard": {},
                "sequence": {"join_crf": 18, "join_preset": "medium", "duck_threshold": 0.05,
                             "duck_ratio": 6.0, "duck_attack_ms": 50.0, "duck_release_ms": 400.0}},
}
# The engine's memory profiles (its `profile` config key) with the engine's own short names, as labels;
# ENGINE_OWN leaves the profile the engine's config has. Read by the worker at each engine start. `profile_video`, for
# a job on a video model, may be SAME: follow `profile`.
ENGINE_OWN, SAME = "engine", "same"
PROFILES: dict[float, str] = {1: "High RAM / high VRAM", 2: "High RAM / low VRAM", 3: "Low RAM / high VRAM",
                              3.5: "Very low RAM / high VRAM", 4: "Low RAM / low VRAM", 4.5: "Low RAM / low VRAM+",
                              5: "Very low RAM / low VRAM, fail safe"}
_HOST = re.compile(r"^[a-z0-9.\-\[\]:]{1,253}:\d{1,5}$")
_GPU_ID = re.compile(r"^[a-z0-9_]{1,20}$")
_TIER = re.compile(r"^[A-Za-z0-9_.\-]{1,16}$")
VIDEO_TIERS_MAX = 3                       # the size menu's places (1 MP, 1.5/2 MP, 4 MP)
PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow")


class SettingsError(Exception):
    """One plain-English line naming the field."""
    def __init__(self, field: str, text: str) -> None:
        super().__init__(f"settings.json: {field}: {text}")
        self.field, self.text = field, text


def _int(value: Any, field: str, lo: float, hi: float, kind: type = int) -> Any:
    if isinstance(value, bool) or not isinstance(value, (kind, int)) or not lo <= value <= hi:
        raise SettingsError(field, f"must be a {'whole ' if kind is int else ''}number from {lo} to {hi}")
    return kind(value)


def _inside_drive(value: Any, field: str) -> str:
    """A folder path relative to the Drive ("" for none): plain segments, none hidden."""
    parts = value.strip("/").split("/") if isinstance(value, str) and value.strip("/") else []
    if (not isinstance(value, str) or value.startswith("/") or "\\" in value or "\0" in value or len(value) > 512
            or any(p in ("", ".", "..") or p.startswith(".") for p in parts)):
        raise SettingsError(field, "must be a folder inside the Drive, such as Storyboards (empty: none)")
    return "/".join(parts)


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise SettingsError(field, "must be true or false")
    return value


def _profile(value: Any, field: str = "engine.profile") -> str | int | float:
    """"engine", or one of the engine's profile numbers (a whole one kept whole: 5, never 5.0); `profile_video` may
    also be "same"."""
    own = (SAME, ENGINE_OWN) if field == "engine.profile_video" else (ENGINE_OWN,)
    if isinstance(value, str) and value in own:
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in PROFILES:
        raise SettingsError(field, f"must be {' or '.join(own)} or one of {', '.join(f'{p:g}' for p in PROFILES)}")
    return int(value) if value == int(value) else float(value)


def profile_choices() -> list[dict[str, Any]]:
    """The memory profile menu: the engine's own first, then each profile by its number and the engine's name."""
    return [{"value": ENGINE_OWN, "label": "Engine's own"},
            *({"value": _profile(p), "label": f"{p:g} · {name}"} for p, name in PROFILES.items())]


def video_profile_choices() -> list[dict[str, Any]]:
    """The video models' menu: the general profile first, then the same choices."""
    return [{"value": SAME, "label": "Same as above"}, *profile_choices()]


def _tiers(value: Any) -> int | list[str]:
    """How many of the catalog's first tiers (1 to VIDEO_TIERS_MAX), or up to that many distinct tier names."""
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= VIDEO_TIERS_MAX:
        return value
    if (isinstance(value, list) and 1 <= len(value) <= VIDEO_TIERS_MAX and len(set(map(str, value))) == len(value)
            and all(isinstance(v, str) and _TIER.match(v) for v in value)):
        return list(value)
    raise SettingsError("modules.generate-image.video_tiers",
                        f"must be 1 to {VIDEO_TIERS_MAX}, or a list of 1 to {VIDEO_TIERS_MAX} different size names")


def _strs(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SettingsError(field, "must be a list of text values")
    return list(value)


# settings an older hub wrote; dropped when read (Temp and inputs became the Hub's own, the archive became the Drive,
# the VRAM hold went: other programs' memory never holds a job)
RETIRED = {"vram.ram_reserve_mb", "vram.margin_mb", "known_programs", "paths.outputs", "paths.inputs", "paths.archive"}
# The storyboards folder: a folder inside the Drive whose storyboards' pictures may hold text (`hub/core/named.py`).
# Left out of the file until storyboards are turned on; STORYBOARDS is the name it then takes by default.
OPTIONAL = {"paths.storyboards"}
STORYBOARDS = "Storyboards"


def _merge(raw: dict, defaults: dict, prefix: str) -> dict:
    out = copy.deepcopy(defaults)
    for key, value in raw.items():
        if prefix + key in RETIRED:
            continue
        if key not in defaults and prefix + key not in OPTIONAL:
            raise SettingsError(prefix + key, "unknown setting")
        out[key] = value
    return out


def check_bind(addrs: list[str], allow_any: bool) -> list[str]:
    """Numeric addresses only; 0.0.0.0 and :: are refused unless explicitly allowed."""
    if not addrs:
        raise SettingsError("server.bind", "needs at least one address")
    for addr in addrs:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise SettingsError("server.bind", f"{addr!r} is not a numeric IP address") from None
        if ip.is_unspecified and not allow_any:
            raise SettingsError("server.bind", f"{addr} listens on every network; use the LAN address")
    if len(set(addrs)) != len(addrs):
        raise SettingsError("server.bind", "lists an address twice")
    return addrs


def validate(raw: Any) -> dict:
    """Return complete, checked settings (missing keys take defaults) or raise SettingsError."""
    if not isinstance(raw, dict):
        raise SettingsError("(top)", "must be a JSON object")
    s = _merge(raw, DEFAULTS, "")
    for section in ("server", "engine", "paths", "vram", "queue"):
        if not isinstance(s[section], dict):
            raise SettingsError(section, "must be an object")
        s[section] = _merge(s[section], DEFAULTS[section], section + ".")
    srv = s["server"]
    srv["allow_any_interface"] = _bool(srv["allow_any_interface"], "server.allow_any_interface")
    srv["bind"] = check_bind(_strs(srv["bind"], "server.bind"), srv["allow_any_interface"])
    srv["port"] = _int(srv["port"], "server.port", 1, 65535)
    srv["extra_hosts"] = [h.lower() for h in _strs(srv["extra_hosts"], "server.extra_hosts")]
    for host in srv["extra_hosts"]:
        if not _HOST.match(host):
            raise SettingsError("server.extra_hosts", f"{host!r} must look like name:port")
    eng = s["engine"]
    for key in ("python", "root"):
        if not isinstance(eng[key], str):
            raise SettingsError(f"engine.{key}", "must be a path")
    for key in ("cc", "cxx"):
        if not isinstance(eng[key], str) or (eng[key] and not eng[key].startswith("/")):
            raise SettingsError(f"engine.{key}", "must be a full path, or empty for none")
    for key in ("drive", "characters"):
        s["paths"].setdefault(key, "")
        if not isinstance(s["paths"][key], str):
            raise SettingsError(f"paths.{key}", "must be a path (empty: not chosen yet)")
    if "storyboards" in s["paths"]:
        s["paths"]["storyboards"] = _inside_drive(s["paths"]["storyboards"], "paths.storyboards")
    eng["args"] = _strs(eng["args"], "engine.args")
    eng.update({k: _strs(eng[k], f"engine.{k}") for k in ("model_folders", "helper_folders")})
    eng["profile"] = _profile(eng["profile"])
    eng["profile_video"] = _profile(eng["profile_video"], "engine.profile_video")
    s["gpus"] = _gpus(s["gpus"])
    vram = s["vram"]
    vram.update({k: _bool(vram[k], f"vram.{k}") for k in ("idle_unload", "clip_previews")})
    vram["idle_minutes"] = _int(vram["idle_minutes"], "vram.idle_minutes", 5, 120)
    s["queue"]["max_waiting"] = _int(s["queue"]["max_waiting"], "queue.max_waiting", 1, 100)
    s["diagnostics"] = _bool(s["diagnostics"], "diagnostics")
    s["modules_disabled"] = _strs(s["modules_disabled"], "modules_disabled")
    s["modules"] = settingsmods.validate(s["modules"])
    s["version"] = DEFAULTS["version"]
    return s


def _gpus(value: Any) -> list[dict]:
    if not isinstance(value, list):
        raise SettingsError("gpus", "must be a list")
    out, seen = [], set()
    for i, g in enumerate(value):
        field = f"gpus[{i}]"
        if not isinstance(g, dict) or set(g) - {"id", "index", "uuid", "engine"}:
            raise SettingsError(field, "must hold id, index, uuid and engine")
        gid = g.get("id")
        if not isinstance(gid, str) or not _GPU_ID.match(gid) or gid in seen:
            raise SettingsError(field + ".id", "must be a short unique name like gpu0")
        uuid = g.get("uuid")
        if uuid is not None and not isinstance(uuid, str):
            raise SettingsError(field + ".uuid", "must be text or null")
        seen.add(gid)
        out.append({"id": gid, "index": _int(g.get("index", 0), field + ".index", 0, 63),
                    "uuid": uuid, "engine": _bool(g.get("engine", False), field + ".engine")})
    return out


def load(data_dir: Path) -> dict:
    path = data_dir / FILE
    try:
        raw = read_json(path)
    except ValueError as e:
        raise SettingsError("(file)", str(e)) from None
    if raw is None:
        raise SettingsError("(file)", f"not found in {data_dir}; run: hub init --data {data_dir} ...")
    return validate(raw)


def save(data_dir: Path, settings: dict) -> None:
    write_json(data_dir / FILE, validate(settings))


def host_entry(addr: str, port: int) -> str:
    return f"[{addr}]:{port}" if ":" in addr else f"{addr}:{port}"


def hosts(settings: dict, port: int) -> frozenset[str]:
    """Accepted `Host` values: each bind with the port, localhost when loopback is bound, extras."""
    names = {host_entry(a, port).lower() for a in settings["server"]["bind"]}
    if LOOPBACK in settings["server"]["bind"]:
        names.add(f"localhost:{port}")
    return frozenset(names | set(settings["server"]["extra_hosts"]))


def drive_root(settings: dict) -> Path | None:
    """`paths.drive`: the one folder for Media's Drive, or None until it is chosen. Temp is always the Hub's own
    (`<data>/outputs`) and never a setting."""
    value = settings["paths"]["drive"]
    return Path(value) if value else None


def characters_root(settings: dict) -> Path | None:
    """`paths.characters`: the Characters folder (named pictures), or None until it is chosen."""
    value = settings["paths"].get("characters", "")
    return Path(value) if value else None


def storyboards_folder(settings: dict) -> str | None:
    """The storyboards folder, relative to the Drive, or None while storyboards are not turned on."""
    return settings["paths"].get("storyboards") or None


def link_base(settings: dict, port: int | None = None) -> str:
    """`http://<first LAN bind>:<port>` (loopback only if nothing else is bound)."""
    binds = settings["server"]["bind"]
    addr = next((a for a in binds if a != LOOPBACK and not a.startswith("::1")), binds[0])
    return "http://" + host_entry(addr, port or settings["server"]["port"])
