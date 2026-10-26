"""Sketch panels kept current (blueprint A.6: "a panel whose shot's context, camera or poses change is
marked stale and redrawn after the current one"), pure. A panel's shot's context, camera or poses have changed exactly
when the prompt `sketch.prompt` compiles for it differs (a whole prompt or its waiting reason, compared as text): the
prompt is what the sketch was drawn from. `before` compiles each panel `panels.take` took out, on the script before a
tool's change; `mark` compiles each one `panels.put` put back, at its new time, and marks stale each drawn one whose
prompt differs (`landing.write`). `drawn` writes a finished sketch, stale when the panel's prompt is no longer the one
its job was submitted with. `due`: drawn next when not drawn or stale. The prompts are kept in memory only.
"""
from __future__ import annotations

from typing import Any

from . import panels, sketch


def _prompt(script: dict, scene: dict, shot: dict, at_ms: int) -> str:
    text, why = sketch.prompt(script, scene, shot, at_ms)
    return text if text is not None else f"waiting: {why}"


def before(script: dict, taken: list[tuple[dict, dict]]) -> dict[str, str]:
    """{panel id -> its prompt at its old time on its cause's scene and shot}, on the script as it was."""
    return {panel["id"]: _prompt(script, cause["scene"], cause["shot"], panel["at_ms"]) for panel, cause in taken}


def mark(script: dict, old: dict[str, str]) -> list[str]:
    """`stale: true` on each put-back panel with a picture, not stale, whose prompt now differs. -> their ids."""
    out = []
    for n, shot, panel in panels.panels(script):
        if panel["id"] not in old or panel["picture"] is None or panel.get("stale"):
            continue
        if _prompt(script, script["scenes"][n - 1], shot, panel["at_ms"]) != old[panel["id"]]:
            panel["stale"] = True
            out.append(panel["id"])
    return out


def drawn(script: dict, ident: str, picture: str, prompt: str | None) -> dict[str, Any]:
    """The panel's `picture` written, `stale` whether its prompt now differs from the one submitted (`prompt`;
    none known: false); an answer for `scripts.change`."""
    found = panels.find(script, ident)
    if found is not None:
        n, shot, panel = found
        panel["picture"] = picture
        panel["stale"] = prompt is not None and _prompt(script, script["scenes"][n - 1], shot,
                                                        panel["at_ms"]) != prompt
    return {"written": found is not None}


def to_draw(panel: dict) -> bool:
    """A panel the drawing takes (with the failed and whole-prompt rules of `drawing.next_panel`)."""
    return panel["picture"] is None or bool(panel.get("stale"))
