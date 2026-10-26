"""Continue a clip, the job (Stage 6): a clip in box 1 becomes the one "V" task at the source's size, in one
pass of N + overlap - 1, with the summary the job card reads; the source never moves (no folder per scene); every
refusal is one plain line, said before submit."""
from __future__ import annotations

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.modules.generate_image import build, chain, models, routes
from hub.worker import enginewire, probe
from tests.engine.continue_kit import (
    DAY,
    FUSED,
    IMAGE,
    LABEL,
    LOOSE,
    OMNI,
    OMNI_LABEL,
    PROMPT,
    PRUNED,
    STEM,
    dump_catalog,
    make_ctx,
    press,
    put_clip,
    real,
)
from tests.engine.helpers import engine_task


@pytest.fixture(scope="module")
def clip_models(tmp_path_factory) -> list[dict]:
    return dump_catalog(tmp_path_factory.mktemp("engine"))


@pytest.fixture
async def ctx(tmp_path, clip_models):
    c = await make_ctx(tmp_path, clip_models)
    put_clip(c)
    return c


def refusal(ctx, params: dict) -> str:
    with pytest.raises(Invalid) as err:
        build.image_job(params, ctx)
    return err.value.text


def engine(request: dict) -> dict:
    """The engine task the worker's adapter makes of a plan's request."""
    return engine_task(request, models.cached())


def engines(plan) -> tuple[dict, ...]:
    return tuple(engine(t) for t in plan.tasks)


def task_for(ctx, n: int, clip_id: str = LOOSE, steps: int = 20) -> dict:
    return {"model_type": PRUNED, "image_mode": 0, "prompt": PROMPT, "resolution": "960x544", "video_length": n,
            "sliding_window_size": n + 17, "sliding_window_overlap": 18, "minimax_h3_multi_window": False,
            "num_inference_steps": steps, "seed": 7, "batch_size": 1, "multi_prompts_gen_type": "FG",
            "image_prompt_type": "V", "video_source": real(ctx, clip_id), "keep_frames_video_source": "",
            "video_prompt_type": "", "minimax_h3_text_encoder": "nvfp4_awq"}


async def test_the_continue_task_for_124_frames(ctx):
    plan = build.image_job(press(), ctx)
    assert engines(plan) == (task_for(ctx, 124),), "every value explicit; no picture key, no width or height"
    assert engine(plan.tasks[0])["video_source"].startswith("/")
    assert plan.summary == {
        "prompt": PROMPT, "model": LABEL, "model_id": PRUNED, "mode": "continue", "kind": "clip", "continues": LOOSE,
        "width": 960, "height": 544, "count": 1, "frames": 124, "seconds": round(123 / 24, 2),
        "scene_seconds": round(124 / 24 + 123 / 24, 2), "steps": 20, "guidance": None, "seeds": [7], "loras": [],
        "references": [STEM]}
    assert (plan.lane_kind, plan.model) == ("image", PRUNED)


async def test_the_longest_step_and_the_one_over_it(ctx):
    plan = build.image_job(press(frames=328, width=1, height=1), ctx)
    sent = engines(plan)
    assert sent == (task_for(ctx, 328),) and sent[0]["sliding_window_size"] == 345, "the size is the clip's"
    assert refusal(ctx, press(frames=345, refs=[LOOSE])) == "Each step is at most 13.7 s"
    assert refusal(ctx, press(frames=330, refs=[LOOSE])) == "Each step is at most 13.7 s", "snapped up to 345"


async def test_the_step_follows_the_card_and_the_text_encoder(ctx):
    ctx.doc(routes.DRAFT, {}).replace({"model": PRUNED, "advancedByModel": {PRUNED: {
        "frames": 141, "text_encoder": "int8"}}})
    plan = build.image_job(press(frames=None), ctx)
    sent = engine(plan.tasks[0])
    assert {k: sent[k] for k in ("video_length", "sliding_window_size", "minimax_h3_text_encoder")} == {
        "video_length": 141, "sliding_window_size": 158, "minimax_h3_text_encoder": "int8"}


async def test_the_probe_sends_the_same_task(ctx, clip_models):
    plan = build.image_job(press(prompt=probe.PROMPT, seed={"mode": "fixed", "value": probe.SEED}), ctx)
    model = next(m for m in clip_models if m["id"] == PRUNED)
    path = real(ctx, LOOSE)
    request = probe.continue_request(model, path, 960, 544, probe.frames(model, None), model["video"]["steps"],
                                     probe.SEED, probe.PROMPT)
    sent = {k: v for k, v in plan.tasks[0].items() if k not in ("judge", "judge_bar")}
    assert enginewire.request_wire(request) == {**sent, "judge": None, "judge_bar": 0.3}, (
        "the face judge is the Hub's, after the engine: the probe has no boxes to judge against")


async def test_the_source_stays_where_it_is(ctx):
    part = routes.session_part(ctx)
    box = {"id": LOOSE, "w": 960, "h": 544, "kind": "clip", "seconds": 5.167}
    part.update(references=[box], last_clip=LOOSE, clip_models={LOOSE: FUSED})
    build.image_job(press(), ctx)
    assert (part["references"], part["last_clip"], part["clip_models"]) == ([box], LOOSE, {LOOSE: FUSED})
    day = ctx.files.roots["clips"] / DAY
    assert [p.name for p in day.iterdir()] == [f"{STEM}.mp4"], "no folder per scene"
    assert ctx.bus.sent == []
    assert refusal(ctx, press(frames=345)) == "Each step is at most 13.7 s"
    assert (day / f"{STEM}.mp4").is_file()


async def test_the_clip_and_model_refusals(ctx):
    assert refusal(ctx, press(refs=[f"clips/{DAY}/gone.mp4"])) == "The clip to continue is gone"
    assert refusal(ctx, press(refs=[f"clips/{DAY}/../x.mp4"])) == "The clip to continue is gone"
    assert refusal(ctx, press(model=OMNI)) == f"{OMNI_LABEL} cannot continue a clip"
    assert refusal(ctx, press(model=IMAGE)) == "Flux 2 Klein 9B cannot continue a clip"
    put_clip(ctx, f"clips/{DAY}/bad.mp4", b"\0\0\0\x08free not an mp4")
    assert refusal(ctx, press(refs=[f"clips/{DAY}/bad.mp4"])) == "This clip is not an MP4 the hub can read"
    put_clip(ctx, f"clips/{DAY}/short.mp4", frames=17)
    assert refusal(ctx, press(refs=[f"clips/{DAY}/short.mp4"])) == "This clip is shorter than 18 frames"
    put_clip(ctx, f"clips/{DAY}/odd.mp4", w=1000, h=500)
    assert refusal(ctx, press(refs=[f"clips/{DAY}/odd.mp4"])) == "This clip's size is not one the model makes"
    put_clip(ctx, f"clips/{DAY}/wide.mp4", w=1632, h=704)
    assert build.image_job(press(refs=[f"clips/{DAY}/wide.mp4"]), ctx).summary["width"] == 1632, \
        "any tier the catalog reports, offered on the size menu or not"


async def test_a_continued_clip_takes_only_box_1(ctx):
    pic = ctx.files.roots["out"] / DAY / "r1.png"
    pic.parent.mkdir(parents=True)
    Image.new("RGB", (960, 544)).save(pic)
    for refs in ([LOOSE, f"out/{DAY}/r1.png"], [f"out/{DAY}/r1.png", LOOSE], [LOOSE, LOOSE]):
        assert refusal(ctx, press(refs=refs)) == "A continued clip takes only box 1", refs
    assert refusal(ctx, press(model=FUSED, refs=[LOOSE, f"out/{DAY}/r1.png"])) == "A continued clip takes only box 1"


async def test_the_scene_cap(ctx):
    put_clip(ctx, f"clips/{DAY}/long.mp4", frames=59 * 24)
    scene = round(59 + 123 / 24, 2)
    assert refusal(ctx, press(refs=[f"clips/{DAY}/long.mp4"])) == f"The scene would be {scene:g} s; the longest is 60 s"
    ctx.settings["continue_max_seconds"] = 65
    assert build.image_job(press(refs=[f"clips/{DAY}/long.mp4"]), ctx).summary["scene_seconds"] == scene


async def test_a_picture_job_and_a_plain_clip_are_as_before(ctx):
    plain = build.image_job(press(mode="new", refs=[]), ctx)
    assert engine(plain.tasks[0])["sliding_window_size"] == 124
    assert "video_source" not in engine(plain.tasks[0]) and plain.summary["mode"] == "new"
    assert chain.source(ctx, []) is None and chain.source(ctx, None) is None
    assert chain.source(ctx, [f"out/{DAY}/r1.png"]) is None, "a picture in box 1 is a start frame, not a continue"
