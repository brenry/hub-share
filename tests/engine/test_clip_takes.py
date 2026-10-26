"""At the controller, the press asks the judges with the speaker (the shot's first
line's, else the first named identity) and carries the shot's framing; the press's own judge (`presstakes`, a
`ShotJudge` on its one shot) says the face, mouth and frame lines; the `job.finished` listener only reads the job's
notes: `last_take` and `last_clip` are the take it marked best, carrying its readings; nothing is submitted."""
from __future__ import annotations

import pytest

from hub.modules.generate_image import build, chain, presstakes, routes, takes
from tests.engine.test_video_refs import CAST, OMNI, clip_models, ctx, payload  # noqa: F401

FACE_OK = {"min": 0.62, "median": 0.7, "first": 0.71, "last": 0.68, "drift": -0.03, "lost_at": None, "present": 1.0}
FACE_LOST = {"min": 0.12, "median": 0.4, "first": 0.61, "last": 0.19, "drift": -0.42, "lost_at": 2.1, "present": 1.0}
MOUTH_OK = {"speaker": "Character 11", "lips": 0.81, "moving": 0.95, "talk": 0.03, "rest": 0.007, "speech": 4.2,
            "present": 1.0}
FRAME_CLOSE = {"size": 0.41, "size_first": 0.4, "size_last": 0.42, "x_first": 0.5, "x_last": 0.52, "y_first": 0.4,
               "y_last": 0.41}


@pytest.fixture
async def c(ctx):  # noqa: F811
    ctx.jobs.builders = {"image": build.image_job}         # the fake jobs build plans as core does
    return ctx


def finished(ctx, job, verdict: dict | None, stems=("c",)) -> dict:  # noqa: F811
    outputs = []
    for stem in stems:
        path = ctx.files.roots["clips"] / "2026-10-17" / f"{stem}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\0" * 64)
        outputs.append(f"clips/2026-10-17/{stem}.mp4")
    notes = {"judged": {str(i + 1): verdict for i in range(len(stems))}} if verdict is not None else {}
    if verdict is not None:                              # the press's last step marked its best take
        notes |= {"best": outputs[-1], "best_task": len(stems), "verdict": "the job's line"}
    return {"state": "done", "tool": "generate-image", "job": job.id, "outputs": outputs, "notes": notes}


def character_11_press(**extra) -> dict:
    return payload(model=OMNI, mode="refs", references=["chars/Character 11.png"], **extra)


def shot(ctx, framing: str, speaker: str | None = None) -> None:  # noqa: F811
    routes.session_part(ctx)["shot"] = {
        "subjects": [{"name": "Character 11"}], "where": "a stage", "camera": {"framing": framing},
        "action": ["the speaker talks"], **({"lines": [{"speaker": speaker, "words": "hello"}]} if speaker else {})}


def line(ctx, job) -> str:  # noqa: F811
    return ctx.jobs.get(job.id).notes["verdict"]


async def test_the_press_asks_the_judges_with_the_speaker_and_carries_the_framing(ctx):  # noqa: F811
    plan = build.image_job(character_11_press(), ctx)
    task = plan.tasks[0]
    assert (task["judge"], task["judge_bar"], task["speaker"]) == ("cpu", 0.3,
                                                                   "Character 11"), "the first named identity"
    assert "framing" not in plan.summary
    shot(ctx, "medium close-up on Character 7", speaker="Character 7")
    plan = build.image_job(character_11_press(), ctx)
    assert plan.tasks[0]["speaker"] == "Character 7" and plan.summary["framing"] == "medium close-up on Character 7"
    ctx.settings = {**ctx.settings, "clip_judge": False}
    assert build.image_job(character_11_press(), ctx).tasks[0]["judge"] is None


def said(c, verdict: dict) -> str:
    """The line the press's own judge gives one take judged `verdict`."""
    plan = presstakes.plan(c, build.image_job(character_11_press(), c))
    return plan.judge.done(1, {"judge": verdict, "seconds": 60.0}).line


async def test_a_held_face_a_mouth_with_the_words_and_a_fitting_frame(c):
    shot(c, "close-up on Character 11", speaker="Character 11")
    verdict = {"face": {"Character 11": FACE_OK}, "mouth": MOUTH_OK, "frame": {"Character 11": FRAME_CLOSE}, "words": {
        "heard": 1.0, "first_miss": None}}
    assert said(c, verdict) == ("Character 11's face held (0.70); Character 11's mouth moves with the words (0.81); "
                                "heard 100% of the words"), "the judge's sentences: the face by its median"
    job = c.jobs.submit("image", character_11_press())
    await chain.on_job_finished(c, finished(c, job, verdict, stems=("a", "b")))
    assert len(c.jobs.jobs) == 1, "nothing submitted from the listener"
    assert routes.session_part(c)["last_take"] == {"id": "clips/2026-10-17/b.mp4", "face": {"Character 11": FACE_OK},
                                                     "mouth": MOUTH_OK, "frame": {"Character 11": FRAME_CLOSE},
                                                     "verdict": "the job's line"}, "the readings, for the assistant"
    assert routes.session_part(c)["last_clip"] == "clips/2026-10-17/b.mp4"


async def test_the_best_take_not_the_newest_is_last_clip_and_last_take(c):
    job = c.jobs.submit("image", character_11_press())
    data = finished(c, job, {"face": {"Character 11": FACE_OK}}, stems=("a", "b"))
    data["notes"] |= {"best": "clips/2026-10-17/a.mp4", "best_task": 1}
    await chain.on_job_finished(c, data)
    assert routes.session_part(c)["last_clip"] == "clips/2026-10-17/a.mp4", "Continue reads the best take"
    assert routes.session_part(c)["last_take"]["id"] == "clips/2026-10-17/a.mp4"


async def test_a_wrong_size_fails_the_take_and_the_frame_lines(c):
    shot(c, "wide shot of the stage")
    verdict = {"face": {"Character 11": FACE_OK}, "mouth": None, "mouth_why": "no speech in the soundtrack",
               "frame": {"Character 11": FRAME_CLOSE}}
    plan = presstakes.plan(c, build.image_job(character_11_press(), c))
    take = plan.judge.done(1, {"judge": verdict})
    assert not take.passes and take.line == ("Character 11's face held (0.70); Character 11's face is 0.41 of the "
                                             "frame's height; the shot asked for a wide shot")
    assert takes.frame_line(verdict, "Character 11", "medium shot", 0.3, 0.12).endswith("asked for a medium shot")
    assert takes.frame_line(verdict, "Character 11", "a tight close up", 0.3, 0.12) is None, "0.41 is a close-up"
    assert takes.frame_line(verdict, "Character 11", "over the shoulder", 0.3,
                            0.12) is None, "no band named: nothing to say"
    assert takes.frame_line(verdict, "Character 4", "wide", 0.3, 0.12) is None, "no numbers for the character"


async def test_a_still_mouth_and_a_lost_face_fail_the_take(c):
    shot(c, "medium shot", speaker="Character 11")
    still = {"face": {"Character 11": FACE_OK}, "mouth": {**MOUTH_OK, "moving": 0.05, "lips": None}, "frame": {}}
    assert said(c, still).startswith("Character 11's face held (0.70); Character 11's mouth is still while speaking "
                                     "(5% of the speaking frames move)")
    lost = {"face": {"Character 11": FACE_LOST}, "mouth": {**MOUTH_OK, "lips": 0.45}, "frame": {}}
    assert said(c, lost).startswith("Character 11's face was lost after 2.1 s (0.61 → 0.19); try a closer picture, "
                                    "the character's views, or a shorter clip; Character 11's mouth does not follow "
                                    "the words (0.45, 0.60 is the bar)")


async def test_a_compound_framing_fits_either_band(c):
    verdict = {"face": {"Character 11": FACE_OK, "Character 4": FACE_OK}, "frame": {"Character 11": {"size": 0.35},
                                                                                    "Character 4": {"size": 0.1}}}
    assert takes.frame_line(verdict, "Character 11", "medium close-up on Character 11", 0.3,
                            0.12) is None, "a close-up fits an MCU"
    assert takes.frame_line(verdict, "Character 11", "medium close-up", 0.3, 0.12) is None
    assert takes.frame_line(verdict, "Character 4", "medium close-up", 0.3, 0.12) == (
        "Character 4's face is 0.10 of the frame's height; the shot asked for a medium shot or a close-up")
    assert takes.frame_subject(verdict, "close-up on Character 4", "Character 11",
                               "Character 11") == "Character 4", "the framing names the character"
    assert takes.frame_subject(verdict, "a wide shot", "Character 4",
                               "Character 11") == "Character 4", "else the speaker"
    assert takes.frame_subject(verdict, "a wide shot", None, "Character 11") == "Character 11", "else the lowest"


async def test_a_faceless_picture_is_named_and_no_judge_keeps_the_newest(c):
    named = {"face": {"Character 11": FACE_OK}, "mouth": MOUTH_OK, "frame": {"Character 11": FRAME_CLOSE},
             "faceless": ["Character 4"]}
    assert said(c, named) == "Character 11's face held (0.70); Character 4's picture shows no face to judge by", \
        "no line: no mouth"
    plain = c.jobs.submit("image", character_11_press())                   # no judge asked: the newest take, no verdict
    await chain.on_job_finished(c, finished(c, plain, None))
    assert routes.session_part(c)["last_take"] == {"id": "clips/2026-10-17/c.mp4", "verdict": None}
    assert "verdict" not in c.jobs.get(plain.id).notes, "no judge asked: nothing said"


async def test_the_judge_not_running_is_said(c):
    assert said(c, {"face": None, "why": "buffalo_l/det_10g.onnx not found"}) == (
        "Not judged: The face judge did not run: buffalo_l/det_10g.onnx not found")
    assert CAST["Character 11.png"] == (1000, 560)


async def test_a_converted_clips_take_is_the_converted_file(c):
    """A job of a render and a voice step: the job's best is the converted clip (its last task's file),
    its readings the render's (task 1)."""
    job = c.jobs.submit("image", character_11_press())
    data = finished(c, job, {"face": {"Character 11": FACE_OK}, "mouth": MOUTH_OK}, stems=("converted",))
    data["notes"] |= {"judged": {"1": {"face": {"Character 11": FACE_OK}, "mouth": MOUTH_OK}}, "best_task": 1}
    await takes.on_clip_finished(c, job, data)
    assert routes.session_part(c)["last_take"]["id"] == "clips/2026-10-17/converted.mp4"
    assert routes.session_part(c)["last_take"]["mouth"] == MOUTH_OK
