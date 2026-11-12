# -*- coding: utf-8 -*-
"""
PyKuai Arcade Arena — Mini-Game Registry & Plug-In Contract (`aa`).
Drop any module in `pykuai/arcade/` defining an `ArcadeGame` subclass to register it automatically.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import importlib.util
import inspect
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from rich.console import Console

_CONFIG_PATH = Path.home() / ".pykuai" / "settings.json"
_GAME_CODE_RE = re.compile(r"^[a-z]{3}$")
_GAMES_CACHE: dict[str, ArcadeGame] = {}


class ArcadeGame(ABC):
    """Base plugin contract for console mini-games inside `aa` (Arcade Arena)."""

    code: str = ""
    title: str = ""
    tagline: str = ""
    order: int = 100
    help_text: str = ""

    @abstractmethod
    def run(self, console: Console) -> int:
        """Run the game session interactively and return exit code (0 on clean exit)."""
        pass


def load_all_games(force_reload: bool = False) -> dict[str, ArcadeGame]:
    """Scan `pykuai/arcade/` for `ArcadeGame` subclasses and return them ordered."""
    global _GAMES_CACHE
    if _GAMES_CACHE and not force_reload:
        return _GAMES_CACHE

    discovered: list[ArcadeGame] = []
    arcade_dir = Path(__file__).resolve().parent
    seen_codes: set[str] = set()

    for file_path in sorted(arcade_dir.glob("*.py")):
        if file_path.name.startswith("__") or file_path.stem == "launcher":
            continue

        module_name = f"pykuai.arcade.{file_path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not (spec and spec.loader):
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    inspect.isclass(attr)
                    and issubclass(attr, ArcadeGame)
                    and attr is not ArcadeGame
                    and getattr(attr, "code", "")
                ):
                    inst = attr()
                    code = inst.code.strip().lower()
                    if not _GAME_CODE_RE.match(code) or code in seen_codes:
                        continue
                    inst.code = code
                    seen_codes.add(code)
                    discovered.append(inst)
        except Exception:
            # Isolate broken game drafts so Arcade Arena stays bootable.
            continue

    discovered.sort(key=lambda g: (getattr(g, "order", 100), g.code))
    _GAMES_CACHE = {g.code: g for g in discovered}
    return _GAMES_CACHE


def get_game(identifier: str) -> ArcadeGame | None:
    """Look up a registered arcade game by short code (case-insensitive)."""
    games = load_all_games()
    return games.get(identifier.strip().lower())


def _read_settings_payload() -> dict[str, object]:
    try:
        if _CONFIG_PATH.exists():
            loaded = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
    except Exception:
        pass
    return {}


def get_high_score(game_code: str) -> int:
    """Read saved personal best score for a game from `~/.pykuai/settings.json`."""
    payload = _read_settings_payload()
    scores = payload.get("arcade_scores")
    if isinstance(scores, dict):
        val = scores.get(game_code)
        if isinstance(val, int) and val >= 0:
            return val
    return 0


def record_high_score(game_code: str, score: int) -> tuple[int, bool]:
    """Persist score if it beats the current record; returns `(best_score, is_new_record)`."""
    best = get_high_score(game_code)
    if score <= best:
        return best, False

    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = _read_settings_payload()
        scores_raw = payload.get("arcade_scores")
        scores: dict[str, int] = dict(scores_raw) if isinstance(scores_raw, dict) else {}
        scores[game_code] = int(score)
        payload["arcade_scores"] = scores
        serialized = json.dumps(payload, indent=2)

        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=str(_CONFIG_PATH.parent),
            prefix=".settings_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(serialized)
                fh.flush()
            os.replace(tmp_name, _CONFIG_PATH)
        except Exception:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except Exception:
                pass
            raise
    except Exception:
        pass
    return int(score), True
