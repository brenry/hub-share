"""A real engine as one of its captures shows it (`main.py --dump-engine`, tests/fixtures/contract/): the fixture the
test fake's upstream 18.05 root is written from (`transcribe`, tests/fixtures/upstream-18.05/h3.json), and the engine
module the worker's catalog reads (`CaptureEngine`), so the catalog the worker builds can be checked against the one
the release built on the server. No engine code runs here: every answer is the capture's."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tests.engine.helpers import FIXTURES, UPSTREAM_H3

UPSTREAM_18_05 = FIXTURES / "contract" / "upstream-18.05" / "engine.json"
COMMIT = "af2ed29"
# The models the fake's upstream root carries from the capture: upstream's H3 line, its speech model and Qwen Image
# 2.1 (the 7B and its Turbo, whose step lock the facts file names).
MODELS = ("minimax_h3_fl2va", "minimax_h3_fl2va_pruned", "minimax_h3_fl2va_pdd", "minimax_h3_ref2va",
          "minimax_h3_ref2va_pruned", "minimax_h3_control", "minimax_h3_control_pruned", "viggle_animate",
          "minimax_h3_tts_ref2va_pruned", "qwen_image_21_7B", "qwen_image_21_turbo_7B")
LONG = 400
# The one value a capture holds none of (config values are redacted): the text encoder quantization upstream falls
# back to (wgp.py:2687, 3462).
SERVER_CONFIG = {"text_encoder_quantization": "int8"}
SOURCE = ("The capture of upstream WanGP {version} ({commit}) as the test fake carries it: "
          "tests/fixtures/contract/upstream-{version}/engine.json, the `--dump-engine` of a fresh checkout on the "
          "server. "
          "Per model: architecture, family, LoRA folder, factory settings and definition (its own `settings` "
          "whole; descriptive texts over {long} characters, callables and `metadata` left out: the Hub reads none "
          "of them). The engine's version, families and accepted settings as captured. Written from the capture "
          "by `HUB_WRITE_GOLDEN=1 pytest tests/engine/test_upstream_capture.py`, which checks that the two agree; "
          "`server_config` alone is transcribed, since a capture holds no config value: the text encoder "
          "quantization wgp.py falls back to (2687, 3462).")


def load(path: Path = UPSTREAM_18_05) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def kept(value: Any) -> bool:
    """A definition's own value the fixture keeps: not a callable's stand-in, not a long descriptive text."""
    return not (isinstance(value, str) and (value.startswith("<object:") or len(value) > LONG))


def transcribe(doc: dict[str, Any], models: tuple[str, ...] = MODELS) -> dict[str, Any]:
    """The fixture `make_engine_root(h3=True)` writes the fake from, as the capture `doc` gives it."""
    out: dict[str, Any] = {
        "source": SOURCE.format(version=doc["engine"]["version"], commit=COMMIT, long=LONG),
        "engine": {"flavour": doc["engine"]["flavour"], "version": doc["engine"]["version"], "commit": COMMIT,
                   "settings_version": doc["engine"]["settings_version"]},
        "server_config": dict(SERVER_CONFIG), "families": doc["families"],
        "accepted_settings": doc["accepted_settings"], "models": {}}
    for model_type in models:
        m = doc["models"][model_type]
        definition = {k: v for k, v in m["definition"].items() if k != "metadata" and (k == "settings" or kept(v))}
        out["models"][model_type] = {"architecture": m["architecture"], "family": m["family"],
                                     "lora_key": m["lora_key"], "definition": definition, "factory": m["factory"]}
    return out


def fixture() -> dict[str, Any]:
    return json.loads(UPSTREAM_H3.read_text(encoding="utf-8"))


class CaptureEngine:
    """The engine module (`wgp`) as the worker's catalog reads it, answered from a capture: the shipped models'
    definitions, families, factory settings and LoRA folders; no file is ever found (the dump's own `_Quiet`)."""

    def __init__(self, doc: dict[str, Any], server_config: dict[str, Any]) -> None:
        self._models = doc["models"]
        self.models_def = {t: copy.deepcopy(m["definition"]) for t, m in doc["models"].items()}
        self.families_infos = {k: tuple(v) for k, v in doc["families"].items()}
        self.server_config = dict(server_config)
        self.WanGP_version, self.settings_version = doc["engine"]["version"], doc["engine"]["settings_version"]
        self.args = SimpleNamespace(lora_config={})
        self.model_dropdowns = SimpleNamespace(get_model_download_status=lambda deps, model_type: 0)

    def get_model_def(self, model_type: str) -> dict | None:
        return self.models_def.get(model_type)

    def get_base_model_type(self, model_type: str) -> str | None:
        return self._models[model_type]["architecture"] if model_type in self._models else None

    def get_model_family(self, model_type: str, for_ui: bool = False) -> str:
        return self._models[model_type]["family"]

    def get_factory_settings(self, model_type: str) -> dict:
        return copy.deepcopy(self._models[model_type]["factory"])

    def get_lora_root(self) -> str:
        return "loras"

    def get_model_handler(self, model_type: str) -> Any:
        key = self._models[model_type]["lora_key"]

        def get_lora_dir(base_model_type: str) -> str:
            if key is None:
                raise LookupError(model_type)
            return key
        return SimpleNamespace(get_lora_dir=get_lora_dir)

    def get_model_recursive_prop(self, model_type: str, prop: str = "URLs", return_list: bool = True) -> list:
        value = (self.models_def.get(model_type) or {}).get(prop) or []
        return self.get_model_recursive_prop(value, prop) if isinstance(value, str) else list(value)

    def _get_dropdown_deps(self) -> Any:
        return SimpleNamespace(get_local_model_filename=lambda name: None)
