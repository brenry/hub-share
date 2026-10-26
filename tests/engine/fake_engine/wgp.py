"""Fake Wan2GP `wgp` for tests: the globals and behaviours the hub worker relies on.

Flavour ("legacy" = HocusPocus's vendored copy, "upstream" = current Wan2GP) comes from `fake_engine.json`;
model definitions are read from `defaults/*.json` and `finetunes/*.json` in the cwd, as the real engine does
(`{"model": {...}, **settings}`; the file name is the model type), and completed from their architecture the way
the real engine's family handlers do (`architectures` in fake_engine.json), so a definition can be as small as
name, description, architecture and URLs. It keeps the real engine's write habits: a `settings` folder in the root,
the config-file fallback to the root's `wgp_config.json`, and LoRA folders created by `get_lora_dir`. Prompts may
hold test switches: CRASH, OOM, SLOW. A video task (image_mode 0) writes a small MP4 (`shared/fake_clip`), an
audio-only model a short WAV (`shared/fake_sound`). GPU memory: `fake_gpu`."""
from __future__ import annotations

import argparse
import copy
import glob
import inspect
import json
import os
import time

from shared import fake_clip, fake_gpu, fake_manifest, fake_png, fake_sound, model_dropdowns

with open("fake_engine.json", encoding="utf-8") as f:
    FAKE = json.load(f)
FLAVOUR = FAKE["flavour"]
WanGP_version, settings_version = FAKE["version"], FAKE["settings_version"]
DEFAULT_LORA_ROOT, CONFIG = "loras", "wgp_config.json"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    for name, default in (("--config", ""), ("--settings", "settings"), ("--loras", ""), ("--profile", "-1"),
                          ("--attention", "")):
        p.add_argument(name, default=default)
    parsed, _ = p.parse_known_args()
    parsed.lora_config = {}
    return parsed


args = fake_gpu.open_record(_parse_args())     # a test may keep a record in the config folder the hub gives
if not os.path.isdir("settings"):
    os.mkdir("settings")
_config_file = os.path.join(os.path.abspath(args.config), CONFIG) if args.config else CONFIG
_load = _config_file if os.path.isfile(_config_file) or not os.path.isfile(CONFIG) else CONFIG
if os.path.isfile(_load):
    with open(_load, encoding="utf-8") as f:
        server_config = json.load(f)
else:
    server_config = {"save_path": "outputs", "image_save_path": "outputs"}
if _load != _config_file or not os.path.isfile(_config_file):
    with open(_config_file, "w", encoding="utf-8") as f:
        json.dump(server_config, f)

primary_settings = FAKE["primary_settings"]
models_def: dict[str, dict] = {}
families_infos = {k: tuple(v) for k, v in FAKE["families"].items()}
wan_model, transformer_type = None, server_config.get("last_model_type")


class _Handler:
    @staticmethod
    def update_default_settings(base_model_type: str, model_def: dict, ui: dict) -> None:
        ui.update(copy.deepcopy(FAKE["handler_defaults"].get(base_model_type, {})))


class LegacyHandler(_Handler):
    @staticmethod
    def get_lora_dir(base_model_type: str, args: argparse.Namespace, lora_root: str) -> str:
        return os.path.join(lora_root, FAKE["lora_keys"][base_model_type])


class UpstreamHandler(_Handler):
    @staticmethod
    def get_lora_dir(base_model_type: str) -> str:
        return FAKE["lora_keys"][base_model_type]


HANDLER = UpstreamHandler if FLAVOUR == "upstream" else LegacyHandler


def get_model_def(model_type: str) -> dict | None:
    return models_def.get(model_type)


def init_model_def(model_type: str, model_def: dict) -> dict:
    """Like the real one: the architecture's handler supplies the defaults and the file's own entries win; an
    unknown architecture is hidden."""
    handler_def = FAKE["architectures"].get(get_base_model_type(model_type))
    if handler_def is None:
        model_def["visible"] = False
        return model_def
    default_model_def = copy.deepcopy(handler_def)
    default_model_def.update(model_def)
    return default_model_def


def load_model_definitions() -> None:
    """The real engine's loader: defaults/ then finetunes/, a later file merging into an earlier one."""
    found = glob.glob(os.path.join("defaults", "*.json")) + glob.glob(os.path.join("finetunes", "*.json"))
    for file_path in sorted(found):
        model_type = os.path.basename(file_path)[:-5]
        with open(file_path, encoding="utf-8") as f:
            json_def = json.load(f)
        model_def = json_def.pop("model")
        model_def["path"] = file_path
        if model_type in models_def:
            models_def[model_type].setdefault("settings", {}).update(json_def)
            models_def[model_type].update(model_def)
        else:
            models_def[model_type] = model_def
            models_def[model_type] = model_def = init_model_def(model_type, model_def)
            model_def["settings"] = json_def


def get_model_recursive_prop(model_type: str, prop: str = "URLs", return_list: bool = True) -> list:
    value = (models_def.get(model_type) or {}).get(prop) or []
    if isinstance(value, str):
        return get_model_recursive_prop(value, prop, return_list)
    return list(value)


def get_local_model_filename(model_filename: str, **_: object) -> str | None:
    """Like the real file locator (shared/utils/files_locator.locate_file): a URL by its base name, an absolute
    path as it is, anything else joined to each checkpoint folder in turn."""
    if model_filename.startswith("http"):
        model_filename = os.path.basename(model_filename)
    if os.path.isabs(model_filename):
        return model_filename if os.path.isfile(model_filename) else None
    for folder in server_config.get("checkpoints_paths") or []:
        path = os.path.join(folder, model_filename)
        if os.path.isfile(path):
            return path
    return None


def get_base_model_type(model_type: str) -> str | None:
    md = get_model_def(model_type)
    return md["architecture"] if md else None


load_model_definitions()
for _old in FAKE.get("deprecated") or []:       # like upstream's import: an old model file goes from every root
    for _folder in server_config.get("checkpoints_paths") or []:
        if os.path.isfile(os.path.join(_folder, _old)):
            os.remove(os.path.join(_folder, _old))


def get_model_handler(model_type: str) -> type[_Handler]:
    return HANDLER


def get_model_name(model_type: str, description_container: list[str] | None = None) -> str:
    """Like the real one, which hands back the description too: a definition without one cannot be used."""
    model_def = get_model_def(model_type)
    (description_container or [""])[0] = model_def["description"]
    return model_def["name"]


def get_model_family(model_type: str, for_ui: bool = False) -> str:
    return get_model_def(model_type)["family"]


def _lora_root() -> str:
    return args.loras or server_config.get("loras_root", DEFAULT_LORA_ROOT) or DEFAULT_LORA_ROOT


def get_lora_dir(model_type: str) -> str:
    """Like the real engine: computes the folder and creates it when missing."""
    base = get_base_model_type(model_type)
    path = (HANDLER.get_lora_dir(base, args, _lora_root()) if FLAVOUR == "legacy"
            else os.path.join(_lora_root(), HANDLER.get_lora_dir(base)))
    os.makedirs(path, exist_ok=True)
    return path


if FLAVOUR == "upstream":
    def get_lora_root() -> str:
        return _lora_root()

    def get_factory_settings(model_type: str) -> dict:
        """Like the real one: the primary settings, the handler's defaults, the definition's own settings on top. A
        model the root carries a capture's factory settings for (`factory`) starts from those instead."""
        md = get_model_def(model_type)
        ui = copy.deepcopy((FAKE.get("factory") or {}).get(model_type) or {})
        if not ui:
            ui = copy.deepcopy(primary_settings)
            ui.update({"settings_version": settings_version, "resolution": "832x480"})
            HANDLER.update_default_settings(md["architecture"], md, ui)
        ui.update(copy.deepcopy(md.get("settings", {})))
        return ui
else:
    def get_lora_search_dirs(model_type: str) -> list[str]:
        return [get_lora_dir(model_type)]


if FAKE.get("locator"):
    from shared import fake_locator as fl  # noqa: F401  (read by the worker's fork adapter)


def get_lora_local_path(lora_dir: str, lora: str) -> str:
    """Like the real one (wgp.py:3836): an absolute path as it is, else the file's name in the LoRA folder."""
    return lora if os.path.isabs(lora) else os.path.join(lora_dir, os.path.basename(lora.split("|")[0]))


def _get_dropdown_deps() -> model_dropdowns.DropdownDeps:
    return model_dropdowns.DropdownDeps(get_lora_dir=get_lora_dir, get_local_model_filename=get_local_model_filename,
                                        get_lora_local_path=get_lora_local_path)


if FAKE.get("generate_video") is not None:      # WanGP 18.05 has none (it names its own generate_media)
    def generate_video(*args, **kwargs) -> None:
        """The real one by its signature alone, the capture's (fake_engine.json): the one-pass switch is a keyword."""

    generate_video.__signature__ = inspect.Signature([inspect.Parameter(  # type: ignore[attr-defined]
        p["name"], getattr(inspect.Parameter, p["kind"]), default={"<required>": inspect.Parameter.empty}.get(
            p["default"], p["default"])) for p in FAKE["generate_video"]])


def release_model() -> None:
    global wan_model
    wan_model = fake_gpu.release()


def validate_task(task: dict) -> dict:
    """Legacy starts from generic defaults; upstream merges the model's factory defaults; `fake_manifest` checks."""
    params = task["params"]
    if FLAVOUR == "legacy":
        return fake_manifest.check({**primary_settings, **params})
    inputs = get_factory_settings(params["model_type"])
    inputs.update({k: v for k, v in params.items() if v is not None or k not in inputs})
    return fake_manifest.check(inputs)


def _single_prompt(mode: object) -> bool:
    return mode == 2 if FLAVOUR == "legacy" else {0: "G", 2: "FG", "": "FG"}.get(mode, mode) == "FG"


def _check_loras(inputs: dict) -> None:
    folder = get_lora_dir(inputs["model_type"])
    names = inputs.get("activated_loras") or []
    missing = [n for n in names if not os.path.isfile(
        os.path.join(folder, os.path.basename(n) if FLAVOUR == "legacy" else n))]
    if missing:
        raise RuntimeError(f"The following Loras files are missing or invalid: {missing}.")
    if len(str(inputs.get("loras_multipliers") or "").split()) > len(names):
        raise RuntimeError("Too many Lora multipliers")


def download_models(model_type: str) -> None:
    """Like the real one before a model loads: a main file named without a URL must be found where it is named (it
    cannot be fetched), and every extra file the definition pulls in (preload_URLs, loras) must already be here,
    since the worker is offline."""
    md = get_model_def(model_type)
    main = (get_model_recursive_prop(model_type, "URLs") or [""])[0]
    if not main.startswith("http") and get_local_model_filename(main) is None:
        raise RuntimeError(f"Model '{main}' was not found locally and no URL was provided to download it.")
    for url in [*(md.get("preload_URLs") or []), *(md.get("loras") or [])]:
        if get_local_model_filename(url) is None:
            raise RuntimeError(f"'{url}' is invalid: the engine is offline")


def generate(inputs: dict, send, stop, outdir: str) -> list[dict]:
    """Make the images; returns [{path, settings}]. `stop()` is checked between steps."""
    global wan_model, transformer_type
    prompt = str(inputs["prompt"])
    if "CRASH" in prompt:
        os._exit(139)
    if "OOM" in prompt:
        raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
    _check_loras(inputs)
    if wan_model is None or transformer_type != inputs["model_type"]:
        download_models(inputs["model_type"])
        release_model()
        for i in (1, 2):
            send("progress", [(i, 2), "Loading Model"])
        wan_model, transformer_type = fake_gpu.load(inputs["model_type"], inputs.get("image_mode") == 0)
    prompts = [prompt] if _single_prompt(inputs.get("multi_prompts_gen_type")) else [
        line for line in prompt.splitlines() if line.strip()]
    steps, delay = int(inputs["num_inference_steps"]), 0.25 if "SLOW" in prompt else 0.002
    out = []
    for text in prompts:
        for step in range(1, steps + 1):
            if stop():
                return out
            time.sleep(delay)
            send("progress", [(step, steps), "Denoising"])
        meta = {k: v for k, v in inputs.items() if k not in ("state", "image_refs")}
        name = get_model_name(inputs["model_type"])
        meta.update(prompt=text, type=f"WanGP v{WanGP_version} by DeepBeepMeep - {name}")
        template = str(inputs.get("output_filename") or "")
        stem = (template.replace("{date}", time.strftime("%Y-%m-%d-%Hh%Mm%Ss")).replace("{seed}", str(inputs["seed"]))
                if template else f"{time.strftime('%Y-%m-%d-%Hh%Mm%Ss')}_seed{inputs['seed']}_{text[:20]}")
        sound = bool(get_model_def(inputs["model_type"]).get("audio_only"))   # the real one's codec default: wav
        clip = inputs.get("image_mode") == 0 and not sound   # a video task: the container the config names
        ext = "wav" if sound else server_config.get("video_container", "mp4") if clip else "png"
        path = os.path.join(outdir, f"{stem}{'' if not out else f'_{len(out)}'}.{ext}")
        if sound:
            fake_sound.write(path, 1.0, json.dumps(meta))
        elif clip:                                      # a continue chained into windows: one file per window
            for made in fake_clip.write(path, inputs, get_model_def(inputs["model_type"]))[:-1]:
                out.append({"path": made, "settings": meta})
        else:
            width, height = (int(v) for v in str(inputs["resolution"]).split("x"))
            comment = json.dumps(meta) if server_config.get("metadata_type") == "metadata" else None
            fake_png.write(path, width, height, comment)
        with open(os.path.join(args.settings, "last_task.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)   # the test rig's window on what the engine received
        out.append({"path": path, "settings": meta})
    return out

