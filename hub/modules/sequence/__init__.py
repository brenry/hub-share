"""Edit Video: a sequence of clips, each cut at its in and out points, played in order and joined into one clip.

A sequence is one small file beside the clips (`Files.sequence*`, core `sequences.py`): clip ids, their order and their
in and out points only. A join is one job on the engine lane that loads no model (`api.NO_MODEL`); the worker runs
ffmpeg and the joined MP4 lands in Clips as the newest clip. Nothing here moves, copies or erases a clip.
"""
from __future__ import annotations
