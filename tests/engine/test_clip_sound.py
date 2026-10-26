"""A sound and a picture make one clip in which the character speaks it. The task a clip with a sound
becomes on FL2VA and Ref2VA (the soundtrack letters, `audio_guide`, the length, the window), each refusal, a clip
without a sound as today, the lip sentence in each place, `translate` keeping the letters, the catalog's
`soundtrack`, and the press that sends a Sounds item. The catalog and the accepted settings are upstream's own H3
capture (`test_upstream_rules`)."""
from __future__ import annotations

import copy
import math
import os
import struct
import time
from pathlib import Path

import pytest

from hub.core import sound
from hub.core.api import Invalid
from hub.modules.generate_image import build, clipsound, models
from hub.worker import enginewire, faults
from hub.worker.adapters import lipsync, tasks, upstream
from hub.worker.engineapi import ClipRequest, Reference
from tests.engine import test_upstream_rules as rules
from tests.engine.test_upstream_rules import ACCEPTED, FL2VA, REF2VA, clip, entry, press, refused, sent
from tests.fakes.wav import float32, tiny_wav

cat, accepted, ref_ctx = rules.cat, rules.accepted, rules.ref_ctx     # the H3 capture's fixtures, shared

LINE = "/sounds/Character 7 line.wav"
LIP = " is speaking with natural lip movements synchronized."


def eight_bit(seconds: float, rate: int = 8_000) -> bytes:
    """A mono 8-bit PCM WAV of silence (unsigned: 0x80)."""
    data = b"\x80" * int(rate * seconds)
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate, 1, 8)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def heard(model: str = FL2VA, seconds: float = 14.0, **extra) -> ClipRequest:
    return clip(model, sound=LINE, sound_seconds=seconds, **extra)


# ---------------------------------------------------------------- the task
def test_fl2va_follows_the_sound_and_keeps_it(cat):
    task = sent(cat, heard())
    assert set(task) <= ACCEPTED
    assert (task["audio_prompt_type"], task["audio_guide"], task["postprocess_audio"]) == ("A", LINE, "")
    # 14 s at 24 fps is 336 frames; the engine floors a length to 107 + 17k (frame_scheduler.py:23-30): 328
    assert (task["video_length"], task["sliding_window_size"]) == (328, 328)
    assert task["prompt"] == "a shot " + lipsync.ALONE


def test_ref2va_follows_the_sound_with_the_identity_picture(cat):
    task = sent(cat, heard(REF2VA, 10.0, references=[Reference("/c/Character 7.png", "identity")]))
    assert set(task) <= ACCEPTED
    assert (task["audio_prompt_type"], task["audio_guide"]) == ("AS", LINE)
    assert (task["video_prompt_type"], task["image_refs"]) == ("I", ["/c/Character 7.png"])
    assert (task["video_length"], task["sliding_window_size"]) == (226, 226), "240 frames floored to 107 + 17*7"


def test_a_sound_on_the_lattice_takes_its_frames_exactly_and_the_window_floor(cat):
    assert sent(cat, heard(seconds=481 / 24))["video_length"] == 481, "the largest window, to the frame"
    short = sent(cat, heard(seconds=107 / 24))
    assert (short["video_length"], short["sliding_window_size"]) == (107, 124), "never under the window floor"


def test_each_refusal_is_one_line(cat):
    name = entry(cat, FL2VA)["name"]
    assert refused(cat, heard(seconds=20.1)) == f"{name} follows at most 20 s of sound in one clip"
    assert refused(cat, heard(seconds=4.4)) == f"{name} follows at least 4.5 s of sound"
    assert refused(cat, heard(references=[Reference("/c.mp4", "source")])) == "A continued clip takes no sound"
    plain = copy.deepcopy(entry(cat, FL2VA))
    del plain["video"]["soundtrack"]
    request = enginewire.request_parse(enginewire.request_wire(heard()))
    with pytest.raises(faults.Refused) as err:
        tasks.clip(request, plain, upstream.LINE)
    assert str(err.value) == f"{name} cannot follow a sound"


def test_a_clip_without_a_sound_is_todays_task(cat):
    today = sent(cat, clip())
    assert sent(cat, clip(sound=None, sound_seconds=None)) == today
    assert today["audio_prompt_type"] == "" and "audio_guide" not in today and today["prompt"] == "a shot"
    assert today["video_length"] == 141


def test_translate_keeps_the_letters_only_for_a_task_with_a_sound():
    with_sound = upstream.translate({"image_mode": 0, "audio_prompt_type": "AS", "audio_guide": LINE}, {})
    assert (with_sound["audio_prompt_type"], with_sound["postprocess_audio"]) == ("AS", "")
    assert upstream.translate({"image_mode": 0, "audio_prompt_type": "A"}, {})["audio_prompt_type"] == ""


# ---------------------------------------------------------------- the lip sentence
def test_the_sentence_goes_at_the_end_of_the_prompt_or_of_its_description_section():
    assert lipsync.ask("Character 7 on stage.", None) == "Character 7 on stage. " + lipsync.ALONE
    assert lipsync.ask("Character 7 on stage.", "Character 7") == "Character 7 on stage. Character 7" + LIP
    ref2va = "summary: a scene\ndetailed_description: [Shot 1] Character 7 talks.\n\noverall_soundscape: a room\n"
    assert lipsync.ask(ref2va, None) == ("summary: a scene\ndetailed_description: [Shot 1] Character 7 talks. "
                                         + lipsync.ALONE + "\n\noverall_soundscape: a room\n")
    fl2va = "integrated_multimodal_description: [Shot 1] Character 7 talks.\noverall_soundscape: a room"
    assert lipsync.ask(fl2va, "Character 7") == ("integrated_multimodal_description: [Shot 1] Character 7 talks. "
                                                 "Character 7" + LIP + "\noverall_soundscape: a room")
    assert lipsync.ask("detailed_description: Character 7 talks.",
                       None) == "detailed_description: Character 7 talks. " \
        + lipsync.ALONE


def test_no_sentence_when_the_prompt_already_asks_for_lips():
    for prompt in ("Character 7 moves the LIPS.", "lip sync please", "detailed_description: Lip movement."):
        assert lipsync.ask(prompt, "Character 7") == prompt


def test_the_name_of_a_named_identity_is_who_speaks(cat):
    named = copy.deepcopy(entry(cat, REF2VA))
    named["video"]["references"]["names"] = True
    request = enginewire.request_parse(enginewire.request_wire(
        heard(REF2VA, references=[Reference("/c/Character 7.png", "identity", "Character 7")])))
    assert tasks.clip(request, named, upstream.LINE)["prompt"] == "a shot Character 7" + LIP


# ---------------------------------------------------------------- the catalog
def test_the_catalog_has_soundtrack_for_the_h3_models_from_the_facts_file(cat):
    found = {m["id"]: (m.get("video") or {}).get("soundtrack") for m in cat["models"]}
    assert {k: v for k, v in found.items() if v} == {
        "minimax_h3_fl2va": "A", "minimax_h3_fl2va_pruned": "A", "minimax_h3_fl2va_pdd": "A",
        "minimax_h3_ref2va": "AS", "minimax_h3_ref2va_pruned": "AS"}
    assert models.ui_model(entry(cat, REF2VA), {})["video"]["soundtrack"] == "AS", "the screen sees it"


# ---------------------------------------------------------------- the press
def sound_item(ctx, stem: str = "120000-000", seconds: float = 10.0, data: bytes | None = None) -> str:
    path = ctx.files.roots["sounds"] / "2026-10-17" / f"{stem}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tiny_wav(seconds=seconds) if data is None else data)
    return f"sounds/2026-10-17/{stem}.wav"


def test_a_sounds_item_goes_with_the_clip_as_its_path_and_length(ref_ctx):
    item = sound_item(ref_ctx)
    own = ref_ctx.files.roots["sounds"] / "2026-10-17" / "120000-000.wav"
    before = own.read_bytes()
    plan = build.image_job(press(references=["chars/Character 11.png"], frames=107, sound=item), ref_ctx)
    request = plan.tasks[0]
    # 10 s at 24 fps is 240 frames; the shortest length on 107 + 17k that holds it is 243 (nothing is cut)
    padded = Path(ref_ctx.data_dir) / clipsound.PADS / "2026-10-17-120000-000-243.wav"
    assert request["sound"] == str(padded) and request["sound_seconds"] == 243 / 24
    assert plan.summary["sound"] == "120000-000" and plan.summary["frames"] == 243, "the sound sets it"
    task = sent(models.cached(), enginewire.request_parse(request))
    assert (task["audio_prompt_type"], task["audio_guide"], task["video_length"]) == ("AS", str(padded), 243)
    assert Path(task["image_refs"][0]).name == "Character 11.png"
    assert own.read_bytes() == before, "the sound's own file is only read"
    sound_bytes = padded.read_bytes()
    assert sound.exact(padded) == math.ceil(243 / 24 * 32_000) / 32_000, "silence up to the clip's last frame"
    assert sound.chunks(sound_bytes)[b"data"][len(sound.chunks(before)[b"data"]):].strip(b"\x00") == b""


def test_a_sound_already_on_the_lattice_goes_as_the_owners_own_file(ref_ctx):
    item = sound_item(ref_ctx, "on-lattice", seconds=243 / 24)
    request = build.image_job(press(references=["chars/Character 11.png"], sound=item), ref_ctx).tasks[0]
    assert request["sound"] == os.path.realpath(ref_ctx.files.roots["sounds"] / "2026-10-17" / "on-lattice.wav")
    assert not (Path(ref_ctx.data_dir) / clipsound.PADS / "2026-10-17-on-lattice-243.wav").exists()


def test_a_short_sound_makes_the_shortest_clip_and_a_long_one_is_refused(ref_ctx):
    short = build.image_job(press(references=["chars/Character 11.png"], sound=sound_item(ref_ctx, "short", 3.0)),
                            ref_ctx)
    assert short.summary["frames"] == 107 and short.tasks[0]["sound_seconds"] == 107 / 24
    label = entry(models.cached(), REF2VA)["name"]
    with pytest.raises(Invalid) as err:
        build.image_job(press(references=["chars/Character 11.png"], sound=sound_item(ref_ctx, "long", 20.1)), ref_ctx)
    assert (err.value.field, err.value.text) == ("sound", f"{label} follows at most 20 s of sound in one clip")


def test_a_padded_copy_older_than_a_day_goes_at_the_next_pad(ref_ctx):
    folder = Path(ref_ctx.data_dir) / clipsound.PADS
    folder.mkdir(parents=True, exist_ok=True)
    old, fresh = folder / "old.wav", folder / "fresh.wav"
    for f in (old, fresh):
        f.write_bytes(b"x")
    os.utime(old, (time.time() - 2 * clipsound.KEEP,) * 2)
    build.image_job(press(references=["chars/Character 11.png"], sound=sound_item(ref_ctx)), ref_ctx)
    assert not old.exists() and fresh.exists()


def test_pad_runs_a_sound_on_in_silence_in_its_own_format(tmp_path):
    for raw, rate, align, zero in ((tiny_wav(1.0), 32_000, 4, b"\x00"), (float32(1.0), 32_000, 4, b"\x00"),
                                   (eight_bit(1.0), 8_000, 1, b"\x80")):
        src, dest = tmp_path / "in.wav", tmp_path / "out.wav"
        src.write_bytes(raw)
        assert sound.pad(src, dest, 1.5)
        data = sound.chunks(dest.read_bytes())[b"data"]
        assert len(data) == int(1.5 * rate) * align and data[-align:] == zero * align
        assert b"fact" not in sound.chunks(dest.read_bytes())
        assert not sound.pad(src, tmp_path / "none.wav", 1.0) and not (tmp_path / "none.wav").exists()


def test_a_sound_the_hub_cannot_read_is_refused_in_one_line(ref_ctx):
    for item in (sound_item(ref_ctx, "bad", data=b"not a wav"), "sounds/2026-10-17/gone.wav", 7):
        with pytest.raises(Invalid) as err:
            build.image_job(press(references=["chars/Character 11.png"], sound=item), ref_ctx)
        assert (err.value.field, err.value.text) == ("sound", clipsound.UNREAD)


def test_a_model_without_soundtrack_refuses_a_sound_in_one_line(ref_ctx):
    with pytest.raises(Invalid) as err:
        clipsound.sound(ref_ctx, {"sound": "sounds/x.wav"}, {"label": "Wan", "video": {"fps": 16}}, False)
    assert err.value.text == "Wan cannot follow a sound"
    with pytest.raises(Invalid) as err:
        clipsound.sound(ref_ctx, {"sound": "sounds/x.wav"}, {"label": "H3", "video": {"soundtrack": "A"}}, True)
    assert err.value.text == "A continued clip takes no sound"
    assert clipsound.sound(ref_ctx, {}, {"label": "Wan", "video": None}, False) is None, "no sound: today's clip"
