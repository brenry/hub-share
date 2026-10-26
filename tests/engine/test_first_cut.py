"""The First cut. Parts on one frame grid, the script's checks and the listing, the pictures, the pick
and the canvas, the prompt and the request, the job, resume and the record, the routes, and a real cut on ffmpeg:
slices of the mix, one clip per part, the join with the mix as its one sound. The catalog is the real worker's answer
for upstream's H3 definitions (`test_upstream_rules.cat`)."""
from __future__ import annotations

import array
import copy
import json
import math
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from hub.core import jobgraph
from hub.core.api import NO_MODEL, Invalid, Take, request_wire
from hub.core.files import Files
from hub.modules.first_cut import made, manifest, parts, pictures, render, routes, script, slices
from hub.modules.generate_image import firstcut, models
from hub.modules.generate_image import routes as groutes
from hub.worker import joincmd
from hub.worker.adapters import lipsync
from tests.engine import test_upstream_rules as rules
from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest
from tests.engine.test_upstream_rules import FL2VA, REF2VA, entry

cat = rules.cat                                   # the H3 capture's catalog, shared
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
GRID = {"fps": 24.0, "min": 107, "step": 17, "window": 362}
RATE = 48_000
FULL = "minimax_h3_ref2va"


# ---------------------------------------------------------------- a mixed script
def line(ident: str, who: str, a: int, b: int, words: str) -> dict:
    return {"id": ident, "kind": "line", "start_ms": a, "end_ms": b, "speaker": who, "words": words,
            "measured": {"start_ms": a, "end_ms": b}}


def shot(ident: str | None, a: int, b: int, camera: Any = "Wide shot", lines: tuple = ()) -> dict:
    out = {"start_ms": a, "end_ms": b, "camera": camera, "events": list(lines),
           "measured": {"start_ms": a, "end_ms": b}}
    return {**out, "id": ident} if ident else out


def written(track: str = "Script 1.wav", size: int = 0, shots: list | None = None) -> dict:
    shots = shots if shots is not None else [
        shot("s1", 0, 9000, "Wide shot of the stage", (line("l1", "Character 7", 4000, 7642,
                                                            "Line one, spoken."),)),
        shot("s2", 9000, 17000, {"framing": "Close shot on Character 6", "move": "slow push in", "on": ["character 6"]},
             (line("l2", "Character 6", 9000, 12642, 'Thank you, "Character 7".'), line("l3", "Character 7", 13000,
                                                                                        15000, "Good.")))]
    return {"version": 2, "lock": {"locked": True},
            "context": {"cast": [{"name": "Character 7"}, {"name": "Character 6"}],
                      "set": {"name": "Set 1", "elements": ["Blue backdrop", "Long table"]},
                      "style": "A scripted scene"},
            "scenes": [{"title": "Scene 1", "cast": ["Character 7", "Character 6"], "shots": shots}],
            "mix": {"length_ms": shots[-1]["measured"]["end_ms"], "hash": "x"},
            "renders": {"track": track, "size": size, "stems": {}}}


def write_wav(path: Path, seconds: float, tones: tuple = ()) -> int:
    """A 48 kHz stereo 16-bit WAV: silence, or each (from_s, to_s, hz) as a tone. -> its size."""
    n = int(round(seconds * RATE))
    data = array.array("h", bytes(4 * n))
    for lo, hi, hz in tones:
        for i in range(int(lo * RATE), min(n, int(hi * RATE))):
            v = int(12000 * math.sin(2 * math.pi * hz * i / RATE))
            data[2 * i] = data[2 * i + 1] = v
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())
    return path.stat().st_size


def put_script(world: Any, name: str, body: dict) -> None:
    (world.files.roots["scripts"] / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")


class World:
    def __init__(self, tmp: Path, catalog: dict) -> None:
        self.data, self.chars = tmp / "data", tmp / "Characters"
        self.chars.mkdir()
        for name, size in (("Character 7", (600, 900)), ("Character 6", (640, 640))):
            Image.new("RGB", size, (90, 90, 90)).save(self.chars / f"{name}.png")
        self.files = Files(self.data, None, self.chars)
        self.gen = FakeCtx("generate-image", self.data, FakeEngine(copy.deepcopy(catalog)))
        self.gen.files = self.files
        self.gen.doc(groutes.DRAFT, {}).replace({"model": REF2VA})
        self.ctx = FakeCtx("first-cut", self.data, FakeEngine(None), {render.KIND: render.job})
        self.ctx.files = self.files
        self.ctx.services["first_cut"] = lambda: firstcut.Cut(self.gen)
        size = write_wav(self.files.roots["sounds"] / "Script 1.wav", 17.0)
        put_script(self, "Script 1", written(size=size))


@pytest.fixture
async def world(tmp_path, cat) -> World:
    w = World(tmp_path, cat)
    await models.catalog(w.gen)
    routes.running.clear()
    routes.last.clear()
    return w


def a_clip(world: World, stem: str, size: int = 64) -> str:
    path = world.files.roots["clips"] / "2026-10-20" / f"{stem}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * size)
    return f"clips/2026-10-20/{stem}.mp4"


# ---------------------------------------------------------------- parts on one frame grid
def lattice(f: int) -> bool:
    return f >= GRID["min"] and (f - GRID["min"]) % GRID["step"] == 0


def test_parts_lie_on_one_frame_grid():
    body = written(shots=[shot("a", 0, 1000), shot("b", 1000, 4321), shot("c", 4321, 9999)])
    got = parts.split(body, GRID)
    assert sum(p["n"] for p in got) == parts.grid(9999, 0, 24.0) == 240
    assert [p["f0"] for p in got] == [0, 24, 104]
    for p in got:
        assert lattice(p["render"]) and p["render"] >= p["n"] and p["render"] <= GRID["window"]
    assert got[0]["n"] == 24 and got[0]["render"] == 107, "a 1 s shot renders `min`"
    assert got[1]["start_ms"] == 1000 and got[2]["end_ms"] == 10_000


def test_a_long_shot_splits_in_the_gap_between_lines():
    lines = (line("l1", "Character 7", 0, 6000, "a"), line("l2", "Character 7", 7000, 13000, "b"),
             line("l3", "Character 7", 14000, 19500, "c"))
    got = parts.split(written(shots=[shot("s4", 0, 20000, lines=lines)]), GRID)
    assert [(p["id"], p["part"], p["of"], p["f0"], p["n"], p["split"]) for p in got] == [
        ("s4.1", 1, 2, 0, 324, "line"), ("s4.2", 2, 2, 324, 156, None)]
    assert got[0]["end_ms"] == 13500, "the cut at the gap's middle"
    assert all(p["n"] <= 362 and p["render"] <= 362 for p in got)
    assert [ln["words"] for ln in got[1]["lines"]] == ["c"] and got[1]["lines"][0]["from_s"] == 0.5


def test_a_line_longer_than_a_window_is_cut_and_said():
    got = parts.split(written(shots=[shot(None, 0, 20000, lines=(line("l1", "Character 7", 0, 19000, "long"),))]), GRID)
    assert [(p["id"], p["n"], p["split"]) for p in got] == [("1.1", 362, "window"), ("1.2", 118, None)]
    assert got[1]["lines"][0]["from_s"] == 0.0 and got[0]["lines"][0]["to_s"] == round(362 / 24, 2)


def test_overlapping_lines_give_no_cut_between_them():
    lines = (line("l1", "Character 7", 0, 8000, "a"), line("l2", "Character 6", 7000, 16000, "b"),
             line("l3", "Character 7", 16000, 19000, "c"))
    one = shot("s1", 0, 20000, lines=lines)
    assert parts.candidates(one, 0, 24.0, 0, 480) == []
    assert [p["split"] for p in parts.split(written(shots=[one]), GRID)] == ["window", None]


# ---------------------------------------------------------------- the script's checks and the listing
def test_unmeasured_gapped_unlocked_or_trackless_scripts_are_refused(world):
    size = (world.files.roots["sounds"] / "Script 1.wav").stat().st_size

    def refused(body: dict) -> str:
        put_script(world, "Bad", body)
        with pytest.raises(Invalid) as err:
            script.read(world.ctx, "Bad")
        return err.value.text

    assert script.read(world.ctx, "Script 1")["size"] == size
    assert refused({**written(size=size), "lock": {"locked": False}}) == \
        "Bad is being changed: render it when its new mix is done"
    assert refused(written(size=size + 1)) == refused(written("Gone.wav", size)) == \
        "Bad has no mixed track: Track it on the Storyboard"
    body = written(size=size)
    del body["scenes"][0]["shots"][1]["measured"]
    assert refused(body) == "Bad's shots are not measured: mix it again"
    body = written(size=size)
    del body["scenes"][0]["shots"][0]["events"][0]["measured"]
    assert refused(body) == "Bad's shots are not measured: mix it again"
    body = written(size=size)
    body["scenes"][0]["shots"][1]["measured"] = {"start_ms": 9100, "end_ms": 17000}
    assert refused(body) == "shot s2 does not start where shot s1 ends: mix it again"
    assert refused({**written(size=size), "version": 1}) == "Bad does not read as a script"
    with pytest.raises(Invalid) as err:
        script.read(world.ctx, "Nobody")
    assert (err.value.field, err.value.text) == ("name", "No script called Nobody")


def test_the_listing_names_mixed_scripts_and_why(world):
    (world.files.roots["scripts"] / "Broken.json").write_text("{", encoding="utf-8")
    put_script(world, "Never", {**written(), "renders": {"track": None, "size": None, "stems": {}}})
    put_script(world, "Held", {**written(size=1), "lock": {"locked": False}})
    got = script.listing(world.ctx)
    assert [(s["name"], s["why"]) for s in got] == [
        ("Broken", "Broken does not read as a script"),
        ("Held", "Held is being changed: render it when its new mix is done"), ("Script 1", None)]
    assert got[2]["seconds"] == 17.0 and got[2]["shots"] == 2


# ---------------------------------------------------------------- the pictures
def test_pictures_sheet_first_else_picture_and_views(world):
    for view in ("left", "right", "back"):
        Image.new("RGB", (600, 900)).save(world.chars / f"Character 7.{view}.png")
    Image.new("RGB", (640, 640)).save(world.chars / "Character 12.png")
    sheet = world.chars / "Character 6" / "sheet"
    sheet.mkdir(parents=True)
    for view in ("front", "face-1", "face-2"):
        Image.new("RGB", (640, 640)).save(sheet / f"{view}.png")
    record = {"sheet": {v: {"file": f"sheet/{v}.png"} for v in ("front", "left", "face-1", "face-2")}}
    (world.chars / "Character 6" / "casting.json").write_text(json.dumps(record), encoding="utf-8")
    character_7 = ["chars/Character 7.png", "chars/Character 7.back.png", "chars/Character 7.left.png"]
    character_6 = ["chars/Character 6/sheet/face-1.png", "chars/Character 6/sheet/front.png",
                   "chars/Character 6/sheet/face-2.png"]
    got = pictures.pick(world.ctx, "s1", ["character 6", "Character 7", "Character 12"], 9, "H3")
    assert [p["id"] for p in got] == [*character_6, *character_7, "chars/Character 12.png"]
    assert [p["name"] for p in got][:4] == ["Character 6"] * 3 + ["Character 7"] and [p["person"] for p in got][-1] == 2
    few = pictures.pick(world.ctx, "s1", ["Character 6", "Character 7", "Character 12"], 5, "H3")
    assert [p["id"] for p in few] == [*character_6[:2], *character_7[:2],
                                      "chars/Character 12.png"], "round-robin, grouped in box order"
    record["sheet"]["face-1"]["file"] = str(sheet / "face-1.png")       # absolute: never read
    (world.chars / "Character 6" / "casting.json").write_text(json.dumps(record), encoding="utf-8")
    (sheet / "front.png").unlink()
    assert [p["id"] for p in pictures.pick(world.ctx, "s1", ["Character 6"], 9, "H3")] == [character_6[2]]
    for who, cap, text in (([], 9, "shot s1 shows nobody; H3 needs a person's picture"),
                           (["Character 6", "Character 7", "Character 12"], 2,
                            "shot s1 shows 3 people; H3 takes 2 pictures"),
                           (["Character 8"], 9, "Character 8 has no picture in Characters")):
        with pytest.raises(Invalid) as err:
            pictures.pick(world.ctx, "s1", who, cap, "H3")
        assert err.value.text == text


# ---------------------------------------------------------------- the pick and the canvas
def test_the_pick_follows_b7_and_never_sets_the_pulldown(cat, world):
    assert firstcut.pick(cat, {"model": REF2VA})["id"] == REF2VA
    assert firstcut.pick(cat, {"model": FL2VA, "lastModel": {"video": FULL}})["id"] == FULL
    one = copy.deepcopy(cat)
    entry(one, FULL)["status"] = "missing"
    assert firstcut.pick(one, {"model": FL2VA, "lastModel": {"video": FULL}})["id"] == REF2VA, "the only one"
    with pytest.raises(Invalid) as err:
        firstcut.pick(cat, {"model": FL2VA})
    assert err.value.text == firstcut.PICK == ("Pick a Ref2VA video model in Generate (one that takes reference "
                                               "pictures and follows a sound)")
    none = copy.deepcopy(cat)
    none["models"] = [m for m in none["models"] if "ref2va" not in m["id"] or "tts" in m["id"]]
    with pytest.raises(Invalid) as err:
        firstcut.pick(none, {"model": REF2VA})
    assert err.value.text == "No Ref2VA video model that follows a sound in your model folders"
    world.gen.doc(groutes.DRAFT, {}).replace({"model": FL2VA, "lastModel": {"image": "", "video": FULL}})
    before, writes = world.gen.doc(groutes.DRAFT, {}).get(), world.gen.doc(groutes.DRAFT, {}).writes
    assert firstcut.Cut(world.gen).facts()["model"] == FULL
    assert world.gen.doc(groutes.DRAFT, {}).get() == before and world.gen.doc(groutes.DRAFT, {}).writes == writes


def test_the_canvas_is_16_9_nearest_832x480(cat, world):
    assert firstcut.canvas(entry(cat, REF2VA), "H3") == (864, 480)
    facts = firstcut.Cut(world.gen).facts()
    assert (facts["size"], facts["fps"], facts["min"], facts["step"], facts["cap"]) == ([864, 480], 24.0, 107, 17, 9)
    assert facts["window"] == 362 and not facts["names"], "frames.max (~15 s, one window), not window_max 481"
    square = copy.deepcopy(entry(cat, REF2VA))
    for tier in square["video"]["tiers"]:
        tier["sizes"].pop("16:9")
    with pytest.raises(Invalid) as err:
        firstcut.canvas(square, "H3")
    assert err.value.text == "H3 makes no 16:9 clip"


# ---------------------------------------------------------------- the prompt and the request
def a_part(body: dict, k: int, pics: list[dict]) -> dict:
    part = parts.split(body, GRID)[k]
    return {**part, "pictures": pics, "sound": "/s.wav", "set": body["context"]["set"],
            "style": body["context"]["style"]}


def test_the_prompt():
    body = written()
    character_6 = [{"person": 0, "name": "Character 6", "id": "a"}, {"person": 0, "name": "Character 6", "id": "b"}]
    text = firstcut.prompt(a_part(body, 1, character_6), {"names": False})
    rows = text.split("\n")
    assert len(rows) == 6 and "" not in rows
    assert [r.split(":")[0] for r in rows] == ["subject_definitions", "summary", "retention_analysis",
                                                "detailed_description", "overall_soundscape", "non_diegetic_music"]
    assert rows[0] == "subject_definitions: <Subject 1> is from <Picture 1>, <Picture 2>."
    assert rows[1] == "summary: [reference generation + audio reuse] Close shot on Character 6. Set 1."
    assert rows[2] == "retention_analysis: <Subject 1> (appears in [Shot 1]): fully_preserved"
    assert rows[3] == ("detailed_description: A scripted scene. Set 1. Blue backdrop. "
                       "Long table. [Shot 1] Close shot on Character 6. slow push in. From 0.00 to 3.64 seconds, "
                       '<Subject 1> speaks with natural lip movements synchronized: Thank you, "Character 7".'), \
        "a line off frame sends nothing"
    assert rows[4:] == ["overall_soundscape: N/A", "non_diegetic_music: N/A"]
    named = firstcut.prompt(a_part(body, 1, character_6), {"names": True})
    assert named.startswith("subject_definitions: <Subject 1> is Character 6, from <Picture 1>, <Picture 2>.\n")
    assert "\nretention_analysis: <Subject 1> (appears in [Shot 1]): fully_preserved - Character 6.\n" in named
    two = [{"person": 0, "name": "Character 7", "id": "a"}, {"person": 1, "name": "Character 6", "id": "b"}]
    wide = firstcut.prompt(a_part(body, 0, two), {"names": False})
    assert "<Subject 2> is from <Picture 2>." in wide and wide.count("fully_preserved") == 2
    assert "From 4.00 to 7.64 seconds, <Subject 1> speaks" in wide, "timed from the part's own start"
    silent = written(shots=[shot("s1", 0, 5000)])
    quiet = firstcut.prompt(a_part(silent, 0, two), {"names": False})
    assert "lip" not in quiet, "no line in frame: no sentence of the Hub's"
    assert lipsync.ask(quiet, None) != quiet and "speaking with natural lip movements synchronized." in \
        lipsync.ask(quiet, None), "the worker adds the engine's lip phrase alone"
    for t in (text, named, wide):
        assert lipsync.ask(t, None) == t, "a line in frame says lip: the worker adds no sentence"
    for t in (text, named, wide, quiet):
        assert "<d>" not in t and "<Audio" not in t
        assert "Character 6," not in t.split("\n")[0] or t is named
    assert '"Character 7"' in text, "the typed quote marks are sent"


def test_the_part_prompt_holds_no_sentence_of_the_hubs():
    """With every field's text and every engine token taken out, only spaces and full stops are left,
    with and without names."""
    words = [f"Field {n:02d}" for n in range(1, 8)]
    part = {"pictures": [{"person": 0, "name": "Character 1", "id": "a"}, {"person": 1, "name": "Character 2",
                                                                            "id": "b"}],
            "who": ["Character 1", "Character 2"], "set": {"name": words[0], "elements": [words[1], words[2]]},
            "camera": {"framing": words[3], "move": words[4]}, "style": words[5],
            "lines": [{"speaker": "Character 1", "in_frame": True, "from_s": 0, "to_s": 2, "words": words[6]},
                      {"speaker": "Character 2", "in_frame": False, "from_s": 2, "to_s": 4, "words": "Line 2"}]}
    syntax = [r"^(?:subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|"
              r"non_diegetic_music): ", r"\(appears in \[Shot 1\]\): fully_preserved(?: - )?", r"\[Shot 1\]",
              re.escape(firstcut.TAGS), r"From \d+\.\d\d to \d+\.\d\d seconds, <Subject \d+> speaks with natural lip "
              r"movements synchronized: ", r", (?=<)", r"<(?:Subject|Picture) \d+>", r" is (?:from )?", r", from ",
              r"N/A"]
    for names in (True, False):
        text = firstcut.prompt(part, {"names": names})
        assert "Line 2" not in text, "a line off frame sends nothing"
        left = text
        for t in sorted([*words, "Character 1", "Character 2"], key=len, reverse=True):
            left = left.replace(t, " ")
        for p in syntax:
            left = re.sub(p, " ", left, flags=re.MULTILINE)
        assert set(left) <= {" ", ".", "\n"}, f"the Hub's own text: {left!r} in {text!r}"


def test_a_shot_prompt_over_4000_is_sent_whole(world):
    body = written()                                                    # no length cap of the Hub's
    body["scenes"][0]["shots"][1]["events"][0]["words"] = "word " * 900
    part = a_part(body, 1, [{"person": 0, "name": "Character 6", "id": "chars/Character 6.png"}])
    text = firstcut.prompt(part, firstcut.Cut(world.gen).facts())
    assert len(text) > 4000
    assert firstcut.Cut(world.gen).clip(part)["task"]["prompt"] == text


def test_the_request(world):
    loras = Path(entry(models.cached(), REF2VA)["lora_dirs"][0])
    loras.mkdir(parents=True, exist_ok=True)
    (loras / "grain.safetensors").write_bytes(b"x")
    world.gen.doc(groutes.DRAFT, {}).replace({
        "model": REF2VA, "advancedByModel": {REF2VA: {"steps": 12}},
        "lorasByModel": {REF2VA: [{"id": f"{loras.name}/grain.safetensors", "strength": 0.8}]}})
    got = render.plan(world.ctx, "Script 1")
    one = got["parts"][1]
    task = one["task"]
    assert [r["role"] for r in task["references"]] == ["identity"]
    assert task["references"][0]["path"] == str((world.chars / "Character 6.png").resolve())
    assert task["references"][0]["name"] is None, "upstream H3 takes no names"
    assert task["sound"] == str(one["slice"].path) and task["sound_seconds"] == one["render"] / 24
    assert task["frames"] == one["render"] == 192 and one["n"] == 192
    assert (task["judge"], task["judge_bar"], task["speaker"]) == ("cpu", 0.3, "Character 6")
    assert task["voices"] == [] and task["video"] is None and task["words"] is None
    assert task["steps"] == 12 and task["loras"] == [["grain.safetensors", 0.8]]
    assert got["facts"]["loras"] == [{"id": f"{loras.name}/grain.safetensors", "name": "grain", "strength": 0.8}]
    assert [r["path"] for r in got["parts"][0]["task"]["references"]] == [
        str((world.chars / "Character 7.png").resolve()), str((world.chars / "Character 6.png").resolve())]
    again = render.plan(world.ctx, "Script 1")["parts"][1]
    assert again["key"] == one["key"], "the key is unchanged by the seed"
    world.gen.settings["clip_face_bar"], world.gen.settings["judge_device"] = 0.5, "cuda"
    judged = render.plan(world.ctx, "Script 1")["parts"][1]
    assert judged["task"]["judge_bar"] == 0.5 and judged["key"] == one["key"], "nor by the judges' fields"
    os.utime(world.chars / "Character 6.png", ns=(1, 1))
    assert render.plan(world.ctx, "Script 1")["parts"][1]["key"] != one["key"], "a changed picture changes the key"


# ---------------------------------------------------------------- the job
def test_the_job_shape(world):
    plan = render.job({"script": "Script 1"}, world.ctx)
    jobgraph.check(plan)
    assert len(plan.tasks) == 3 and plan.model == REF2VA
    join = plan.tasks[-1]
    assert join["kind"] == "join" and [t["kind"] for t in plan.tasks[:-1]] == ["video", "video"]
    assert plan.inputs[-1] == {"items.0.path": (1, "kept"), "items.1.path": (2, "kept")}
    assert [(i["path"], i["in"], i["out"], i["frames"], i["audio"]) for i in join["items"]] == [
        ("", 0, 216, 226, False), ("", 0, 192, 192, False)]
    track = os.path.realpath(world.files.roots["sounds"] / "Script 1.wav")
    assert join["audio"] == [{"path": track, "at_ms": 0, "in": 0, "out": 17000, "fps": 1000.0, "level": 1.0,
                              "fade_in": 0, "fade_out": 0, "duck": False}]
    assert (join["crf"], join["preset"], join["out_kind"], join["canvas"]) == (
        18, "medium", "mp4", {"w": 864, "h": 480, "fps": 24.0})
    assert plan.takes == (((1,),), ((2,),)) and not plan.judge.again(1, 2)
    assert plan.judge.shots == [{"lines": [{"speaker": "Character 7"}],
                                 "camera": {"framing": "Wide shot of the stage"}},
                                {"lines": [{"speaker": "Character 6"}],
                                 "camera": {"framing": "Close shot on Character 6"}}]
    s = plan.summary
    assert s["step_names"] == ["Shot s1 · 9.0 s", "Shot s2 · 8.0 s", "Join · 17.0 s"]
    assert (s["title"], s["mode"], s["frames"], s["shots"], s["width"]) == ("First cut · Script 1 · 2 parts",
                                                                             "first-cut",
                                                                             408, 2, 864)
    assert all(Path(p).is_file() for p in plan.finish.used), "the slices are cut"
    one = render.plan(world.ctx, "Script 1")["parts"][0]
    made.write(world.ctx, "Script 1", {"s1": {"key": one["key"], "clip": a_clip(world, "a"), "frames": 226}}, None)
    plan = render.job({"script": "Script 1"}, world.ctx)
    jobgraph.check(plan)
    assert len(plan.tasks) == 2 and plan.inputs[-1] == {"items.1.path": (1, "kept")}
    assert plan.tasks[-1]["items"][0]["path"] == str((world.files.roots["clips"] / "2026-10-20" / "a.mp4").resolve())
    assert plan.summary["step_names"] == ["Shot s2 · 8.0 s", "Join · 17.0 s"]
    two = render.plan(world.ctx, "Script 1")["parts"][1]
    made.write(world.ctx, "Script 1", {"s2": {"key": two["key"], "clip": a_clip(world, "b"), "frames": 192}}, None)
    alone = render.job({"script": "Script 1"}, world.ctx)
    jobgraph.check(alone)
    assert alone.model == NO_MODEL and len(alone.tasks) == 1 and alone.takes == () and alone.judge is None
    assert alone.summary["step_names"] == ["Join · 17.0 s"]


def test_a_long_shot_is_shown_as_its_parts_in_the_step_names(world):
    lines = (line("l1", "Character 7", 0, 11000, "a"), line("l2", "Character 6", 12000, 24000, "b"))
    size = write_wav(world.files.roots["sounds"] / "Long.wav", 25.0)
    put_script(world, "Long", written("Long.wav", size, [shot("s4", 0, 25000, lines=lines)]))
    plan = render.job({"script": "Long"}, world.ctx)
    assert plan.summary["step_names"] == ["Shot s4 part 1 of 2 · 11.5 s", "Shot s4 part 2 of 2 · 13.5 s",
                                          "Join · 25.0 s"]
    assert [i["out"] for i in plan.tasks[-1]["items"]] == [276, 324]


# ---------------------------------------------------------------- resume and the record
def test_resume_and_current(world):
    got = render.plan(world.ctx, "Script 1")
    a, b = got["parts"]
    made.write(world.ctx, "Script 1", {"s1": {"key": a["key"], "clip": a_clip(world, "a"), "frames": 226},
                                   "s2": {"key": "0" * 16, "clip": a_clip(world, "b"), "frames": 192}}, None)
    again = render.plan(world.ctx, "Script 1")
    assert [p["state"] for p in again["parts"]] == ["made", "changed"]
    plan = render.job({"script": "Script 1"}, world.ctx)
    assert len(plan.tasks) == 2 and plan.finish.reused == 1, "the changed part rendered, the matching one reused"
    (world.files.roots["clips"] / "2026-10-20" / "a.mp4").unlink()
    assert [p["state"] for p in render.plan(world.ctx, "Script 1")["parts"]] == ["missing", "changed"]
    assert len(render.job({"script": "Script 1"}, world.ctx).tasks) == 3, "a deleted clip is rendered again"
    made.write(world.ctx, "Script 1", {"s1": {"key": a["key"], "clip": a_clip(world, "c"), "frames": 226},
                                   "s2": {"key": b["key"], "clip": a_clip(world, "d"), "frames": 192}}, None)
    key = render.plan(world.ctx, "Script 1")["cut_key"]
    made.write(world.ctx, "Script 1", {}, {"key": key, "clip": a_clip(world, "cut"), "frames": 408})
    with pytest.raises(Invalid) as err:
        render.job({"script": "Script 1"}, world.ctx)
    assert err.value.text == "Script 1's first cut is current: delete a shot's clip in Media to render it again"
    (world.files.roots["clips"] / "2026-10-20" / "cut.mp4").unlink()
    assert len(render.job({"script": "Script 1"}, world.ctx).tasks) == 1, "the join alone"


async def test_finish_files_records_pointers_only(world):
    answer = routes.press(world.ctx, "Script 1")
    job = world.ctx.jobs.get(answer["job"])
    fin = job.plan.finish
    assert answer == {"job": job.id, "render": 2, "reused": 0} and fin.job == job.id
    used = list(fin.used)
    job.takes = {1: Take(False, (0.0, 1.0, 0.1), "Character 7's mouth is still while the character speaks (12% …)"),
                 2: Take(True, (1.0, 2.0, 1.0), "Character 6's face held (0.70)")}
    await fin({1: a_clip(world, "120000-001"), 2: a_clip(world, "120100-001"), 3: a_clip(world, "120200-001")})
    record = world.ctx.doc("made", {}).get()                # the paths read from the record (flat names)
    held = record["scripts"]["Script 1"]
    assert set(record) == {"version", "scripts"} and set(held) == {"parts", "cut"}
    clips = [held["parts"]["s1"]["clip"], held["parts"]["s2"]["clip"], held["cut"]["clip"]]
    assert all(world.files.roots["clips"].joinpath(c.split("/", 1)[1]).is_file() for c in clips), clips
    assert held["parts"]["s1"] == {"key": fin.rendered[0][2], "clip": clips[0], "frames": 226}
    assert held["cut"] == {"key": render.plan(world.ctx, "Script 1")["cut_key"], "clip": clips[2], "frames": 408}
    text = json.dumps(record)
    assert all(t["seed"] is None for t in job.plan.tasks[:-1]), "a part sends no seed"
    assert job.plan.summary["seeds"] == []
    assert not any(w in text for w in ("spoken", "Thank", "mouth", "prompt", "Character 6"))
    assert not any(Path(p).exists() for p in used), "the job's slices removed"
    assert routes.memory("Script 1")["flags"] == {
        fin.rendered[0][2]: "Character 7's mouth is still while the character speaks (12% …)"}
    detail = routes.detail(world.ctx, "Script 1")
    assert [(p["state"], p["flag"]) for p in detail["parts"]] == [
        ("made", "Character 7's mouth is still while the character speaks (12% …)"), ("made", None)]
    assert detail["cut"]["id"] == clips[2]


async def test_a_failed_render_keeps_its_parts(world):
    answer = routes.press(world.ctx, "Script 1")
    fin = world.ctx.jobs.get(answer["job"]).plan.finish
    await fin({1: a_clip(world, "120000-001")})
    held = world.ctx.doc("made", {}).get()["scripts"]["Script 1"]
    assert list(held["parts"]) == ["s1"] and "cut" not in held
    routes.running.clear()
    plan = render.job({"script": "Script 1"}, world.ctx)
    assert len(plan.tasks) == 2 and plan.summary["step_names"][0] == "Shot s2 · 8.0 s"


async def test_a_stale_cut_is_never_current(world):
    answer = routes.press(world.ctx, "Script 1")
    await world.ctx.jobs.get(answer["job"]).plan.finish({1: a_clip(world, "100000-001"), 2: a_clip(world, "100100-001"),
                                                         3: a_clip(world, "100200-001")})
    old = world.ctx.doc("made", {}).get()["scripts"]["Script 1"]["cut"]
    with pytest.raises(Invalid):
        render.job({"script": "Script 1"}, world.ctx)                    # current
    s1 = world.ctx.doc("made", {}).get()["scripts"]["Script 1"]["parts"]["s1"]["clip"]   # read from the record
    world.files.roots["clips"].joinpath(s1.split("/", 1)[1]).unlink()   # deleted in Media
    routes.running.clear()
    again = routes.press(world.ctx, "Script 1")
    assert again["render"] == 1
    fin = world.ctx.jobs.get(again["job"]).plan.finish
    await fin({1: a_clip(world, "110000-001", 96)})                    # the new take landed; the join did not
    held = world.ctx.doc("made", {}).get()["scripts"]["Script 1"]
    new = held["parts"]["s1"]["clip"]                                  # a flat name, its file there
    assert new.endswith(" - Script 1 shots s1.mp4") and \
        world.files.roots["clips"].joinpath(new.split("/", 1)[1]).is_file()
    assert "cut" not in held
    assert render.plan(world.ctx, "Script 1")["cut_key"] != old["key"], "the same part key, another clip: another cut"
    made.write(world.ctx, "Script 1", {}, old)                             # even an old cut put back is not current
    routes.running.clear()
    plan = render.job({"script": "Script 1"}, world.ctx)
    assert len(plan.tasks) == 1 and plan.tasks[0]["kind"] == "join", "the join alone, with the new take"


async def test_a_refused_submit_leaves_no_slices(world):
    jobs = world.ctx.jobs
    built: list = []

    class Full(Exception):
        text = "The queue is full"

    def submit(kind: str, params: dict) -> Any:
        built.append(jobs.builders[kind](params, world.ctx))
        raise Full()

    world.ctx.jobs = type("Refusing", (), {"submit": staticmethod(submit), "get": jobs.get})()
    assert routes.press(world.ctx, "Script 1") == {"problem": "The queue is full"}
    assert built and built[0].finish.used and not any(Path(p).exists() for p in built[0].finish.used)
    old = Path(world.ctx.data_dir) / "slices" / "old.wav"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"x")
    os.utime(old, (1, 1))
    await manifest.MODULE.start(world.ctx)
    assert not old.exists(), "slices older than a day go at start"


async def test_a_part_that_cannot_be_filed_says_so_on_its_row(world, monkeypatch):
    real = world.files.file_clip

    def file_clip(item: str, group: str, name: str) -> str:
        if name == "s2":
            raise Invalid("name", "Use a plain clip name, without slashes")
        return real(item, group, name)

    monkeypatch.setattr(world.files, "file_clip", file_clip)
    answer = routes.press(world.ctx, "Script 1")
    await world.ctx.jobs.get(answer["job"]).plan.finish({1: a_clip(world, "100000-001"), 2: a_clip(world, "100100-001"),
                                                         3: a_clip(world, "100200-001")})
    rows = routes.detail(world.ctx, "Script 1")["parts"]
    assert [(r["state"], r["flag"]) for r in rows] == [
        ("made", None), ("missing", "Its clip stayed where it landed in Clips: Use a plain clip name, without slashes")]
    assert "cut" not in world.ctx.doc("made", {}).get()["scripts"]["Script 1"]
    longest = "\u3042" * 81                                             # 243 bytes: its group "<name> shots" fits
    assert script.name_of(longest) == longest and len(f"{longest} shots".encode()) <= 255
    with pytest.raises(Invalid):
        script.name_of("\u3042" * 82 + "abcd")                          # 250 bytes: its group would not


async def test_a_remix_rerenders_only_the_changed_shot(world):
    answer = routes.press(world.ctx, "Script 1")
    await world.ctx.jobs.get(answer["job"]).plan.finish({1: a_clip(world, "100000-001"), 2: a_clip(world, "100100-001"),
                                                         3: a_clip(world, "100200-001")})
    size = write_wav(world.files.roots["sounds"] / "Script 1.wav", 17.0, ((10.0, 16.0, 440.0),))   # shot 2's sound only
    put_script(world, "Script 1", written(size=size))
    got = render.plan(world.ctx, "Script 1")
    assert [p["state"] for p in got["parts"]] == ["made", "changed"]
    routes.running.clear()
    plan = render.job({"script": "Script 1"}, world.ctx)
    assert plan.summary["step_names"] == ["Shot s2 · 8.0 s", "Join · 17.0 s"]


# ---------------------------------------------------------------- the routes
async def test_routes(world):
    put_script(world, "Held", {**written(size=1), "lock": {"locked": False}})
    listed = await routes.get_scripts(world.ctx, FakeRequest())
    assert [(s["name"], s["state"], s["job"], s["cut"]) for s in listed["scripts"]] == [
        ("Held", "none", None, None), ("Script 1", "none", None, None)]
    held = await routes.get_script(world.ctx, FakeRequest({"name": "Held"}))
    assert held["why"] == "Held is being changed: render it when its new mix is done" and held["parts"] is None
    with pytest.raises(Invalid) as err:
        await routes.get_script(world.ctx, FakeRequest({"name": "Nobody"}))
    assert err.value.field == "name"
    detail = await routes.get_script(world.ctx, FakeRequest({"name": "Script 1"}))
    assert detail["why"] is None and detail["order"] is None and detail["problem"] is None
    p = detail["parts"][1]
    assert {k: p[k] for k in ("id", "shot", "part", "of", "start_ms", "end_ms", "frames", "render_frames", "who",
                              "lines", "split", "state", "clip", "flag")} == {
        "id": "s2", "shot": "s2", "part": 1, "of": 1, "start_ms": 9000.0, "end_ms": 17000.0, "frames": 192,
        "render_frames": 192, "who": ["Character 6"], "lines": 2, "split": None, "state": "missing", "clip": None,
        "flag": None}
    sent = await routes.post_render(world.ctx, FakeRequest(body=b'{"name": "Script 1"}'))
    assert sent == {"job": "j_1", "render": 2, "reused": 0}
    assert world.ctx.bus.sent[-1] == ("changed", "changed", {"name": "Script 1"})
    busy = await routes.post_render(world.ctx, FakeRequest(body=b'{"name": "Script 1"}'))
    assert busy == {"problem": "Script 1 is rendering"}
    detail = await routes.get_script(world.ctx, FakeRequest({"name": "Script 1"}))
    assert (detail["state"], detail["job"], detail["order"]) == ("queued", "j_1", ["s1", "s2"])
    refused = await routes.post_render(world.ctx, FakeRequest(body=b'{"name": "Held"}'))
    assert refused == {"problem": "Held is being changed: render it when its new mix is done"}
    world.ctx.jobs.get("j_1").state, world.ctx.jobs.get("j_1").error = "failed", "Step 2 · out of memory"
    await routes.on_finished(world.ctx, {"job": "j_1", "kind": "first-cut.render", "state": "failed"})
    assert world.ctx.bus.sent[-1] == ("changed", "changed", {"name": "Script 1"}) and routes.running == {}
    detail = await routes.get_script(world.ctx, FakeRequest({"name": "Script 1"}))
    assert (detail["state"], detail["problem"], detail["order"]) == ("failed", "Step 2 · out of memory", None)
    del world.ctx.services["first_cut"]
    off = await routes.get_script(world.ctx, FakeRequest({"name": "Script 1"}))
    assert off["why"] == "Generate Image is not running" and off["parts"] is None


# ---------------------------------------------------------------- a real cut
def goertzel(samples: list[float], hz: float) -> float:
    k = 2 * math.cos(2 * math.pi * hz / RATE)
    s1 = s2 = 0.0
    for x in samples:
        s1, s2 = x + k * s1 - s2, s1
    return math.sqrt(max(0.0, s1 * s1 + s2 * s2 - k * s1 * s2)) / len(samples)


def mono(path: Path, lo: float, hi: float) -> list[float]:
    with wave.open(str(path), "rb") as w:
        w.setpos(int(lo * RATE))
        raw = array.array("h", w.readframes(int((hi - lo) * RATE)))
    return [raw[i] / 32768 for i in range(0, len(raw), 2)]


@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="no ffmpeg installed here")
def test_a_real_cut_slices_and_joins_with_one_track(tmp_path):
    track = tmp_path / "sounds" / "Mix.wav"
    size = write_wav(track, 10.0, ((0.0, 4.0, 300.0), (4.0, 10.0, 700.0)))
    body = written("Mix.wav", size, [shot("s1", 0, 4000), shot("s2", 4000, 10000)])
    facts = {"fps": 24.0, "min": 30, "step": 8, "window": 94, "size": [160, 96]}
    every = parts.split(body, facts)
    assert [(p["id"], p["n"], p["render"]) for p in every] == [
        ("s1.1", 94, 94), ("s1.2", 2, 30), ("s2.1", 94, 94), ("s2.2", 50, 54)]

    class Here:
        data_dir = tmp_path / "first-cut"

    with wave.open(str(track), "rb") as w:
        whole = array.array("h", w.readframes(w.getnframes()))
    colours = ["red", "lime", "blue", "yellow"]
    paths = []
    for p, colour in zip(every, colours, strict=True):
        cut = slices.where(Here, track, size, track.stat().st_mtime_ns, p["start_ms"], p["render"], 24.0)
        slices.cut(track, cut)
        assert cut.length == math.ceil(p["render"] * RATE / 24)
        with wave.open(str(cut.path), "rb") as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 2, RATE)
            got = array.array("h", w.readframes(w.getnframes()))
        inside = min(cut.length, len(whole) // 2 - cut.start)
        assert got[:2 * inside] == whole[2 * cut.start:2 * (cut.start + inside)]
        assert set(got[2 * inside:]) <= {0} and len(got) == 2 * cut.length
        clip = tmp_path / f"{p['id']}.mp4"
        sec = p["render"] / 24
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=160x96:r=24:d={sec}",
                        "-f", "lavfi", "-i", f"sine=frequency=1500:sample_rate=48000:duration={sec}",
                        "-frames:v", str(p["render"]), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        str(clip)], check=True, capture_output=True, timeout=120)
        paths.append(str(clip))
    assert every[-1]["render"] > every[-1]["n"], "the last slice runs past the track's end: zeros"
    req = request_wire(render.join(every, paths, facts, str(track), 0, 10000))
    state = tmp_path / "state"
    (state / "outbox").mkdir(parents=True)
    cmd = joincmd.build(req, [], FFMPEG, str(state), "fc", True)
    done = subprocess.run(cmd.argv, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr
    out = Path(cmd.out)
    total = sum(p["n"] for p in every)
    assert total == cmd.expect == 240
    probe = json.loads(subprocess.run([FFPROBE, "-v", "error", "-count_frames", "-select_streams", "v:0",
                                       "-show_entries", "stream=nb_read_frames", "-of", "json", str(out)],
                                      check=True, capture_output=True, text=True).stdout)
    assert int(probe["streams"][0]["nb_read_frames"]) == total
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(out), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         check=True, capture_output=True).stdout
    frame = 160 * 96 * 3
    rgb = {"red": (255, 0, 0), "lime": (0, 255, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0)}

    def colour_at(i: int) -> str:
        at = i * frame + (48 * 160 + 80) * 3
        px = raw[at:at + 3]
        return min(rgb, key=lambda c: sum((a - b) ** 2 for a, b in zip(px, rgb[c], strict=True)))

    edge = 0
    for k, p in enumerate(every):
        edge += p["n"]
        assert colour_at(edge - 1) == colours[k], f"part {p['id']}'s last frame"
        if k + 1 < len(every):
            assert colour_at(edge) == colours[k + 1], f"the frame after part {p['id']}"
    heard = tmp_path / "heard.wav"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(out), "-vn", "-ac", "2", "-ar", str(RATE), "-c:a",
                    "pcm_s16le", str(heard)], check=True, capture_output=True, timeout=120)
    with wave.open(str(heard), "rb") as w:
        assert abs(w.getnframes() / RATE - total / 24) < 0.03
    first, second = mono(heard, 0.5, 3.5), mono(heard, 4.5, 9.5)
    assert goertzel(first, 300) > 20 * goertzel(first, 700) and goertzel(second, 700) > 20 * goertzel(second, 300)
    for chunk in (first, second):
        loud = max(goertzel(chunk, 300), goertzel(chunk, 700))
        assert goertzel(chunk, 1500) < loud / 100, "the clips' own sound is gone"


async def test_unfiled_flag_clears_when_refiled(world, monkeypatch):
    real = world.files.file_clip
    fail = {"on": True}

    def file_clip(item, group, name):
        if name == "s2" and fail["on"]:
            raise Invalid("name", "nope")
        return real(item, group, name)

    monkeypatch.setattr(world.files, "file_clip", file_clip)
    answer = routes.press(world.ctx, "Script 1")
    await world.ctx.jobs.get(answer["job"]).plan.finish({1: a_clip(world, "100000-001"), 2: a_clip(world, "100100-001"),
                                                         3: a_clip(world, "100200-001")})
    fail["on"] = False
    routes.running.clear()
    again = routes.press(world.ctx, "Script 1")
    assert again["render"] == 1
    await world.ctx.jobs.get(again["job"]).plan.finish({1: a_clip(world, "110000-001"), 2: a_clip(world, "110100-001")})
    rows = routes.detail(world.ctx, "Script 1")["parts"]
    assert [(r["state"], r["flag"]) for r in rows] == [("made", None), ("made", None)], rows
