"""The capture of upstream WanGP 18.05 (tests/fixtures/contract/upstream-18.05/engine.json) against what the Hub
assumes of it: the fixture the fake's upstream root is written from (h3.json, written from the capture), the facts
file's names and rules, and the catalog the worker builds from the capture's own definitions, which must be the
catalog the release built on the server, less the 3D models it leaves out."""
from __future__ import annotations

import copy
import json
import os
from typing import Any

from hub.worker import catalog, enginedump
from hub.worker.adapters import soundtask, upstream
from tests.engine.capture_engine import SERVER_CONFIG, CaptureEngine, fixture, load, transcribe
from tests.engine.helpers import UPSTREAM_H3

DOC = load()
CHECKED = ("minimax_h3_fl2va_pruned", "minimax_h3_ref2va_pruned", "minimax_h3_tts_ref2va_pruned", "qwen_image_21_7B")


def moved(have: Any, want: Any, at: str = "") -> list[str]:
    """Every path where the fixture (`have`) and the capture (`want`) differ, with both values."""
    if isinstance(have, dict) and isinstance(want, dict):
        return [p for k in sorted({*have, *want}) for p in (
            [f"{at}/{k}: only the capture holds it"] if k not in have else
            [f"{at}/{k}: the capture does not hold it"] if k not in want else moved(have[k], want[k], f"{at}/{k}"))]
    return [] if have == want else [f"{at}: {json.dumps(have)[:80]} is {json.dumps(want)[:80]} in the capture"]


def test_the_fake_root_is_written_from_the_capture():
    want = transcribe(DOC)
    if os.environ.get("HUB_WRITE_GOLDEN"):
        UPSTREAM_H3.write_text(json.dumps(want, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    assert moved(fixture(), want) == []


def test_the_capture_is_the_line_the_facts_file_names():
    facts = upstream.facts_file()
    assert DOC["engine"] == {"flavour": "upstream", "version": "18.05", "settings_version": 2.8}
    assert DOC["left_out"] == {"finetunes": 0, "hub_auto": 0, "unreadable": []}, "a fresh checkout: nothing of ours"
    architectures = {m["architecture"] for m in DOC["models"].values()}
    assert set(facts["models"]) <= architectures
    assert set(facts["renamed"]["ids"].values()) | set(facts["steps"]["locked"]) <= set(DOC["models"])
    assert set(facts["renamed"]["ids"]) & set(DOC["models"]) == {"minimax_h3_ref2va"}, "the 33B trap, alone"
    assert set(DOC["models"]) >= set(CHECKED)
    assert DOC["accepted_settings"] and "postprocess_audio" in DOC["accepted_settings"]
    assert not DOC["names"]["probe"]["generate_video"], "18.05 has no generate_video: no engine one-pass switch"


def sorted_encoders(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The entries with each clip's text encoders in name order: a capture's definitions are written with their keys
    sorted, so the engine's own order of its encoder choices is not in it."""
    out = json.loads(json.dumps(entries))
    for entry in out:
        if isinstance(entry.get("video"), dict) and entry["video"].get("text_encoders"):
            entry["video"]["text_encoders"].sort()
    return out


def built_catalog() -> list[dict[str, Any]]:
    """The catalog the current worker builds from the capture, redacted as a dump redacts it."""
    out = catalog.build(CaptureEngine(DOC, SERVER_CONFIG), "/engine", upstream.Upstream())["models"]
    for entry in out:
        for key in enginedump.ENTRY_DROPS:
            entry.pop(key, None)
        if isinstance(entry.get("video"), dict):
            entry["video"].pop("text_encoders_found", None)
            entry["video"].pop("sound_join", None)       # not in the release catalog: checked on its own below
            entry["video"].pop("soundtrack", None)       # not in the release catalog: checked in test_clip_sound
            for key in ("reference_video", "reference_video_seconds"):   # checked in test_clip_video
                entry["video"].pop(key, None)
            entry["video"].pop("voice_reference", None)  # checked in test_voice_reference
    return sorted_encoders(out)


def test_h3s_sound_join_comes_from_its_own_definition():
    """Each H3 line the Hub continues makes one frame's sound again at the join, with the repair its
    definition names (25 ms in 18.05, minimax_h3_handler.py:651); no other model carries a sound join."""
    out = catalog.build(CaptureEngine(DOC, SERVER_CONFIG), "/engine", upstream.Upstream())["models"]
    joins = {e["id"]: e["video"]["sound_join"] for e in out if (e.get("video") or {}).get("sound_join")}
    assert joins and set(next(iter(joins.values()))) == {"frames", "repair_ms"}
    assert all(j == {"frames": 1, "repair_ms": 25.0} for j in joins.values()), joins
    assert all(i.startswith("minimax_h3_") for i in joins), sorted(joins)


def test_the_worker_builds_the_release_catalog_from_the_capture():
    mesh = {t for t, m in DOC["models"].items() if m["definition"].get("mesh_outputs")}
    released = DOC["catalog"]["models"]
    assert len(mesh) >= 10 and {e["id"] for e in released if e["id"] in mesh} == mesh, \
        "the release listed every 3D model as a picture model"
    built = built_catalog()
    assert [e["id"] for e in built if e["kind"] == "speech"] == ["minimax_h3_tts_ref2va_pruned"], "one speech model"
    expected = copy.deepcopy([e for e in released if e["id"] not in mesh])
    for e in expected:                                    # not in the release catalog: Ref2VA continues ("V")
        if (e.get("video") or {}).get("references", {}).get("role") == "identity" and e["id"].startswith("minimax_h3"):
            e["video"].update(continues=True, overlap=18)
    assert [e["id"] for e in built if e["kind"] == "sound"] == [   # the cue models, not in the release catalog
        "stable_audio3_medium", "stable_audio3_small", "stable_audio3_small_sfx"]
    assert [e for e in built if e["kind"] not in ("speech", "sound")] == sorted_encoders(expected)


def test_what_the_catalog_gives_the_models_the_owner_checks():
    entries = {e["id"]: e for e in built_catalog()}
    facts = upstream.facts_file()
    for model_type, refs in (("minimax_h3_fl2va_pruned", {"role": "start", "end": True, "min": 0, "max": 2}),
                             ("minimax_h3_ref2va_pruned", {"role": "identity", "min": 0, "max": 9, "letters": "I",
                                                           "names": False, "cutout": "all"})):
        e = entries[model_type]
        assert e["kind"] == "video" and e["budget"] == 2048 * 2048 and not e["lock_steps"]
        v = e["video"]
        assert v["frames"] == {"min": 107, "step": 17, "max": 362, "default": 124}
        assert (v["window_min"], v["window_max"], v["fps"], v["one_pass"]) == (124, 481, 24, None)
        assert v["tiers"] == facts["tiers"]["h3"]["tiers"] and v["references"] == refs
        assert (v["encoder_key"], v["text_encoder_default"]) == ("config", "int8")
    assert entries["minimax_h3_fl2va_pruned"]["was"] == ["minimax_h3"]
    assert entries["minimax_h3_ref2va_pruned"]["was"] == ["minimax_h3_ref2va"]
    assert entries["minimax_h3_ref2va"]["was"] == ["minimax_h3_ref2va_full"], "the 33B trap"
    qwen, turbo = entries["qwen_image_21_7B"], entries["qwen_image_21_turbo_7B"]
    assert (qwen["kind"], qwen["budget"], qwen["was"], qwen["steps"]) == ("image", 1920 * 1088, ["qwen_image_21"], 40)
    assert (turbo["lock_steps"], turbo["steps"]) == (True, 8)
    speech = DOC["models"]["minimax_h3_tts_ref2va_pruned"]
    assert speech["definition"]["audio_only"] and speech["family"] == "tts"
    voice = entries["minimax_h3_tts_ref2va_pruned"]                      # found by its fields
    assert (voice["kind"], voice["video"], voice["loras"], voice["script"]) == ("speech", None, False, "speaker")
    assert voice["speech"] == {"seconds": {"min": 4, "max": 300, "default": 15}, "references": 1}
    audio = {t for t, m in DOC["models"].items() if m["definition"].get("audio_only")}
    assert len(audio) > 20 and {e["id"] for e in entries.values() if e["id"] in audio and e["kind"] != "sound"} == {
        voice["id"]}, "music and the speech models whose script is not read stay out"
    sounds = {e["id"]: e for e in entries.values() if e["kind"] == "sound"}       # the cue models
    assert {k: e["cues"] for k, e in sounds.items()} == {
        "stable_audio3_small_sfx": {"effect": 0, "reaction": 0, "room": 0},
        "stable_audio3_small": {"music": 0},
        "stable_audio3_medium": {"effect": 1, "reaction": 1, "room": 1, "music": 1}}
    assert [sounds[k]["speech"]["seconds"]["max"] for k in sorted(sounds)] == [380, 120, 120], "the cap's range"
    assert all(not e["loras"] and "why_not" not in e for k, e in sounds.items() if k != "stable_audio3_medium")
    assert sounds["stable_audio3_medium"].get("why_not") == (None if soundtask.flash_ready() else soundtask.BLOCKED)
