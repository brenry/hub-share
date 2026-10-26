"""The plan before the render: what the engine will make of a clip task, from its own read-only preflight,
before any GPU work. Stdlib only; the engine's modules are imported at the call, inside the engine's Python.

Upstream's `shared/mcp/preflight.py` `preflight(session, prepare_generation, prepare_postprocess, settings, …)` runs
the same preparation as a submission and reports, per task, the sliding windows it plans (`window_report`, :65-102:
each window's frames, seconds, new frames, a hard cut, the pictures it receives, its prompt head), the total it will
really make, and diagnostics (prompt and window counts that differ, an end image no window gets, more windows than
the frame maximum needs, LoRAs not found); it promises "No downloads, model loading, inference, GPU reservation"
(:146). A continued clip's plan "is resolved during generation" (:203-204): no windows then, and this says so. The
Hub's task is already a settings dict, so the identity stands in for the MCP server's own `prepare_generation`.
`READS` names nothing of the categories the contract test walks: this module reads no definition field or setting
of its own; what it reads is the preflight module, cited above.
"""
from __future__ import annotations

import importlib
from typing import Any

PREFLIGHT = "shared.mcp.preflight"              # upstream's module (cited above), imported at the call
READS: dict[str, dict[str, str]] = {c: {} for c in ("wgp", "api", "definition", "settings", "generate_video",
                                                    "suffixes")}
NO_PREFLIGHT = "This engine has no preflight"
LATER = "The window plan of a continued clip is resolved during generation"


def _windows(report: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for w in report.get("windows") or []:
        if not isinstance(w, dict):
            continue
        out.append({"n": int(w.get("window") or len(out) + 1), "frames": int(w.get("generated_frames") or 0),
                    "seconds": float(w.get("generated_seconds") or 0.0), "new_frames": int(w.get("new_frames") or 0),
                    "new_shot": bool(w.get("new_shot")), "pictures": [str(p) for p in w.get("pictures") or []]})
    return out


def reduce(report: dict[str, Any]) -> dict[str, Any]:
    """The engine's preflight report as the Hub shows it: `valid`, `windows`, `total_seconds`, `warnings`, `errors`,
    `notes` (what the engine could not check here)."""
    warnings, errors = [], []
    for d in report.get("diagnostics") or []:
        if not isinstance(d, dict):
            continue
        line = str(d.get("message") or "").strip()
        if not line:
            continue
        (errors if str(d.get("severity")) == "error" else warnings).append(line)
    tasks = [t for t in report.get("tasks") or [] if isinstance(t, dict)]
    first = tasks[0] if tasks else {}
    plan = first.get("window_plan") if isinstance(first.get("window_plan"), dict) else {}
    notes = [str(n) for n in first.get("checks_unavailable") or []]
    if plan.get("note"):
        notes.append(str(plan["note"]))
    out: dict[str, Any] = {"valid": bool(report.get("valid")) and not errors, "windows": _windows(plan),
                           "warnings": warnings, "errors": errors, "notes": notes}
    if plan.get("total_seconds") is not None:
        out["total_seconds"] = float(plan["total_seconds"])
    elif isinstance(first.get("requested_video"), dict) and first["requested_video"].get("duration_seconds"):
        out["total_seconds"] = float(first["requested_video"]["duration_seconds"])
    return out


def plan(session: Any, task: dict[str, Any]) -> dict[str, Any]:
    """The plan of one engine task, through the engine's preflight; an engine that has none, or one that raises,
    answers with one `errors` line and no windows, never an exception."""
    try:
        preflight = importlib.import_module(PREFLIGHT).preflight
    except Exception:  # noqa: BLE001  (an older engine, or a broken module: one line, not a crash)
        return {"valid": False, "windows": [], "warnings": [], "errors": [NO_PREFLIGHT], "notes": []}
    try:
        report = preflight(session, lambda source: source, lambda *a, **k: None, settings=task, detail="summary")
    except Exception as exc:  # noqa: BLE001
        line = (str(exc).strip().splitlines() or [type(exc).__name__])[0][:200]
        return {"valid": False, "windows": [], "warnings": [], "errors": [line], "notes": []}
    out = reduce(report if isinstance(report, dict) else {})
    if not out["windows"] and not out["errors"] and any(f in str(task.get("image_prompt_type") or "") for f in "VL"):
        out["notes"] = [*out["notes"], LATER] if LATER not in out["notes"] else out["notes"]
    return out
