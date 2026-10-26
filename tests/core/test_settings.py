"""Settings: defaults, validation, bind rules, UI edits, atomic writes, derived hosts."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from hub import settings as cfg
from hub.core import store
from hub.settings_edit import ui_patch


def base() -> dict:
    return copy.deepcopy(cfg.DEFAULTS)


def test_defaults_are_complete_and_hold_no_machine_facts() -> None:
    s = cfg.validate({})
    assert s["server"] == {"bind": ["127.0.0.1"], "port": 42010, "extra_hosts": [], "allow_any_interface": False}
    assert s["vram"]["idle_unload"] is True and s["vram"]["idle_minutes"] == 10
    assert s["queue"]["max_waiting"] == 10 and s["gpus"] == []
    assert "192.168" not in json.dumps(cfg.DEFAULTS)


@pytest.mark.parametrize("addr", ["0.0.0.0", "::"])
def test_any_interface_is_refused_unless_allowed(addr: str) -> None:
    s = base()
    s["server"]["bind"] = [addr]
    with pytest.raises(cfg.SettingsError, match="every network"):
        cfg.validate(s)
    s["server"]["allow_any_interface"] = True
    assert cfg.validate(s)["server"]["bind"] == [addr]


@pytest.mark.parametrize("patch, field", [
    ({"server": {"bind": ["lan-host"]}}, "server.bind"),
    ({"server": {"bind": []}}, "server.bind"),
    ({"server": {"bind": ["10.0.0.2", "10.0.0.2"]}}, "server.bind"),
    ({"server": {"port": 0}}, "server.port"),
    ({"server": {"port": "42010"}}, "server.port"),
    ({"server": {"extra_hosts": ["no port"]}}, "server.extra_hosts"),
    ({"vram": {"idle_minutes": 1}}, "vram.idle_minutes"),
    ({"vram": {"idle_unload": "yes"}}, "vram.idle_unload"),
    ({"queue": {"max_waiting": 0}}, "queue.max_waiting"),
    ({"gpus": [{"id": "gpu0", "index": 0, "uuid": None, "engine": True, "extra": 1}]}, "gpus[0]"),
    ({"gpus": [{"id": "g", "index": 0, "uuid": None, "engine": True}] * 2}, "gpus[1].id"),
    ({"diagnostics": 1}, "diagnostics"),
    ({"surprise": True}, "surprise"),
    ({"server": {"surprise": 1}}, "server.surprise"),
    ({"modules": {"generate-image": {"ref_caps": {"some_model": 9}}}}, "modules.generate-image.ref_caps"),
    ({"modules": {"generate-image": {"ref_caps": {"some_model": True}}}}, "modules.generate-image.ref_caps"),
    ({"modules": {"generate-image": {"video_tiers": 0}}}, "modules.generate-image.video_tiers"),
    ({"modules": {"generate-image": {"video_tiers": 4}}}, "modules.generate-image.video_tiers"),
    ({"modules": {"generate-image": {"video_tiers": True}}}, "modules.generate-image.video_tiers"),
    ({"modules": {"generate-image": {"video_tiers": "540p"}}}, "modules.generate-image.video_tiers"),
    ({"modules": {"generate-image": {"video_tiers": []}}}, "modules.generate-image.video_tiers"),
    ({"modules": {"generate-image": {"video_tiers": ["540p", "540p"]}}}, "modules.generate-image.video_tiers"),
    ({"modules": {"generate-image": {"video_tiers": ["a", "b", "c", "d"]}}}, "modules.generate-image.video_tiers"),
    ({"modules": {"generate-image": {"video_tiers": ["5 40p"]}}}, "modules.generate-image.video_tiers"),
    ({"modules": {"generate-image": {"video_tiers": [540]}}}, "modules.generate-image.video_tiers"),
    ({"modules": {"generate-image": {"video_tiers": ["xxxxxxxxxxxxxxxxx"]}}}, "modules.generate-image.video_tiers"),
    ({"engine": {"profile_video": 6}}, "engine.profile_video"),
])
def test_bad_values_name_the_field(patch: dict, field: str) -> None:
    s = base()
    for key, value in patch.items():
        s[key] = {**s[key], **value} if isinstance(value, dict) else value
    with pytest.raises(cfg.SettingsError) as e:
        cfg.validate(s)
    assert e.value.field == field
    assert str(e.value).startswith("settings.json: ")


def test_load_missing_and_corrupt(tmp_path: Path) -> None:
    with pytest.raises(cfg.SettingsError, match="hub init"):
        cfg.load(tmp_path)
    (tmp_path / "settings.json").write_text("{nope")
    with pytest.raises(cfg.SettingsError, match="not valid JSON"):
        cfg.load(tmp_path)


def test_save_is_atomic_and_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg.save(tmp_path, cfg.validate({}))
    path = tmp_path / "settings.json"
    assert os.stat(path).st_mode & 0o777 == 0o600
    before = path.read_text()

    def crash(src: str, dst: str) -> None:
        raise OSError("power cut")

    monkeypatch.setattr(store.os, "replace", crash)
    s = cfg.validate({})
    s["vram"]["idle_minutes"] = 30
    with pytest.raises(OSError):
        cfg.save(tmp_path, s)
    assert path.read_text() == before
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_a_left_over_temp_file_never_replaces_the_original(tmp_path: Path) -> None:
    cfg.save(tmp_path, cfg.validate({}))
    (tmp_path / ".settings.json.abc.tmp").write_text("{half")
    assert cfg.load(tmp_path)["version"] == 2


@pytest.mark.parametrize("value", [4, 4.0, 7.5, 45])
def test_the_speech_turn_takes_seconds_from_4_to_45(value) -> None:
    turn = cfg.validate({"modules": {"generate-image": {"speech_turn_seconds": value}}})
    assert turn["modules"]["generate-image"]["speech_turn_seconds"] == float(value)


@pytest.mark.parametrize("value", [3.9, 45.5, True, "5", None])
def test_a_speech_turn_outside_4_to_45_is_refused(value) -> None:
    with pytest.raises(cfg.SettingsError) as err:
        cfg.validate({"modules": {"generate-image": {"speech_turn_seconds": value}}})
    assert str(err.value) == ("settings.json: modules.generate-image.speech_turn_seconds: must be a number from 4.0 "
                              "to 45.0")


AUDIENCE = {"audience_level": 0.6, "audience_fade_in_ms": 100, "audience_fade_out_ms": 1000,
            "audience_most_ms": 4000}
SCENE = {"scene_takes_max": 2, "scene_retake_minutes": 15, "scene_words_bar": 0.8,
         "scene_unscripted_seconds": 2.5}


def test_module_defaults_sit_under_what_the_owner_set() -> None:
    caps, tiers = cfg.DEFAULTS["modules"]["generate-image"]["ref_caps"], ["540p", "720p"]
    s = cfg.validate({"modules": {"loras": {"folders": []}}})
    assert s["modules"] == {"loras": {"folders": []}, "generate-image": {"ref_caps": caps, "video_tiers": tiers,
                                                                         "continue_max_seconds": 60,
                                                                         "speech_turn_seconds": 5.0,
                                                                         "speech_join_seconds": 0.10,
                                                                         "plan_before_render": True,
                                                                         "speech_takes_max": 3,
                                                                         "speech_words_bar": 0.9,
                                                                         "speech_judge": True, "clip_judge": True,
                                                                         "clip_face_bar": 0.3,
                                                                         "judge_device": "cpu", "clip_lips_bar": 0.6,
                                                                         "frame_close": 0.3, "frame_wide": 0.12,
                                                                         "voice_route": "convert",
                                                                         **AUDIENCE, **SCENE},
                            "storyboard": {},
                            "sequence": {"join_crf": 18, "join_preset": "medium", **DUCK}}
    mine = cfg.validate({"modules": {"generate-image": {"ref_caps": {"my_model": 5}}}})
    assert mine["modules"]["generate-image"] == {"ref_caps": {"my_model": 5}, "video_tiers": tiers,
                                                 "continue_max_seconds": 60, "speech_turn_seconds": 5.0,
                                                 "speech_join_seconds": 0.10, "plan_before_render": True,
                                                 "speech_takes_max": 3, "speech_words_bar": 0.9,
                                                 "speech_judge": True, "clip_judge": True, "clip_face_bar": 0.3,
                                                 "judge_device": "cpu", "clip_lips_bar": 0.6,
                                                 "frame_close": 0.3, "frame_wide": 0.12,
                                                 "voice_route": "convert", **AUDIENCE, **SCENE}, \
        "the saved table replaces the default"


def test_the_retired_take_keys_load_and_are_saved_without(tmp_path) -> None:
    """A file holding the retired `clip_takes_max` and `speech_takes` loads; the next save drops
    them; every other module key is kept."""
    import json

    raw = cfg.validate({})
    raw["modules"]["generate-image"].update(clip_takes_max=1, speech_takes=1, speech_takes_max=2)
    (tmp_path / cfg.FILE).write_text(json.dumps(raw))
    s = cfg.load(tmp_path)
    gi = s["modules"]["generate-image"]
    assert "clip_takes_max" not in gi and "speech_takes" not in gi and gi["speech_takes_max"] == 2
    cfg.save(tmp_path, raw)
    saved = json.loads((tmp_path / cfg.FILE).read_text())["modules"]["generate-image"]
    assert "clip_takes_max" not in saved and "speech_takes" not in saved and saved["speech_takes_max"] == 2
    assert "clip_takes_max" not in cfg.validate({"modules": {"generate-image": {"clip_takes_max": 99}}})[
        "modules"]["generate-image"], "dropped before its range is checked: never refused"


def test_ui_patch_allows_only_idle_diagnostics_and_folders() -> None:
    s = cfg.validate({})
    new = ui_patch(s, {"vram": {"idle_minutes": 20, "idle_unload": False}, "diagnostics": True})
    assert new["vram"]["idle_minutes"] == 20 and new["vram"]["idle_unload"] is False and new["diagnostics"]
    assert s["vram"]["idle_minutes"] == 10
    for bad in ({"server": {"port": 1}}, {"queue": {"max_waiting": 1}}, {"engine": {"args": []}}, {"gpus": []},
                {"modules": {"assistant": {}}}, {"paths": {"data": "/"}}, []):
        with pytest.raises(cfg.SettingsError):
            ui_patch(s, bad)
    with pytest.raises(cfg.SettingsError):
        ui_patch(s, {"vram": {"idle_minutes": 500}})


def test_hosts_and_links_follow_the_binds() -> None:
    s = base()
    s["server"].update(bind=["192.0.2.10", "127.0.0.1"], extra_hosts=["assistant.example:42010"])
    s = cfg.validate(s)
    assert cfg.hosts(s, 42010) == {"192.0.2.10:42010", "127.0.0.1:42010", "localhost:42010", "assistant.example:42010"}
    assert cfg.link_base(s) == "http://192.0.2.10:42010"
    s["server"].update(bind=["::1"], extra_hosts=[])
    assert cfg.hosts(s, 5) == {"[::1]:5"}


def test_memory_profile_is_the_engines_own_or_one_of_its_numbers() -> None:
    assert cfg.validate({})["engine"]["profile"] == "engine", "the engine's own by default"
    for value in ("engine", 1, 2, 3, 3.5, 4, 4.5, 5):
        assert cfg.validate({"engine": {"profile": value}})["engine"]["profile"] == value
    whole = cfg.validate({"engine": {"profile": 5.0}})["engine"]["profile"]
    assert whole == 5 and isinstance(whole, int), "a whole profile is kept whole"
    for bad in (0, 6, 3.2, -1, True, "5", "", None, [5]):
        with pytest.raises(cfg.SettingsError) as e:
            cfg.validate({"engine": {"profile": bad}})
        assert e.value.field == "engine.profile" and "engine or one of 1, 2, 3, 3.5, 4, 4.5, 5" in e.value.text
    assert ui_patch(cfg.validate({}), {"engine": {"profile": 4.5}})["engine"]["profile"] == 4.5
    assert [c["value"] for c in cfg.profile_choices()] == ["engine", *cfg.PROFILES]


def test_video_profile_follows_the_profile_or_is_one_of_its_choices() -> None:
    assert cfg.validate({})["engine"]["profile_video"] == "same", "same as above by default"
    for value in ("same", "engine", 1, 3.5, 5):
        assert cfg.validate({"engine": {"profile_video": value}})["engine"]["profile_video"] == value
    for bad in (0, 6, True, "", None, "Same"):
        with pytest.raises(cfg.SettingsError) as e:
            cfg.validate({"engine": {"profile_video": bad}})
        assert e.value.field == "engine.profile_video" and "same or engine or one of 1, 2" in e.value.text
    with pytest.raises(cfg.SettingsError) as e:
        cfg.validate({"engine": {"profile": "same"}})
    assert e.value.field == "engine.profile", "the general profile has nothing above it to follow"
    assert ui_patch(cfg.validate({}), {"engine": {"profile_video": 4}})["engine"]["profile_video"] == 4
    assert [c["value"] for c in cfg.video_profile_choices()] == ["same", "engine", *cfg.PROFILES]
    assert cfg.video_profile_choices()[0]["label"] == "Same as above"


def test_video_sizes_are_a_count_or_up_to_three_names() -> None:
    assert cfg.validate({})["modules"]["generate-image"]["video_tiers"] == ["540p", "720p"], "the saved menu"
    for value in (1, 3, ["720p"], ["540p", "1080p", "480p"], ["8k"]):
        assert cfg.validate({"modules": {"generate-image": {"video_tiers": value}}})["modules"]["generate-image"][
            "video_tiers"] == value
    s = cfg.validate({})
    new = ui_patch(s, {"modules": {"generate-image": {"video_tiers": ["720p", "1080p"]}}})
    assert new["modules"]["generate-image"] == {**s["modules"]["generate-image"], "video_tiers": ["720p", "1080p"]}
    for bad in ({"modules": {"generate-image": {"ref_caps": {}}}}, {"modules": {"generate-image": []}},
                {"modules": {"generate-image": {"video_tiers": []}}}):
        with pytest.raises(cfg.SettingsError) as e:
            ui_patch(s, bad)
        assert e.value.field.startswith("modules.generate-image")


DUCK = {"duck_threshold": 0.05, "duck_ratio": 6.0, "duck_attack_ms": 50.0, "duck_release_ms": 400.0}


def test_the_sequence_settings_and_each_bound() -> None:
    assert cfg.validate({})["modules"]["sequence"] == {"join_crf": 18, "join_preset": "medium", **DUCK}
    assert "sequence" not in cfg.validate({})["modules_disabled"], "Edit Video is on by default"
    ok = cfg.validate({"modules": {"sequence": {"max_items": 999, "join_crf": 0, "join_preset": "veryslow",
                                                "duck_ratio": 4}}})
    assert ok["modules"]["sequence"] == {"join_crf": 0, "join_preset": "veryslow", **DUCK,
                                         "duck_ratio": 4.0}, "a whole number is a float setting too"
    presets = "must be one of ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow"
    for retired in (0, 1000, True, "any"):                       # retired, dropped when read
        assert "max_items" not in cfg.validate({"modules": {"sequence": {"max_items": retired}}})["modules"]["sequence"]
    for key, bad, text in (("duck_threshold", 0, "must be a number from 0.001 to 1.0"),
                           ("duck_ratio", 21, "must be a number from 1.0 to 20.0"),
                           ("duck_attack_ms", "50", "must be a number from 1.0 to 2000.0"),
                           ("duck_release_ms", True, "must be a number from 10.0 to 9000.0"),
                           ("join_crf", -1, "must be a whole number from 0 to 51"),
                           ("join_crf", 52, "must be a whole number from 0 to 51"),
                           ("join_crf", 18.0, "must be a whole number from 0 to 51"),
                           ("join_preset", "turbo", presets), ("join_preset", ["medium"], presets)):
        with pytest.raises(cfg.SettingsError) as e:
            cfg.validate({"modules": {"sequence": {key: bad}}})
        assert (e.value.field, e.value.text) == (f"modules.sequence.{key}", text)
        assert str(e.value) == f"settings.json: modules.sequence.{key}: {text}"


@pytest.mark.parametrize("value", [0.4, 10.5, True, "2.5", None])
def test_unscripted_seconds_outside_half_to_ten_is_refused(value) -> None:
    with pytest.raises(cfg.SettingsError) as err:
        cfg.validate({"modules": {"generate-image": {"scene_unscripted_seconds": value}}})
    assert str(err.value) == ("settings.json: modules.generate-image.scene_unscripted_seconds: must be a number from "
                              "0.5 to 10.0")
