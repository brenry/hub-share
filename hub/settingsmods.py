"""The modules' settings (`settings.json` `modules`), checked: each module's defaults under the saved values, then
each value in its range. Split from `settings.py` (which holds the schema, the defaults and the save) so the
module numbers can grow: Generate Image's continue cap, the speech turn, join and takes numbers, the plan
gate, the face judge's bar and device, the voice route (`convert`, SeedVC after the render, or `reference`, the
engine's audio reference), the scene's audience (level, fades and longest reaction), a scene's takes (takes per
shot, re-take minutes, words bar; a clip press's too); the retired keys (`RETIRED`, by module, dropped when read);
the sequence's encode. The helpers (`SettingsError`, `_int`, `_bool`, `_tiers`, `PRESETS`) are `settings.py`'s,
taken at the call.
"""
from __future__ import annotations

import copy
from typing import Any

GI = "generate-image"
NUMBERS = (("continue_max_seconds", 10, 600, int), ("speech_turn_seconds", 4.0, 45.0, float),
           ("speech_join_seconds", 0.0, 0.14, float), ("speech_takes_max", 1, 6, int),
           ("speech_words_bar", 0.5, 1.0, float), ("clip_face_bar", 0.1, 0.9, float),
           ("clip_lips_bar", 0.3, 0.9, float), ("frame_close", 0.1, 0.9, float), ("frame_wide", 0.02, 0.5, float),
           ("audience_level", 0.0, 2.0, float), ("audience_fade_in_ms", 0, 2000, int),     # the scene's
           ("audience_fade_out_ms", 0, 4000, int), ("audience_most_ms", 1000, 10000, int),  # audience, in its file only
           ("scene_takes_max", 1, 4, int), ("scene_retake_minutes", 0, 120, int),   # a scene's re-takes,
           ("scene_words_bar", 0.5, 1.0, float),                                    # in its file only
           ("scene_unscripted_seconds", 0.5, 10.0, float))      # speech that is not the line
RETIRED = {GI: ("clip_takes_max", "speech_takes"),          # an older Hub's; dropped when read,
           "storyboard": ("max_cells", "cell_text_max"),    # never refused
           "sequence": ("max_items",)}
FLAGS = ("plan_before_render", "speech_judge", "clip_judge")
DEVICES = ("cpu", "cuda")
ROUTES = ("convert", "reference")          # in settings.json only, no screen
DUCK = (("duck_threshold", 0.001, 1.0), ("duck_ratio", 1.0, 20.0), ("duck_attack_ms", 1.0, 2000.0),
        ("duck_release_ms", 10.0, 9000.0))


def validate(modules: Any) -> dict[str, dict[str, Any]]:
    """The `modules` part, complete and checked; raises `SettingsError` naming the field."""
    from hub import settings as S  # late: that module holds the helpers and imports this one

    if not isinstance(modules, dict) or not all(isinstance(v, dict) for v in modules.values()):
        raise S.SettingsError("modules", "must map module ids to objects")
    mods = dict(modules)
    for mod_id, gone in RETIRED.items():                    # the retired keys go before the merge
        if isinstance(mods.get(mod_id), dict):
            mods[mod_id] = {k: v for k, v in mods[mod_id].items() if k not in gone}
    for mod_id, part in S.DEFAULTS["modules"].items():      # a module's defaults under the saved values
        mods[mod_id] = {**copy.deepcopy(part), **mods.get(mod_id, {})}
    gi, caps = mods[GI], mods[GI]["ref_caps"]
    if not isinstance(caps, dict) or not all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 6
                                             for v in caps.values()):
        raise S.SettingsError(f"modules.{GI}.ref_caps", "must map model id beginnings to 1 to 6 images")
    gi["video_tiers"] = S._tiers(gi["video_tiers"])
    for key, lo, hi, kind in NUMBERS:
        gi[key] = S._int(gi[key], f"modules.{GI}.{key}", lo, hi, kind)
    for key in FLAGS:
        gi[key] = S._bool(gi[key], f"modules.{GI}.{key}")
    if gi["judge_device"] not in DEVICES:
        raise S.SettingsError(f"modules.{GI}.judge_device", f"must be one of {', '.join(DEVICES)}")
    if gi["voice_route"] not in ROUTES:
        raise S.SettingsError(f"modules.{GI}.voice_route", f"must be one of {', '.join(ROUTES)}")
    seq = mods["sequence"]
    seq["join_crf"] = S._int(seq["join_crf"], "modules.sequence.join_crf", 0, 51)
    if seq["join_preset"] not in S.PRESETS:
        raise S.SettingsError("modules.sequence.join_preset", f"must be one of {', '.join(S.PRESETS)}")
    for key, lo, hi in DUCK:                                   # the compressor keyed by track 1
        seq[key] = S._int(seq[key], f"modules.sequence.{key}", lo, hi, float)
    return mods
