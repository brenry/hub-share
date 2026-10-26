"""The engine's checks on an Omni task's reference manifest, copied from its `reference_manifest.py` (the item rules)
and `ref2va.py` (the picture's shape, the detail value), each failing the task with the engine's kind of line, so a
task the Hub builds is checked against an engine-shaped refusal. A manifest is the list under any `*_references`
key; a picture file that is not there is left alone (the worker tests send stand-in paths)."""
from __future__ import annotations

import os

IMAGE_INTENTS = {"identity", "scene", "style", "composition"}
DETAILS = ("match", "max")


def _shape(path: str) -> None:
    from PIL import Image

    with Image.open(path) as im:
        width, height = im.size
    if width > 4 * height or height > 4 * width:
        raise ValueError(f"A reference image must be within 1:4 and 4:1, got {width}x{height}.")


def check(inputs: dict) -> dict:
    """The task's inputs as they came, once every manifest and detail value has passed; else the engine's line."""
    for key, value in inputs.items():
        if key.endswith("_reference_detail") and value is not None and value not in DETAILS:
            raise ValueError("Reference detail must be 'match' or 'max'.")
        if not key.endswith("_references") or not isinstance(value, list):
            continue
        for index, raw in enumerate(value, 1):
            if not isinstance(raw, dict):
                raise ValueError(f"Reference {index} must be an object.")
            if str(raw.get("type") or raw.get("kind") or "").strip().lower() != "image":
                raise ValueError(f"Reference {index} must be an image, video, or audio reference.")
            path = str(raw.get("path") or "").strip()
            if not path:
                raise ValueError(f"Reference {index} has no uploaded file.")
            intent = str(raw.get("image_intent") or "identity").strip().lower()
            if intent not in IMAGE_INTENTS:
                raise ValueError(f"Reference {index} has invalid image intent {intent!r}; expected one of: "
                                 f"{', '.join(sorted(IMAGE_INTENTS))}.")
            if raw.get("remove_background") is not None and not isinstance(raw["remove_background"], bool):
                raise ValueError(f"Reference {index} remove_background must be true or false.")
            if raw.get("character_name") is not None and not isinstance(raw["character_name"], str):
                raise ValueError(f"Reference {index} character_name must be text.")
            if os.path.isfile(path):
                _shape(path)
    return inputs
