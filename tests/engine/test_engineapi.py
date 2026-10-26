"""The Hub's side of the engine seam (`hub/worker/engineapi.py`, `enginewire.py`) and the adapters behind it: the
types round-trip through the wire and refuse what they do not know; a request crosses with its kind; `select` picks the
adapter for each fake flavour and refuses a root no adapter drives in one line; the facts files hold only what an
adapter may name."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from hub.worker import adapters, engineapi, enginewire
from hub.worker.adapters import fork, upstream
from hub.worker.engineapi import (
    Canvas,
    ClipRequest,
    Done,
    Encoders,
    Failure,
    Frames,
    Guidance,
    JoinItem,
    JoinRequest,
    JoinSound,
    KeyFamilies,
    Loras,
    ModelFacts,
    PictureRequest,
    Progress,
    Reference,
    References,
    Steps,
    Tier,
    Video,
)
from tests.engine.helpers import FIXTURES, make_engine_root

CLIP = ModelFacts(
    id="m", name="M", family="F", status="available", kind="video", base=None, steps=Steps(20, 1, 50, False),
    guidance=None, block=32, loras=None, references=References(["identity"], 1, 9),
    video=Video(fps=24, frames=Frames(124, 17, 345, 141), tiers=[Tier("540p", {"16:9": [960, 544]})],
                encoders=Encoders(["a", "b"], {"a": "A", "b": "B"}, "a", None), one_pass=True, continues=True,
                overlap=18))
PICTURE = ModelFacts(id="p", name="P", family="F", status="partial", kind="image", base="q",
                     steps=Steps(4, locked=True), guidance=Guidance(1.5), block=16, loras=Loras(["/l"], True),
                     references=None, video=None, why_not="one line")


JOIN = JoinRequest([JoinItem("/c/a.mp4", 0, 124, 24.0, 960, 544, 124, True)], Canvas(960, 544, 24.0), [], 18,
                   "medium")
REQUESTS = [
    PictureRequest("p", "a cat", (64, 48), 7, steps=4, guidance=1.0, loras=[("ink", 0.8)],
                   references=[Reference("/a.png", "reference")]),
    ClipRequest("m", "a shot", (960, 544), 7, 141, references=[Reference("/a.png", "identity", "Character 11", True)],
                encoder="a", detail="max"),
    ClipRequest("m", "on", (960, 544), 1, 107, steps=20, references=[Reference("/c/a.mp4", "source")]),
    JOIN,
]


def through_the_wire(value):
    return enginewire.parse(type(value), json.loads(json.dumps(enginewire.wire(value))))


@pytest.mark.parametrize("value", [
    CLIP, PICTURE, *REQUESTS,
    Progress("denoising", 3, 20, "Denoising"), Done(False, "m", Failure("oom", "Out of GPU memory")), Done(True, None),
], ids=lambda v: type(v).__name__)
def test_types_round_trip_through_the_wire(value):
    assert through_the_wire(value) == value


@pytest.mark.parametrize("request_", REQUESTS, ids=lambda r: r.kind)
def test_a_request_crosses_with_its_kind(request_):
    data = json.loads(json.dumps(enginewire.request_wire(request_)))
    assert data["kind"] == request_.kind and enginewire.request_parse(data) == request_
    assert {r.role for r in getattr(request_, "references", [])} <= set(engineapi.ROLES)


def test_a_join_item_keeps_its_wire_names():
    item = enginewire.wire(JOIN)["items"][0]
    assert list(item) == ["path", "in", "out", "fps", "w", "h", "frames", "audio", "sound"], \
        "the join's own words (join.py)"
    placed = enginewire.wire(JoinSound("/s/fx.wav", 3000, 0, 500, 1000.0))
    assert list(placed) == ["path", "at_ms", "in", "out", "fps", "level", "fade_in", "fade_out", "duck"]
    assert enginewire.parse(JoinSound, placed).in_ == 0
    old = {"path": "/s/fx.wav", "at_ms": 3000, "in": 0, "out": 500, "fps": 1000.0}
    assert enginewire.parse(JoinSound, old) == JoinSound("/s/fx.wav", 3000, 0, 500, 1000.0), "a bed's keys default"
    with pytest.raises(ValueError, match="unknown field in_"):
        enginewire.parse(JoinItem, {**item, "in_": 0})
    for bad, said in (({"kind": "settings"}, "unknown kind 'settings'"), ({}, "unknown kind None"),
                      ({"kind": "video", "model_type": "m"}, "unknown field model_type")):
        with pytest.raises(ValueError, match=said):
            enginewire.request_parse(bad)


def test_parse_refuses_what_it_does_not_know():
    wire = enginewire.wire(CLIP)
    for bad, said in (({**wire, "extra": 1}, "unknown field extra"),
                      ({**wire, "video": {**wire["video"], "chain": True}}, "unknown field chain"),
                      ({k: v for k, v in wire.items() if k != "name"}, "missing field name"),
                      ({**wire, "block": "32"}, "block"),
                      ({**wire, "steps": {**wire["steps"], "locked": 1}}, "locked")):
        with pytest.raises(ValueError, match=said):
            enginewire.parse(ModelFacts, bad)
    with pytest.raises(ValueError, match="size"):
        enginewire.parse(ClipRequest, {**enginewire.wire(ClipRequest("m", "p", (1, 2), 1, 9)), "size": [1, 2, 3]})
    assert (PictureRequest.kind, ClipRequest.kind, JoinRequest.kind) == ("image", "video", "join")
    assert set(engineapi.EVENTS) == {"loading", "loaded", "progress", "output", "done"}


def test_select_picks_each_flavour_and_refuses_a_stranger(tmp_path):
    root = str(make_engine_root(tmp_path / "e"))
    assert adapters.select(root, SimpleNamespace(list_model_defs=lambda: [])).name == "upstream"
    assert adapters.select(root, SimpleNamespace()).name == "fork", "an opened session without the listing call"
    assert adapters.select(root).name == "fork", "before opening: the fake's api defines no listing call"
    lister = tmp_path / "lister"
    (lister / "shared").mkdir(parents=True)
    (lister / "wgp.py").write_text("")
    (lister / "shared" / "api.py").write_text("class S:\n    def list_model_defs(self):\n        return []\n")
    assert adapters.select(str(lister)).name == "upstream", "before opening: the api defines it"
    with pytest.raises(engineapi.NoAdapter) as err:
        adapters.select(str(tmp_path / "nothing"))
    assert len(str(err.value).splitlines()) == 1 and "nothing" in str(err.value)
    assert [adapters.by_flavour(f).name for f in ("legacy", "upstream")] == ["fork", "upstream"]


def test_every_adapter_meets_the_protocol():
    assert [a.name for a in adapters.ADAPTERS] == ["upstream", "fork"], "probe order"
    for adapter in adapters.ADAPTERS:
        assert isinstance(adapter, engineapi.Adapter), adapter.name
        assert isinstance(adapter.families, KeyFamilies)
    assert (fork.Fork.factory_underneath, upstream.Upstream.factory_underneath) == (True, False)


# Model ids R16 read from the fork's code (§3.1) that no capture holds: the fork's renamed ids (its engine was never
# captured; the fake's capture holds the rest). Upstream's are all in the capture of 18.05.
READ_IN_R16 = {"minimax_h3_full", "minimax_h3_ref2va_full", "qwen_image_21"}


def test_facts_files_name_families_and_known_models_only():
    """A facts file names only the types and architectures a capture holds (the fake's, and the one of upstream
    18.05), or the fork ids R16 read from code (`READ_IN_R16`): in `models`, the rename map, the step locks and
    the speech scripts."""
    known = {n for p in (FIXTURES / "contract").glob("*/engine.json")
             for t, m in json.loads(p.read_text())["models"].items() for n in (t, m["architecture"])}
    for adapter in adapters.ADAPTERS:
        facts = adapter.facts()
        assert set(facts) <= {"why", "families", "models", "tiers", "ffmpeg", "companions", "budget", "renamed",
                              "steps", "speech", "faces", "cues"}, adapter.name   # `cues`
        KeyFamilies(**facts["families"])                      # every family is a field the helpers know
        assert set(facts["models"]) <= known, f"{adapter.name} names a model no capture holds"
        renamed = (facts.get("renamed") or {}).get("ids") or {}
        assert set(renamed) <= known | READ_IN_R16 and set(renamed.values()) <= known | READ_IN_R16, adapter.name
        assert set((facts.get("steps") or {}).get("locked") or {}) <= known | READ_IN_R16, adapter.name
        assert set((facts.get("speech") or {}).get("script") or {}) <= known, adapter.name
        cues = {k: v for k, v in (facts.get("cues") or {}).items() if k != "why"}
        assert {m for ids in cues.values() for m in ids} <= known, adapter.name
    with pytest.raises(ValueError, match="not an adapter facts file"):
        bad = FIXTURES.parent / "engine" / "fake_engine" / "overlay.json"
        engineapi.read_facts(str(bad))


def test_no_family_means_no_match():
    none = KeyFamilies()
    assert none.suffixes() == {} and none.fields() == []
    assert fork.FAMILIES.suffixes()["encoder_default"].endswith(fork.FAMILIES.encoder_default)
