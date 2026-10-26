"""A spoken line's takes are its own job's (`presstakes`); the `job.finished` listener only
reads the job's notes. The best take (`notes.best`) is `last_take`, its words span teaches the pace; with no reading
the file's own span does and the card says the judge did not run; a line under the bar submits no job."""
from __future__ import annotations

import asyncio

from hub.modules.generate_image import build, chain, models, pace, presstakes, screen, takes
from tests.engine.test_generate_speech import ctx, press, request_of  # noqa: F401
from tests.engine.test_pace import wav
from tests.engine.test_upstream_rules import SPEECH, cat  # noqa: F401

WORDS = " ".join(["word"] * 30)


def finished(job, verdicts: dict[int, dict] | None, sounds: list[str], **notes) -> dict:
    judged = {"judged": {str(t): {"words": v} for t, v in verdicts.items()}} if verdicts else {}
    return {"state": "done", "tool": "generate-image", "job": job.id, "outputs": sounds, "notes": {**judged, **notes}}


def sound(c, stem: str) -> str:
    out = c.files.roots["sounds"] / "2026-10-17" / f"{stem}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(wav([(10.0, 0.5)]))
    return f"sounds/2026-10-17/{stem}.wav"


def test_a_line_press_is_one_task_and_the_judge_is_asked(ctx):  # noqa: F811
    plan = build.image_job(press(prompt=WORDS), ctx)
    assert [t["seed"] for t in plan.tasks] == [7] and plan.summary["seeds"] == [7] and plan.summary["count"] == 1
    assert plan.tasks[0]["judge"] is True
    ctx.settings = {**ctx.settings, "speech_judge": False}
    assert build.image_job(press(prompt=WORDS), ctx).tasks[0]["judge"] is False


def test_the_best_take_is_kept_the_pace_learned_and_no_job_submitted(ctx):  # noqa: F811
    job = ctx.jobs.submit("image", press(prompt=WORDS))
    a, b = sound(ctx, "a"), sound(ctx, "b")
    verdicts = {1: {"heard": 0.7, "first_miss": 5.4, "span": 9.0, "words": 30},
                2: {"heard": 0.95, "first_miss": 8.1, "span": 10.0, "words": 30}}
    said = "Take 2 of 2 is best (take 1: heard 70%); Heard 95% of the words; re-takes used 0.0 of 15 min"
    asyncio.run(chain.on_job_finished(ctx, finished(job, verdicts, [a, b], best=b, best_task=2, verdict=said)))
    assert pace.read(ctx) == {"pace": 3.0, "runs": 1}, "the best take's span, not the file's"
    assert len(ctx.jobs.jobs) == 1 and "verdict" not in job.notes, "the listener submits and says nothing"
    view = screen.view(ctx, ctx.engine.catalog, next(m for m in ctx.engine.catalog["models"] if m["id"] == SPEECH))
    assert view["last_take"] == {"id": b, **verdicts[2], "verdict": said}
    assert models.find(ctx.engine.catalog, SPEECH) is not None


def test_under_the_bar_no_job_is_submitted_from_the_listener(ctx):  # noqa: F811
    ctx.settings = {**ctx.settings, "speech_takes_max": 2, "speech_words_bar": 0.9}
    job = ctx.jobs.submit("image", press(prompt=WORDS))
    bad = {1: {"heard": 0.6, "first_miss": 5.4, "span": 9.0, "words": 30}}
    a = sound(ctx, "a")
    asyncio.run(chain.on_job_finished(ctx, finished(job, bad, [a], best=a, best_task=1, verdict="under")))
    assert len(ctx.jobs.jobs) == 1, "nothing re-takes from job.finished"
    assert not hasattr(takes, "retake") and not hasattr(takes, "remember") and not hasattr(takes, "presses")


def test_an_unheard_line_keeps_the_files_pace_and_says_the_judge_did_not_run(ctx):  # noqa: F811
    ctx.settings = {**ctx.settings, "speech_judge": False}
    job = ctx.jobs.submit("image", press(prompt=WORDS))
    assert job.plan.takes == () and job.plan.finish is None, "the judge off: the plain plan"
    asyncio.run(chain.on_job_finished(ctx, finished(job, None, [sound(ctx, "a")])))
    assert ctx.jobs.get(job.id).notes["verdict"] == takes.UNHEARD
    assert pace.read(ctx)["runs"] == 1 and len(ctx.jobs.jobs) == 1, "no re-take without a verdict"
    assert takes.best_of({}) is None
    assert takes.best_of({1: {"heard": 0.9, "first_miss": 2.0}, 2: {"heard": 0.9, "first_miss": None}}) == 2


def test_a_heard_press_with_no_reading_learns_from_its_file(ctx):  # noqa: F811
    """Judge on, Whisper absent: the job's own line (`LineJudge`, UNHEARD) stays; the pace from the file."""
    ctx.jobs.builders = {"image": presstakes.job}                  # the job kind as the manifest maps it
    job = ctx.jobs.submit("image", press(prompt=WORDS))
    assert isinstance(job.plan.finish, presstakes.Finish) and len(job.plan.tasks) == 3
    a = sound(ctx, "a")
    asyncio.run(chain.on_job_finished(ctx, finished(job, None, [a], best=a, best_task=1, verdict=takes.UNHEARD)))
    assert pace.read(ctx)["runs"] == 1
    assert screen.view(ctx, ctx.engine.catalog, next(m for m in ctx.engine.catalog["models"] if m["id"] == SPEECH))[
        "last_take"] == {"id": a, "verdict": takes.UNHEARD}


def test_no_listener_submits_a_job():
    """`takes.py` submits nothing; the job kind is `presstakes.job`."""
    from pathlib import Path

    from hub.modules.generate_image import manifest

    assert "ctx.jobs.submit" not in Path(takes.__file__).read_text()
    assert manifest.MODULE.jobs["image"] is presstakes.job
