"""A setting an older hub wrote is dropped when read, never refused."""
from __future__ import annotations

from hub import settings


def test_ram_reserve_from_an_older_hub_is_dropped() -> None:
    raw = {"vram": {"idle_unload": True, "idle_minutes": 10, "ram_reserve_mb": 4096}}
    merged = settings._merge(raw, settings.DEFAULTS, "")
    assert settings._merge(merged["vram"], settings.DEFAULTS["vram"], "vram.") == {
        "idle_unload": True, "idle_minutes": 10, "clip_previews": False}


def test_the_vram_hold_keys_from_an_older_hub_are_dropped() -> None:
    raw = {"vram": {"idle_unload": False, "idle_minutes": 20, "margin_mb": 1024},
           "known_programs": {"ollama": "Ollama", "Xorg": "Desktop"}}
    s = settings.validate(raw)
    assert "known_programs" not in s and s["vram"] == {"idle_unload": False, "idle_minutes": 20, "clip_previews": False}
