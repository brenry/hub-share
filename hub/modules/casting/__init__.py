"""Casting: a character's sheet from its picture and up to 8 more ("bits"), each with a keep and an ignore
line, and its facts; one orbit on a Ref2VA model (Generate's service "orbit"), six views taken from it at full size,
shown to approve. Nothing is in Characters until Approve: the draft lives in memory (`state`); Approve copies
the sheet, the orbit and the bits into the character's folder beside its picture in Characters with `casting.json`
(`record`).
"""
from __future__ import annotations
