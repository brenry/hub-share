"""The VRAM plan: run, or release the lane's other model and then run (one image lane per GPU)."""
from __future__ import annotations

from dataclasses import fields, replace

import pytest

from hub.core.plan import Plan, Situation, decide

GB = 1024
BASE = Situation(lane="image.gpu0", model="flux", label="Flux", resident=(), need=None)


def s(**kw: object) -> Situation:
    return replace(BASE, **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize("name, sit, light, action, release, text", [
    ("loaded, need unknown", s(resident=("flux",)), "green", "run", (), "Flux loaded"),
    ("loaded, need known", s(resident=("flux",), need=16 * GB), "green", "run", (), "Flux loaded"),
    ("swap models", s(resident=("qwen",), need=18 * GB), "amber", "release", ("image.gpu0",), "Switching to Flux"),
    ("load, nothing resident", s(need=18 * GB), "amber", "run", (), "Loading Flux"),
    ("first run", s(), "amber", "run", (), "First run of this model"),
    ("first run unloads the lane's other model", s(resident=("qwen",)), "amber", "release", ("image.gpu0",),
     "First run of this model"),
    ("a need bigger than any card still runs", s(need=400 * GB), "amber", "run", (), "Loading Flux"),
])
def test_rows(name: str, sit: Situation, light: str, action: str, release: tuple, text: str) -> None:
    plan = decide(sit)
    assert (plan.light, plan.action, plan.release, plan.text) == (light, action, release, text)


def test_the_plan_knows_nothing_of_other_programs() -> None:
    assert {f.name for f in fields(Situation)} == {"lane", "model", "label", "resident", "need"}
    assert {f.name for f in fields(Plan)} == {"light", "action", "text", "release"}
