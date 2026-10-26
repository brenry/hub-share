"""Run by the engine's Python: `golden_tasks.py <worker dir> <root> <state> <out.json> [requests]`. Opens the worker's
Engine on a fake root and writes, as one JSON object, the engine task each of TASKS becomes (`Engine._params`, exactly
what `submit_task` is given). `test_adapter_golden.py` compares it with the stored file: moving engine knowledge into
the adapters must change no byte of any task. With `requests`: what each of the Hub's requests (as the modules send
them: the fork's `requests`, the same picture and clips as TASKS; on an upstream root, `upstream_requests`, the same
in upstream's own H3 models) becomes through the adapter (`Engine._task`, then `_params`)."""
from __future__ import annotations

import json
import sys

CLIP = {"model_type": "minimax_h3", "prompt": "a lighthouse at dusk", "resolution": "960x544", "seed": 7,
        "image_mode": 0, "video_length": 141, "sliding_window_size": 141, "minimax_h3_multi_window": False,
        "num_inference_steps": 3, "batch_size": 1, "multi_prompts_gen_type": "FG", "image_prompt_type": "",
        "video_prompt_type": "", "minimax_h3_text_encoder": "nvfp4_awq"}
IMAGE = {"model_type": "flux2_klein_9b", "prompt": "a cat", "resolution": "64x48", "seed": 7, "batch_size": 1,
         "image_mode": 1, "multi_prompts_gen_type": "FG", "video_prompt_type": "KI", "remove_background_images_ref": 0,
         "activated_loras": ["style/ink.safetensors", "grain.safetensors"], "loras_multipliers": "0.8 1.0",
         "num_inference_steps": 4, "guidance_scale": 1.0, "image_refs": ["/abs/character 11.png"]}
# The picture a module makes of PICTURE (`requests`): its reference under the model's letter, no guidance (Klein 9B has
# none), whole multipliers as the Hub writes them.
MADE_PICTURE = {"model_type": "flux2_klein_9b", "prompt": "a cat", "resolution": "64x48", "batch_size": 1,
                "image_mode": 1, "multi_prompts_gen_type": "FG", "video_prompt_type": "I",
                "remove_background_images_ref": 0, "activated_loras": ["style/ink.safetensors", "grain.safetensors"],
                "loras_multipliers": "0.8 1", "num_inference_steps": 4, "image_refs": ["/abs/character 11.png"],
                "seed": 7}
TASKS = {
    "image": IMAGE,
    "picture": MADE_PICTURE,
    "image_plain": {**IMAGE, "model_type": "z_image", "video_prompt_type": "", "activated_loras": [],
                    "loras_multipliers": "", "image_refs": None, "multi_prompts_gen_type": "G"},
    "clip": CLIP,
    "clip_start_end": {**CLIP, "image_prompt_type": "SE", "image_start": "/abs/a.png", "image_end": "/abs/b.png",
                       "image_fit_mode": "crop"},
    "clip_identity": {**CLIP, "model_type": "minimax_h3_ref2va", "minimax_h3_reference_detail": "max",
                      "minimax_h3_references": [{"type": "image", "path": "/abs/character 11.png",
                                                 "image_intent": "identity"}]},
    "clip_continue": {**CLIP, "model_type": "minimax_h3_fused_turbo", "video_length": 107, "sliding_window_size": 124,
                      "sliding_window_overlap": 18, "image_prompt_type": "V", "video_source": "/abs/clip.mp4",
                      "keep_frames_video_source": ""},
}


def picture():
    from engineapi import PictureRequest, Reference
    return PictureRequest("flux2_klein_9b", "a cat", (64, 48), 7, steps=4,
                          loras=[("style/ink.safetensors", 0.8), ("grain.safetensors", 1)],
                          references=[Reference("/abs/character 11.png", "reference")])


def requests() -> dict:
    from engineapi import ClipRequest, Reference
    clip = {"prompt": CLIP["prompt"], "size": (960, 544), "seed": 7, "frames": 141, "steps": 3}
    return {
        "picture": picture(),
        "clip": ClipRequest("minimax_h3", **clip),
        "clip_start_end": ClipRequest("minimax_h3", **clip, references=[Reference("/abs/a.png", "start"),
                                                                         Reference("/abs/b.png", "end")]),
        "clip_identity": ClipRequest("minimax_h3_ref2va", **clip, references=[Reference("/abs/character 11.png",
                                                                                        "identity")],
                                     detail="max"),
        "clip_continue": ClipRequest("minimax_h3_fused_turbo", **{**clip, "frames": 107},
                                     references=[Reference("/abs/clip.mp4", "source")]),
    }


def upstream_requests() -> dict:
    """The same picture and clips for upstream's own H3 models (`make_engine_root(h3=True)`): the pruned FL2VA where the
    fork had its H3, the pruned Ref2VA for identities (two, both cut out), and what upstream adds: a text encoder by
    `config`, the full FL2VA, the 8-step PDD and the shortest clip (its window at the floor)."""
    from engineapi import ClipRequest, Reference
    clip = {"prompt": CLIP["prompt"], "size": (960, 544), "seed": 7, "frames": 141, "steps": 20}
    fl2va = "minimax_h3_fl2va_pruned"
    return {
        "picture": picture(),
        "clip": ClipRequest(fl2va, **clip),
        "clip_start_end": ClipRequest(fl2va, **clip, references=[Reference("/abs/a.png", "start"),
                                                                 Reference("/abs/b.png", "end")]),
        "clip_identity": ClipRequest("minimax_h3_ref2va_pruned", **clip,
                                     references=[Reference("/abs/character 11.png", "identity", cutout=True),
                                                 Reference("/abs/character 4.png", "identity", cutout=True)]),
        "clip_continue": ClipRequest(fl2va, **{**clip, "frames": 107},
                                     references=[Reference("/abs/clip.mp4", "source")]),
        "clip_encoder": ClipRequest("minimax_h3_fl2va", **clip, encoder="nvfp4_awq"),
        "clip_pdd": ClipRequest("minimax_h3_fl2va_pdd", **{**clip, "steps": 8}),
        "clip_shortest": ClipRequest(fl2va, **{**clip, "frames": 107}),
    }


def main(worker: str, root: str, state: str, out: str, mode: str = "tasks") -> int:
    sys.path.insert(0, worker)
    import wan2gp
    engine = wan2gp.Engine(root, state, [], [])
    engine.open()
    if mode == "requests":
        made = {name: engine._params(engine._task(r), r.model)
                for name, r in (upstream_requests() if engine.api == "upstream" else requests()).items()}
        with open(out, "w", encoding="utf-8") as f:
            f.write(json.dumps(made, indent=1, ensure_ascii=False) + "\n")
        return 0
    with open(out, "w", encoding="utf-8") as f:
        made = {name: engine._params(settings, settings["model_type"]) for name, settings in TASKS.items()}
        f.write(json.dumps(made, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:6]))
