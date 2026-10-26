"""Save's command lines (`hub/worker/joincmd.py`): track 2's sounds delayed and mixed under track 1 (with
`normalize=0`, or `volume=<inputs>` where ffmpeg's `amix` lacks it), never copied; a WAV of track 1's sounds, or of
silence as long as track 2 when track 1 is empty; 16-bit PCM, 48 kHz, stereo."""
from __future__ import annotations

from hub.worker import joincmd
from tests.engine.test_joincmd import HEAD, SCALE, TAIL, build, facts, item, request

FMT = "asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo"
WAV_TAIL = ["-map", "[a]", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", "-map_metadata", "-1",
            "/s/outbox/join-j1.wav"]


def sound(path: str, lo: int, hi: int, frames: int = 20_000) -> dict:
    """A track-1 sound: milliseconds as frames."""
    return {"path": path, "in": lo, "out": hi, "fps": 1000.0, "w": 0, "h": 0, "frames": frames, "audio": True,
            "sound": True}


def placed(path: str, at_ms: int, lo: int, hi: int, fps: float = 1000.0) -> dict:
    return {"path": path, "at_ms": at_ms, "in": lo, "out": hi, "fps": fps}


def wav(*items: dict, audio: list | None = None) -> dict:
    return {"items": list(items), "canvas": {"w": 0, "h": 0, "fps": 1000.0}, "audio": audio or [], "crf": 18,
            "preset": "medium", "out_kind": "wav"}


def test_a_sound_on_track_2_is_delayed_and_mixed_under_two_whole_clips_never_copied():
    req = request(item("/c/a.mp4", audio=False), item("/c/b.mp4"), audio=[placed("/s/fx.wav", 3000, 500, 2000)])
    cmd = joincmd.build(req, [facts(sound=None), facts()], "ffmpeg", "/s", "j1", True)
    assert cmd.path == "encode" and cmd.expect == 248 and cmd.n == 2
    graph = ";".join([
        f"[0:v]trim=start_frame=0:end_frame=124,setpts=PTS-STARTPTS,{SCALE},fps=24.000000,format=yuv420p[v0]",
        "anullsrc=r=48000:cl=stereo,atrim=duration=5.166667[a0]",
        f"[1:v]trim=start_frame=0:end_frame=124,setpts=PTS-STARTPTS,{SCALE},fps=24.000000,format=yuv420p[v1]",
        f"[1:a]atrim=start=0.000000:end=5.166667,{FMT}[a1]",
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][base]",
        f"[2:a]atrim=start=0.500000:end=2.000000,{FMT},adelay=3000|3000[s0]",
        "[base][s0]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"])
    assert cmd.argv == [*HEAD, "-i", "/c/a.mp4", "-i", "/c/b.mp4", "-i", "/s/fx.wav", "-filter_complex", graph,
                        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", *TAIL]


def test_without_normalize_the_mix_is_raised_to_equal_levels():
    req = request(item("/c/a.mp4"), audio=[placed("/s/fx.wav", 0, 0, 900), placed("/c/b.mp4", 1000, 0, 24, 24.0)])
    cmd = joincmd.build(req, [facts()], "ffmpeg", "/s", "j1", False)
    graph = cmd.argv[cmd.argv.index("-filter_complex") + 1].split(";")
    assert graph[-3] == f"[1:a]atrim=start=0.000000:end=0.900000,{FMT},adelay=0|0[s0]"
    assert graph[-2] == f"[2:a]atrim=start=0.000000:end=1.000000,{FMT},adelay=1000|1000[s1]", "a clip: its sound"
    assert graph[-1] == "[base][s0][s1]amix=inputs=3:duration=first:dropout_transition=0,volume=3[a]"


def test_a_wav_of_track_1_sounds_trimmed_and_joined():
    cmd = build(wav(sound("/s/a.wav", 1000, 16000), sound("/s/b.wav", 0, 2500)), [])
    graph = ";".join([f"[0:a]atrim=start=1.000000:end=16.000000,{FMT}[a0]",
                      f"[1:a]atrim=start=0.000000:end=2.500000,{FMT}[a1]",
                      "[a0][a1]concat=n=2:v=0:a=1[a]"])
    assert cmd.argv == [*HEAD, "-i", "/s/a.wav", "-i", "/s/b.wav", "-filter_complex", graph, *WAV_TAIL]
    assert (cmd.kind, cmd.seconds, cmd.fps, cmd.expect, cmd.out) == ("wav", 17.5, 100.0, 1750, "/s/outbox/join-j1.wav")


def test_one_sound_trimmed_to_15_seconds():
    cmd = build(wav(sound("/s/long.wav", 4000, 19000, 600_000)), [])
    assert cmd.argv[cmd.argv.index("-filter_complex") + 1] == (
        f"[0:a]atrim=start=4.000000:end=19.000000,{FMT}[a0];[a0]concat=n=1:v=0:a=1[a]")
    assert cmd.seconds == 15.0


def test_with_track_1_empty_the_wav_is_silence_as_long_as_track_2_with_its_sounds_mixed_in():
    cmd = build(wav(audio=[placed("/s/fx.wav", 3000, 0, 1500), placed("/s/fx.wav", 0, 0, 500)]), [])
    graph = ";".join(["anullsrc=r=48000:cl=stereo,atrim=duration=4.500000[base]",
                      f"[0:a]atrim=start=0.000000:end=1.500000,{FMT},adelay=3000|3000[s0]",
                      f"[1:a]atrim=start=0.000000:end=0.500000,{FMT},adelay=0|0[s1]",
                      "[base][s0][s1]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[a]"])
    assert cmd.argv == [*HEAD, "-i", "/s/fx.wav", "-i", "/s/fx.wav", "-filter_complex", graph, *WAV_TAIL]
    assert (cmd.seconds, cmd.n) == (4.5, 2)


def test_a_wav_of_track_1_with_a_sound_on_track_2():
    cmd = build(wav(sound("/s/a.wav", 0, 3000), audio=[placed("/s/fx.wav", 1000, 0, 500)]), [])
    graph = cmd.argv[cmd.argv.index("-filter_complex") + 1].split(";")
    assert graph[1] == "[a0]concat=n=1:v=0:a=1[base]"
    assert graph[-1] == "[base][s0]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"


# ---------------------------------------------------------------- level, fades, ducking
DUCK = "sidechaincompress=threshold=0.050000:ratio=6.000000:attack=50.000000:release=400.000000"


def test_a_beds_level_and_fades_come_before_its_delay_and_nothing_set_is_todays_chain():
    bed = {**placed("/s/bed.wav", 1000, 0, 4000), "level": 0.5, "fade_in": 1000, "fade_out": 500}
    assert joincmd.shape(bed) == ",volume=0.500000,afade=t=in:st=0:d=1.000000,afade=t=out:st=3.500000:d=0.500000"
    assert joincmd.shape(placed("/s/bed.wav", 0, 0, 4000)) == ""
    assert joincmd.shape({**placed("/s/bed.wav", 0, 0, 4000), "level": 1.0, "fade_in": 0, "duck": False}) == ""
    long = joincmd.shape({**placed("/s/bed.wav", 0, 0, 400), "fade_in": 1000, "fade_out": 1000})
    assert long == ",afade=t=in:st=0:d=0.400000,afade=t=out:st=0.000000:d=0.400000", "a fade is at most the item"
    cmd = build(wav(sound("/s/a.wav", 0, 3000), audio=[bed]), [])
    graph = cmd.argv[cmd.argv.index("-filter_complex") + 1].split(";")
    assert graph[-2] == f"[1:a]atrim=start=0.000000:end=4.000000,{FMT}{joincmd.shape(bed)},adelay=1000|1000[s0]"
    assert graph[-1] == "[base][s0]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"


def test_a_ducked_bed_is_pressed_by_track_1_padded_to_the_files_length():
    bed = {**placed("/s/bed.wav", 1000, 0, 4000), "duck": True}
    req = {**wav(sound("/s/a.wav", 0, 3000), audio=[bed, placed("/s/fx.wav", 0, 0, 500)]),
           "duck": {"threshold": 0.05, "ratio": 6.0, "attack": 50.0, "release": 400.0}}
    cmd = build(req, [])
    graph = cmd.argv[cmd.argv.index("-filter_complex") + 1].split(";")
    assert graph[2:] == [
        "[base]asplit=2[base0][sc0]",
        f"[1:a]atrim=start=0.000000:end=4.000000,{FMT},adelay=1000|1000,apad=whole_dur=3.000000,atrim=end=3.000000[s0]",
        f"[s0][sc0]{DUCK}[d0]",
        f"[2:a]atrim=start=0.000000:end=0.500000,{FMT},adelay=0|0[s1]",
        "[base0][d0][s1]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[a]"]
    two = build({**req, "audio": [bed, {**bed, "at_ms": 0}], "duck": {"ratio": 4}}, [])
    graph = two.argv[two.argv.index("-filter_complex") + 1].split(";")
    assert graph[2] == "[base]asplit=3[base0][sc0][sc1]" and graph[-1].startswith("[base0][d0][d1]amix=inputs=3")
    assert graph[4].endswith(":ratio=4.000000:attack=50.000000:release=400.000000[d0]"), "the request's numbers"
    clip_req = request(item("/c/a.mp4"), audio=[bed])
    graph = joincmd.build(clip_req, [facts()], "ffmpeg", "/s", "j1", True).argv
    text = graph[graph.index("-filter_complex") + 1]
    assert "apad=whole_dur=5.166667,atrim=end=5.166667[s0]" in text, "an MP4's length is track 1's clips'"
