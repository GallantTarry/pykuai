# -*- coding: utf-8 -*-
"""
PyKuai Binary Tools Locator (FFmpeg, FFprobe, UnRAR, yt-dlp)
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

_BINARY_VERSION_CACHE: dict[str, str] = {}

USER_TOOLS_DIR = Path.home() / ".pykuai" / "tools"
FFMPEG_WIN_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_WIN_SHA256_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256"
_USER_AGENT = "pykuai-tools/1.0"


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


def _parse_sha256(raw_text: str) -> str:
    """Extract and validate the leading 64-char hex digest from a .sha256 payload."""
    parts = (raw_text or "").strip().split()
    digest = parts[0].lower() if parts else ""
    if len(digest) != 64 or not all(ch in "0123456789abcdef" for ch in digest):
        raise ValueError("Invalid SHA256 checksum response.")
    return digest


def _file_sha256(path: Path) -> str:
    """Compute lowercase hexadecimal SHA256 digest of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _stream_urllib_to_file(
    url: str,
    dest: Path,
    *,
    timeout: int,
    bypass_proxy: bool,
    progress_cb: Optional[Callable[[int, Optional[int]], None]] = None,
) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    ctx_mgr = (
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)
        if bypass_proxy
        else urllib.request.urlopen(req, timeout=timeout)
    )
    with ctx_mgr as resp:
        raw_len = resp.headers.get("Content-Length") if resp.headers else None
        total = int(raw_len) if raw_len and raw_len.isdigit() else None
        downloaded = 0
        if progress_cb:
            progress_cb(0, total)
        with open(dest, "wb") as out:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(downloaded, total)


def _download_to_file(
    url: str,
    dest: Path,
    *,
    timeout: int = 60,
    progress_cb: Optional[Callable[[int, Optional[int]], None]] = None,
) -> None:
    """Download URL to dest with Python urllib, falling back to curl or direct connection on proxy/TLS quirks."""
    errors: list[str] = []
    try:
        _stream_urllib_to_file(url, dest, timeout=timeout, bypass_proxy=False, progress_cb=progress_cb)
        return
    except (urllib.error.URLError, OSError, ValueError) as exc:
        errors.append(f"urllib: {exc}")

    curl_bin = shutil.which("curl")
    if curl_bin:
        try:
            proc = subprocess.run(
                [curl_bin, "-fsSL", "--retry", "2", "--connect-timeout", "15", "-A", _USER_AGENT, "-o", str(dest), url],
                capture_output=True,
                text=True,
                timeout=max(timeout, 300),
            )
            if proc.returncode == 0 and dest.is_file():
                if progress_cb:
                    size = dest.stat().st_size
                    progress_cb(size, size)
                return
            err_msg = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
            errors.append(f"curl: {err_msg}")
        except Exception as exc:
            errors.append(f"curl: {exc}")

    try:
        _stream_urllib_to_file(url, dest, timeout=timeout, bypass_proxy=True, progress_cb=progress_cb)
        return
    except (urllib.error.URLError, OSError, ValueError) as exc:
        errors.append(f"direct: {exc}")

    raise RuntimeError(" ; ".join(errors))


def install_ffmpeg_binaries(
    target_dir: Optional[Path] = None,
    *,
    zip_url: str = FFMPEG_WIN_ZIP_URL,
    sha256_url: str = FFMPEG_WIN_SHA256_URL,
    progress_cb: Optional[Callable[[int, Optional[int]], None]] = None,
) -> tuple[Path, Path]:
    """Download, SHA256-verify, and atomically extract ffmpeg.exe + ffprobe.exe into USER_TOOLS_DIR."""
    if os.name != "nt":
        raise RuntimeError("Automatic FFmpeg binary installation is currently supported on Windows only.")

    dest_dir = Path(target_dir) if target_dir is not None else USER_TOOLS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    targets = {"ffmpeg.exe": dest_dir / "ffmpeg.exe", "ffprobe.exe": dest_dir / "ffprobe.exe"}

    with tempfile.TemporaryDirectory(prefix="pykuai_ffmpeg_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        sha_path = tmp_path / "ffmpeg.sha256"
        zip_path = tmp_path / "ffmpeg.zip"

        _download_to_file(sha256_url, sha_path, timeout=20)
        expected_sha = _parse_sha256(sha_path.read_text(encoding="utf-8", errors="replace"))

        _download_to_file(zip_url, zip_path, timeout=120, progress_cb=progress_cb)
        actual_sha = _file_sha256(zip_path)
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"FFmpeg archive SHA256 mismatch (expected {expected_sha[:12]}..., got {actual_sha[:12]}...)."
            )

        staged: dict[str, Path] = {}
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    base = os.path.basename(info.filename).lower()
                    if base not in targets or base in staged:
                        continue
                    stage_file = dest_dir / f".{base}.tmp"
                    with zf.open(info, "r") as src, open(stage_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    staged[base] = stage_file

            if set(staged.keys()) != set(targets.keys()):
                missing = ", ".join(sorted(set(targets.keys()) - set(staged.keys())))
                raise RuntimeError(f"FFmpeg archive missing required executable(s): {missing}")

            for name, stage_file in staged.items():
                dest_file = targets[name]
                os.replace(stage_file, dest_file)
                _BINARY_VERSION_CACHE.pop(str(dest_file), None)
        finally:
            for name in targets:
                stage_file = dest_dir / f".{name}.tmp"
                if stage_file.exists():
                    try:
                        stage_file.unlink()
                    except OSError:
                        pass

    return targets["ffmpeg.exe"], targets["ffprobe.exe"]


def ensure_ffmpeg(
    console=None,
    *,
    interactive: Optional[bool] = None,
    auto_confirm: bool = False,
    target_dir: Optional[Path] = None,
) -> str | None:
    """Resolve FFmpeg or interactively prompt to install official binaries into ~/.pykuai/tools/ on Windows."""
    existing = get_ffmpeg()
    if existing:
        return existing

    def _emit(msg: str) -> None:
        if console is not None:
            console.print(msg)
        else:
            print(re.sub(r"\[/?[^\]]+\]", "", msg))

    if os.name != "nt":
        _emit(
            "[yellow]⚠ FFmpeg not found. Install via your package manager "
            "(e.g. brew install ffmpeg or sudo apt install ffmpeg).[/yellow]"
        )
        return None

    can_prompt = (sys.stdin is not None and sys.stdin.isatty()) if interactive is None else interactive
    if not auto_confirm:
        if not can_prompt:
            return None
        dest_hint = str(Path(target_dir) if target_dir is not None else USER_TOOLS_DIR)
        _emit(f"[yellow]⚠ FFmpeg / FFprobe not found locally.[/yellow]")
        _emit(
            f"[dim]Official Windows essentials (~95 MB, SHA256 verified) can be installed to "
            f"{dest_hint}[/dim]"
        )
        try:
            answer = input("Download FFmpeg & FFprobe now? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        if answer and answer not in {"y", "yes"}:
            return None

    try:
        if console is not None:
            from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn, TransferSpeedColumn

            with Progress(
                SpinnerColumn(style="#00FF00"),
                TextColumn("[#00FF00]{task.description}[/#00FF00]"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                console=console,
                transient=True,
            ) as progress:
                task_id = progress.add_task("Downloading FFmpeg...", total=None)

                def _on_progress(done: int, total: Optional[int]) -> None:
                    progress.update(task_id, total=total, completed=done)

                ffmpeg_exe, _ = install_ffmpeg_binaries(target_dir=target_dir, progress_cb=_on_progress)
        else:
            ffmpeg_exe, _ = install_ffmpeg_binaries(target_dir=target_dir)

        _emit(f"[#00FF00]✓ FFmpeg installed to {ffmpeg_exe}[/#00FF00]")
        return str(ffmpeg_exe)
    except Exception as exc:
        _emit(f"[yellow]⚠ Failed to auto-install FFmpeg: {exc}[/yellow]")
        _emit("[dim]You can manually place ffmpeg.exe and ffprobe.exe into ~/.pykuai/tools/ or install via winget install Gyan.FFmpeg[/dim]")
        return None


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
        bin_tuple = _parse_version_tuple(bin_ver)
        mod_tuple = _parse_version_tuple(mod_ver)
        has_curl_cffi = importlib.util.find_spec("curl_cffi") is not None
        # Standalone yt-dlp binaries bundle curl_cffi/certifi/brotli, so prefer them on equal version when curl_cffi isn't installed in Python.
        if bin_tuple > mod_tuple or (bin_tuple == mod_tuple and not has_curl_cffi):
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
