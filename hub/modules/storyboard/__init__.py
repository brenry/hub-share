"""Clip Cells: a numbered list of cells in a Drive folder, each cell one picture and the text of one clip.

A storyboard is the folder `<storyboards folder>/<name>/` (`paths.storyboards`, a folder inside the Drive); its
pictures in name order are its cells (`01.png`, `02.png`...), a cell's number is its place. A cell's text lives in
the picture's one text field (`Files.picture_text`): header lines `seconds: N`, `camera: <words>`, `cast: <names>`,
a blank line, then the clip text, exactly as it is rendered. Nothing else is kept on disk: the record is the files.
Declarations only (`manifest.py`); the core publishes them as tools. No tab and no routes yet.
"""
from __future__ import annotations
