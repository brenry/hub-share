"""The join's command lines (`hub/worker/joincmd.py`), argument by argument: the copy path for whole clips of one
stream, the encode path for everything else (Stage 11 §5.2)."""
from __future__ import annotations

import copy

import pytest

from hub.worker import joincmd

STATE = "/s"
HEAD = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-progress", "pipe:1"]
TAIL = ["-map_metadata", "-1", "-movflags", "+faststart", "/s/outbox/join-j1.mp4"]
VIDEO = {"codec": "h264", "profile": "High", "w": 960, "h": 544, "pix_fmt": "yuv420p", "fps": "24/1",
         "extradata_hash": "CRC32:6d1b2c3a"}
SOUND = {"codec": "aac", "rate": "48000", "channels": 2}
SCALE = "scale=960:544:force_original_aspect_ratio=decrease,pad=960:544:(ow-iw)/2:(oh-ih)/2,setsar=1"


def item(path: str, frames: int = 124, lo: int = 0, hi: int | None = None, *, w: int = 960, h: int = 544,
         fps: float = 24.0, audio: bool = True) -> dict:
    return {"path": path, "in": lo, "out": frames if hi is None else hi, "fps": fps, "w": w, "h": h,
            "frames": frames, "audio": audio}


def request(*items: dict, **extra) -> dict:
    first = items[0]
    return {"items": list(items), "canvas": {"w": first["w"], "h": first["h"], "fps": first["fps"]}, "audio": [],
            "crf": 18, "preset": "medium", **extra}


def facts(video: dict | None = VIDEO, sound: dict | None = SOUND, **change) -> dict:
    return {"v": None if video is None else {**video, **change}, "a": sound}


def build(req: dict, probed: list[dict]) -> joincmd.Command:
    return joincmd.build(req, probed, "ffmpeg", STATE, "j1")


def test_two_whole_clips_of_one_stream_are_copied_through_a_quoted_list():
    req = request(item("/c/a.mp4"), item("/c/it's.mp4", 141))
    cmd = build(req, [facts(), facts()])
    assert cmd.path == "copy" and cmd.expect == 124 + 141 and cmd.n == 2 and cmd.fps == 24.0
    assert cmd.argv == [*HEAD, "-f", "concat", "-safe", "0", "-i", "/s/join-j1.txt", "-map", "0", "-c", "copy",
                        *TAIL]
    assert cmd.list_file == "/s/join-j1.txt"
    assert cmd.listing == "file '/c/a.mp4'\nfile '/c/it'\\''s.mp4'\n"


def test_whole_clips_without_sound_anywhere_are_copied():
    req = request(item("/c/a.mp4", audio=False), item("/c/b.mp4", audio=False))
    assert build(req, [facts(sound=None), facts(sound=None)]).path == "copy"


def encode_argv(inputs: list[str], graph: str, sound: bool) -> list[str]:
    return [*HEAD, *[x for p in inputs for x in ("-i", p)], "-filter_complex", graph, "-map", "[v]",
            *(["-map", "[a]"] if sound else []), "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-pix_fmt", "yuv420p", *(["-c:a", "aac", "-b:a", "192k", "-ar", "48000"] if sound else []), *TAIL]


def test_a_trim_takes_the_encode_path_with_its_exact_graph():
    req = request(item("/c/a.mp4", 124, 12, 112), item("/c/b.mp4"))
    cmd = build(req, [facts(), facts()])
    graph = ";".join([
        f"[0:v]trim=start_frame=12:end_frame=112,setpts=PTS-STARTPTS,{SCALE},fps=24.000000,format=yuv420p[v0]",
        "[0:a]atrim=start=0.500000:end=4.666667,asetpts=PTS-STARTPTS,aresample=48000,"
        "aformat=channel_layouts=stereo[a0]",
        f"[1:v]trim=start_frame=0:end_frame=124,setpts=PTS-STARTPTS,{SCALE},fps=24.000000,format=yuv420p[v1]",
        "[1:a]atrim=start=0.000000:end=5.166667,asetpts=PTS-STARTPTS,aresample=48000,"
        "aformat=channel_layouts=stereo[a1]",
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"])
    assert cmd.path == "encode" and cmd.listing is None and cmd.expect == 100 + 124
    assert cmd.argv == encode_argv(["/c/a.mp4", "/c/b.mp4"], graph, True)


def test_two_sizes_are_letterboxed_to_the_first_and_silence_fills_an_input_without_sound():
    req = request(item("/c/wide.mp4"), item("/c/tall.mp4", 97, w=544, h=960, fps=16.0, audio=False))
    req["crf"], req["preset"] = 23, "slow"
    cmd = build(req, [facts(), facts(w=544, h=960, fps="16/1", sound=None)])
    graph = cmd.argv[cmd.argv.index("-filter_complex") + 1].split(";")
    assert graph[2] == (f"[1:v]trim=start_frame=0:end_frame=97,setpts=PTS-STARTPTS,{SCALE},fps=24.000000,"
                        "format=yuv420p[v1]")
    assert graph[3] == "anullsrc=r=48000:cl=stereo,atrim=duration=6.062500[a1]"
    assert graph[4] == "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    assert cmd.argv[cmd.argv.index("-crf"):cmd.argv.index("-crf") + 4] == ["-crf", "23", "-preset", "slow"]
    assert cmd.expect == 124 + round(97 * 24 / 16)


def test_no_input_with_sound_gives_a_silent_concat_and_no_audio_codec():
    req = request(item("/c/a.mp4", 124, 0, 100, audio=False), item("/c/b.mp4", audio=False))
    cmd = build(req, [facts(sound=None), facts(sound=None)])
    graph = ";".join([
        f"[0:v]trim=start_frame=0:end_frame=100,setpts=PTS-STARTPTS,{SCALE},fps=24.000000,format=yuv420p[v0]",
        f"[1:v]trim=start_frame=0:end_frame=124,setpts=PTS-STARTPTS,{SCALE},fps=24.000000,format=yuv420p[v1]",
        "[v0][v1]concat=n=2:v=1:a=0[v]"])
    assert cmd.argv == encode_argv(["/c/a.mp4", "/c/b.mp4"], graph, False)
    assert "-c:a" not in cmd.argv and "[a]" not in cmd.argv


@pytest.mark.parametrize("second", [
    facts(extradata_hash="CRC32:00000000"),       # another encoder's parameter sets
    facts(extradata_hash=None),                   # an ffprobe that prints no hash
    facts(profile="Main"), facts(w=544), facts(pix_fmt="yuv420p10le"), facts(fps="16/1"),
    facts(sound={**SOUND, "rate": "44100"}), facts(sound=None),
    facts(video=None),                            # a probe that failed
])
def test_any_stream_difference_or_a_missing_hash_takes_the_encode_path(second):
    req = request(item("/c/a.mp4"), item("/c/b.mp4"))
    assert build(req, [facts(), second]).path == "encode"


def test_no_hash_anywhere_never_copies():
    req = request(item("/c/a.mp4"), item("/c/b.mp4"))
    assert build(req, [facts(extradata_hash=None), facts(extradata_hash=None)]).path == "encode"


def test_an_empty_track_2_gives_the_same_argv_as_none():
    for items in ([item("/c/a.mp4"), item("/c/b.mp4")], [item("/c/a.mp4", 124, 3, 50), item("/c/b.mp4")]):
        with_track = request(*items)
        without = copy.deepcopy(with_track)
        del without["audio"]
        assert build(with_track, [facts(), facts()]) == build(without, [facts(), facts()])
        assert build({**with_track, "out_kind": "mp4"}, [facts(), facts()]) == build(without, [facts(), facts()])


def test_the_probe_command_and_its_facts():
    assert joincmd.probe_argv("ffprobe", "/c/a.mp4") == ["ffprobe", "-v", "error", "-show_streams",
                                                          "-show_data_hash", "CRC32", "-of", "json", "/c/a.mp4"]
    probed = {"streams": [
        {"codec_type": "video", "codec_name": "h264", "profile": "High", "width": 960, "height": 544,
         "pix_fmt": "yuv420p", "r_frame_rate": "24/1", "extradata_hash": "CRC32:6d1b2c3a", "index": 0},
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2, "profile": "LC"}]}
    assert joincmd.facts(probed) == facts()
    assert joincmd.facts(None) == {"v": None, "a": None}
    assert joincmd.facts({"streams": [probed["streams"][0]]}) == facts(sound=None)
