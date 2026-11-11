# -*- coding: utf-8 -*-
"""
PyKuai Binary Tools Locator (FFmpeg, FFprobe, UnRAR, yt-dlp)
"""
import os
import shutil
from pathlib import Path


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
