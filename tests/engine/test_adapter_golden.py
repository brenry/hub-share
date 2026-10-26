"""The adapter split changes no behaviour: for the fake engine in both flavours, the catalog the worker answers
(`main.py --dump-catalog`) and the engine task each Hub task becomes (`golden_tasks.py`) are byte-identical to the
files stored before engine key knowledge moved into `hub/worker/adapters/` (`tests/fixtures/adapters/`). The engine
root's path is the only thing normalised (`<root>`).

The fork's tasks are the crafted TASKS (its own keys) and the Hub's requests are held equal to them. Upstream's are
the Hub's requests through the upstream adapter on upstream's own H3 definitions (`make_engine_root(h3=True)`, from the
capture of 18.05), stored in Stage 9 step 5 and unchanged by the capture: no fork key or fork model id is in
them, and every key is one upstream accepts.

To store a new expected file on purpose (a behaviour change, said in the commit): `HUB_WRITE_GOLDEN=1 pytest <this>`.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.engine.helpers import ENGINE_PYTHON, FIXTURES, HERE, UPSTREAM_H3, WORKER, make_engine_root

GOLDEN = FIXTURES / "adapters"
DRIVER = HERE / "golden_tasks.py"


def normal(text: str, root: Path) -> str:
    for path in sorted({str(root), os.path.realpath(root)}, key=len, reverse=True):
        text = text.replace(path, "<root>")
    return text


def check(name: str, text: str) -> None:
    path = GOLDEN / name
    if os.environ.get("HUB_WRITE_GOLDEN"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        pytest.skip(f"wrote {name}")
    assert text == path.read_text(encoding="utf-8"), f"{name} differs from the stored file"


@pytest.mark.parametrize("flavour", ["legacy", "upstream"])
def test_the_catalog_is_byte_identical(tmp_path, flavour):
    root = make_engine_root(tmp_path, flavour)
    out = tmp_path / "catalog.json"
    subprocess.run([ENGINE_PYTHON, "-B", str(WORKER), "--root", str(root), "--dump-catalog", str(out)],
                   check=True, capture_output=True, timeout=60)
    check(f"catalog-{flavour}.json", normal(out.read_text(encoding="utf-8"), root))


def made(tmp_path: Path, flavour: str, mode: str) -> str:
    """The driver's file (`golden_tasks.py`) for a root of this flavour: the fork's fake root, upstream's with its own
    H3 definitions."""
    root = make_engine_root(tmp_path, flavour, h3=flavour == "upstream")
    out = tmp_path / "tasks.json"
    subprocess.run([ENGINE_PYTHON, "-B", str(DRIVER), str(WORKER.parent), str(root), str(tmp_path / "state"),
                    str(out), mode], check=True, capture_output=True, timeout=60)
    return normal(out.read_text(encoding="utf-8"), root)


@pytest.mark.parametrize("flavour", ["legacy", "upstream"])
def test_every_engine_task_is_byte_identical(tmp_path, flavour):
    check(f"tasks-{flavour}.json", made(tmp_path, flavour, "tasks" if flavour == "legacy" else "requests"))


def test_a_hub_request_becomes_the_stored_engine_task(tmp_path):
    """Stage 9 step 4: the modules send requests and the adapter builds the engine task. The same picture and clips in
    the Hub's words (`golden_tasks.requests`: a picture with a reference, a text clip, a start and end frame, an
    identity, a continue) become exactly the engine parameters stored for the fork (key order aside)."""
    got = json.loads(made(tmp_path, "legacy", "requests"))
    stored = json.loads((GOLDEN / "tasks-legacy.json").read_text(encoding="utf-8"))
    assert set(got) == {"picture", "clip", "clip_start_end", "clip_identity", "clip_continue"}
    for name, params in got.items():
        assert params == stored[name], name


FORK_KEYS = ("_multi_window", "_text_encoder", "_references", "_reference_detail", "image_fit_mode", "MMAudio_setting")


def test_upstreams_tasks_hold_only_keys_it_accepts():
    """R16 §4 rule 1: every key of every stored upstream task is one upstream accepts (the fixture's list); no fork key
    and no fork model id is left in them; the pruned FL2VA stands where the fork's H3 stood."""
    accepted = set(json.loads(UPSTREAM_H3.read_text(encoding="utf-8"))["accepted_settings"])
    stored = json.loads((GOLDEN / "tasks-upstream.json").read_text(encoding="utf-8"))
    assert {"picture", "clip", "clip_start_end", "clip_identity", "clip_continue"} <= set(stored)
    for name, task in stored.items():
        assert set(task) <= accepted, (name, sorted(set(task) - accepted))
        assert not [k for k in task if k.endswith(FORK_KEYS)], name
    fork_types = {"minimax_h3", "minimax_h3_fused_turbo", "minimax_h3_ref2va"}
    assert not {t["model_type"] for t in stored.values()} & fork_types
