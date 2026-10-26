"""The contract between the worker and the engine it reads (Stage 9's capture), over every capture in
`tests/fixtures/contract/<name>-<version>/engine.json` (a `main.py --dump-engine` file): the fake's own (fake-17.17)
and the capture of upstream WanGP 18.05 (upstream-18.05, Stage 10).

Each module that reads the engine declares what it reads (`READS`, each name tagged `both`, `legacy` or `upstream`).
For a capture of one flavour: every name tagged for it is published (names), every field and setting is held by some
shipped model and every suffix rule matches a key (fields), each but where `GAPS` says why not; the fake root that
stands in for the capture (`STAND_INS`) agrees with it on every one of those fields (fake equals capture), the
one-pass answer is pinned as observed, and an AST walk finds no read a module left out of its `READS`.
"""
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from hub.worker import catalog, catalogvideo, definitions, wan2gp
from hub.worker.adapters import fork, modelfiles, upstream, upstream_weights, voiceconvert
from tests.engine.helpers import ENGINE_PYTHON, FAKE_ENGINE, FIXTURES, UPSTREAM_H3, WORKER, make_engine_root

CAPTURES = sorted(p.parent for p in (FIXTURES / "contract").glob("*/engine.json"))
MODULES: list[ModuleType] = [catalog, catalogvideo, definitions, wan2gp, fork, upstream, upstream_weights,
                             modelfiles, voiceconvert]
CATEGORIES = ("wgp", "api", "definition", "settings", "generate_video", "suffixes")
TAGS = ("both", "legacy", "upstream")
# Read, but no dump can show it, by construction.
UNSEEN = {"path": "dropped from every definition (redaction rule 1)",
          "hub_auto": "the Hub's own pointer field: pointers are left out of a dump",
          "hub_base": "the Hub's own pointer field: pointers are left out of a dump",
          "hub_files": "the Hub's own field in a model's file choices (adapters/modelfiles.py), never in a dump",
          "events": "a job's instance attribute: seen only once a task runs",
          "_thread": "a job's private instance attribute: seen only once a task runs"}
# Read, but not in the capture: the fake carries no model that sets it (its own capture), or the engine line does not
# publish it and the read finds nothing there (18.05). A name starting "_" is a suffix rule. Each listed name must
# really be missing there, so the list cannot go stale.
FORK_FAMILY = "the HocusPocus line's key family (upstream.facts.json `families`): 18.05 has none (R9 §5)"
GAPS = {"fake-17.17": {"embedded_guidance": "no fake model uses embedded guidance",
                       "finetune_custom_urls": "the fake's 17.17 models list no files of their own (18.05's H3 does)",
                       "vision_encoder_filename": "no fake 17.17 model has a separate vision encoder (18.05's krea2)",
                       "text_encoder_URLs": "the fake's 17.17 models name no text encoder file (18.05's do)",
                       "transformer_quantization": "the fake publishes no quantization globals; upstream 18.05 does "
                                                   "(wgp.py:3455), read by upstream_weights.runtime_def",
                       "text_encoder_quantization": "as transformer_quantization (upstream wgp.py:3462)",
                       "mesh_outputs": "no fake model makes a 3D asset (18.05's do: test_upstream_capture)",
                       "lock_inference_steps": "no fake model locks its steps",
                       "no_lora": "no fake model refuses LoRAs",
                       "audio_only": "no fake model is audio only",
                       "reference_video_max_frames": "no fake 17.17 model takes a reference video (18.05's Ref2VA "
                                                     "does)",
                       "system_configs": "the fake's upstream flavour carries the fork's H3 definitions: no config "
                                         "groups (upstream H3's text encoders, upstream.native)",
                       "text_encoder_variant": "the same: the fork's H3 definitions name no text encoder variant",
                       "resolution_budget": "the same: no fake model names its budget (upstream's H3 does, "
                                            "tests/fixtures/upstream-18.05; the default stands for the rest)",
                       "audio_overlap_repair_ms": "the same: the fork's H3 definitions join no sound across a "
                                                  "continue (upstream's H3 does: 25 ms, minimax_h3_handler.py:651)"},
        "upstream-18.05": {"generate_video": "18.05 has none (its generate_media): no engine one-pass switch, "
                                             "and one pass is the window's (upstream.window)",
                           "frames_maximum": "18.05 caps a clip by its window (window_default, upstream.native)",
                           "text_encoder_variant": "no shipped definition sets it; the H3 handler reads it when a "
                                                   "finetune does (minimax_h3_handler.py:350)",
                           **dict.fromkeys(("omni_reference", "omni_reference_limits", "omni_reference_detail_choices",
                                            "omni_reference_detail_default", "_multi_window", "_reference_detail",
                                            "_sidecar", "_text_encoder_default", "_text_encoder_variants"),
                                           FORK_FAMILY)}}
# The one-pass answer (R9 §2), as each capture's catalog gives it: Stage 5b's fix matches reality or this names it.
# 18.05: none (no switch; a clip is one pass when its window holds it).
PINNED = {"fake-17.17": {m: {"minimax_h3_multi_window": False}
                         for m in ("minimax_h3", "minimax_h3_fused_turbo", "minimax_h3_ref2va")},
          "upstream-18.05": dict.fromkeys((f"minimax_h3_{m}" for m in (
              "fl2va", "fl2va_pdd", "fl2va_pruned", "fl2va_pruned_pdd", "fl2va_pruned_veda", "fl2va_veda", "ref2va",
              "ref2va_pdd", "ref2va_pruned", "ref2va_pruned_pdd", "ref2va_pruned_veda", "ref2va_veda", "vdn",
              "vdn_pruned")), None)}
# The fake root that stands in for each capture (`make_engine_root` arguments) and the models compared: the fake's
# own capture against the fake as its overlay keeps it; 18.05 against the root written from it, on its models.
STAND_INS = {"fake-17.17": {"flavour": "upstream", "h3": False}, "upstream-18.05": {"flavour": "upstream", "h3": True}}
MISSING = object()


def capture(folder: Path) -> dict[str, Any]:
    return json.loads((folder / "engine.json").read_text(encoding="utf-8"))


def reads(flavour: str) -> dict[str, set[str]]:
    """Every name the modules read that the `flavour` line publishes."""
    out: dict[str, set[str]] = {c: set() for c in CATEGORIES}
    for module in MODULES:
        for category, names in module.READS.items():
            out[category] |= {n for n, tag in names.items() if tag in ("both", flavour)}
    return out


def keys_of(models: dict[str, Any]) -> tuple[set[str], set[str]]:
    """(definition fields, settings and factory keys) over every shipped model."""
    fields, settings = set(), set()
    for m in models.values():
        fields |= set(m["definition"])
        settings |= set(m["settings"]) | set(m["factory"])
    return fields, settings


def published(doc: dict[str, Any]) -> set[str]:
    names = {n for k, v in doc["names"].items() if k != "probe" for n in v}
    names |= {n for n, there in doc["names"]["probe"].items() if there}
    names |= {p["name"] for p in doc["generate_video"] or []}
    for cls in doc["classes"].values():
        names |= set(cls["attributes"]) | set(cls["fields"] or [])
    return names


def test_every_module_declares_its_reads():
    for module in MODULES:
        assert tuple(module.READS) == CATEGORIES, module.__name__
        bad = [(c, n, t) for c, names in module.READS.items() for n, t in names.items() if t not in TAGS]
        assert bad == [], module.__name__


@pytest.fixture(scope="module", params=CAPTURES, ids=[p.name for p in CAPTURES])
def doc(request) -> dict[str, Any]:
    out = capture(request.param)
    out["_name"] = request.param.name
    return out


def skipped(doc: dict[str, Any], name: str) -> bool:
    return name in UNSEEN or name in GAPS.get(doc["_name"], {})


def test_every_name_read_is_published(doc):
    want, have = reads(doc["engine"]["flavour"]), published(doc)
    missing = sorted(f"{c}:{n}" for c in ("wgp", "api", "generate_video") for n in want[c]
                     if n not in have and not skipped(doc, n))
    assert missing == [], "read but not published (dead or wrong)"


def test_every_field_read_is_held_by_a_shipped_model(doc):
    want = reads(doc["engine"]["flavour"])
    fields, settings = keys_of(doc["models"])
    keyword = {p["name"] for p in doc["generate_video"] or []}
    missing = [f"definition:{n}" for n in sorted(want["definition"]) if n not in fields and not skipped(doc, n)]
    missing += [f"settings:{n}" for n in sorted(want["settings"]) if n not in settings and not skipped(doc, n)]
    missing += [f"suffix:{s}" for s in sorted(want["suffixes"])
                if not any(k.endswith(s) for k in fields | settings | keyword) and not skipped(doc, s)]
    assert missing == [], "read but held by no shipped model (dead or wrong)"
    present = fields | settings | keyword | published(doc)
    stale = [n for n in GAPS.get(doc["_name"], {})
             if (any(k.endswith(n) for k in present) if n.startswith("_") else n in present)]
    assert stale == [], "listed as a gap but present: take it off GAPS"


@pytest.fixture(scope="module")
def fake_dump(doc, tmp_path_factory) -> dict[str, Any]:
    base = tmp_path_factory.mktemp(f"fake-{doc['_name']}")
    root = make_engine_root(base, **STAND_INS[doc["_name"]])
    out = base / "engine.json"
    subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--dump-engine", str(out)],
                   check=True, capture_output=True, timeout=60)
    return json.loads(out.read_text(encoding="utf-8"))


def edited(facts: dict[str, Any], edit: dict[str, Any]) -> dict[str, Any]:
    """A capture model with the overlay's test-only edits applied (null removes a field)."""
    facts = json.loads(json.dumps(facts))
    for target, changes in ((facts["definition"], edit.get("model") or {}),
                            (facts["settings"], edit.get("settings") or {})):
        for k, v in changes.items():
            target.pop(k, None) if v is None else target.__setitem__(k, v)
    return facts


def compared(name: str) -> tuple[dict[str, str], dict[str, Any]]:
    """({capture model: fake model}, test-only edits by fake model) for the capture `name`."""
    if STAND_INS[name]["h3"]:
        return {m: m for m in json.loads(UPSTREAM_H3.read_text(encoding="utf-8"))["models"]}, {}
    overlay = json.loads((FAKE_ENGINE / "overlay.json").read_text(encoding="utf-8"))
    return overlay["keep"], overlay.get("edits") or {}


def test_the_fake_equals_the_capture_on_every_field_read(doc, fake_dump):
    keep, edits = compared(doc["_name"])
    want = reads(doc["engine"]["flavour"])
    differ, held = [], 0
    for model_type, fake_id in sorted(keep.items()):
        real = edited(doc["models"][model_type], edits.get(fake_id) or {})
        fake = fake_dump["models"][fake_id]
        for part, names in (("definition", want["definition"]), ("settings", want["settings"]),
                            ("factory", want["settings"])):
            keys = names | {k for k in {*real[part], *fake[part]} if any(k.endswith(s) for s in want["suffixes"])}
            held += sum(k in real[part] for k in keys)
            differ += [f"{fake_id}.{part}.{k}" for k in sorted(keys)
                       if real[part].get(k, MISSING) != fake[part].get(k, MISSING)]
    assert held > 100, "the comparison covers the models' fields"
    assert differ == [], "the fake holds a value the engine does not publish"


def test_the_one_pass_answer_is_pinned(doc):
    seen = {m["id"]: m["video"]["one_pass"] for m in doc["catalog"]["models"] if m.get("video")}
    assert doc["_name"] in PINNED, f"pin the one_pass values {doc['_name']} shows: {seen}"
    assert seen == PINNED[doc["_name"]]


def walked(module: ModuleType) -> dict[str, set[str]]:
    """What a module's code reads: `w.<name>` (or `self.w.<name>`, `getattr`/`hasattr(w, "<name>")`), and string
    literals as `.get("…")` or `["…"]` on `model_def` (definition) or `settings`/`factory` (settings)."""
    out: dict[str, set[str]] = {"wgp": set(), "definition": set(), "settings": set()}
    var = {"model_def": "definition", "settings": "settings", "factory": "settings"}

    def engine(node: ast.AST) -> bool:
        return (isinstance(node, ast.Name) and node.id == "w") or (
            isinstance(node, ast.Attribute) and node.attr == "w" and isinstance(node.value, ast.Name)
            and node.value.id == "self")

    def literal(node: ast.AST) -> str | None:
        return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None

    for node in ast.walk(ast.parse(Path(module.__file__).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute) and engine(node.value):
            out["wgp"].add(node.attr)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "hasattr") \
                and len(node.args) >= 2 and engine(node.args[0]) and literal(node.args[1]):
            out["wgp"].add(literal(node.args[1]))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" \
                and isinstance(node.func.value, ast.Name) and node.func.value.id in var and node.args \
                and literal(node.args[0]):
            out[var[node.func.value.id]].add(literal(node.args[0]))
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in var \
                and literal(node.slice):
            out[var[node.value.id]].add(literal(node.slice))
    return out


@pytest.mark.parametrize("module", MODULES, ids=[m.__name__.rsplit(".", 1)[-1] for m in MODULES])
def test_reads_is_complete(module):
    found = walked(module)
    assert any(found.values()) or module in (fork, upstream), "the walk sees the module's reads"
    left_out = sorted(f"{c}:{n}" for c, names in found.items() for n in names if n not in module.READS[c])
    assert left_out == []


def test_the_walk_sees_what_it_should():
    assert {"generate_video"} <= walked(catalogvideo)["wgp"] and "t2v_class" in walked(catalogvideo)["definition"]
    assert "video_length" in walked(catalogvideo)["settings"] and "models_def" in walked(catalog)["wgp"]
    assert {"transformer_type", "wan_model", "server_config"} <= walked(wan2gp)["wgp"]
    assert "get_factory_settings" in walked(upstream)["wgp"] and "i2v_class" in walked(fork)["definition"]
