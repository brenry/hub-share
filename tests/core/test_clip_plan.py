"""The facts of a clip model from its catalog entry and the sums a clip is planned with (`hub/core/clipplan.py`,
re-exported by `hub.core.api`). The catalog entries are the real worker's answer for the fake engine's
definitions; a picture model gives None."""
from __future__ import annotations

import json
import subprocess

import pytest

from hub.core.api import Invalid, clip_facts, frames_for, snap_frames, tier_size
from tests.engine.helpers import ENGINE_PYTHON, WORKER, load_catalog, make_engine_root


@pytest.fixture(scope="module")
def clips(tmp_path_factory) -> dict[str, dict]:
    base = tmp_path_factory.mktemp("engine")
    root = make_engine_root(base, "legacy")
    out = base / "catalog.json"
    subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--dump-catalog", str(out)],
                   check=True, capture_output=True, timeout=60)
    return {m["id"]: m for m in json.loads(out.read_text())["models"] if m["kind"] == "video"}


def start_model(clips: dict[str, dict]) -> dict:
    return next(m for m in clips.values() if (m["video"].get("references") or {}).get("role") == "start")


def test_every_clip_model_gives_its_facts_from_the_catalog(clips: dict[str, dict]) -> None:
    assert clips, "the fake engine has clip models"
    for model in clips.values():
        facts, own = clip_facts(model), model["video"]
        refs = own.get("references") or {}
        assert facts is not None and set(facts) == {"role", "end", "refs", "fps", "frames", "steps", "tiers",
                                                    "encoders"}
        assert (facts["role"], facts["end"]) == (refs.get("role"), bool(refs.get("end")))
        assert facts["refs"] == {"min": refs.get("min", 0), "max": refs.get("max", 0), "key": refs.get("key")}
        assert (facts["fps"], facts["frames"], facts["steps"]) == (own["fps"], own["frames"], own["steps"])
        assert facts["tiers"] == own["tiers"], "every tier, not only the ones a screen offers"
        assert facts["encoders"] == own.get("text_encoders", [])
    roles = {clip_facts(m)["role"] for m in clips.values()}
    assert {"start", "identity"} <= roles


def test_a_picture_model_gives_none() -> None:
    pictures = load_catalog("catalog_upstream.json")["models"]
    assert pictures and all(clip_facts(m) is None for m in pictures)
    assert clip_facts({"kind": "video", "video": {"tiers": []}}) is None
    assert clip_facts({"kind": "video", "video": None}) is None


def test_a_model_that_takes_no_pictures_has_no_role() -> None:
    facts = clip_facts({"kind": "video", "video": {"tiers": [{"name": "a", "sizes": {"1:1": [64, 64]}}]}})
    assert facts is not None and (facts["role"], facts["end"], facts["refs"]) == (None, False,
                                                                                {"min": 0, "max": 0, "key": None})


def test_snap_frames_keeps_the_lattice(clips: dict[str, dict]) -> None:
    facts = clip_facts(start_model(clips))
    f = facts["frames"]
    assert snap_frames(facts, f["min"]) == f["min"] and snap_frames(facts, f["min"] + 1) == f["min"] + f["step"]
    assert snap_frames(facts, 1) == f["min"] and snap_frames(facts, 10**6) == f["max"]
    for odd in (None, True, 3.5, "130"):
        assert snap_frames(facts, odd) == f["default"]
    assert all((snap_frames(facts, n) - f["min"]) % f["step"] == 0 for n in range(f["min"], f["max"]))


def test_frames_for_is_seconds_times_fps_snapped(clips: dict[str, dict]) -> None:
    facts = clip_facts(start_model(clips))
    f, fps = facts["frames"], facts["fps"]
    for seconds in (1, 5, 5.5, 6, 30):
        assert frames_for(facts, seconds) == snap_frames(facts, round(seconds * fps))
        assert frames_for(facts, seconds) >= min(f["max"], round(seconds * fps)), "never shorter than asked"
    for odd in (None, True, "5", float("nan"), float("inf")):
        assert frames_for(facts, odd) == f["default"]


def test_tier_size_takes_a_tier_by_name(clips: dict[str, dict]) -> None:
    facts = clip_facts(start_model(clips))
    for tier in facts["tiers"]:
        for aspect, (w, h) in tier["sizes"].items():
            assert tier_size(facts, tier["name"], aspect, 1.0) == (w, h)
    first = facts["tiers"][0]
    wide = max(first["sizes"].values(), key=lambda s: s[0] / s[1])
    assert tier_size(facts, first["name"], "auto", 10.0) == tuple(wide), "no such aspect: the size nearest the ratio"
    with pytest.raises(Invalid) as err:
        tier_size(facts, "no such tier", "1:1", 1.0)
    assert err.value.field == "tier"
