# -*- coding: utf-8 -*-
"""
PyKuai Retro SFX Audio Engine
Zero-dependency non-blocking sound effects powered by CC0 WAV assets.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "sfx"
_CONFIG_PATH = Path.home() / ".pykuai" / "settings.json"
_SFX_FILES = {
    "snake": "snake.wav",
    "type": "type.wav",
    "key": "key.wav",
    "enter": "enter.wav",
    "click": "click.wav",
    "paste": "paste.wav",
}
_SFX_CACHE: Optional[bool] = None


def _load_persisted_state() -> bool:
    env_override = os.environ.get("PYKUAI_SFX", "").strip().lower()
    if env_override in {"0", "false", "off", "no"}:
        return False
    if env_override in {"1", "true", "on", "yes"}:
        return True

    try:
        if _CONFIG_PATH.exists():
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "sfx_enabled" in data:
                return bool(data["sfx_enabled"])
    except Exception:
        pass
    return True


def _save_persisted_state(enabled: bool) -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {}
        if _CONFIG_PATH.exists():
            try:
                loaded = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload = loaded
            except Exception:
                pass
        payload["sfx_enabled"] = bool(enabled)
        _CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def is_sfx_enabled() -> bool:
    """Return whether retro UI & snake sound effects are currently enabled."""
    global _SFX_CACHE
    if _SFX_CACHE is None:
        _SFX_CACHE = _load_persisted_state()
    return _SFX_CACHE


def set_sfx_enabled(enabled: bool) -> bool:
    """Persist and apply retro SFX state."""
    global _SFX_CACHE
    _SFX_CACHE = bool(enabled)
    _save_persisted_state(_SFX_CACHE)
    if not _SFX_CACHE:
        stop_sfx()
    return _SFX_CACHE


def toggle_sfx() -> bool:
    """Flip SFX state; chime when enabled or silence immediately when muted."""
    new_state = set_sfx_enabled(not is_sfx_enabled())
    if new_state:
        play_sfx("click")
    return new_state


def stop_sfx() -> None:
    """Immediately stop any active asynchronous Windows audio playback."""
    if sys.platform != "win32":
        return
    try:
        import winsound

        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


def play_sfx(name: str) -> None:
    """Play a named retro sound effect ('snake', 'type', 'key', 'enter', 'click', or 'paste') cleanly."""
    if not is_sfx_enabled():
        return

    filename = _SFX_FILES.get(name)
    if not filename:
        return

    wav_path = _ASSETS_DIR / filename
    if not wav_path.is_file():
        return

    if sys.platform == "win32":
        try:
            import winsound

            winsound.PlaySound(
                str(wav_path),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
        except Exception:
            pass
        return

    for player in ("afplay", "paplay", "aplay"):
        exe = shutil.which(player)
        if exe:
            try:
                subprocess.Popen(
                    [exe, str(wav_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
            return
