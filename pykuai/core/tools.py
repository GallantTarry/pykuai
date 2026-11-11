# -*- coding: utf-8 -*-
"""
PyKuai Binary Tools Locator (FFmpeg, FFprobe, UnRAR, yt-dlp)
"""
from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_BINARY_VERSION_CACHE: dict[str, str] = {}


def get_tool_path(tool_name: str) -> str | None:
    """
    Locate bundled or system binary tools in priority order:
    1. Package-local tools/ directory
    2. System PATH environment variable
    3. User home ~/.pykuai/tools/
    4. Development fallback path
    """
    ext = ".exe" if os.name == "nt" else ""
    target_names = [f"{tool_name}{ext}", f"{tool_name.lower()}{ext}", f"{tool_name.upper()}{ext}"]

    # 1. Package built-in tools directory
    current_dir = Path(__file__).resolve().parent
    local_tools_dir = current_dir.parent / "tools"
    for name in target_names:
        p = local_tools_dir / name
        if p.exists() and p.is_file():
            return str(p)

    # 2. System PATH lookup
    system_path = shutil.which(tool_name)
    if system_path:
        return system_path

    # 3. User directory ~/.pykuai/tools
    user_tools_dir = Path.home() / ".pykuai" / "tools"
    for name in target_names:
        p = user_tools_dir / name
        if p.exists() and p.is_file():
            return str(p)

    # 4. Development fallback directory
    fallback_dir = Path.home() / "Documents" / "GitHub" / "pyside6-pykuai-app" / "PyKuai" / "tools"
    for name in target_names:
        p = fallback_dir / name
        if p.exists() and p.is_file():
            return str(p)

    return None


def get_ffmpeg() -> str | None:
    return get_tool_path("ffmpeg")


def get_ffprobe() -> str | None:
    return get_tool_path("ffprobe")


def get_unrar() -> str | None:
    return get_tool_path("UnRAR") or get_tool_path("unrar")


def get_ytdlp() -> str | None:
    return get_tool_path("yt-dlp")


def _parse_version_tuple(ver_str: str) -> tuple[int, ...]:
    """Convert CalVer/SemVer strings like '2026.10.26' into comparable int tuples."""
    nums = [int(part) for part in re.findall(r"\d+", ver_str or "")]
    return tuple(nums) if nums else (0,)


def _get_binary_ytdlp_version(bin_path: str) -> str:
    """Query external yt-dlp binary version cleanly with in-process caching."""
    if bin_path in _BINARY_VERSION_CACHE:
        return _BINARY_VERSION_CACHE[bin_path]
    try:
        res = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ver = (res.stdout or "").strip().splitlines()[0].strip() if res.returncode == 0 else ""
    except Exception:
        ver = ""
    _BINARY_VERSION_CACHE[bin_path] = ver
    return ver


def resolve_ytdlp_runner() -> tuple[list[str], str] | None:
    """
    Resolve the freshest available yt-dlp invocation command and version string.

    Compares the Python `yt_dlp` package (kept current via `pp` / pip) against any
    local or PATH `yt-dlp` binary, preferring the newest version so stale bundled
    executables never shadow upgraded extractors.
    """
    mod_cmd: list[str] | None = None
    mod_ver = ""
    if importlib.util.find_spec("yt_dlp") is not None:
        mod_cmd = [sys.executable, "-m", "yt_dlp"]
        try:
            mod_ver = importlib.metadata.version("yt-dlp")
        except Exception:
            mod_ver = ""

    bin_path = get_ytdlp()
    bin_ver = _get_binary_ytdlp_version(bin_path) if bin_path else ""

    if mod_cmd and bin_path:
        if _parse_version_tuple(bin_ver) > _parse_version_tuple(mod_ver):
            return ([bin_path], bin_ver or "binary")
        return (mod_cmd, mod_ver or "module")

    if mod_cmd:
        return (mod_cmd, mod_ver or "module")
    if bin_path:
        return ([bin_path], bin_ver or "binary")
    return None


def get_js_runtimes() -> list[tuple[str, str]]:
    """
    Detect installed JavaScript runtimes supported by yt-dlp's EJS solver
    (deno, node, bun, quickjs) in priority order.
    """
    runtimes: list[tuple[str, str]] = []
    for name in ("deno", "node", "bun", "quickjs"):
        found = shutil.which(name)
        if not found and os.name == "nt" and name == "node":
            win_node = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe"
            if win_node.is_file():
                found = str(win_node)
        if found:
            runtimes.append((name, found))
    return runtimes
