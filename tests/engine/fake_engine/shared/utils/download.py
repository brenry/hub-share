"""Fake `shared.utils.download`: upstream's presence call for a handler's bundles (no fetch), and its one Hugging Face
download, which here only leaves a "network" marker in the root and fails (the worker must never reach it)."""
from __future__ import annotations

import os

from shared.utils import files_locator as fl


def download_def_missing_files(download_def):
    """Like upstream's (shared/utils/download.py:199): each bundle's file (or empty folder list's folder) found
    nowhere, as a path under a checkpoint folder."""
    if download_def is None:
        return []
    if isinstance(download_def, list):
        return [m for one in download_def for m in download_def_missing_files(one)]
    missing = []
    for folder, files in zip(download_def.get("sourceFolderList", []), download_def.get("fileList", []), strict=False):
        if not files and fl.locate_folder(folder, error_if_none=False) is None:
            missing.append(folder)
        missing += [p for p in (os.path.join(folder, f) if folder else f for f in files)
                    if fl.locate_file(p, error_if_none=False) is None]
    return missing


def _hf_download(*, gen=None, show_filename=True, file_index=1, file_count=1, **kwargs):
    with open("network", "a", encoding="utf-8") as f:
        f.write(f"{kwargs.get('filename')}\n")
    raise RuntimeError("network")
