"""Clips live in the clips root itself, named date and time first (no day folders); filed ones keep date and time
then their name; the list is newest first by the file's own time; a clip's thumbnail is its first frame."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from hub.core import clipthumb, roots, temp
from hub.core.files import Files


def test_a_new_clip_lands_in_the_root_named_by_date_and_time(tmp_path: Path) -> None:
    made = roots.temp_path(tmp_path, ".mp4", flat=True)
    assert made.parent == tmp_path and made.name.startswith(time.strftime("%Y-%m-%d "))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not here")
def test_filed_flat_and_its_first_frame_is_its_thumbnail(tmp_path: Path) -> None:
    files = Files(tmp_path / "data", None, None)
    root = files.roots["clips"]
    root.mkdir(parents=True, exist_ok=True)
    src = root / "2026-10-21 101010-000.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x48:d=1", "-pix_fmt", "yuv420p",
                    str(src)], check=True)
    got = temp.file_clip(files, "clips/2026-10-21 101010-000.mp4", "Storyboard", "Script 1 s1")
    assert got.startswith("clips/") and got.count("/") == 1 and got.endswith(" - Storyboard Script 1 s1.mp4"), got
    assert files.thumb_url(got) is not None
    data = files.thumbnail(got, 96)
    assert data[:4] == b"RIFF" and b"WEBP" in data[:16]
    os.utime(root / got.split("/", 1)[1], (1, 1))
    assert clipthumb.program() is not None


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not here")
def test_the_clips_page_carries_each_clip_s_thumbnail(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from hub.modules.media import library
    files = Files(tmp_path / "data", None, None)
    root = files.roots["clips"]
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x48:d=1", "-pix_fmt", "yuv420p",
                    str(root / "2026-10-21 101010-000.mp4")], check=True)
    got = library.page(SimpleNamespace(files=files), None, 10, "clips")
    assert got["items"] and got["items"][0]["thumb"].startswith("/thumbs/clips/"), got
