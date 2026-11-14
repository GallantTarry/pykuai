# -*- coding: utf-8 -*-
"""
PyKuai XP Playground — Native-Style Internet Explorer 6 Engine (`pykuai.arcade.ie6`).

Drives a local Chromium/Edge headless browser over CDP (`pykuai.core.yt_auth`) inside a
Windows XP IE6 CRT window:
  • Pure user bookmarks (`~/.pykuai/ie6_bookmarks.json`, no pre-pinned third-party portals).
  • Direct URL & domain navigation (never hijacking domains to search portals), with automatic `http://`
    fallback when bare domains lack HTTPS.
  • Retina `2x` HiDPI CDP capture + `UnsharpMask` + lossless 24-bit TrueColor Half-Block (`▀`)
    square-pixel rendering (`render_image_to_halfblock`) with 1x–4x zoom, panning, direct mouse
    click/wheel forwarding, and live keyboard input + secondary text-reader mode.
"""
from __future__ import annotations

import base64
import collections
from dataclasses import dataclass, field
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import queue
import re
import select
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Optional
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageFilter
from rich.text import Text

from pykuai.core.yt_auth import (
    _CdpClient,
    _fetch_cdp_version_ws,
    _pick_free_port,
    _terminate_browser,
    find_chromium_browser,
)

IE6_BOOKMARKS_PATH = Path.home() / ".pykuai" / "ie6_bookmarks.json"
ABOUT_HOME_URL = "about:home"
IE6_VIEWPORT_W = 880
IE6_VIEWPORT_H = 520
IE6_DEVICE_SCALE = 2


@dataclass(frozen=True)
class TerminalGraphicsInfo:
    """Detected terminal pixel-projection capabilities and single-cell pixel size."""

    sixel_supported: bool = False
    cell_w: int = 10
    cell_h: int = 20
    source: str = "fallback"


_CACHED_TERM_GFX: Optional[TerminalGraphicsInfo] = None


def _parse_terminal_caps_reply(reply: str) -> TerminalGraphicsInfo:
    cell_w, cell_h = 10, 20
    m_size = re.search(r"\x1b\[6;(\d+);(\d+)t", reply)
    if m_size:
        parsed_h = int(m_size.group(1))
        parsed_w = int(m_size.group(2))
        if 8 <= parsed_h <= 64 and 4 <= parsed_w <= 36:
            cell_h, cell_w = parsed_h, parsed_w

    sixel_ok = False
    m_da = re.search(r"\x1b\[\?([0-9;]+)c", reply)
    if m_da:
        attrs = m_da.group(1).split(";")
        sixel_ok = "4" in attrs
    return TerminalGraphicsInfo(
        sixel_supported=sixel_ok,
        cell_w=cell_w,
        cell_h=cell_h,
        source="da1+csi16t" if sixel_ok else "no-sixel-da1",
    )


def _probe_win32_vt(timeout: float) -> str:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    STD_INPUT_HANDLE = -10
    STD_OUTPUT_HANDLE = -11
    ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
    WAIT_OBJECT_0 = 0
    KEY_EVENT = 0x0001

    class COORD(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class UCHAR(ctypes.Union):
        _fields_ = [("UnicodeChar", wintypes.WCHAR), ("AsciiChar", ctypes.c_char)]

    class KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [
            ("bKeyDown", wintypes.BOOL),
            ("wRepeatCount", wintypes.WORD),
            ("wVirtualKeyCode", wintypes.WORD),
            ("wVirtualScanCode", wintypes.WORD),
            ("uChar", UCHAR),
            ("dwControlKeyState", wintypes.DWORD),
        ]

    class EVENT_UNION(ctypes.Union):
        _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("_pad", ctypes.c_byte * 16)]

    class INPUT_RECORD(ctypes.Structure):
        _fields_ = [("EventType", wintypes.WORD), ("Event", EVENT_UNION)]

    h_in = k32.GetStdHandle(STD_INPUT_HANDLE)
    h_out = k32.GetStdHandle(STD_OUTPUT_HANDLE)
    mode_in = wintypes.DWORD(0)
    mode_out = wintypes.DWORD(0)
    if not k32.GetConsoleMode(h_in, ctypes.byref(mode_in)) or not k32.GetConsoleMode(h_out, ctypes.byref(mode_out)):
        return ""

    old_in = mode_in.value
    old_out = mode_out.value
    buf_chars: list[str] = []
    try:
        k32.SetConsoleMode(h_out, old_out | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        k32.SetConsoleMode(h_in, ENABLE_VIRTUAL_TERMINAL_INPUT)
        probe_bytes = b"\x1b[c\x1b[16t"
        written = wintypes.DWORD(0)
        k32.WriteFile(h_out, probe_bytes, len(probe_bytes), ctypes.byref(written), None)

        records = (INPUT_RECORD * 128)()
        read_n = wintypes.DWORD(0)
        deadline = time.monotonic() + timeout
        got_da = False
        got_size = False
        while time.monotonic() < deadline:
            rem_ms = max(5, int((deadline - time.monotonic()) * 1000))
            if k32.WaitForSingleObject(h_in, rem_ms) != WAIT_OBJECT_0:
                break
            if not k32.ReadConsoleInputW(h_in, records, 128, ctypes.byref(read_n)):
                break
            for i in range(read_n.value):
                rec = records[i]
                if rec.EventType != KEY_EVENT:
                    continue
                ke = rec.Event.KeyEvent
                if not ke.bKeyDown:
                    continue
                ch = ke.uChar.UnicodeChar
                if ch and ch != "\x00":
                    buf_chars.append(ch)
                    if ch == "c":
                        got_da = True
                    elif ch == "t":
                        got_size = True
            if got_da and got_size:
                break
    finally:
        k32.SetConsoleMode(h_in, old_in)
        k32.SetConsoleMode(h_out, old_out)
    return "".join(buf_chars)


def _probe_posix_vt(timeout: float) -> str:
    import termios
    import tty

    fd = sys.__stdin__.fileno()
    old_attrs = termios.tcgetattr(fd)
    chunks: list[str] = []
    try:
        tty.setraw(fd)
        sys.__stdout__.write("\x1b[c\x1b[16t")
        sys.__stdout__.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rem = max(0.005, deadline - time.monotonic())
            rlist, _, _ = select.select([fd], [], [], rem)
            if not rlist:
                break
            part = os.read(fd, 512).decode("utf-8", errors="ignore")
            if not part:
                break
            chunks.append(part)
            joined = "".join(chunks)
            if "c" in joined and "t" in joined:
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
    return "".join(chunks)


def probe_terminal_sixel_info(timeout: float = 0.14) -> TerminalGraphicsInfo:
    """
    Detect whether the active interactive terminal supports Sixel graphics (`CSI c` attr 4)
    and query its physical character-cell pixel size (`CSI 16t`), safely caching the result.
    Must be invoked before Textual enters raw application mode.
    """
    global _CACHED_TERM_GFX
    env_flag = (os.environ.get("PYKUAI_SIXEL") or "").strip().lower()
    if env_flag in ("0", "false", "no", "off"):
        info = TerminalGraphicsInfo(False, 10, 20, "env-disabled")
        _CACHED_TERM_GFX = info
        return info

    is_tty = bool(
        sys.__stdin__ is not None
        and sys.__stdout__ is not None
        and sys.__stdin__.isatty()
        and sys.__stdout__.isatty()
    )
    if not is_tty:
        info = TerminalGraphicsInfo(env_flag in ("1", "true", "yes", "on"), 10, 20, "non-tty")
        _CACHED_TERM_GFX = info
        return info

    reply = ""
    try:
        reply = _probe_win32_vt(timeout) if sys.platform == "win32" else _probe_posix_vt(timeout)
    except Exception:
        reply = ""

    info = _parse_terminal_caps_reply(reply)
    if env_flag in ("1", "true", "yes", "on") and not info.sixel_supported:
        info = TerminalGraphicsInfo(True, info.cell_w, info.cell_h, "env-forced")
    _CACHED_TERM_GFX = info
    return info


def get_cached_terminal_sixel_info() -> TerminalGraphicsInfo:
    """Return cached terminal graphics capability info (probing once if still uninitialized)."""
    if _CACHED_TERM_GFX is not None:
        return _CACHED_TERM_GFX
    return probe_terminal_sixel_info()

_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?(?:[/?#].*)?$")
_DOMAIN_HEAD_RE = re.compile(
    r"^(?:localhost(?::\d{1,5})?|[^\s/?#.]+\.[^\s/?#]+(?::\d{1,5})?)(?:[/?#].*)?$",
    re.IGNORECASE,
)

_HEX_STR_CACHE: dict[int, str] = {}


def _hex_color(rgb_int: int) -> str:
    s = _HEX_STR_CACHE.get(rgb_int)
    if s is None:
        s = f"#{rgb_int:06x}"
        if len(_HEX_STR_CACHE) < 32768:
            _HEX_STR_CACHE[rgb_int] = s
    return s


_STEALTH_NEW_DOC_JS = """
(() => {
    try {
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    } catch (e) {}
    const origOpen = window.open;
    window.open = function(url) {
        if (url) {
            try { location.href = new URL(String(url), location.href).href; }
            catch (e) { location.href = String(url); }
            return window;
        }
        return origOpen ? origOpen.apply(this, arguments) : window;
    };
    document.addEventListener('click', function(ev) {
        const tgt = ev.target && ev.target.closest ? ev.target.closest('a[target]') : null;
        if (tgt && String(tgt.target || '').toLowerCase() === '_blank') {
            tgt.target = '_self';
        }
    }, true);
})();
"""

_EXTRACT_DOM_JS = r"""
(() => {
    try {
        const title = String(document.title || location.href || '').trim();
        const url = String(location.href || '');
        const lines = [];
        const rawText = (document.body && document.body.innerText) ? document.body.innerText : '';
        const seenLine = new Set();
        for (const raw of rawText.split(/\r?\n/)) {
            const s = raw.replace(/\s+/g, ' ').trim();
            if (s.length < 2) continue;
            if (seenLine.has(s)) continue;
            seenLine.add(s);
            lines.push(s.slice(0, 220));
            if (lines.length >= 65) break;
        }

        const links = [];
        const seenHref = new Set();
        const anchors = document.querySelectorAll('a[href]');
        for (const a of anchors) {
            const rawHref = (a.getAttribute('href') || '').trim();
            if (!rawHref || rawHref.startsWith('#') || rawHref.toLowerCase().startsWith('javascript:')) continue;
            let href = '';
            try { href = new URL(a.href, location.href).href; } catch (e) { continue; }
            if (!href.startsWith('http://') && !href.startsWith('https://')) continue;
            const txt = (a.innerText || a.getAttribute('title') || a.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
            if (txt.length < 2) continue;
            const rect = a.getBoundingClientRect();
            if (rect.width <= 0 && rect.height <= 0) continue;
            const dedupKey = href + '|' + txt.slice(0, 32);
            if (seenHref.has(dedupKey)) continue;
            seenHref.add(dedupKey);
            links.push({text: txt.slice(0, 72), href: href});
            if (links.length >= 55) break;
        }

        const inputs = [];
        const fields = document.querySelectorAll('input, textarea');
        for (let i = 0; i < fields.length; i++) {
            const el = fields[i];
            const typ = (el.getAttribute('type') || 'text').toLowerCase();
            if (!['text', 'search', 'url', ''].includes(typ) && el.tagName !== 'TEXTAREA') continue;
            const rect = el.getBoundingClientRect();
            if (rect.width < 40 || rect.height < 12) continue;
            el.setAttribute('data-pykuai-idx', String(inputs.length));
            inputs.push({
                idx: inputs.length,
                placeholder: String(el.getAttribute('placeholder') || el.getAttribute('name') || 'Input').slice(0, 48),
                value: String(el.value || '').slice(0, 120)
            });
            if (inputs.length >= 3) break;
        }

        return JSON.stringify({
            ready: document.readyState,
            url: url,
            title: title,
            lines: lines,
            links: links,
            inputs: inputs
        });
    } catch (err) {
        return JSON.stringify({error: String(err)});
    }
})()
"""


@dataclass
class PageLink:
    """Single clickable hyperlink extracted from the rendered page."""

    text: str
    href: str


@dataclass
class PageInput:
    """Single visible search/text input box detected on the page."""

    idx: int
    placeholder: str
    value: str


@dataclass
class PageSnapshot:
    """Immutable view snapshot shared between the background browser worker and Textual UI."""

    seq: int = 0
    url: str = ABOUT_HOME_URL
    title: str = "Microsoft Internet Explorer"
    loading: bool = False
    status_text: str = "Done"
    backend_label: str = "Ready"
    error: str = ""
    can_back: bool = False
    can_forward: bool = False
    lines: list[str] = field(default_factory=list)
    links: list[PageLink] = field(default_factory=list)
    inputs: list[PageInput] = field(default_factory=list)
    shot_image: Optional[Image.Image] = None
    shot_seq: int = 0
    sixel_payload: str = ""
    sixel_size: tuple[int, int] = (0, 0)
    sixel_bounds: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    sixel_key: tuple[object, ...] = ()
    sixel_shot_seq: int = 0


def load_bookmarks() -> list[dict[str, str]]:
    """Load user-saved IE6 bookmarks from `~/.pykuai/ie6_bookmarks.json`."""
    try:
        if IE6_BOOKMARKS_PATH.is_file():
            raw = json.loads(IE6_BOOKMARKS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                cleaned: list[dict[str, str]] = []
                seen: set[str] = set()
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url") or "").strip()
                    label = str(item.get("label") or url).strip()
                    if url and url not in seen:
                        seen.add(url)
                        cleaned.append({"label": label[:34], "url": url})
                return cleaned
    except Exception:
        pass
    return []


def save_bookmarks(bookmarks: list[dict[str, str]]) -> None:
    """Persist IE6 bookmarks atomically to `~/.pykuai/ie6_bookmarks.json`."""
    try:
        IE6_BOOKMARKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=str(IE6_BOOKMARKS_PATH.parent),
            prefix=".ie6_bm_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                json.dump(bookmarks, fh, ensure_ascii=False, indent=2)
                fh.flush()
            os.replace(tmp_name, IE6_BOOKMARKS_PATH)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    except Exception:
        pass


def _normalize_proxy_url(raw: str) -> str:
    """Normalize proxy URL schemes into syntax accepted by Chromium `--proxy-server`."""
    val = (raw or "").strip()
    if val.lower().startswith("socks5h://"):
        return "socks5://" + val[10:]
    if val.lower().startswith("socks4a://"):
        return "socks4://" + val[10:]
    return val


def detect_local_proxy_flags() -> tuple[tuple[str, ...], str]:
    """
    Mirror the user's current OS/environment proxy settings for headless Chromium.

    Checks terminal proxy environment variables (`ALL_PROXY`, `HTTPS_PROXY`, `HTTP_PROXY`)
    first so CLI proxy sessions work on Windows too, then inspects Windows WinINET registry
    (`ProxyEnable`, `ProxyServer`, `AutoConfigURL`, `ProxyOverride`) live so toggling a local
    proxy client takes effect without restarting PyKuai.
    """
    env_all = _normalize_proxy_url(os.environ.get("ALL_PROXY") or os.environ.get("all_proxy") or "")
    env_https = _normalize_proxy_url(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "")
    env_http = _normalize_proxy_url(os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or "")
    env_no_proxy = (os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or "").strip()

    flags: list[str] = []
    if env_all or env_https or env_http:
        if env_all and not env_http and not env_https:
            proxy_spec = env_all
        elif env_http and env_https and env_http == env_https:
            proxy_spec = env_http
        else:
            parts: list[str] = []
            if env_http:
                parts.append(f"http={env_http}")
            if env_https:
                parts.append(f"https={env_https}")
            if env_all and (not env_http or not env_https):
                parts.append(env_all)
            proxy_spec = ";".join(parts)
        flags.append(f"--proxy-server={proxy_spec}")
        bypass = env_no_proxy.replace(",", ";") if env_no_proxy else "localhost;127.0.0.1;<local>"
        flags.append(f"--proxy-bypass-list={bypass}")
        return tuple(flags), "|".join(flags)

    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            ) as reg_key:
                try:
                    enabled = int(winreg.QueryValueEx(reg_key, "ProxyEnable")[0] or 0)
                except OSError:
                    enabled = 0
                try:
                    server = _normalize_proxy_url(str(winreg.QueryValueEx(reg_key, "ProxyServer")[0] or ""))
                except OSError:
                    server = ""
                try:
                    override = str(winreg.QueryValueEx(reg_key, "ProxyOverride")[0] or "").strip()
                except OSError:
                    override = ""
                try:
                    pac_url = str(winreg.QueryValueEx(reg_key, "AutoConfigURL")[0] or "").strip()
                except OSError:
                    pac_url = ""

            if enabled and server:
                flags.append(f"--proxy-server={server}")
                flags.append(f"--proxy-bypass-list={override or 'localhost;127.0.0.1;<local>'}")
            elif pac_url:
                flags.append(f"--proxy-pac-url={pac_url}")
            return tuple(flags), f"wininet:{enabled}:{server}:{override}:{pac_url}"
        except Exception:
            pass

    return (), "direct"


def resolve_navigation_target(raw_text: str) -> tuple[str, bool]:
    """
    Resolve address-bar input into `(url, allow_http_fallback)`.

    Rules (direct-navigation first, never redirecting domains/URLs to a search engine):
      • Empty / `about:home` / `about:blank` -> built-in IE6 start page
      • Explicit scheme (`http://`, `https://`, `file://`, `about:`) -> navigate directly
      • Bare `localhost`, IPv4, `host:port`, or any domain (`example.com`, `sub.site.cn/path?q=1`)
        -> prepend `http://` (localhost/IPv4) or `https://` (domains, with automatic `http://` fallback)
      • Any other bare host token without spaces -> treat as direct hostname (`https://<token>`)
      • Multi-word query with spaces (or `? <query>`) -> Baidu search
    """
    text = (raw_text or "").strip().strip('"').strip("'")
    if not text or text.lower() in ("about:home", "about:blank"):
        return ABOUT_HOME_URL, False

    lower = text.lower()
    if lower.startswith("about:") or _SCHEME_RE.match(text):
        return text, False

    # Recover common missing-colon typos like `https//example.com` or `http//example.com`
    if lower.startswith("https//"):
        return "https://" + text[7:], True
    if lower.startswith("http//"):
        return "http://" + text[6:], False

    if lower.startswith("localhost") or _IPV4_RE.match(text):
        return f"http://{text}", False

    head = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].strip()
    if _DOMAIN_HEAD_RE.match(head):
        return f"https://{text}", True

    if text.startswith("? ") and len(text) > 2:
        return "https://www.baidu.com/s?wd=" + urllib.parse.quote_plus(text[2:].strip()), False

    if " " not in text and not any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return f"https://{text}", True

    return "https://www.baidu.com/s?wd=" + urllib.parse.quote_plus(text), False


class _SimpleHtmlParser(HTMLParser):
    """Lightweight HTML parser used when no local Chromium/Edge executable is found."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self._skip_depth = 0
        self._in_title = False
        self._in_a = False
        self._cur_href = ""
        self._a_buf: list[str] = []
        self._text_buf: list[str] = []
        self.title = ""
        self.lines: list[str] = []
        self.links: list[PageLink] = []
        self._seen_links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag_l = tag.lower()
        if tag_l in ("script", "style", "noscript", "svg"):
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if tag_l == "title":
            self._in_title = True
        elif tag_l == "a":
            attr_map = dict(attrs)
            href = (attr_map.get("href") or "").strip()
            if href and not href.startswith("#") and not href.lower().startswith("javascript:"):
                resolved = urllib.parse.urljoin(self.base_url, href)
                if resolved.startswith(("http://", "https://")):
                    self._in_a = True
                    self._cur_href = resolved
                    self._a_buf = []
        elif tag_l in ("p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr"):
            self._flush_text()

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l in ("script", "style", "noscript", "svg"):
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag_l == "title":
            self._in_title = False
        elif tag_l == "a" and self._in_a:
            txt = " ".join("".join(self._a_buf).split())[:72]
            if len(txt) >= 2 and self._cur_href not in self._seen_links and len(self.links) < 55:
                self._seen_links.add(self._cur_href)
                self.links.append(PageLink(text=txt, href=self._cur_href))
            self._in_a = False
            self._cur_href = ""
            self._a_buf = []
        elif tag_l in ("p", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self._flush_text()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title:
            self.title += data
            return
        if self._in_a:
            self._a_buf.append(data)
        self._text_buf.append(data)

    def _flush_text(self) -> None:
        if not self._text_buf:
            return
        cleaned = " ".join("".join(self._text_buf).split())
        self._text_buf.clear()
        if len(cleaned) >= 2 and len(self.lines) < 65:
            self.lines.append(cleaned[:220])


def build_home_snapshot(bookmarks: list[dict[str, str]], seq: int = 1) -> PageSnapshot:
    """Build the clean built-in IE6 Start Page snapshot."""
    links = [PageLink(text=bm["label"], href=bm["url"]) for bm in bookmarks]
    return PageSnapshot(
        seq=seq,
        url=ABOUT_HOME_URL,
        title="Microsoft Internet Explorer",
        loading=False,
        status_text="Ready · Enter any URL or domain in the Address bar above",
        backend_label="Internet Explorer 6",
        lines=[
            "Microsoft Internet Explorer 6 (Windows XP Desktop)",
            "• Enter any full URL or domain in the Address bar (e.g. github.com, example.org, 127.0.0.1:8080).",
            "• Click anywhere inside the live browser viewport, scroll with mouse wheel, or type directly.",
            "• Use [🔍 1x..4x] to zoom into HiDPI text, [★ Save] to bookmark, and [Txt] for clean reader mode.",
        ],
        links=links,
        inputs=[],
        shot_image=None,
        shot_seq=0,
    )


def _pack_halfblock_buffer(pbuf: list[int], cols: int, rows: int) -> Text:
    """
    Pack a `(cols, rows * 2)` RGB int grid into `rows` lines of lossless 24-bit `▀` half-blocks.
    Merges adjacent identical `(glyph, style)` runs to keep Textual rendering fast and tear-free.
    """
    text = Text(no_wrap=True)
    append = text.append
    for r in range(rows):
        top_row = (r * 2) * cols
        bot_row = top_row + cols
        run_chars: list[str] = []
        cur_style: Optional[str] = None
        for x in range(cols):
            ct = pbuf[top_row + x]
            cb = pbuf[bot_row + x]
            if ct == cb:
                glyph = "█"
                style = _hex_color(ct)
            else:
                glyph = "▀"
                style = f"{_hex_color(ct)} on {_hex_color(cb)}"
            if style == cur_style:
                run_chars.append(glyph)
            else:
                if run_chars and cur_style is not None:
                    append("".join(run_chars), style=cur_style)
                    run_chars.clear()
                cur_style = style
                run_chars.append(glyph)
        if run_chars and cur_style is not None:
            append("".join(run_chars), style=cur_style)
        if r + 1 < rows:
            append("\n")
    return text


def render_home_pixel_canvas(cols: int, rows: int, bookmarks: Optional[list[dict[str, str]]] = None) -> Text:
    """
    Render a crisp high-resolution Windows XP Internet Explorer 6 Start Page into `cols x rows`
    square Half-Block (`▀`) cells when `about:home` is open in Live View mode.
    """
    w = max(20, cols)
    h = max(12, rows * 2)
    bg_white = (248, 250, 253)
    pbuf = [((bg_white[0] << 16) | (bg_white[1] << 8) | bg_white[2])] * (w * h)

    # Luna top accent ribbon inside page
    hdr_h = max(8, h // 5)
    for y in range(hdr_h):
        t = y / max(1, hdr_h - 1)
        r = int(12 + 34 * t)
        g = int(78 + 70 * t)
        b = int(206 + 38 * t)
        c = (r << 16) | (g << 8) | b
        row = y * w
        for x in range(w):
            pbuf[row + x] = c
    gold_line = (245 << 16) | (158 << 8) | 11
    for x in range(w):
        pbuf[hdr_h * w + x] = gold_line

    # Centered classic IE6 `'e'` globe emblem with soft shadow & diagonal golden swoosh
    cx = w // 2
    cy = max(hdr_h + 10, int(h * 0.52))
    rad = max(8, min(w // 6, (h - hdr_h) // 3))
    c_globe = (24 << 16) | (124 << 8) | 232
    c_hi = (125 << 16) | (211 << 8) | 252
    c_e = (248 << 16) | (250 << 8) | 252
    c_gold = (250 << 16) | (204 << 8) | 21
    c_gold_dk = (217 << 16) | (119 << 8) | 6

    for y in range(max(hdr_h + 2, cy - rad - 3), min(h - 2, cy + rad + 4)):
        dy = (y - cy) / max(1.0, rad)
        row = y * w
        for x in range(max(2, cx - rad - 6), min(w - 2, cx + rad + 7)):
            dx = (x - cx) / max(1.0, rad)
            dist = dx * dx + dy * dy
            ring_u = dx * 0.62 + dy * 0.92
            ring_v = dx * 0.85 - dy * 0.58
            on_ring = (abs(ring_u) <= 0.16 and 0.68 <= abs(ring_v) <= 1.28) or (
                0.78 <= (ring_u * ring_u + (ring_v * 0.78) ** 2) <= 1.15 and dy > -0.25
            )
            if on_ring and ring_u + dy > -0.15:
                pbuf[row + x] = c_gold if dy < 0.25 else c_gold_dk
            elif dist <= 0.88:
                # Carve crisp letter 'e' inside the globe
                in_bar = abs(dy) <= 0.15 and -0.52 <= dx <= 0.54
                in_c_outer = 0.26 <= dist <= 0.56 and not (dx > 0.18 and 0.08 < dy < 0.36)
                if in_bar or in_c_outer:
                    pbuf[row + x] = c_e
                elif dx < -0.12 and dy < -0.18:
                    pbuf[row + x] = c_hi
                else:
                    pbuf[row + x] = c_globe
            elif on_ring:
                pbuf[row + x] = c_gold_dk

    # Subtle bottom card bar hinting where saved favorites appear
    card_w = min(w - 8, 52)
    bx0 = (w - card_w) // 2
    by0 = min(h - 6, cy + rad + 5)
    c_card = (226 << 16) | (232 << 8) | 240
    c_accent = (37 << 16) | (99 << 8) | 235
    if by0 + 3 < h:
        for y in range(by0, by0 + 3):
            row = y * w
            for x in range(bx0, bx0 + card_w):
                pbuf[row + x] = c_card if y != by0 else c_accent

    _ = bookmarks
    return _pack_halfblock_buffer(pbuf, w, rows)


def _crop_for_zoom(
    img: Image.Image,
    pix_w: int,
    pix_h: int,
    zoom: int = 1,
    pan_x: float = 0.5,
    pan_y: float = 0.5,
    sharpen: bool = True,
    resampling: Image.Resampling = Image.Resampling.LANCZOS,
) -> tuple[Image.Image, tuple[float, float, float, float]]:
    """Crop/pan/resize a browser screenshot to `(pix_w, pix_h)` cleanly."""
    zoom = max(1, min(4, int(zoom)))
    half_span = 0.5 / zoom
    cx = min(1.0 - half_span, max(half_span, pan_x))
    cy = min(1.0 - half_span, max(half_span, pan_y))
    u0, v0 = cx - half_span, cy - half_span
    u1, v1 = cx + half_span, cy + half_span

    iw, ih = img.size
    crop_box = (
        max(0, int(round(u0 * iw))),
        max(0, int(round(v0 * ih))),
        min(iw, int(round(u1 * iw))),
        min(ih, int(round(v1 * ih))),
    )
    cropped = img if zoom == 1 else img.crop(crop_box)
    if cropped.size == (pix_w, pix_h) and cropped.mode == "RGB":
        out_img = cropped
    else:
        resized = cropped.resize((pix_w, pix_h), resampling).convert("RGB")
        out_img = (
            resized.filter(ImageFilter.UnsharpMask(radius=0.7, percent=85, threshold=2))
            if sharpen
            else resized
        )
    return out_img, (u0, v0, u1, v1)


def render_image_to_halfblock(
    img: Image.Image,
    cols: int,
    rows: int,
    zoom: int = 1,
    pan_x: float = 0.5,
    pan_y: float = 0.5,
) -> tuple[Text, tuple[float, float, float, float]]:
    """
    Crop/zoom a HiDPI browser screenshot, downsample with Lanczos + crisp UnsharpMask,
    and pack into lossless 24-bit TrueColor `▀` half-blocks (`cols x rows` terminal cells,
    representing `cols x (rows*2)` 1:1 square pixels).
    """
    cols = max(20, int(cols))
    rows = max(8, int(rows))
    pix_w = cols
    pix_h = rows * 2
    sharpened, bounds = _crop_for_zoom(img, pix_w, pix_h, zoom=zoom, pan_x=pan_x, pan_y=pan_y, sharpen=True)

    mv = memoryview(sharpened.tobytes())
    pbuf = [
        (mv[i] << 16) | (mv[i + 1] << 8) | mv[i + 2]
        for i in range(0, len(mv), 3)
    ]
    return _pack_halfblock_buffer(pbuf, pix_w, rows), bounds


def _append_sixel_rle(append: Any, code: int, count: int) -> None:
    ch = chr(code)
    if count >= 4:
        append(f"!{count}{ch}")
    elif count == 3:
        append(ch * 3)
    elif count == 2:
        append(ch * 2)
    else:
        append(ch)


_SIXEL_RLE_RE = re.compile(rb"([\x3f-\x7e])\1{3,}")
_SIXEL_RLE_PREFIX: tuple[bytes, ...] = tuple(f"!{i}".encode("ascii") for i in range(4096))


def _sixel_rle_sub(m: re.Match[bytes]) -> bytes:
    grp = m.group(0)
    n = len(grp)
    pref = _SIXEL_RLE_PREFIX[n] if n < 4096 else f"!{n}".encode("ascii")
    return pref + grp[:1]


def _encode_sixel_numpy(q_img: Image.Image, max_colors: int) -> str:
    import numpy as np

    w, h = q_img.size
    pal = q_img.getpalette() or []
    arr = np.asarray(q_img, dtype=np.uint8)
    used_colors = np.flatnonzero(np.bincount(arr.ravel(), minlength=max(1, max_colors)))

    hdr: list[bytes] = [f'\x1bP0;0;0q"1;1;{w};{h}'.encode("ascii")]
    for c in used_colors.tolist():
        if c * 3 + 2 < len(pal):
            r = round(pal[c * 3] * 100 / 255)
            g = round(pal[c * 3 + 1] * 100 / 255)
            b = round(pal[c * 3 + 2] * 100 / 255)
            hdr.append(f"#{c};2;{r};{g};{b}".encode("ascii"))

    pad_h = (6 - (h % 6)) % 6
    if pad_h:
        arr = np.vstack([arr, np.zeros((pad_h, w), dtype=np.uint8)])

    nbands = arr.shape[0] // 6
    n_slots = max(max_colors, int(used_colors[-1]) + 1 if used_colors.size else 1)
    bm = np.zeros((n_slots, w), dtype=np.uint8)
    cols = np.arange(w)
    bits_lut = (1, 2, 4, 8, 16, 32)
    out = bytearray(b"".join(hdr))
    rle_sub = _SIXEL_RLE_RE.sub

    for b_idx in range(nbands):
        band = arr[b_idx * 6 : (b_idx + 1) * 6]
        active_h = 6 if (not pad_h or b_idx + 1 < nbands) else (6 - pad_h)
        bm.fill(0)
        for dr in range(active_h):
            bm[band[dr], cols] |= bits_lut[dr]
        band_cs = np.flatnonzero(bm.any(axis=1))
        rows_b = (bm[band_cs] + 63).tobytes()
        first_c = True
        for idx, c in enumerate(band_cs.tolist()):
            row_raw = rows_b[idx * w : (idx + 1) * w].rstrip(b"?")
            if not row_raw:
                continue
            if not first_c:
                out.append(36)
            first_c = False
            out.extend(f"#{c}".encode("ascii"))
            out.extend(rle_sub(_sixel_rle_sub, row_raw))
        if b_idx + 1 < nbands:
            out.append(45)
    out.extend(b"\x1b\\")
    return bytes(out).decode("ascii")


def _encode_sixel_stdlib(q_img: Image.Image) -> str:
    w, h = q_img.size
    pal = q_img.getpalette() or []
    raw = memoryview(q_img.tobytes())
    used = sorted(set(raw))

    parts = [f'\x1bP0;0;0q"1;1;{w};{h}']
    append = parts.append
    for c in used:
        if c * 3 + 2 < len(pal):
            r = round(pal[c * 3] * 100 / 255)
            g = round(pal[c * 3 + 1] * 100 / 255)
            b = round(pal[c * 3 + 2] * 100 / 255)
            append(f"#{c};2;{r};{g};{b}")

    nbands = (h + 5) // 6
    for b_idx in range(nbands):
        y0 = b_idx * 6
        rows_slice = [raw[(y0 + dr) * w : (y0 + dr + 1) * w] for dr in range(6) if (y0 + dr) < h]
        active_h = len(rows_slice)
        band_colors = sorted({px for r_mv in rows_slice for px in r_mv})
        first_c = True
        for c in band_colors:
            cols_bits = bytearray(w)
            for dr in range(active_h):
                bit = 1 << dr
                r_mv = rows_slice[dr]
                for x in range(w):
                    if r_mv[x] == c:
                        cols_bits[x] |= bit
            last_x = w - 1
            while last_x >= 0 and cols_bits[last_x] == 0:
                last_x -= 1
            if last_x < 0:
                continue
            if not first_c:
                append("$")
            first_c = False
            append(f"#{c}")
            x = 0
            while x <= last_x:
                val = cols_bits[x]
                nxt = x + 1
                while nxt <= last_x and cols_bits[nxt] == val:
                    nxt += 1
                _append_sixel_rle(append, 63 + val, nxt - x)
                x = nxt
        if b_idx + 1 < nbands:
            append("-")
    append("\x1b\\")
    return "".join(parts)


def encode_image_to_sixel(rgb_img: Image.Image, max_colors: int = 256, *, dither: bool = False) -> str:
    """Encode an RGB PIL Image into a compact, fast DEC Sixel DCS string."""
    q = rgb_img.quantize(
        colors=max_colors,
        method=Image.Quantize.FASTOCTREE,
        dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE,
    )
    try:
        return _encode_sixel_numpy(q, max_colors=max_colors)
    except ImportError:
        return _encode_sixel_stdlib(q)


def render_image_to_sixel(
    img: Image.Image,
    target_w: int,
    target_h: int,
    zoom: int = 1,
    pan_x: float = 0.5,
    pan_y: float = 0.5,
    max_colors: int = 128,
    dither: bool = False,
) -> tuple[str, tuple[float, float, float, float], tuple[int, int]]:
    """
    Crop/zoom/scale a browser screenshot cleanly into exact `(sixel_w, sixel_h)` native
    terminal pixels (height floored to multiple of 6) and return `(sixel_dcs, crop_bounds, (sixel_w, sixel_h))`.
    """
    sixel_w = max(80, int(target_w))
    sixel_h = max(24, (int(target_h) // 6) * 6)
    resampling = Image.Resampling.BILINEAR if zoom == 1 else Image.Resampling.BICUBIC
    frame_img, bounds = _crop_for_zoom(
        img,
        sixel_w,
        sixel_h,
        zoom=zoom,
        pan_x=pan_x,
        pan_y=pan_y,
        sharpen=False,
        resampling=resampling,
    )
    return encode_image_to_sixel(frame_img, max_colors=max_colors, dither=dither), bounds, (sixel_w, sixel_h)


class _StreamingCdpClient(_CdpClient):
    """CDP WebSocket client that queues async push events (e.g. Screencast) instead of dropping them."""

    def __init__(self, ws_url: str, *, timeout: float = 18.0) -> None:
        super().__init__(ws_url, timeout=timeout)
        self._events: collections.deque[dict[str, Any]] = collections.deque()

    def call(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        req_id = self._next_id
        self._next_id += 1
        payload = json.dumps({"id": req_id, "method": method, "params": params or {}}).encode("utf-8")
        self._send_frame(0x1, payload)
        while True:
            msg = json.loads(self._recv_text_message())
            if msg.get("id") != req_id:
                if "method" in msg:
                    self._events.append(msg)
                continue
            if "error" in msg:
                raise RuntimeError(f"CDP error for {method}: {msg['error']}")
            return msg.get("result") or {}

    def notify(self, method: str, params: Optional[dict[str, Any]] = None) -> None:
        """Send a CDP command without blocking for its acknowledgement."""
        req_id = self._next_id
        self._next_id += 1
        payload = json.dumps({"id": req_id, "method": method, "params": params or {}}).encode("utf-8")
        self._send_frame(0x1, payload)

    def poll_events(self, wait_s: float = 0.0) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        while self._events:
            out.append(self._events.popleft())
        while True:
            if not self._buf:
                rlist, _, _ = select.select([self._sock], [], [], wait_s if not out else 0.0)
                if not rlist:
                    break
            msg = json.loads(self._recv_text_message())
            if "method" in msg:
                out.append(msg)
        return out


class IE6BrowserSession:
    """
    Non-blocking Chromium/Edge CDP browser worker for XP Playground's native-style IE6 window.
    """

    def __init__(self, initial_bookmarks: Optional[list[dict[str, str]]] = None) -> None:
        self._lock = threading.Lock()
        self._cmd_q: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self._stop_event = threading.Event()
        self._bookmarks = initial_bookmarks if initial_bookmarks is not None else load_bookmarks()
        self._snapshot = build_home_snapshot(self._bookmarks, seq=1)
        self._seq = 1
        self._shot_seq = 0
        self._back_stack: list[str] = []
        self._fwd_stack: list[str] = []
        self._current_real_url = ABOUT_HOME_URL

        self._proc: Optional[subprocess.Popen[bytes]] = None
        self._cdp: Optional[_StreamingCdpClient] = None
        self._tmp_profile: Optional[tempfile.TemporaryDirectory[str]] = None
        self._browser_label = ""
        self._proxy_sig = ""
        self._vp_w = IE6_VIEWPORT_W
        self._vp_h = IE6_VIEWPORT_H
        self._vp_scale = IE6_DEVICE_SCALE
        self._stream_max_w = IE6_VIEWPORT_W
        self._stream_max_h = IE6_VIEWPORT_H
        self._screencast_active = False
        self._last_stream_frame_ts = 0.0
        self._last_stream_dom_ts = 0.0
        self._worker: Optional[threading.Thread] = None
        self._sixel_cfg: tuple[bool, int, int, int, float, float] = (False, 800, 450, 1, 0.5, 0.5)
        self._sixel_wake = threading.Event()
        self._sixel_cfg_event = threading.Event()
        self._sixel_thread: Optional[threading.Thread] = None

    def _ensure_sixel_worker(self) -> None:
        if self._sixel_thread is not None and self._sixel_thread.is_alive():
            return
        self._stop_event.clear()
        self._sixel_thread = threading.Thread(
            target=self._sixel_worker_loop, name="pykuai-ie6-sixel", daemon=True
        )
        self._sixel_thread.start()

    def _sixel_worker_loop(self) -> None:
        last_cfg_only: tuple[object, ...] = ()
        last_encode_ts = 0.0
        while not self._stop_event.is_set():
            self._sixel_wake.wait(timeout=0.5)
            self._sixel_wake.clear()
            while not self._stop_event.is_set():
                with self._lock:
                    self._sixel_cfg_event.clear()
                    enabled, tw, th, zoom, px, py = self._sixel_cfg
                    snap = self._snapshot
                    img = snap.shot_image
                    shot_seq = snap.shot_seq
                    url = snap.url
                    cfg_only = (tw, th, zoom, px, py, url)
                    if (
                        not enabled
                        or img is None
                        or url == ABOUT_HOME_URL
                        or (snap.sixel_key == cfg_only and snap.sixel_shot_seq == shot_seq)
                    ):
                        break
                if cfg_only == last_cfg_only:
                    wait_rem = 0.082 - (time.monotonic() - last_encode_ts)
                    if wait_rem > 0.004:
                        self._sixel_cfg_event.wait(timeout=wait_rem)
                        continue
                try:
                    payload, bounds, sixel_size = render_image_to_sixel(
                        img,
                        tw,
                        th,
                        zoom=zoom,
                        pan_x=px,
                        pan_y=py,
                        max_colors=128,
                        dither=False,
                    )
                except Exception:
                    break
                last_cfg_only = cfg_only
                last_encode_ts = time.monotonic()
                with self._lock:
                    cur = self._snapshot
                    cfg_now = self._sixel_cfg
                    if (
                        cfg_now[0]
                        and cfg_now[1:] == (tw, th, zoom, px, py)
                        and cur.url == url
                    ):
                        self._seq += 1
                        cur.seq = self._seq
                        cur.sixel_payload = payload
                        cur.sixel_size = sixel_size
                        cur.sixel_bounds = bounds
                        cur.sixel_key = cfg_only
                        cur.sixel_shot_seq = shot_seq

    def start(self) -> None:
        """Start the background worker thread safely (idempotent)."""
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._worker_loop, name="pykuai-ie6-cdp", daemon=True)
        self._worker.start()
        if self._sixel_cfg[0]:
            self._ensure_sixel_worker()

    def close(self) -> None:
        """Stop the worker thread and terminate the isolated headless browser cleanly."""
        self._stop_event.set()
        self._sixel_cfg_event.set()
        self._sixel_wake.set()
        try:
            self._cmd_q.put(("close",))
        except Exception:
            pass
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=1.5)
        if self._sixel_thread is not None and self._sixel_thread.is_alive():
            self._sixel_thread.join(timeout=0.8)
        self._shutdown_browser()

    def configure_sixel(
        self,
        enabled: bool,
        target_w: int,
        target_h: int,
        zoom: int = 1,
        pan_x: float = 0.5,
        pan_y: float = 0.5,
    ) -> None:
        """Update background Sixel pre-encoder target dimensions/zoom without blocking UI."""
        cfg = (
            bool(enabled),
            max(80, int(target_w)),
            max(24, (int(target_h) // 6) * 6),
            max(1, min(4, int(zoom))),
            round(float(pan_x), 4),
            round(float(pan_y), 4),
        )
        wake = False
        with self._lock:
            if cfg != self._sixel_cfg:
                self._sixel_cfg = cfg
                if not cfg[0]:
                    self._snapshot.sixel_payload = ""
                    self._snapshot.sixel_key = ()
                    self._snapshot.sixel_shot_seq = 0
                elif self._snapshot.shot_image is not None and self._snapshot.url != ABOUT_HOME_URL:
                    wake = True
        if cfg[0]:
            self._ensure_sixel_worker()
        if wake:
            self._sixel_cfg_event.set()
            self._sixel_wake.set()

    def get_snapshot(self) -> PageSnapshot:
        with self._lock:
            snap = self._snapshot
            return PageSnapshot(
                seq=snap.seq,
                url=snap.url,
                title=snap.title,
                loading=snap.loading,
                status_text=snap.status_text,
                backend_label=snap.backend_label,
                error=snap.error,
                can_back=snap.can_back,
                can_forward=snap.can_forward,
                lines=list(snap.lines),
                links=list(snap.links),
                inputs=list(snap.inputs),
                shot_image=snap.shot_image,
                shot_seq=snap.shot_seq,
                sixel_payload=snap.sixel_payload,
                sixel_size=snap.sixel_size,
                sixel_bounds=snap.sixel_bounds,
                sixel_key=snap.sixel_key,
                sixel_shot_seq=snap.sixel_shot_seq,
            )

    def navigate(self, raw_url_or_query: str) -> str:
        url, allow_http_fallback = resolve_navigation_target(raw_url_or_query)
        self.start()
        self._cmd_q.put(("nav", url, True, allow_http_fallback))
        return url

    def go_home(self, bookmarks: list[dict[str, str]]) -> None:
        self._bookmarks = bookmarks
        self.start()
        self._cmd_q.put(("home", bookmarks))

    def back(self) -> None:
        self.start()
        self._cmd_q.put(("back",))

    def forward(self) -> None:
        self.start()
        self._cmd_q.put(("forward",))

    def reload(self) -> None:
        self.start()
        self._cmd_q.put(("reload",))

    def dispatch_click(self, norm_x: float, norm_y: float) -> None:
        self.start()
        self._cmd_q.put(("click", norm_x, norm_y))

    def dispatch_scroll(self, delta_y: int) -> None:
        self.start()
        self._cmd_q.put(("scroll", delta_y))

    def dispatch_type(self, text: str, press_enter: bool = True) -> None:
        self.start()
        self._cmd_q.put(("type", text, press_enter))

    def dispatch_key(self, key: str, code: str, vk: int) -> None:
        self.start()
        self._cmd_q.put(("key", key, code, vk))

    def submit_dom_input(self, input_idx: int, text: str) -> None:
        self.start()
        self._cmd_q.put(("dom_input", input_idx, text))

    def set_viewport(
        self,
        css_w: int,
        css_h: int,
        scale: int = IE6_DEVICE_SCALE,
        stream_max_w: Optional[int] = None,
        stream_max_h: Optional[int] = None,
    ) -> None:
        """Update target browser CSS viewport & Screencast stream pixel dimensions dynamically."""
        cw = max(480, min(1600, int(css_w)))
        ch = max(320, min(1080, int(css_h)))
        sc = max(1, min(2, int(scale)))
        mw = max(320, min(1920, int(stream_max_w if stream_max_w is not None else cw)))
        mh = max(200, min(1200, int(stream_max_h if stream_max_h is not None else ch)))
        if (
            cw == self._vp_w
            and ch == self._vp_h
            and sc == self._vp_scale
            and mw == self._stream_max_w
            and mh == self._stream_max_h
        ):
            return
        self._vp_w = cw
        self._vp_h = ch
        self._vp_scale = sc
        self._stream_max_w = mw
        self._stream_max_h = mh
        if self._worker is not None and self._worker.is_alive():
            self._cmd_q.put(("resize", cw, ch, sc, mw, mh))

    def request_live_frame(self) -> None:
        if self._cmd_q.empty() and not self._stop_event.is_set():
            self._cmd_q.put(("refresh_shot",))

    # ── Worker internals ──

    def _update_snapshot(self, **changes: Any) -> None:
        wake_sixel = False
        with self._lock:
            snap = self._snapshot
            self._seq += 1
            for key, val in changes.items():
                setattr(snap, key, val)
            snap.seq = self._seq
            snap.can_back = bool(self._back_stack)
            snap.can_forward = bool(self._fwd_stack)
            if snap.url == ABOUT_HOME_URL:
                snap.sixel_payload = ""
                snap.sixel_key = ()
                snap.sixel_shot_seq = 0
            elif "shot_image" in changes and snap.shot_image is not None and self._sixel_cfg[0]:
                wake_sixel = True
        if wake_sixel:
            self._sixel_wake.set()

    def _apply_viewport_metrics(self, cdp: _StreamingCdpClient) -> None:
        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": self._vp_w,
                "height": self._vp_h,
                "deviceScaleFactor": self._vp_scale,
                "mobile": False,
            },
        )

    def _start_screencast(self, cdp: _StreamingCdpClient) -> None:
        try:
            if self._screencast_active:
                cdp.call("Page.stopScreencast")
        except Exception:
            pass
        try:
            cdp.call(
                "Page.startScreencast",
                {
                    "format": "jpeg",
                    "quality": 85,
                    "maxWidth": self._stream_max_w,
                    "maxHeight": self._stream_max_h,
                    "everyNthFrame": 2,
                },
            )
            self._screencast_active = True
            self._last_stream_frame_ts = 0.0
            self._last_stream_dom_ts = time.monotonic()
        except Exception:
            self._screencast_active = False

    def _stop_screencast(self, cdp: Optional[_StreamingCdpClient]) -> None:
        if cdp is None or not self._screencast_active:
            self._screencast_active = False
            return
        self._screencast_active = False
        try:
            cdp.call("Page.stopScreencast")
        except Exception:
            pass

    def _ensure_cdp(self) -> Optional[_StreamingCdpClient]:
        proxy_flags, proxy_sig = detect_local_proxy_flags()
        if (
            self._cdp is not None
            and self._proc is not None
            and self._proc.poll() is None
            and proxy_sig == self._proxy_sig
        ):
            return self._cdp

        found = find_chromium_browser()
        if not found:
            return None

        label, exe = found
        self._shutdown_browser()
        self._proxy_sig = proxy_sig
        port = _pick_free_port()
        tmp_dir = tempfile.TemporaryDirectory(prefix="pykuai_ie6_")
        self._tmp_profile = tmp_dir
        cmd = [
            exe,
            "--headless=new",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={tmp_dir.name}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-quic",
            "--mute-audio",
            f"--window-size={self._vp_w},{self._vp_h}",
            *proxy_flags,
            "about:blank",
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        _fetch_cdp_version_ws(port, self._proc, timeout=8.0)

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/json/list", timeout=2.5) as resp:
            targets = json.loads(resp.read().decode("utf-8", errors="replace"))
        page_ws = next(t["webSocketDebuggerUrl"] for t in targets if t.get("type") == "page")

        cdp = _StreamingCdpClient(page_ws, timeout=18.0)
        cdp.call("Page.enable")
        self._apply_viewport_metrics(cdp)
        cdp.call("Emulation.setUserAgentOverride", {"userAgent": _DESKTOP_UA})
        cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": _STEALTH_NEW_DOC_JS})
        self._cdp = cdp
        self._screencast_active = False
        self._browser_label = f"{label} Live"
        return cdp

    def _shutdown_browser(self) -> None:
        self._screencast_active = False
        proc, cdp, tmp_dir = self._proc, self._cdp, self._tmp_profile
        self._proc = None
        self._cdp = None
        self._tmp_profile = None
        if cdp is not None:
            try:
                cdp.close()
            except Exception:
                pass
        if proc is not None:
            _terminate_browser(proc)
        if tmp_dir is not None:
            try:
                tmp_dir.cleanup()
            except Exception:
                pass

    def _drain_screencast_events(self, cdp: _StreamingCdpClient) -> None:
        events = cdp.poll_events(0.0)
        if not events:
            return
        latest_b64: Optional[str] = None
        for ev in events:
            if ev.get("method") == "Page.screencastFrame":
                params = ev.get("params") or {}
                sid = params.get("sessionId")
                if sid is not None:
                    try:
                        cdp.notify("Page.screencastFrameAck", {"sessionId": sid})
                    except Exception:
                        pass
                data_b64 = params.get("data")
                if data_b64:
                    latest_b64 = data_b64

        if not latest_b64:
            return
        now = time.monotonic()
        frame_interval = 0.068 if self._sixel_cfg[0] else 0.050
        if (now - self._last_stream_frame_ts) < frame_interval:
            return
        try:
            raw = base64.b64decode(latest_b64)
            shot_img = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            return
        self._last_stream_frame_ts = now
        self._shot_seq += 1
        self._update_snapshot(shot_image=shot_img, shot_seq=self._shot_seq)

        # Periodically sync lightweight DOM state during continuous streaming (SPA navigation / titles)
        if (now - self._last_stream_dom_ts) >= 1.5 and self._current_real_url != ABOUT_HOME_URL:
            self._last_stream_dom_ts = now
            try:
                res = cdp.call(
                    "Runtime.evaluate",
                    {"expression": "JSON.stringify({url:String(location.href||''),title:String(document.title||'')})", "returnByValue": True},
                )
                raw_val = res.get("result", {}).get("value")
                if raw_val:
                    meta = json.loads(raw_val)
                    new_u = str(meta.get("url") or "")
                    new_t = str(meta.get("title") or "")
                    if new_u and not new_u.startswith(("about:", "chrome-error://")):
                        if new_u != self._current_real_url:
                            self._push_history(new_u, record_hist=True)
                        self._update_snapshot(
                            url=self._current_real_url,
                            title=new_t or self._current_real_url,
                            status_text=f"Done · {self._current_real_url[:58]}",
                        )
            except Exception:
                pass

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            streaming = (
                self._cdp is not None
                and self._screencast_active
                and self._current_real_url != ABOUT_HOME_URL
            )
            if streaming and self._cdp is not None:
                try:
                    self._drain_screencast_events(self._cdp)
                except Exception:
                    self._screencast_active = False

            try:
                item = self._cmd_q.get(timeout=0.02 if streaming else 0.25)
            except queue.Empty:
                continue

            kind = item[0]
            if kind == "close":
                break
            try:
                if kind == "home":
                    _, bookmarks = item
                    self._stop_screencast(self._cdp)
                    self._push_history(ABOUT_HOME_URL, record_hist=True)
                    with self._lock:
                        self._seq += 1
                        home = build_home_snapshot(bookmarks, seq=self._seq)
                        home.can_back = bool(self._back_stack)
                        home.can_forward = bool(self._fwd_stack)
                        self._snapshot = home
                elif kind == "nav":
                    _, url, record_hist, allow_http_fallback = item
                    self._handle_navigate(
                        url,
                        record_hist=record_hist,
                        allow_http_fallback=allow_http_fallback,
                    )
                elif kind == "resize":
                    _, cw, ch, sc, mw, mh = item
                    self._vp_w, self._vp_h, self._vp_scale = cw, ch, sc
                    self._stream_max_w, self._stream_max_h = mw, mh
                    if self._cdp is not None and self._proc is not None and self._proc.poll() is None:
                        self._apply_viewport_metrics(self._cdp)
                        if self._current_real_url != ABOUT_HOME_URL:
                            self._start_screencast(self._cdp)
                            self._capture_screenshot_only()
                elif kind == "back":
                    if self._back_stack:
                        prev = self._back_stack.pop()
                        if self._current_real_url:
                            self._fwd_stack.append(self._current_real_url)
                        self._current_real_url = prev
                        if prev == ABOUT_HOME_URL:
                            self._stop_screencast(self._cdp)
                            self._show_home_no_hist()
                        else:
                            self._handle_navigate(prev, record_hist=False)
                elif kind == "forward":
                    if self._fwd_stack:
                        nxt = self._fwd_stack.pop()
                        if self._current_real_url:
                            self._back_stack.append(self._current_real_url)
                        self._current_real_url = nxt
                        if nxt == ABOUT_HOME_URL:
                            self._stop_screencast(self._cdp)
                            self._show_home_no_hist()
                        else:
                            self._handle_navigate(nxt, record_hist=False)
                elif kind == "reload":
                    if self._current_real_url == ABOUT_HOME_URL:
                        self._stop_screencast(self._cdp)
                        self._show_home_no_hist()
                    else:
                        self._handle_navigate(self._current_real_url, record_hist=False)
                elif kind == "click":
                    _, norm_x, norm_y = item
                    self._handle_click(norm_x, norm_y)
                elif kind == "scroll":
                    _, delta_y = item
                    self._handle_scroll(delta_y)
                elif kind == "type":
                    _, text, press_enter = item
                    self._handle_type(text, press_enter)
                elif kind == "key":
                    _, key_name, code, vk = item
                    self._handle_special_key(key_name, code, vk)
                elif kind == "dom_input":
                    _, idx, text = item
                    self._handle_dom_input(idx, text)
                elif kind == "refresh_shot":
                    self._capture_screenshot_only()
            except Exception as exc:
                self._update_snapshot(
                    loading=False,
                    error=str(exc),
                    status_text=f"Error: {str(exc)[:68]}",
                )
        self._shutdown_browser()

    def _push_history(self, new_url: str, record_hist: bool) -> None:
        if record_hist and self._current_real_url and self._current_real_url != new_url:
            self._back_stack.append(self._current_real_url)
            if len(self._back_stack) > 40:
                self._back_stack.pop(0)
            self._fwd_stack.clear()
        self._current_real_url = new_url

    def _show_home_no_hist(self) -> None:
        with self._lock:
            self._seq += 1
            home = build_home_snapshot(self._bookmarks, seq=self._seq)
            home.can_back = bool(self._back_stack)
            home.can_forward = bool(self._fwd_stack)
            self._snapshot = home

    def _handle_navigate(
        self,
        url: str,
        record_hist: bool = True,
        allow_http_fallback: bool = False,
    ) -> None:
        if url == ABOUT_HOME_URL:
            self._stop_screencast(self._cdp)
            self._push_history(ABOUT_HOME_URL, record_hist=record_hist)
            self._show_home_no_hist()
            return

        self._push_history(url, record_hist=record_hist)
        self._update_snapshot(
            url=url,
            loading=True,
            error="",
            status_text=f"Opening {url}...",
        )

        try:
            cdp = self._ensure_cdp()
        except Exception:
            cdp = None

        if cdp is None:
            self._handle_http_fallback(url)
            return

        try:
            nav_res = cdp.call("Page.navigate", {"url": url})
            err_text = str(nav_res.get("errorText") or "")
            if err_text and allow_http_fallback and url.startswith("https://"):
                http_url = "http://" + url[8:]
                self._current_real_url = http_url
                self._update_snapshot(url=http_url, loading=True, status_text=f"Retrying {http_url}...")
                nav_res = cdp.call("Page.navigate", {"url": http_url})
                err_text = str(nav_res.get("errorText") or "")
            self._poll_and_sync_page(cdp, max_wait=12.0, nav_error=err_text)
            self._start_screencast(cdp)
        except Exception as exc:
            self._shutdown_browser()
            self._handle_http_fallback(url, note=f"HTTP Fallback ({str(exc)[:30]})")

    def _poll_and_sync_page(
        self,
        cdp: _StreamingCdpClient,
        max_wait: float = 5.0,
        nav_error: str = "",
    ) -> None:
        deadline = time.monotonic() + max_wait
        data: Optional[dict[str, Any]] = None
        last_len = -1
        stable_ticks = 0

        while time.monotonic() < deadline and not self._stop_event.is_set():
            if not self._cmd_q.empty():
                break
            time.sleep(0.16)
            try:
                res = cdp.call("Runtime.evaluate", {"expression": _EXTRACT_DOM_JS, "returnByValue": True})
                raw_val = res.get("result", {}).get("value")
                if not raw_val:
                    continue
                parsed = json.loads(raw_val)
                if "error" in parsed:
                    continue
                data = parsed
                cur_len = len(parsed.get("lines", [])) + len(parsed.get("links", []))
                ready = parsed.get("ready", "")
                if ready == "complete" and cur_len == last_len:
                    stable_ticks += 1
                    if stable_ticks >= (1 if cur_len > 0 else 2):
                        break
                elif ready == "interactive" and cur_len > 12:
                    stable_ticks += 1
                    if stable_ticks >= 2:
                        break
                else:
                    stable_ticks = 0
                last_len = cur_len
            except Exception:
                continue

        if data is None:
            try:
                res = cdp.call("Runtime.evaluate", {"expression": _EXTRACT_DOM_JS, "returnByValue": True})
                raw_val = res.get("result", {}).get("value")
                if raw_val:
                    parsed = json.loads(raw_val)
                    if "error" not in parsed:
                        data = parsed
            except Exception:
                pass

        shot_img = self._grab_shot_pil(cdp)
        self._apply_dom_data(data or {}, shot_img, nav_error=nav_error)

    def _grab_shot_pil(self, cdp: _CdpClient) -> Optional[Image.Image]:
        try:
            shot = cdp.call("Page.captureScreenshot", {"format": "jpeg", "quality": 92})
            b64 = shot.get("data")
            if not b64:
                return None
            raw = base64.b64decode(b64)
            return Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            return None

    def _apply_dom_data(
        self,
        data: dict[str, Any],
        shot_img: Optional[Image.Image],
        nav_error: str = "",
    ) -> None:
        raw_loc = str(data.get("url") or "")
        is_chrome_err = raw_loc.startswith("chrome-error://")
        real_url = self._current_real_url if (is_chrome_err or not raw_loc) else raw_loc
        if real_url and real_url != "about:blank" and not is_chrome_err:
            self._current_real_url = real_url
        err_msg = ""
        if is_chrome_err or (nav_error and nav_error != "net::ERR_ABORTED"):
            err_msg = nav_error or "Navigation failed (check URL or local proxy)"
        title = str(data.get("title") or real_url or "Internet Explorer")
        lines = [str(x) for x in (data.get("lines") or [])]
        links = [
            PageLink(text=str(item.get("text") or ""), href=str(item.get("href") or ""))
            for item in (data.get("links") or [])
            if item.get("href")
        ]
        inputs = [
            PageInput(
                idx=int(item.get("idx", 0)),
                placeholder=str(item.get("placeholder") or "Input"),
                value=str(item.get("value") or ""),
            )
            for item in (data.get("inputs") or [])
        ]

        changes: dict[str, Any] = {
            "url": self._current_real_url,
            "title": title,
            "loading": False,
            "error": err_msg,
            "backend_label": self._browser_label or "HiDPI Chromium",
            "lines": lines,
            "links": links,
            "inputs": inputs,
            "status_text": (
                f"{err_msg} · {self._current_real_url[:44]}"
                if err_msg
                else f"Done · {self._current_real_url[:58]}"
            ),
        }
        if shot_img is not None:
            self._shot_seq += 1
            changes["shot_image"] = shot_img
            changes["shot_seq"] = self._shot_seq
        self._update_snapshot(**changes)

    def _capture_screenshot_only(self) -> None:
        with self._lock:
            url = self._snapshot.url
            loading = self._snapshot.loading
        if url == ABOUT_HOME_URL or loading or self._cdp is None:
            return
        shot_img = self._grab_shot_pil(self._cdp)
        if shot_img is not None:
            self._shot_seq += 1
            self._update_snapshot(shot_image=shot_img, shot_seq=self._shot_seq)

    def _handle_click(self, norm_x: float, norm_y: float) -> None:
        if self._cdp is None or self._current_real_url == ABOUT_HOME_URL:
            return
        px = max(1, min(self._vp_w - 2, int(round(norm_x * self._vp_w))))
        py = max(1, min(self._vp_h - 2, int(round(norm_y * self._vp_h))))
        before_url = self._current_real_url
        for ev_type, btn, clicks in (
            ("mouseMoved", "none", 0),
            ("mousePressed", "left", 1),
            ("mouseReleased", "left", 1),
        ):
            self._cdp.call(
                "Input.dispatchMouseEvent",
                {
                    "type": ev_type,
                    "x": px,
                    "y": py,
                    "button": btn,
                    "clickCount": clicks,
                },
            )
        self._last_stream_frame_ts = 0.0
        if not self._cmd_q.empty():
            return
        time.sleep(0.05)
        if self._screencast_active:
            nav_url = before_url
            try:
                res = self._cdp.call(
                    "Runtime.evaluate",
                    {"expression": "String(location.href || '')", "returnByValue": True},
                )
                nav_url = str(res.get("result", {}).get("value") or before_url)
            except Exception:
                pass
            if nav_url == before_url:
                return
        self._poll_and_sync_page(self._cdp, max_wait=1.8)
        if self._current_real_url != before_url and before_url:
            if not self._back_stack or self._back_stack[-1] != before_url:
                self._back_stack.append(before_url)
                self._fwd_stack.clear()
                self._update_snapshot()

    def _handle_scroll(self, delta_y: int) -> None:
        if self._cdp is None or self._current_real_url == ABOUT_HOME_URL:
            return
        self._cdp.call(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseWheel",
                "x": self._vp_w // 2,
                "y": self._vp_h // 2,
                "deltaX": 0,
                "deltaY": int(delta_y),
            },
        )
        self._last_stream_frame_ts = 0.0
        if self._screencast_active or not self._cmd_q.empty():
            return
        time.sleep(0.10)
        data: dict[str, Any] = {}
        try:
            res = self._cdp.call("Runtime.evaluate", {"expression": _EXTRACT_DOM_JS, "returnByValue": True})
            raw_val = res.get("result", {}).get("value")
            if raw_val:
                parsed = json.loads(raw_val)
                if "error" not in parsed:
                    data = parsed
        except Exception:
            pass
        shot_img = self._grab_shot_pil(self._cdp)
        if data:
            self._apply_dom_data(data, shot_img)
        elif shot_img is not None:
            self._shot_seq += 1
            self._update_snapshot(shot_image=shot_img, shot_seq=self._shot_seq)

    @staticmethod
    def _dispatch_enter_key(cdp: _CdpClient) -> None:
        cdp.call(
            "Input.dispatchKeyEvent",
            {
                "type": "keyDown",
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
                "nativeVirtualKeyCode": 13,
                "text": "\r",
                "unmodifiedText": "\r",
            },
        )
        cdp.call(
            "Input.dispatchKeyEvent",
            {
                "type": "keyUp",
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
                "nativeVirtualKeyCode": 13,
            },
        )

    def _handle_type(self, text: str, press_enter: bool) -> None:
        if self._cdp is None or self._current_real_url == ABOUT_HOME_URL:
            return
        if text:
            self._cdp.call("Input.insertText", {"text": text})
        if press_enter:
            self._dispatch_enter_key(self._cdp)
        self._last_stream_frame_ts = 0.0
        if not press_enter and self._screencast_active:
            return
        time.sleep(0.18 if press_enter else 0.06)
        self._poll_and_sync_page(self._cdp, max_wait=2.4 if press_enter else 0.4)

    def _handle_special_key(self, key_name: str, code: str, vk: int) -> None:
        if self._cdp is None or self._current_real_url == ABOUT_HOME_URL:
            return
        if vk == 13 or key_name == "Enter":
            self._dispatch_enter_key(self._cdp)
        else:
            down_payload: dict[str, Any] = {
                "type": "keyDown",
                "key": key_name,
                "code": code,
                "windowsVirtualKeyCode": vk,
            }
            if key_name == " ":
                down_payload["text"] = " "
            self._cdp.call("Input.dispatchKeyEvent", down_payload)
            self._cdp.call(
                "Input.dispatchKeyEvent",
                {"type": "keyUp", "key": key_name, "code": code, "windowsVirtualKeyCode": vk},
            )
        self._last_stream_frame_ts = 0.0
        if vk != 13 and self._screencast_active:
            return
        time.sleep(0.16 if vk == 13 else 0.06)
        if vk == 13:
            self._poll_and_sync_page(self._cdp, max_wait=2.4)
        else:
            self._capture_screenshot_only()

    def _handle_dom_input(self, input_idx: int, query_text: str) -> None:
        if self._cdp is None or self._current_real_url == ABOUT_HOME_URL:
            return
        before_url = self._current_real_url
        js = f"""
        (() => {{
            const el = document.querySelector('[data-pykuai-idx="{int(input_idx)}"]');
            if (!el) return false;
            el.focus();
            el.value = {json.dumps(query_text)};
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            if (el.form && typeof el.form.submit === 'function') {{
                try {{ el.form.submit(); }} catch (e) {{}}
            }}
            return true;
        }})()
        """
        self._cdp.call("Runtime.evaluate", {"expression": js, "returnByValue": True})
        self._dispatch_enter_key(self._cdp)
        time.sleep(0.35)
        self._poll_and_sync_page(self._cdp, max_wait=3.5)
        if self._current_real_url != before_url and before_url:
            if not self._back_stack or self._back_stack[-1] != before_url:
                self._back_stack.append(before_url)
                self._fwd_stack.clear()
                self._update_snapshot()

    def _handle_http_fallback(self, url: str, note: str = "HTTP Text Fallback") -> None:
        req = urllib.request.Request(url, headers={"User-Agent": _DESKTOP_UA})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            final_url = resp.geturl() or url
            ctype = resp.headers.get("Content-Type", "")
            charset = "utf-8"
            m = re.search(r"charset=([\w-]+)", ctype, re.IGNORECASE)
            if m:
                charset = m.group(1)
            raw_html = resp.read(512_000).decode(charset, errors="replace")

        parser = _SimpleHtmlParser(final_url)
        parser.feed(raw_html)
        parser._flush_text()
        self._current_real_url = final_url
        title = " ".join(parser.title.split()) or final_url
        self._update_snapshot(
            url=final_url,
            title=title,
            loading=False,
            error="",
            backend_label=note,
            lines=parser.lines or ["(No readable text extracted from HTML.)"],
            links=parser.links,
            inputs=[],
            status_text=f"Done ({note}) · {len(parser.links)} links",
        )
