"""Envelope parsing (every catalogue example) and a line's outbox: coalescing, barriers, overflow, beat."""
from __future__ import annotations

import asyncio

import pytest

from hub.core import messages as M
from hub.core.line import Bucket, Outbox

CATALOGUE = [
    '{"t":"hello","id":"h1","d":{"proto":1,"role":"media","screen":"scr_7Q2KX9AB","label":"Right","subs":null}}',
    '{"t":"focus","d":{"tool":"generate-image"}}',
    '{"t":"sockets","d":{"tool":"generate-image","mode":"refs","primary":"reference","sockets":[]}}',
    '{"t":"sub","d":{"lanes":["jobs","gpu"]}}', '{"t":"unsub","d":{"lanes":["gpu"]}}',
    '{"t":"send","id":"snd_01J9ZK4M2Q","d":{"tool":"generate-image","socket":"reference","items":["out/a.png"]}}',
    '{"t":"received","re":"snd_01J9ZK4M2Q","d":{"placed":[],"refused":[]}}',
    '{"t":"job.submit","id":"r7","d":{"tool":"generate-image","kind":"image","params":{}}}',
    '{"t":"job.cancel","id":"r8","d":{"job":"j_8KQ2M4XZ"}}', '{"t":"job.clear","id":"r9","d":{"gpu":"gpu0"}}',
    '{"t":"job.dismiss","d":{"job":"j_8KQ2M4XZ"}}',
    '{"t":"gpu.refresh"}', '{"t":"gpu.plan","id":"r13","d":{"model":"qwen_image_edit_plus"}}',
    '{"t":"loras.touch","id":"r17","d":{"ids":["x"]}}',
]


@pytest.mark.parametrize("raw", CATALOGUE)
def test_every_catalogue_example_parses(raw: str) -> None:
    m = M.parse(raw)
    assert set(m) == {"t", "id", "re", "d"} and isinstance(m["d"], dict)


@pytest.mark.parametrize("raw", ["not json", "[]", '{"d":{}}', '{"t":"Hello"}', '{"t":"x","id":"has space"}',
                                 '{"t":"x","id":""}', '{"t":"x","d":[1]}', '{"t":"x","extra":1}',
                                 '{"t":"' + "a" * 65 + '"}', '{"t":"x","re":5}'])
def test_malformed_envelopes_are_refused(raw: str) -> None:
    with pytest.raises(M.ProtocolError):
        M.parse(raw)


def test_messages_encode_compactly() -> None:
    assert M.encode(M.msg("reply", {"a": 1}, re="r1")) == '{"t":"reply","re":"r1","d":{"a":1}}'
    assert M.error("invalid", "Write a prompt", re="r7", field="prompt") == {
        "t": "error", "re": "r7", "d": {"code": "invalid", "text": "Write a prompt", "field": "prompt"}}


async def test_coalescing_keeps_the_latest_in_place() -> None:
    box = Outbox(limit=10)
    box.push({"n": 1}, key="gpu")
    box.push({"x": "other"})
    box.push({"n": 2}, key="gpu")
    assert [await box.next(1) for _ in range(2)] == [{"n": 2}, {"x": "other"}]


async def test_a_state_change_is_a_barrier_for_later_progress() -> None:
    box = Outbox(limit=10)
    box.push({"p": 10}, key="job:1")
    box.push({"state": "done"}, key="job:1", replace=False)
    box.push({"p": 90}, key="job:1")
    box.push({"p": 95}, key="job:1")
    assert [await box.next(1) for _ in range(3)] == [{"p": 10}, {"state": "done"}, {"p": 95}]


async def test_overflow_and_beat_timeout() -> None:
    box = Outbox(limit=2)
    assert box.push({"a": 1}) and box.push({"a": 2})
    assert not box.push({"a": 3})
    assert box.push({"a": 4}, key=None) is False
    await box.next(1)
    await box.next(1)
    assert await box.next(0.05) is None
    waiter = asyncio.create_task(box.next(1))
    await asyncio.sleep(0.01)
    box.push({"late": True})
    assert await waiter == {"late": True}


def test_bucket_allows_a_burst_then_refuses() -> None:
    b = Bucket(rate=0.001, burst=3)
    assert [b.take() for _ in range(4)] == [True, True, True, False]
