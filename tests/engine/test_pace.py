"""The voice's pace measured from every finished line. `speech_span` on made WAVs; one reading and the
running average; a wrong read not kept; the request carries the pace once one is measured; `planned` at a pace."""
from __future__ import annotations

import math
import struct
from pathlib import Path

from hub.core import sound
from hub.modules.generate_image import build, chain, pace, screen
from hub.worker.adapters import turns
from tests.engine.test_generate_speech import ctx, press, request_of  # noqa: F401
from tests.engine.test_upstream_rules import SPEECH, cat  # noqa: F401

RATE = 32_000


def wav(parts: list[tuple[float, float]], bits: int = 16, channels: int = 2) -> bytes:
    """Stereo 16-bit WAV of (seconds, amplitude) parts: 0.0 is digital silence, else a 220 Hz tone offset from zero."""
    frames: list[float] = []
    for seconds, amp in parts:
        n = int(seconds * RATE)
        frames += [amp * (0.6 + 0.4 * math.sin(2 * math.pi * 220 * i / RATE)) for i in range(n)]
    flat = [v for v in frames for _ in range(channels)]
    data = struct.pack(f"<{len(flat)}h", *(int(v * 32767) for v in flat))
    fmt = struct.pack("<HHIIHH", 1, channels, RATE, RATE * channels * 2, channels * 2, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_speech_span_is_first_sound_to_last(tmp_path: Path):
    p = tmp_path / "a.wav"
    p.write_bytes(wav([(0.5, 0.0), (2.0, 0.5), (0.3, 0.0), (1.0, 0.5), (0.4, 0.0)]))
    assert abs(sound.speech_span(p) - 3.3) < 0.02, "silence inside the speech counts, the ends do not"
    p.write_bytes(wav([(1.0, 0.0)]))
    assert sound.speech_span(p) is None
    p.write_bytes(wav([(0.2, 0.0), (1.0, 0.005), (0.2, 0.0)]))
    assert sound.speech_span(p) is None, "under the engine's quiet line is not sound"


def test_a_reading_is_words_per_heard_second_and_a_wrong_read_is_dropped(tmp_path: Path):
    p = tmp_path / "a.wav"
    p.write_bytes(wav([(0.5, 0.0), (10.0, 0.5), (0.5, 0.0)]))
    assert abs(pace.reading(p, 30) - 3.0) < 0.01
    assert pace.reading(p, 0) is None and pace.reading(p, 100) is None, "0 words, or 10 w/s: not kept"
    p.write_bytes(wav([(0.5, 0.5)]))
    assert pace.reading(p, 2) is None, "a span under a second is not a read"
    (tmp_path / "bad.wav").write_bytes(b"not a wav")
    assert pace.reading(tmp_path / "bad.wav", 5) is None


def test_the_running_average_learns_each_line_and_caps_its_memory(ctx, tmp_path: Path):  # noqa: F811
    assert pace.read(ctx) == {"pace": 2.6, "runs": 0} and pace.current(ctx) is None
    p = tmp_path / "line.wav"
    p.write_bytes(wav([(10.0, 0.5)]))
    words = " ".join(["word"] * 30)                           # 30 words in 10 s: 3.0
    assert pace.learn(ctx, p, words) == 3.0
    assert pace.read(ctx) == {"pace": 3.0, "runs": 1} and pace.current(ctx) == 3.0
    assert pace.learn(ctx, p, " ".join(["word"] * 20)) == 2.0
    assert pace.read(ctx) == {"pace": 2.5, "runs": 2}
    for _ in range(40):
        pace.learn(ctx, p, " ".join(["word"] * 40))            # 4.0 again and again
    assert pace.read(ctx)["runs"] == 42 and abs(pace.read(ctx)["pace"] - 4.0) < 0.05, "the memory is 20 runs deep"
    pace.reset(ctx)
    assert pace.read(ctx) == {"pace": 2.6, "runs": 0}


def test_a_finished_line_is_measured_and_the_next_request_carries_the_pace(ctx, tmp_path: Path):  # noqa: F811
    import asyncio
    job = ctx.jobs.submit("image", press(prompt=" ".join(["word"] * 30)))
    out = ctx.files.roots["sounds"] / "2026-10-17" / "120000-000.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(wav([(10.0, 0.5)]))
    item = "sounds/2026-10-17/120000-000.wav"
    done = {"state": "done", "tool": "generate-image", "job": job.id, "outputs": [item]}
    asyncio.run(chain.on_job_finished(ctx, done))
    assert pace.read(ctx) == {"pace": 3.0, "runs": 1}
    assert request_of(build.image_job(press(), ctx)).pace == 3.0
    model = next(m for m in ctx.engine.catalog["models"] if m["id"] == SPEECH)
    view = screen.view(ctx, ctx.engine.catalog, model)
    assert (view["speech_pace"], view["speech_pace_runs"]) == (3.0, 1)
    asyncio.run(chain.on_job_finished(ctx, {"state": "failed", "tool": "generate-image", "job": job.id, "outputs": []}))
    assert pace.read(ctx)["runs"] == 1, "a failed job teaches nothing"


def test_planned_at_a_faster_pace_groups_more_words_per_turn():
    text = "One two three four five six seven. Eight nine ten eleven twelve thirteen. Fourteen fifteen sixteen."
    assert turns.planned(text, 3.9) < turns.planned(text) == turns.planned(text, None)
    assert len(turns.blocks(text, 5.0, 3.9)[1]) <= len(turns.blocks(text, 5.0)[1])
