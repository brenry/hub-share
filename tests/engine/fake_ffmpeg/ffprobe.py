"""A fake ffprobe: `-show_streams ... -of json PATH` prints the streams of a `tiny_mp4` (h264 video with an
`extradata_hash`, aac sound when the file has a sound track)."""
from __future__ import annotations

import json
import os
import sys

import fakelib


def main() -> int:
    folder, args, config = fakelib.start()
    fakelib.record(folder, "ffprobe", args)
    path = args[-1]
    try:
        f = fakelib.facts(path)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"{path}: {exc}\n")
        return 1
    name = os.path.basename(path)
    video = {"index": 0, "codec_name": "h264", "profile": "High", "codec_type": "video", "width": f["w"],
             "height": f["h"], "pix_fmt": "yuv420p", "r_frame_rate": f"{round(f['fps'])}/1"}
    no_hash = config.get("no_hash") or []
    if not (no_hash is True or name in no_hash):
        video["extradata_hash"] = (config.get("hash") or {}).get(name, "CRC32:6d1b2c3a")
    streams = [video]
    if f["audio"]:
        streams.append({"index": 1, "codec_name": "aac", "profile": "LC", "codec_type": "audio",
                        "sample_rate": "48000", "channels": 2, "extradata_hash": "CRC32:0a1b2c3d"})
    sys.stdout.write(json.dumps({"streams": streams}, indent=4) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
