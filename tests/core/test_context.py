"""A listener's refusal or fault is one line on stderr, never silent; the other listeners still run."""
from __future__ import annotations

import asyncio

from hub.core.context import Events


class Ctx:
    module_id = "generate-image"


async def test_a_listener_that_raises_writes_one_stderr_line_and_the_rest_run(capsys):
    seen: list[dict] = []
    events = Events()

    async def on_finished(ctx, data):
        raise RuntimeError("Ref2VA follows at most 20 s of sound in one clip\nsecond line")

    async def other(ctx, data):
        seen.append(data)

    events.listen("job.finished", on_finished, Ctx())
    events.listen("job.finished", other, Ctx())
    events.emit("job.finished", {"job": "j_1"})
    await asyncio.gather(*events._tasks)
    out = capsys.readouterr()
    assert out.err == "generate-image listener on_finished: Ref2VA follows at most 20 s of sound in one clip\n"
    assert out.out == "" and seen == [{"job": "j_1"}]


async def test_a_fault_with_no_text_names_its_type(capsys):
    events = Events()

    async def bad(ctx, data):
        raise KeyError()

    events.listen("x", bad, object())
    events.emit("x", {})
    await asyncio.gather(*events._tasks)
    assert capsys.readouterr().err == "? listener bad: KeyError\n"
