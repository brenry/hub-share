"""Fake `shared.utils.files_locator`: the real one's lookups over the config's checkpoint folders (`fake_locator`)."""
from __future__ import annotations

from shared.fake_locator import get_checkpoints_paths, get_smart_download_root, locate_file, locate_folder

__all__ = ["get_checkpoints_paths", "get_smart_download_root", "locate_file", "locate_folder"]
