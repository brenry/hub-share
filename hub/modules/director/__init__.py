"""The Director: the Storyboard tab and its routes, one JSON file per script in `<data>/scripts`, the Hub's
own root beside Sounds, drawn as a timeline of scenes, shots and their events (lines, cues, poses), each timed in
milliseconds from the script's start (`scriptshape.py`); the script tools on the MCP server, which write every script,
and the lane the tab follows; each line timed from its words; the keyframes of each shot; the sketch panels and
the loop that draws them.
A rename and a delete are the tab's.
"""
from __future__ import annotations
