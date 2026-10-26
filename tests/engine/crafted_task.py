"""Run by the engine's Python: `crafted_task.py <worker dir> <root> <state> <task.json> <out.json>`. Opens the worker's
Engine on a fake root and runs one request whose engine task is the one in task.json, as given (`Engine._task`
replaced): how a test reaches the engine with a task no Hub request makes (a window shorter than the clip, so the
engine chains passes). Writes {"events": [...], "done": {...}} to out.json."""
from __future__ import annotations

import json
import sys


def main(worker: str, root: str, state: str, task_path: str, out: str) -> int:
    sys.path.insert(0, worker)
    import wan2gp
    from engineapi import ClipRequest
    with open(task_path, encoding="utf-8") as f:
        task = json.load(f)
    engine = wan2gp.Engine(root, state, [], [])
    engine.open()
    engine._task = lambda request: task                     # the crafted engine task, as given
    events: list[dict] = []
    request = ClipRequest(task["model_type"], task["prompt"], (1, 1), task["seed"], task["video_length"])
    done = engine.run("crafted", 1, request, events.append)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"events": events, "done": done}, f)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:6]))
