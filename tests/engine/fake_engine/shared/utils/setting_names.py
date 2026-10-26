"""Fake `shared/utils/setting_names.py` (upstream's; the fork has none, and its adapter never reads it): the settings a
task may hold. Upstream's own list, as the capture holds it (`tests/fixtures/upstream-18.05/h3.json`,
found beside the test fakes the root names), plus the keys the fake's own definitions announce: its upstream flavour
still carries the fork's H3 definitions, whose families (the reference list, its detail, the text encoder, the one-pass
switch) real upstream refuses. `make_engine_root(h3=True)` writes the fixture's list alone in its place."""
from __future__ import annotations

import json
import os


def accepted_setting_names() -> list[str]:
    import wgp

    names = set(wgp.primary_settings) | {p["name"] for p in wgp.FAKE["generate_video"]}
    for model_def in wgp.models_def.values():
        names |= set(model_def.get("settings") or {})
    fixture = os.path.join(str(wgp.FAKE.get("fakes") or ""), os.pardir, "fixtures", "upstream-18.05", "h3.json")
    with open(fixture, encoding="utf-8") as f:
        names |= set(json.load(f)["accepted_settings"])
    return sorted(names)
