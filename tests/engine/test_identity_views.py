"""A character's views go with the character's picture. A box holding a character with views sends the
character's picture then the character's views, each an identity of the character's name and cut-out; over the model's
cap in all is refused in one line; a model whose boxes are not identities, and a character without views, give today's
task."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.modules.generate_image import build, models
from hub.worker import enginewire
from tests.engine import test_upstream_rules as rules
from tests.engine.test_upstream_rules import REF2VA, entry, press, sent

cat, accepted, ref_ctx = rules.cat, rules.accepted, rules.ref_ctx


def add_views(ctx, name: str, *views: str) -> None:
    folder = Path(ctx.files._real["chars"])
    for v in views:
        Image.new("RGB", (640, 640)).save(folder / f"{name}.{v}.png")


def test_a_character_with_views_sends_them_as_identities_of_the_characters_name(ref_ctx, accepted):
    add_views(ref_ctx, "Character 11", "side", "body")
    plan = build.image_job(press(references=["chars/Character 11.png", "chars/Character 4.png"], cutout=[True, True]),
                           ref_ctx)
    refs = plan.tasks[0]["references"]
    # upstream Ref2VA takes no names with its pictures: nameless identities, each with the box's cut-out
    assert [(Path(r["path"]).name, r["role"], r["name"], r["cutout"]) for r in refs] == [
        ("Character 11.png", "identity", None, True), ("Character 11.body.png", "identity", None, True),
        ("Character 11.side.png", "identity", None, True), ("Character 4.png", "identity", None, True)]
    task = sent(models.cached(), enginewire.request_parse(plan.tasks[0]))
    assert [Path(p).name for p in task["image_refs"]] == ["Character 11.png", "Character 11.body.png",
                                                          "Character 11.side.png", "Character 4.png"]


def test_without_views_the_task_is_todays(ref_ctx):
    before = build.image_job(press(references=["chars/Character 11.png"]), ref_ctx).tasks[0]
    assert [Path(r["path"]).name for r in before["references"]] == ["Character 11.png"]


def test_over_the_cap_with_views_is_refused_naming_the_character(ref_ctx):
    cap = int(entry(models.cached(), REF2VA)["video"]["references"]["max"])
    add_views(ref_ctx, "Character 12", *[f"v{i}" for i in range(cap)])
    label = entry(models.cached(), REF2VA)["name"]
    with pytest.raises(Invalid) as err:
        build.image_job(press(references=["chars/Character 12.png"]), ref_ctx)
    assert err.value.text == f"{label} takes {cap} identities; Character 12 with its views makes {cap + 1}"
