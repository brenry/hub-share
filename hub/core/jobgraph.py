"""A job's steps that read what an earlier step made: `JobPlan.inputs`, checked at submit,
filled by the lane as each task starts. Pure: no I/O.

`inputs[k-1]` says, for task k, which of its request's fields take what an earlier task made, `{field: (j, kind)}`
(j counted from 1, before k): "file" is the real path of the file task j landed, made for the next step (a between
file, `between`); "kept" is the same path of a file made to keep, landed in Media as it is made. A
field so filled is a string field of task k's request kind, or `items.<i>.path` (i from 0) of a request whose list
`items` has an item i, sent empty, or `audio.<i>.path` of its list `audio` (a join's track-2 sound), or
`references.<i>.path` of a clip's pictures (a start frame drawn by an earlier step). A
plan with no `inputs` (every job but a converted voice or a scene) is untouched by all of this.

`JobPlan.takes` holds, per shot, its takes, each a run of tasks in order; take 1 always runs, take t when
take t − 1 ran and was judged under the bar or failed and the plan's judge allows it (`runs`), a take's later task
when its first made a file. "best" hands on the last task of the shot's made take of highest rank
(`best`): its source is the last task of the shot's first take. A plan with no `takes` is untouched by this.
"""
from __future__ import annotations

import re
import typing
from collections.abc import Mapping
from typing import Any

from hub.core.api import Invalid, JobPlan, Judge, Take
from hub.core.supervisor import EngineFailed
from hub.core.takeplan import best
from hub.worker.engineapi import REQUESTS

MADE = ("file", "kept", "best")          # what an earlier step can hand on: its landed file's real path
NOTHING = "Step {} has nothing from step {}"
FAILED = "take {} failed: {}"
ITEM = re.compile(r"(items|audio|references)\.(\d+)\.path")   # a join's clip, a sound; a clip's picture


def _strings(kind: Any) -> set[str]:
    cls = REQUESTS.get(kind) if isinstance(kind, str) else None
    return {name for name, hint in typing.get_type_hints(cls).items() if hint is str} if cls else set()


def check(plan: JobPlan) -> None:
    """`inputs` empty, or one mapping per task whose every source is an earlier task's file and every field an
    empty string field of that task's request kind; else one line."""
    _takes(plan)
    if not plan.inputs:
        return
    if len(plan.inputs) != len(plan.tasks):
        raise Invalid("params", f"Inputs name {len(plan.inputs)} steps; the job has {len(plan.tasks)}")
    for k, (task, wants) in enumerate(zip(plan.tasks, plan.inputs, strict=True), 1):
        if not isinstance(wants, Mapping):
            raise Invalid("params", f"Step {k}'s inputs are not a mapping")
        fields = _strings(task.get("kind") if isinstance(task, Mapping) else None)
        for name, source in wants.items():
            if not isinstance(source, tuple) or len(source) != 2 or source[1] not in MADE:
                raise Invalid("params", f"Step {k}'s {name} names no earlier step's file")
            j = source[0]
            if not isinstance(j, int) or isinstance(j, bool) or not 1 <= j < k:
                raise Invalid("params", f"Step {k}'s {name} reads step {j}, which is not before it")
            if source[1] == "best" and j not in {shot[0][-1] for shot in plan.takes}:
                raise Invalid("params", f"Step {k}'s {name} reads step {j}, which ends no shot's first take")
            if ITEM.fullmatch(name):
                _item(task, name, k, j)
                continue
            if name not in fields:
                raise Invalid("params", f"Step {k} has no text field {name}")
            if task.get(name) != "":
                raise Invalid("params", f"Step {k}'s {name} is filled by step {j}; it is sent empty")


def _takes(plan: JobPlan) -> None:
    """`takes` empty, or disjoint runs of tasks in order, a shot's takes of equal length; else one line."""
    after = 0
    for n, shot in enumerate(plan.takes, 1):
        if not shot or len({len(take) for take in shot}) != 1:
            raise Invalid("params", f"Shot {n}'s takes are not of equal length")
        for take in shot:
            if not take or list(take) != list(range(take[0], take[0] + len(take))) or take[0] <= after \
                    or take[-1] > len(plan.tasks):
                raise Invalid("params", f"Shot {n}'s takes are not runs of steps in order")
            after = take[-1]


def _item(task: Mapping, name: str, k: int, j: int) -> None:
    """`items.<i>.path` (or `audio.<i>.path`): task k's list has an item i whose `path` is sent empty; else one
    line."""
    found = ITEM.fullmatch(name)
    i, items = int(found.group(2)), task.get(found.group(1))   # type: ignore[union-attr]
    if not isinstance(items, list) or not i < len(items) or not isinstance(items[i], Mapping):
        raise Invalid("params", f"Step {k} has no item {i}")
    if items[i].get("path") != "":
        raise Invalid("params", f"Step {k}'s {name} is filled by step {j}; it is sent empty")


def where(plan: JobPlan, k: int) -> tuple[int, int, int] | None:
    """Task k's (shot, take, the take's first task), shot and take from 1; None when it is in no take."""
    for n, shot in enumerate(plan.takes, 1):
        for t, take in enumerate(shot, 1):
            if take[0] <= k <= take[-1]:
                return n, t, take[0]
    return None


def _failed(take: tuple[int, ...], takes: Mapping[int, Take]) -> bool:
    return any(j in takes and not takes[j].passes and not takes[j].rank for j in take)


def runs(plan: JobPlan, k: int, takes: Mapping[int, Take], made: Mapping[int, str | None],
         judge: Judge | None) -> bool:
    """Whether task k runs. Take 1 always; take t's first task when take t − 1's first task ran and its `Take`
    does not pass, or the take failed, and `judge.again(shot, t)`; a take's later task when its first made a
    file. A task in no take: always."""
    at = where(plan, k)
    if at is None:
        return True
    shot, t, first = at
    if k != first:
        return bool(made.get(first)) and not _failed(plan.takes[shot - 1][t - 1], takes)
    if t == 1:
        return True
    before = plan.takes[shot - 1][t - 2]
    ran = before[0] in takes and (not takes[before[0]].passes or _failed(before, takes))
    return ran and judge is not None and judge.again(shot, t)


def absorbs(plan: JobPlan, k: int, made: Mapping[int, str | None], judge: Judge | None) -> bool:
    """A failure of task k is a failed take, not a failed job, when its shot has a take made, or a later take
    the judge allows; always, for a judge that says so (`alone`: the Track job's, every group alone)."""
    at = where(plan, k)
    if at is None:
        return False
    if getattr(judge, "alone", False):
        return True
    shot, t, _ = at
    takes = plan.takes[shot - 1]
    if any(made.get(take[-1]) for take in takes):
        return True
    return t < len(takes) and judge is not None and judge.again(shot, t + 1)


def fill(request: dict, inputs: Mapping[str, tuple[int, str]], made: Mapping[int, str], step: int,
         plan: JobPlan | None = None, takes: Mapping[int, Take] | None = None) -> dict:
    """Task `step`'s request with each field of `inputs` set to what its source made (`made`: task -> landed path);
    a source that made nothing fails the job in one line. A "best" source is the shot's best take (`best`). No
    inputs: the request as sent."""
    if not inputs:
        return request
    out = dict(request)
    for name, (j, kind) in inputs.items():
        if kind == "best" and plan is not None:
            shot = next(n for n, s in enumerate(plan.takes, 1) if s[0][-1] == j)
            j = best(plan, shot, takes or {}, made) or j
        if not made.get(j):
            raise EngineFailed("runtime", NOTHING.format(step, j))
        if found := ITEM.fullmatch(name):
            key, i = found.group(1), int(found.group(2))
            out[key] = [dict(it) for it in out[key]] if out[key] is request.get(key) else out[key]
            out[key][i]["path"] = made[j]
        else:
            out[name] = made[j]
    return out


def between(plan: JobPlan) -> set[int]:
    """The tasks whose file a later task reads as "file" (counted from 1): made for the next step, not to keep.
    A "kept" source lands in Media as it is made."""
    return {j for wants in plan.inputs for j, kind in wants.values() if kind == "file"}


def named(inputs: Mapping[str, tuple[int, str]], key: str = "items") -> set[int]:
    """The items of the list `key` whose `path` the inputs fill (`<key>.<i>.path`): the only ones sent with an empty
    path."""
    return {int(m.group(2)) for name in inputs if (m := ITEM.fullmatch(name)) and m.group(1) == key}

