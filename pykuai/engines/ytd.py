# -*- coding: utf-8 -*-
"""
YouTube & Stream Downloader Engine (`ytd` - YouTube Download)
Powered by yt-dlp (https://github.com/yt-dlp/yt-dlp) and FFmpeg.

Supports YouTube (with automated JS runtime & EJS challenge resolution),
Bilibili, X/Twitter, and 1,000+ extractors with MP4 muxing and MP3/M4A extraction.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt

from pykuai.core.base import BaseEngine
from pykuai.core.tools import ensure_ffmpeg, get_ffmpeg, get_js_runtimes, resolve_ytdlp_runner
from pykuai.core.ui import print_error, print_info, print_step, print_warning


@dataclass(frozen=True)
class FormatProfile:
    key: str
    label: str
    is_audio: bool
    ffmpeg_expr: str
    fallback_expr: str
    extra_args: tuple[str, ...]


FORMAT_PROFILES: dict[str, FormatProfile] = {
    "best": FormatProfile(
        key="best",
        label="Best MP4 (Auto Mux)",
        is_audio=False,
        ffmpeg_expr="bv*+ba/b",
        fallback_expr="b[ext=mp4]/b",
        extra_args=("--merge-output-format", "mp4", "--remux-video", "mp4"),
    ),
    "1080p": FormatProfile(
        key="1080p",
        label="1080p MP4 (H.264 preferred)",
        is_audio=False,
        ffmpeg_expr="bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]",
        fallback_expr="b[height<=1080][ext=mp4]/b[height<=1080]",
        extra_args=("--merge-output-format", "mp4", "--remux-video", "mp4"),
    ),
    "720p": FormatProfile(
        key="720p",
        label="720p MP4 (H.264 preferred)",
        is_audio=False,
        ffmpeg_expr="bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=720]+ba/b[height<=720]",
        fallback_expr="b[height<=720][ext=mp4]/b[height<=720]",
        extra_args=("--merge-output-format", "mp4", "--remux-video", "mp4"),
    ),
    "mp3": FormatProfile(
        key="mp3",
        label="MP3 Audio (Best Quality)",
        is_audio=True,
        ffmpeg_expr="ba/b",
        fallback_expr="ba/b",
        extra_args=("--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"),
    ),
    "m4a": FormatProfile(
        key="m4a",
        label="M4A Audio (AAC)",
        is_audio=True,
        ffmpeg_expr="ba[ext=m4a]/ba/b",
        fallback_expr="ba/b",
        extra_args=("--extract-audio", "--audio-format", "m4a"),
    ),
}

FORMAT_ALIASES: dict[str, str] = {
    "video": "best",
    "mp4": "best",
    "audio": "mp3",
}


def _normalize_format(fmt: str) -> FormatProfile:
    """Resolve CLI/TUI format names and legacy aliases to a FormatProfile."""
    clean = (fmt or "best").strip().lower()
    canonical = FORMAT_ALIASES.get(clean, clean)
    return FORMAT_PROFILES.get(canonical, FORMAT_PROFILES["best"])


def _clean_text(raw: str) -> str:
    clean = raw.strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in "\"'":
        return clean[1:-1].strip()
    return clean


def _validate_url(url: str) -> tuple[bool, str]:
    clean = _clean_text(url)
    if not clean:
        return False, ""
    if any(c.isspace() or ord(c) < 32 or 127 <= ord(c) <= 159 for c in clean):
        return False, "Invalid URL"
    try:
        parsed = urlsplit(clean)
        _ = parsed.port  # Validate the port while parsing the host.
    except ValueError:
        return False, "Invalid URL"
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or "\\" in parsed.netloc:
        return False, "Invalid URL"
    host = parsed.hostname.lower().rstrip(".")
    if host == "youtube.com" or host.endswith(".youtube.com") or host == "youtu.be":
        return True, "✓ YouTube"
    if host == "bilibili.com" or host.endswith(".bilibili.com") or host == "b23.tv":
        return True, "✓ Bilibili"
    if host in {"x.com", "twitter.com"} or host.endswith((".x.com", ".twitter.com")):
        return True, "✓ X"
    return True, "✓ URL"


def _looks_like_netscape_cookies(path: str) -> bool:
    """Return True when path is an existing Netscape-format cookies.txt file."""
    if not path or not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for _ in range(12):
                line = fh.readline()
                if not line:
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith(("# Netscape HTTP Cookie File", "# HTTP Cookie File")):
                    return True
                if not stripped.startswith("#") and line.count("\t") >= 6:
                    return True
    except OSError:
        return False
    return False


def _discover_cookies_file(save_dir: str = "") -> str:
    """Locate an existing exported Netscape cookies.txt in common folders."""
    candidates: list[Path] = []
    if save_dir:
        sdir = Path(save_dir)
        candidates.extend([sdir / "cookies.txt", sdir / "www.youtube.com_cookies.txt"])
    cwd = Path.cwd()
    candidates.extend([cwd / "cookies.txt", cwd / "www.youtube.com_cookies.txt"])
    pykuai_dir = Path.home() / ".pykuai"
    candidates.extend([pykuai_dir / "cookies.txt", pykuai_dir / "youtube_cookies.txt"])
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        candidates.extend([downloads / "www.youtube.com_cookies.txt", downloads / "cookies.txt"])
        try:
            extra = sorted(
                (p for p in downloads.glob("*cookies*.txt") if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            candidates.extend(extra[:5])
        except OSError:
            pass

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = str(candidate.resolve())
        except OSError:
            resolved = os.path.abspath(str(candidate))
        key = os.path.normcase(resolved)
        if key in seen:
            continue
        seen.add(key)
        if _looks_like_netscape_cookies(resolved):
            return resolved
    return ""


def _is_cookie_db_error(errors: list[str]) -> bool:
    """Detect Windows/Chromium cookie database copy or DPAPI/ABE decryption errors."""
    joined = "\n".join(errors).lower()
    if "cookie database" in joined or "cookies database" in joined:
        return True
    if "could not copy" in joined and "cookie" in joined:
        return True
    if "failed to decrypt with dpapi" in joined or "app-bound encryption" in joined:
        return True
    if "unable to decrypt" in joined and "cookie" in joined:
        return True
    return False


def _validate_connection_options(cookies_browser: str, cookies_file: str, proxy_url: str) -> str:
    """Reject unusable arguments before spawning the downloader."""
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 for value in (cookies_browser, cookies_file, proxy_url) for c in value):
        return "Cookie and proxy options cannot contain control characters."
    browser = _clean_text(cookies_browser).lower() or "none"
    cookie_path = _clean_text(cookies_file)
    if browser not in {"none", "chrome", "edge", "firefox", "brave"}:
        return f"Unsupported cookie browser: {browser}"
    if browser != "none" and cookie_path:
        return "Choose either browser cookies or a cookies file, not both."
    if cookie_path and not os.path.isfile(os.path.expanduser(cookie_path)):
        return f"Cookies file not found: {cookie_path}"
    return ""


_FINAL_FILE_PREFIX = "__PYKUAI_FILE__:"


YTD_HELP_TITLE = "ytd  ·  YouTube Download Studio"
YTD_HELP_TEXT = """\
[bold #00d2ff]Overview[/]
  Download video or extract audio from YouTube and supported URLs using [bold]yt-dlp[/] and [bold]FFmpeg[/].

[bold #00d2ff]URL Input & Validation[/]
  • Paste any video, Shorts, playlist, or supported media URL into the URL bar.
  • Live validation highlights recognized URLs; bare domains automatically normalize to [#e5e7eb]https://[/] on submit.

[bold #00d2ff]Format Profiles[/]
  • [bold #10b981]Best[/]   [#d8dee9]Best MP4 (Auto Mux) — highest video + audio merged into MP4.[/]
  • [bold #10b981]1080p[/]  [#d8dee9]Full HD MP4 — caps video height at 1080p (H.264/M4A preferred).[/]
  • [bold #10b981]720p[/]   [#d8dee9]HD MP4 — caps video height at 720p (H.264/M4A preferred).[/]
  • [bold #10b981]MP3[/]    [#d8dee9]MP3 Audio — extracts and transcodes best audio to MP3 (--audio-quality 0).[/]
  • [bold #10b981]M4A[/]    [#d8dee9]M4A Audio — extracts AAC/M4A audio at best available bitrate.[/]
  • [dim #9ca3af]CLI format aliases:[/] [#d8dee9]video / mp4 -> best, audio -> mp3.[/]

[bold #00d2ff]Scope & Subtitles[/]
  • [bold #e5e7eb]Single[/]     Downloads only the single linked item (passes --no-playlist even with &list=).
  • [bold #e5e7eb]Playlist[/]   Downloads the full playlist or collection (--yes-playlist).
  • [bold #e5e7eb]Subs[/]       Downloads manual and auto captions for English & Chinese (en, zh-Hans, zh-Hant, zh) and embeds them when FFmpeg is present.

[bold #00d2ff]Cookies & Proxy[/]
  • [bold #e5e7eb]Cookie[/]   None, Chrome, Edge, Firefox (--cookies-from-browser), or File (Netscape cookies.txt).
  • [bold #e5e7eb]File[/]     Auto-detects cookies.txt in save/working dir, ~/.pykuai/cookies.txt, or ~/Downloads; you can also paste any cookies.txt path.
  • [dim #9ca3af]Windows Auto-Fallback: When Chrome or Edge locks/blocks its cookie DB (yt-dlp #7271 / DPAPI #10927), ytd automatically falls back to detected cookies.txt or cookieless mode instead of aborting public videos.[/]
  • [bold #e5e7eb]Proxy[/]    Optional http://, https://, socks4://, or socks5:// proxy URL.

[bold #00d2ff]Output Directory, Naming & Stream Probing[/]
  • [bold #e5e7eb]Dir[/]      Target save folder (defaults to current working directory; outer quotes on pasted paths are stripped).
  • Files save as: [dim #9ca3af]%(title).150B \\[%(id)s] \\[<profile>].%(ext)s[/]
  • [bold #f59e0b]Formats[/]  Probes and lists all available video/audio streams (-F) without downloading.

[bold #00d2ff]Smart Resilience & Challenge Solving[/]
  • Automatically enables [bold]ejs:github[/] JS challenge solving when Node/Deno is present.
  • Retries failed downloads with a safe fallback format selector on HTTP 403 or unavailable stream errors and prints actionable diagnostics.

[bold #00d2ff]CLI Usage & Shortcuts[/]
  • [bold #e5e7eb]pykuai tt ytd[/]                                 Open interactive Studio
  • [bold #e5e7eb]pykuai tt ytd <url> \\[-f best|1080p|720p|mp3|m4a] \\[-o dir][/]
  • Flags: [dim #9ca3af]-p/--playlist, --subs, --cookies-from-browser, --cookies <txt>, --proxy <url>, -F/--list-formats[/]
  • Keys: [bold]?[/] or [bold]F1[/] opens this guide · [bold]Esc[/] closes modals/Studio · [bold]Ctrl+C[/] aborts active download."""


def _build_ytd_studio_app(initial_url: str = ""):
    """Construct the clickable Cyber-Dark YouTube Download (ytd) Studio (lazy-loaded)."""
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal, VerticalScroll
    from textual.widgets import Button, Input, Static
    from pykuai.core.tui import (
        ActionChip,
        CYBER_TUI_CSS,
        PyKuaiStudioApp,
        StudioHeader,
        ToggleChip,
    )

    runner = resolve_ytdlp_runner()
    ytdlp_lbl = f"yt-dlp {runner[1]}" if runner else "yt-dlp missing"
    ffmpeg_lbl = "ffmpeg" if get_ffmpeg() else "no ffmpeg"
    runtimes = get_js_runtimes()
    js_lbl = "/".join(rt for rt, _ in runtimes) if runtimes else "no js"

    init_clean = _clean_text(initial_url)
    detected_cookie = _discover_cookies_file()
    media_css = CYBER_TUI_CSS + """
    #studio-card {
        height: 24;
        padding: 0 1;
    }
    #studio-scroll {
        height: 1fr;
        min-height: 1;
    }
    .studio-title, .shown-err, .hint-footer {
        height: auto;
    }
    .shown-err {
        max-height: 3;
    }
    .hidden-section {
        display: none;
    }
    .cookie-warn {
        color: #f59e0b;
        height: auto;
        margin-top: 0;
        margin-bottom: 0;
    }
    Screen.narrow .option-row {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr;
        grid-rows: 1;
        grid-gutter: 0 1;
        height: auto;
    }
    Screen.narrow .option-row .field-label,
    Screen.narrow #ck-file {
        column-span: 2;
    }
    Screen.narrow #ck-file {
        width: 100%;
    }
    Screen.narrow .option-row ToggleChip {
        width: 1fr;
        min-width: 0;
        margin-right: 0;
    }
    .action-bar ActionChip {
        width: 1fr;
        min-width: 0;
        padding: 0 1;
    }
    Input.cyber-input {
        margin-bottom: 0;
    }
    .slim-row {
        height: 1;
        layout: horizontal;
        margin-top: 0;
        margin-bottom: 0;
    }
    .hint-footer {
        margin-top: 0;
    }
    .action-bar {
        margin-top: 1;
        margin-bottom: 0;
    }
    """

    class YtdStudioApp(PyKuaiStudioApp):
        CSS = media_css
        HELP_TITLE = YTD_HELP_TITLE
        HELP_TEXT = YTD_HELP_TEXT

        def compose(self) -> ComposeResult:
            ok, status_text = _validate_url(init_clean)
            status_cls = "status-ok" if ok else ("status-err" if init_clean else "status-dim")

            with Container(id="studio-card"):
                yield StudioHeader("🎬 ytd  [dim #6b7280]·  yt-dlp[/]")
                with VerticalScroll(id="studio-scroll"):

                    with Horizontal(classes="field-header"):
                        yield Static("URL", classes="field-label")
                        yield Static(status_text, id="url-status", classes=status_cls)

                    yield Input(
                        value=init_clean,
                        placeholder="https://...",
                        id="url-input",
                        classes="cyber-input",
                    )

                    with Horizontal(classes="compact-tight option-row"):
                        yield Static("Video: ", classes="field-label")
                        yield ToggleChip("Best", value="best", active=True, id="fmt-best")
                        yield ToggleChip("1080p", value="1080p", active=False, id="fmt-1080p")
                        yield ToggleChip("720p", value="720p", active=False, id="fmt-720p")

                    with Horizontal(classes="compact-row option-row"):
                        yield Static("Audio: ", classes="field-label")
                        yield ToggleChip("MP3", value="mp3", active=False, id="fmt-mp3")
                        yield ToggleChip("M4A", value="m4a", active=False, id="fmt-m4a")

                    with Horizontal(classes="compact-row option-row"):
                        yield Static("Scope:", classes="field-label")
                        yield ToggleChip("Single", value="single", active=True, id="scope-single")
                        yield ToggleChip("Playlist", value="playlist", active=False, id="scope-playlist")
                        yield ToggleChip("Subs", value="subs", active=False, id="opt-subs")

                    with Horizontal(classes="compact-tight option-row"):
                        yield Static("Cookie:", classes="field-label")
                        yield ToggleChip("None", value="none", active=(not detected_cookie), id="ck-none")
                        yield ToggleChip("Chrome", value="chrome", active=False, id="ck-chrome")
                        yield ToggleChip("Edge", value="edge", active=False, id="ck-edge")
                        yield ToggleChip("Firefox", value="firefox", active=False, id="ck-firefox")

                    with Horizontal(classes="compact-row option-row"):
                        yield Static("      ", classes="field-label")
                        yield ToggleChip("cookies.txt", value="file", active=bool(detected_cookie), id="ck-file")

                    with Horizontal(
                        id="cookies-row",
                        classes="slim-row" if detected_cookie else "slim-row hidden-section",
                    ):
                        yield Static("File: ", classes="field-label")
                        yield Input(
                            value=detected_cookie,
                            placeholder="path/to/cookies.txt (~/.pykuai/cookies.txt)",
                            id="cookies-input",
                            classes="cyber-slim",
                        )

                    yield Static(
                        "⚠ Windows Chrome/Edge locks cookie DB while running; auto-falls back to cookies.txt or None.",
                        id="cookie-note",
                        classes="cookie-warn hidden-section",
                        markup=False,
                    )

                    with Horizontal(classes="compact-tight"):
                        yield Static("Dir:  ", classes="field-label")
                        yield Input(
                            value=os.getcwd(),
                            placeholder=".",
                            id="out-input",
                            classes="cyber-slim",
                        )

                    with Horizontal(classes="slim-row"):
                        yield Static("Proxy:", classes="field-label")
                        yield Input(
                            placeholder="http://127.0.0.1:7897 (optional)",
                            id="proxy-input",
                            classes="cyber-slim",
                        )

                    yield Static(
                        f"{ytdlp_lbl} · {ffmpeg_lbl} · {js_lbl}",
                        id="engine-info",
                        classes="hint-footer",
                        markup=False,
                    )

                yield Static("", id="form-error", classes="hidden-err", markup=False)

                with Horizontal(classes="action-bar"):
                    yield ActionChip("⚡ Run", variant_class="-primary", id="btn-run")
                    yield ActionChip("Formats", variant_class="-preset", id="btn-probe")
                    yield ActionChip("✕ Cancel", variant_class="-danger", id="btn-cancel")

        def on_mount(self) -> None:
            self.screen.set_class(self.size.width < 76, "narrow")
            if init_clean:
                self.query_one("#btn-run", ActionChip).focus()
            else:
                self.query_one("#url-input", Input).focus()

        def on_resize(self, event) -> None:
            self.screen.set_class(event.size.width < 76, "narrow")

        def _set_error(self, message: str = "") -> None:
            err = self.query_one("#form-error", Static)
            err.update(message)
            err.set_classes("shown-err" if message else "hidden-err")

        def _refresh_url_status(self, url_val: str) -> None:
            ok, msg = _validate_url(url_val)
            badge = self.query_one("#url-status", Static)
            badge.update(msg)
            if ok:
                badge.set_classes("status-ok")
            elif _clean_text(url_val):
                badge.set_classes("status-err")
            else:
                badge.set_classes("status-dim")

        def _select_radio_group(self, prefix: str, target_id: str) -> None:
            for chip in self.query(ToggleChip):
                if chip.id and chip.id.startswith(prefix):
                    chip.active = (chip.id == target_id)

        def _active_group_value(self, prefix: str, default: str) -> str:
            for chip in self.query(ToggleChip):
                if chip.id and chip.id.startswith(prefix) and chip.active:
                    return str(chip.value)
            return default

        def _sync_cookie_widgets(self, choice: str) -> None:
            cookies_row = self.query_one("#cookies-row")
            cookie_note = self.query_one("#cookie-note")
            cookies_row.set_class(choice != "file", "hidden-section")
            show_win_warn = os.name == "nt" and choice in ("chrome", "edge")
            cookie_note.set_class(not show_win_warn, "hidden-section")

        def on_input_changed(self, event: Input.Changed) -> None:
            if event.input.id == "url-input":
                self._refresh_url_status(event.value)
                self._set_error("")
            elif event.input.id in ("cookies-input", "out-input", "proxy-input"):
                self._set_error("")

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "url-input":
                ok, _ = _validate_url(event.value)
                if ok:
                    self.query_one("#btn-run", ActionChip).focus()
            elif event.input.id in ("cookies-input", "out-input", "proxy-input"):
                self._submit("download")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            btn = event.button
            self._set_error("")
            bid = btn.id or ""

            if bid.startswith("fmt-"):
                self._select_radio_group("fmt-", bid)
            elif bid.startswith("scope-"):
                self._select_radio_group("scope-", bid)
            elif bid.startswith("ck-"):
                self._select_radio_group("ck-", bid)
                choice = str(getattr(btn, "value", "none"))
                self._sync_cookie_widgets(choice)
                if choice == "file":
                    self.query_one("#cookies-input", Input).focus()
            elif isinstance(btn, ToggleChip):
                btn.active = not btn.active
            elif bid == "btn-run":
                self._submit("download")
            elif bid == "btn-probe":
                self._submit("probe")
            elif bid == "btn-cancel":
                self.exit(None)

        def _submit(self, action: str) -> None:
            url_val = _clean_text(self.query_one("#url-input", Input).value)
            ok, msg = _validate_url(url_val)
            if not url_val:
                self._set_error("Please enter or paste a video/playlist URL.")
                self.query_one("#url-input", Input).focus()
                return
            if not ok:
                self._set_error(msg)
                self.query_one("#url-input", Input).focus()
                return

            fmt_key = self._active_group_value("fmt-", "best")
            is_playlist = self._active_group_value("scope-", "single") == "playlist"
            subtitles = self.query_one("#opt-subs", ToggleChip).active
            ck_choice = self._active_group_value("ck-", "none")
            if ck_choice == "file":
                cookies_browser = "none"
                cookies_file = os.path.expanduser(_clean_text(self.query_one("#cookies-input", Input).value))
                if not cookies_file:
                    self._set_error("Enter a cookies.txt file path (or select None / Firefox).")
                    self.query_one("#cookies-input", Input).focus()
                    return
            else:
                cookies_browser = ck_choice
                cookies_file = ""

            raw_out = _clean_text(self.query_one("#out-input", Input).value) or "."
            out_dir = os.path.abspath(os.path.expanduser(raw_out))
            proxy_url = _clean_text(self.query_one("#proxy-input", Input).value)

            opt_err = _validate_connection_options(cookies_browser, cookies_file, proxy_url)
            if opt_err:
                self._set_error(opt_err)
                target = "#cookies-input" if cookies_file else "#proxy-input"
                self.query_one(target, Input).focus()
                return

            self.exit(
                (action, url_val, fmt_key, is_playlist, subtitles, cookies_browser, cookies_file, out_dir, proxy_url)
            )

    return YtdStudioApp()


def _launch_ytd_studio(
    initial_url: str = "",
) -> Optional[tuple[str, str, str, bool, bool, str, str, str, str]]:
    """Launch clickable ytd Studio inside interactive TTY."""
    app = _build_ytd_studio_app(initial_url=initial_url)
    result = app.run(mouse=True)
    sys.stdout.flush()
    return result


def _build_ytdlp_command(
    runner_cmd: list[str],
    url: str,
    profile: FormatProfile,
    save_dir: str,
    ffmpeg_bin: Optional[str],
    js_runtimes: list[tuple[str, str]],
    *,
    is_playlist: bool = False,
    subtitles: bool = False,
    cookies_browser: str = "none",
    cookies_file: str = "",
    proxy_url: str = "",
    list_formats: bool = False,
    use_fallback_format: bool = False,
) -> list[str]:
    """Assemble yt-dlp CLI arguments with JS runtime & EJS solver configuration."""
    cmd = list(runner_cmd)
    cmd.extend([
        "--ignore-config",
        "--no-colors",
        "--encoding", "utf-8",
        "--windows-filenames",
        "--no-mtime",
        "--retries", "5",
        "--fragment-retries", "5",
        "--file-access-retries", "3",
        "--remote-components", "ejs:github",
    ])

    for rt_name, rt_path in js_runtimes:
        cmd.extend(["--js-runtimes", f"{rt_name}:{rt_path}"])

    if ffmpeg_bin:
        cmd.extend(["--ffmpeg-location", ffmpeg_bin])

    cookies_browser = _clean_text(cookies_browser).lower()
    if cookies_browser and cookies_browser != "none":
        cmd.extend(["--cookies-from-browser", cookies_browser])
    elif cookies_file:
        cmd.extend(["--cookies", os.path.abspath(os.path.expanduser(_clean_text(cookies_file)))])

    if proxy_url:
        cmd.extend(["--proxy", _clean_text(proxy_url)])

    cmd.append("--yes-playlist" if is_playlist else "--no-playlist")

    if list_formats:
        cmd.extend(["-F", "--", _clean_text(url)])
        return cmd

    cmd.extend([
        "--newline",
        "--concurrent-fragments", "4",
        "--paths", save_dir,
        "-o", f"%(title).150B [%(id)s] [{profile.key}].%(ext)s",
        "--print", f"after_move:{_FINAL_FILE_PREFIX}%(filepath)j",
        "--no-simulate",
        "--no-quiet",
    ])

    format_expr = profile.ffmpeg_expr if ffmpeg_bin and not use_fallback_format else profile.fallback_expr
    cmd.extend(["-f", format_expr])
    if ffmpeg_bin:
        cmd.extend(profile.extra_args)

    if subtitles:
        cmd.extend(["--write-subs", "--write-auto-subs", "--sub-langs", "en.*,zh.*"])
        if ffmpeg_bin and not profile.is_audio:
            cmd.append("--embed-subs")

    cmd.extend(["--", _clean_text(url)])
    return cmd


class YtdEngine(BaseEngine):
    name = "ytd"
    description = "YouTube Download (yt-dlp + FFmpeg)"
    usage = "tt ytd | tt ytd <url> [-f best|1080p|720p|mp3|m4a] [-o dir]"
    category = "Media & Video"
    requires = ["yt-dlp>=2026.10.0", "yt-dlp-ejs>=0.8.0"]
    help_text = YTD_HELP_TEXT

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("url", nargs="?", default="", help="Target stream or playlist URL")
        parser.add_argument(
            "-f", "--format",
            choices=["best", "1080p", "720p", "mp3", "m4a", "video", "audio", "mp4"],
            default="best",
            help="Download profile: best (MP4), 1080p, 720p, mp3 (audio), m4a (audio)",
        )
        parser.add_argument("-p", "--playlist", action="store_true", help="Download full playlist or collection")
        parser.add_argument("--subs", action="store_true", help="Download English/Chinese subtitles; embed in video when FFmpeg is available")
        parser.add_argument(
            "--cookies-from-browser",
            choices=["none", "chrome", "edge", "firefox", "brave"],
            default="none",
            help="Read session cookies from your local browser if a site asks to sign in",
        )
        parser.add_argument("--cookies", default="", help="Path to exported Netscape cookies.txt")
        parser.add_argument("--proxy", default="", help="Override HTTP/SOCKS proxy URL")
        parser.add_argument("-F", "--list-formats", action="store_true", help="Inspect available streams without downloading")
        parser.add_argument("--install-ffmpeg", action="store_true", help="Download official FFmpeg/FFprobe binaries into ~/.pykuai/tools/")
        parser.add_argument("-o", "--output-dir", default=".", help="Output directory (default: current directory)")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        if getattr(args, "install_ffmpeg", False):
            return 0 if ensure_ffmpeg(console=console, interactive=False, auto_confirm=True) else 1

        url = _clean_text(getattr(args, "url", "") or "")
        if not url:
            return self.run_interactive(console)

        save_dir = os.path.abspath(os.path.expanduser(_clean_text(getattr(args, "output_dir", ".") or ".")))
        if getattr(args, "list_formats", False):
            return self._list_formats(
                url=url,
                is_playlist=getattr(args, "playlist", False),
                cookies_browser=getattr(args, "cookies_from_browser", "none"),
                cookies_file=getattr(args, "cookies", ""),
                proxy_url=getattr(args, "proxy", ""),
                console=console,
            )

        return self._download(
            url=url,
            fmt_key=getattr(args, "format", "best"),
            is_playlist=getattr(args, "playlist", False),
            subtitles=getattr(args, "subs", False),
            cookies_browser=getattr(args, "cookies_from_browser", "none"),
            cookies_file=getattr(args, "cookies", ""),
            save_dir=save_dir,
            proxy_url=getattr(args, "proxy", ""),
            console=console,
        )

    def launch_with_path(self, console: Console, path: str) -> int:
        """Open interactive Studio pre-loaded with a positional URL in TTY, or download directly."""
        from pykuai.core.tui import is_interactive_tty

        clean = _clean_text(path)
        if is_interactive_tty():
            return self.run_interactive(console, initial_url=clean)
        return self._download(
            url=clean,
            fmt_key="best",
            is_playlist=False,
            subtitles=False,
            cookies_browser="none",
            cookies_file="",
            save_dir=os.getcwd(),
            proxy_url="",
            console=console,
        )

    def run_interactive(self, console: Console, initial_url: str = "") -> int:
        from pykuai.core.tui import is_interactive_tty

        if is_interactive_tty():
            selection = _launch_ytd_studio(initial_url=initial_url)
            if not selection:
                console.print("[dim]› Cancelled.[/dim]")
                return 0
            (
                action,
                url,
                fmt_key,
                is_playlist,
                subtitles,
                cookies_browser,
                cookies_file,
                save_dir,
                proxy_url,
            ) = selection
            if action == "probe":
                return self._list_formats(
                    url=url,
                    is_playlist=is_playlist,
                    cookies_browser=cookies_browser,
                    cookies_file=cookies_file,
                    proxy_url=proxy_url,
                    console=console,
                )
            return self._download(
                url=url,
                fmt_key=fmt_key,
                is_playlist=is_playlist,
                subtitles=subtitles,
                cookies_browser=cookies_browser,
                cookies_file=cookies_file,
                save_dir=save_dir,
                proxy_url=proxy_url,
                console=console,
            )

        if not sys.stdin.isatty():
            print_error("No interactive input available. Use: pykuai tt ytd <url> [options]")
            return 1

        # Rich prompt fallback when only stdout is redirected.
        console.print("[bold #FF9800]🎬 ytd (yt-dlp + FFmpeg)[/bold #FF9800]")
        url = _clean_text(initial_url or Prompt.ask("[#10b981]?[/#10b981] Video or playlist URL"))
        if not url:
            print_error("No URL provided.")
            return 1

        mode = Prompt.ask(
            "[#10b981]?[/#10b981] Format profile [1: Best MP4, 2: 1080p, 3: 720p, 4: MP3, 5: M4A]",
            choices=["1", "2", "3", "4", "5"],
            default="1",
        )
        fmt_map = {"1": "best", "2": "1080p", "3": "720p", "4": "mp3", "5": "m4a"}

        scope = Prompt.ask(
            "[#10b981]?[/#10b981] Scope [1: Single video, 2: Playlist]",
            choices=["1", "2"],
            default="1",
        )
        out_raw = Prompt.ask("[#10b981]?[/#10b981] Output directory", default=".")

        return self._download(
            url=url,
            fmt_key=fmt_map[mode],
            is_playlist=(scope == "2"),
            subtitles=False,
            cookies_browser="none",
            cookies_file="",
            save_dir=os.path.abspath(_clean_text(out_raw) or "."),
            proxy_url="",
            console=console,
        )

    def _run_subprocess(
        self,
        cmd: list[str],
        console: Console,
        *,
        verbose_all: bool = False,
    ) -> tuple[int, list[str], list[str], Optional[str]]:
        """Execute yt-dlp with UTF-8 output streaming, clean progress filtering, and error capture."""
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        errors: list[str] = []
        warnings: list[str] = []
        final_file: Optional[str] = None
        last_pct_bucket = -1

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
            )
        except (OSError, ValueError) as exc:
            message = f"ERROR: Unable to start yt-dlp: {exc}"
            console.print(f"[bold #FF5252]  {escape(message)}[/bold #FF5252]")
            return 127, [message], warnings, final_file

        try:
            assert process.stdout is not None
            for line_bytes in iter(process.stdout.readline, b""):
                line = line_bytes.decode("utf-8", errors="replace").strip()
                # Remote titles must not inject terminal escape/control sequences.
                line = "".join(c for c in line if (ord(c) >= 32 and not 127 <= ord(c) <= 159) or c == "\t")
                if not line:
                    continue

                if line.startswith(_FINAL_FILE_PREFIX):
                    try:
                        path = json.loads(line[len(_FINAL_FILE_PREFIX):])
                        if isinstance(path, str):
                            final_file = path
                    except (ValueError, TypeError):
                        pass
                    continue

                if line.startswith("ERROR:"):
                    if line not in errors:
                        errors.append(line)
                        console.print(f"  {line}", style="bold #FF5252", markup=False, highlight=False)
                    continue

                if line.startswith("WARNING:"):
                    if line not in warnings:
                        warnings.append(line)
                    if "No title found" not in line:
                        console.print(f"  {line}", style="#FF9800", markup=False, highlight=False)
                    continue

                if verbose_all:
                    console.print(line, markup=False, highlight=False)
                    continue

                if line.startswith("[download]"):
                    pct_match = re.search(r"(\d+(?:\.\d+)?)%", line)
                    if "Destination:" in line:
                        last_pct_bucket = -1
                    elif pct_match:
                        bucket = int(float(pct_match.group(1)) // 20)
                        if bucket == last_pct_bucket and bucket < 5:
                            continue
                        last_pct_bucket = bucket
                    console.print(f"  {line}", style="#10b981", markup=False, highlight=False)
                elif line.startswith(("[Merger]", "[VideoRemuxer]", "[ExtractAudio]", "[EmbedSubtitle]", "[info]", "[youtube] [jsc:")):
                    console.print(f"  {line}", style="#38BDF8", markup=False, highlight=False)

            process.wait()
        except KeyboardInterrupt:
            console.print("\nDownload cancelled.", style="dim")
            return 130, errors, warnings, final_file
        except OSError as exc:
            message = f"ERROR: Reading yt-dlp output failed: {exc}"
            errors.append(message)
            console.print(message, style="bold #FF5252", markup=False, highlight=False)
            return 1, errors, warnings, final_file
        finally:
            # Also runs on SystemExit from the CLI's signal handler.
            try:
                if process.poll() is None:
                    try:
                        process.terminate()
                    except OSError:
                        pass  # The process may have exited between poll and terminate.
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            finally:
                if process.stdout is not None:
                    process.stdout.close()

        return process.returncode, errors, warnings, final_file

    def _print_diagnostics(
        self,
        errors: list[str],
        js_runtimes: list[tuple[str, str]],
        console: Console,
        *,
        had_cookie_fallback: bool = False,
    ) -> bool:
        """Render actionable remediation hints tailored to the captured yt-dlp failure."""
        joined = "\n".join(errors).lower()

        if _is_cookie_db_error(errors):
            console.print()
            console.print(
                Panel(
                    "[bold #FF9800]Browser Cookie Locked / Blocked on Windows[/bold #FF9800]\n"
                    "Chrome & Edge lock their cookie DB while running (yt-dlp #7271) "
                    "and Chromium 127+ blocks DPAPI decryption (#10927).\n"
                    "  [dim]1.[/dim] Export [bold]cookies.txt[/bold] (e.g. 'Get cookies.txt LOCALLY') -> choose [bold #00FF00]Cookie: File[/bold #00FF00] or save to [bold]~/.pykuai/cookies.txt[/bold]\n"
                    "  [dim]2.[/dim] Or use [bold #00FF00]Firefox[/bold #00FF00] under Cookie (works while open)\n"
                    "  [dim]3.[/dim] Or select Cookie: [bold]None[/bold] + switch proxy node",
                    border_style="#FF9800",
                    box=box.ROUNDED,
                    expand=False,
                )
            )
            return True

        if "sign in to confirm" in joined or "login_required" in joined or "age-restricted" in joined:
            console.print()
            extra = (
                "Browser cookies were locked/blocked on Windows and cookieless retry hit YouTube's sign-in gate.\n"
                if had_cookie_fallback
                else "YouTube flagged requests from your current IP/proxy node or requires sign-in.\n"
            )
            console.print(
                Panel(
                    "[bold #FF9800]YouTube Sign-In / Bot Check[/bold #FF9800]\n"
                    f"{extra}"
                    "  [dim]1.[/dim] Choose [bold #00FF00]Cookie: File[/bold #00FF00] in Studio (or save exported cookies to [bold]~/.pykuai/cookies.txt[/bold])\n"
                    "  [dim]2.[/dim] Or select [bold #00FF00]Firefox[/bold #00FF00] under Cookie (works while open)\n"
                    "  [dim]3.[/dim] Or switch to a cleaner proxy node ([bold]Proxy[/bold] / [bold]--proxy[/bold])",
                    border_style="#FF9800",
                    box=box.ROUNDED,
                    expand=False,
                )
            )
            return True

        if "http error 403" in joined or "signature" in joined or "challenge" in joined:
            js_tip = (
                f"JS: {', '.join(r for r, _ in js_runtimes)}"
                if js_runtimes
                else "No JS runtime — install Node.js or Deno"
            )
            print_warning(f"Stream 403 / challenge error ({js_tip}). Try `pykuai pp -U` or cookies.txt.")
            return True

        if (
            "timed out" in joined
            or "urlopen error" in joined
            or "proxy" in joined
            or "unexpected_eof" in joined
            or "sslerror" in joined
            or "eof occurred" in joined
        ):
            print_warning("Network/TLS/proxy error. Check your VPN/proxy connection or set `Proxy` / `--proxy`.")
            return True

        return False

    def _run_with_cookie_recovery(
        self,
        runner_cmd: list[str],
        url: str,
        profile: FormatProfile,
        save_dir: str,
        ffmpeg_bin: Optional[str],
        js_runtimes: list[tuple[str, str]],
        console: Console,
        *,
        is_playlist: bool = False,
        subtitles: bool = False,
        cookies_browser: str = "none",
        cookies_file: str = "",
        proxy_url: str = "",
        list_formats: bool = False,
        verbose_all: bool = False,
    ) -> tuple[int, list[str], Optional[str], bool]:
        """Run yt-dlp and auto-recover from Windows Chromium cookie DB locks."""
        eff_browser = _clean_text(cookies_browser).lower() or "none"
        eff_file = _clean_text(cookies_file)
        had_cookie_fallback = False

        cmd = _build_ytdlp_command(
            runner_cmd,
            url,
            profile,
            save_dir,
            ffmpeg_bin,
            js_runtimes,
            is_playlist=is_playlist,
            subtitles=subtitles,
            cookies_browser=eff_browser,
            cookies_file=eff_file,
            proxy_url=proxy_url,
            list_formats=list_formats,
        )
        rc, errors, _, final_file = self._run_subprocess(cmd, console, verbose_all=verbose_all)
        if rc == 0 or rc == 130:
            return rc, errors, final_file, had_cookie_fallback

        if eff_browser != "none" and not eff_file and _is_cookie_db_error(errors):
            discovered = _discover_cookies_file(save_dir)
            if discovered:
                print_warning(
                    f"{eff_browser.title()} cookie database is locked/blocked on Windows — "
                    f"retrying with detected cookies file: {escape(discovered)}"
                )
                eff_browser = "none"
                eff_file = discovered
            else:
                print_warning(
                    f"{eff_browser.title()} cookie database is locked/blocked on Windows — "
                    "retrying without browser cookies..."
                )
                eff_browser = "none"
                eff_file = ""
            had_cookie_fallback = True
            recovery_cmd = _build_ytdlp_command(
                runner_cmd,
                url,
                profile,
                save_dir,
                ffmpeg_bin,
                js_runtimes,
                is_playlist=is_playlist,
                subtitles=subtitles,
                cookies_browser=eff_browser,
                cookies_file=eff_file,
                proxy_url=proxy_url,
                list_formats=list_formats,
            )
            rc, retry_errors, _, retry_file = self._run_subprocess(recovery_cmd, console, verbose_all=verbose_all)
            errors = retry_errors or errors
            final_file = retry_file or final_file
            if rc == 0 or rc == 130:
                return rc, errors, final_file, had_cookie_fallback

        if not list_formats and rc != 0:
            joined_err = "\n".join(errors).lower()
            is_auth_gate = "sign in to confirm" in joined_err or "login_required" in joined_err
            transient_fail = any(
                tok in joined_err
                for tok in ("http error 403", "requested format is not available", "signature solving failed")
            )
            if not is_auth_gate and transient_fail:
                print_warning("Stream error — retrying a compatible stream once...")
                retry_cmd = _build_ytdlp_command(
                    runner_cmd,
                    url,
                    profile,
                    save_dir,
                    ffmpeg_bin,
                    js_runtimes,
                    is_playlist=is_playlist,
                    subtitles=subtitles,
                    cookies_browser=eff_browser,
                    cookies_file=eff_file,
                    proxy_url=proxy_url,
                    use_fallback_format=True,
                )
                rc, retry_errors, _, retry_file = self._run_subprocess(retry_cmd, console)
                errors = retry_errors or errors
                final_file = retry_file or final_file

        return rc, errors, final_file, had_cookie_fallback

    def _list_formats(
        self,
        url: str,
        is_playlist: bool,
        cookies_browser: str,
        cookies_file: str,
        proxy_url: str,
        console: Console,
    ) -> int:
        url = _clean_text(url)
        valid, message = _validate_url(url)
        if not valid:
            print_error(message or "Invalid URL")
            return 1

        option_error = _validate_connection_options(cookies_browser, cookies_file, proxy_url)
        if option_error:
            print_error(escape(option_error))
            return 1

        runner = resolve_ytdlp_runner()
        if not runner:
            print_error("yt-dlp is not available. Run `pykuai pp -y` to install `yt-dlp`.")
            return 1

        runner_cmd, ytdlp_ver = runner
        ffmpeg_bin = get_ffmpeg()
        js_runtimes = get_js_runtimes()

        print_step(f"Probing streams via [bold #00FF00]yt-dlp {escape(ytdlp_ver)}[/bold #00FF00]: [bold]{escape(url)}[/bold]")
        rc, errors, _, had_cookie_fallback = self._run_with_cookie_recovery(
            runner_cmd,
            url,
            FORMAT_PROFILES["best"],
            os.getcwd(),
            ffmpeg_bin,
            js_runtimes,
            console,
            is_playlist=is_playlist,
            cookies_browser=cookies_browser,
            cookies_file=cookies_file,
            proxy_url=proxy_url,
            list_formats=True,
            verbose_all=True,
        )
        if rc == 130:
            return rc
        if rc != 0:
            self._print_diagnostics(errors, js_runtimes, console, had_cookie_fallback=had_cookie_fallback)
            return 1
        return 0

    def _download(
        self,
        url: str,
        fmt_key: str,
        is_playlist: bool,
        subtitles: bool,
        cookies_browser: str,
        cookies_file: str,
        save_dir: str,
        proxy_url: str,
        console: Console,
    ) -> int:
        url = _clean_text(url)
        valid, message = _validate_url(url)
        if not valid:
            print_error(message or "Invalid URL")
            return 1

        option_error = _validate_connection_options(cookies_browser, cookies_file, proxy_url)
        if option_error:
            print_error(escape(option_error))
            return 1

        runner = resolve_ytdlp_runner()
        if not runner:
            print_error("yt-dlp not found. Run `pykuai pp` (Pull Packages) to install `yt-dlp`.")
            return 1

        runner_cmd, ytdlp_ver = runner
        ffmpeg_bin = get_ffmpeg()
        if not ffmpeg_bin:
            ffmpeg_bin = ensure_ffmpeg(console=console)
        js_runtimes = get_js_runtimes()
        profile = _normalize_format(fmt_key)

        if profile.is_audio and not ffmpeg_bin:
            print_error(
                "FFmpeg is required for MP3/M4A audio extraction. "
                "Run `pykuai tt ytd --install-ffmpeg` or place ffmpeg.exe in `~/.pykuai/tools/`."
            )
            return 1
        if not ffmpeg_bin:
            print_warning(
                "FFmpeg is unavailable; downloading a combined stream in its original container. "
                "Run `pykuai tt ytd --install-ffmpeg` anytime for MP4 muxing & audio conversion."
            )
        if subtitles and (not ffmpeg_bin or profile.is_audio):
            print_info("Subtitles will be saved as separate files for this profile.")

        rt_desc = ", ".join(r for r, _ in js_runtimes) if js_runtimes else "none"
        print_step(
            f"Fetching via [bold #00FF00]yt-dlp {ytdlp_ver}[/bold #00FF00] "
            f"[dim](JS: {rt_desc}, FFmpeg: {'yes' if ffmpeg_bin else 'no'})[/dim]"
        )
        print_info(f"Target: [bold]{escape(url)}[/bold]")
        print_info(f"Profile: [bold #00FF00]{profile.label}[/bold #00FF00]")

        try:
            os.makedirs(save_dir, exist_ok=True)
            rc, errors, final_file, had_cookie_fallback = self._run_with_cookie_recovery(
                runner_cmd,
                url,
                profile,
                save_dir,
                ffmpeg_bin,
                js_runtimes,
                console,
                is_playlist=is_playlist,
                subtitles=subtitles,
                cookies_browser=cookies_browser,
                cookies_file=cookies_file,
                proxy_url=proxy_url,
            )
            if rc == 130:
                return rc

            if rc == 0:
                size_line = ""
                if final_file and os.path.isfile(final_file):
                    size_mb = os.path.getsize(final_file) / (1024 * 1024)
                    size_line = f"  [bold #E0E0E0]File:[/bold #E0E0E0]   [bold #00FF00]{escape(final_file)}[/bold #00FF00] [dim]({size_mb:.2f} MB)[/dim]\n"
                else:
                    size_line = f"  [bold #E0E0E0]Dir:[/bold #E0E0E0]    [dim]{escape(save_dir)}[/dim]\n"
                card = (
                    "[bold #00FF00]✅ Saved[/bold #00FF00]\n"
                    f"{size_line}"
                    f"  [bold #E0E0E0]Mode:[/bold #E0E0E0]   [bold #FF9800]{profile.label}[/bold #FF9800]  "
                    f"[dim](yt-dlp {escape(ytdlp_ver)} · {'FFmpeg' if ffmpeg_bin else 'native stream'})[/dim]"
                )
                console.print()
                console.print(Panel(card, border_style="#10b981", box=box.ROUNDED, expand=False))
                return 0

            has_hint = self._print_diagnostics(
                errors,
                js_runtimes,
                console,
                had_cookie_fallback=had_cookie_fallback,
            )
            print_error("Media fetch failed. See details above." if has_hint else "Media fetch failed.")
            return 1
        except Exception as exc:
            print_error(f"Media engine execution failed: {escape(str(exc))}")
            return 1
