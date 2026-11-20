# -*- coding: utf-8 -*-
"""
PyKuai Terminal UI & Cyber-Dark Aesthetics
"""
import ctypes
import io
import os
import sys
import time
import shutil
from typing import Callable, Optional

from rich.cells import cell_len

from pykuai import __version__
from pykuai.core.audio import is_sfx_enabled, toggle_sfx

# Force UTF-8 terminal output to prevent Windows CP1252/GBK encoding errors
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console, Group
from rich.theme import Theme
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

# Cyber-Dark Theme
CYBER_THEME = Theme({
    "brand.orange": "#FF9800",
    "terminal.green": "#00FF00",
    "terminal.emerald": "#10b981",
    "gray.dim": "#666666",
    "gray.light": "#E0E0E0",
    "status.error": "#FF5252",
    "status.warn": "#FF9800",
    "status.success": "#00FF00",
    "status.info": "#38BDF8",
})

console = Console(theme=CYBER_THEME, legacy_windows=False)


def get_banner() -> str:
    """Render minimal Cyber-Dark ASCII Banner."""
    return (
        "[bold #00FF00]██████╗ ██╗   ██╗██╗  ██╗██╗   ██╗ █████╗ ██╗[/]\n"
        "[bold #00FF00]██╔══██╗╚██╗ ██╔╝██║ ██╔╝██║   ██║██╔══██╗██║[/]\n"
        "[bold #10b981]██████╔╝ ╚████╔╝ █████═╝ ██║   ██║███████║██║[/]\n"
        "[bold #10b981]██╔═══╝   ╚██╔╝  ██╔═██╗ ██║   ██║██╔══██║██║[/]\n"
        "[bold #047857]██║        ██║   ██║  ██╗╚██████╔╝██║  ██║██║[/]\n"
        "[bold #047857]╚═╝        ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝[/]"
    )


_watchdog_spawned = False
_wt_settings_path = None


def _spawn_watchdog(settings_path: str):
    """Spawn a detached watchdog process to clean up settings.json on unexpected exit."""
    global _watchdog_spawned
    if _watchdog_spawned:
        return
    try:
        import subprocess
        CREATE_NO_WINDOW = 0x08000000
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            [sys.executable, "-m", "pykuai.core.watchdog", str(os.getpid()), settings_path],
            cwd=os.path.expanduser("~"),
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            close_fds=True
        )
        _watchdog_spawned = True
    except Exception:
        pass


def apply_terminal_identity(title: str = "pykuai"):
    """
    Inject dynamic terminal identity:
    1. Set tab and window title to 'pykuai'
    2. Apply multi-res icon.ico to Win32 console and Windows Terminal tab
    3. Start background watchdog to guarantee clean settings.json restoration on exit
    """
    global _wt_settings_path
    import ctypes

    # 1. Set terminal title
    try:
        sys.stdout.write(f"\033]0;{title}\007")
        sys.stdout.flush()
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass

    ico_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.ico"))
    if not os.path.exists(ico_path):
        return

    # 2. Inject Windows Terminal tab icon (guarded by watchdog)
    try:
        import json
        wt_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows Terminal\settings.json"),
        ]
        for sp in wt_paths:
            if os.path.exists(sp):
                _wt_settings_path = sp
                _spawn_watchdog(sp)
                with open(sp, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                changed = False
                profiles_list = data.get("profiles", {}).get("list", [])
                for p in profiles_list:
                    pname = p.get("name", "")
                    if pname in ["Windows PowerShell", "PowerShell", "命令提示符", "Command Prompt"]:
                        if p.get("icon") != ico_path:
                            p["icon"] = ico_path
                            changed = True
                if changed:
                    with open(sp, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                break
    except Exception:
        pass

    # 3. Inject Win32 native console window icon (conhost)
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = kernel32.GetConsoleWindow() or user32.GetForegroundWindow()
        if hwnd:
            WM_SETICON = 0x80
            ICON_SMALL = 0
            ICON_BIG = 1
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010
            h_icon = user32.LoadImageW(None, ico_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
            if h_icon:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_icon)
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_icon)
    except Exception:
        pass


def restore_terminal_identity(original_title: str = "Windows PowerShell"):
    """
    Restore terminal state on exit or interruption:
    1. Disable VT mouse reporting if active
    2. Remove temporary icon override from Windows Terminal settings.json
    3. Restore terminal window title
    """
    global _wt_settings_path
    import ctypes

    # 1. Restore Win32 console mode (if raw input active) and disable VT mouse reporting
    try:
        if _console_restore_hook is not None:
            _console_restore_hook()
    except Exception:
        pass
    try:
        if sys.stdout and sys.stdout.isatty():
            sys.stdout.write("\x1b[?1000l\x1b[?1006l")
            sys.stdout.flush()
    except Exception:
        pass

    # 2. Restore terminal title
    try:
        sys.stdout.write(f"\033]0;{original_title}\007")
        sys.stdout.flush()
        ctypes.windll.kernel32.SetConsoleTitleW(original_title)
    except Exception:
        pass

    # 2. Immediately clean Windows Terminal settings.json
    try:
        wt_paths = [
            _wt_settings_path,
            os.path.expandvars(r"%LOCALAPPDATA%\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows Terminal\settings.json"),
        ]
        import json
        for sp in wt_paths:
            if sp and os.path.exists(sp):
                with open(sp, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                changed = False
                profiles_list = data.get("profiles", {}).get("list", [])
                for p in profiles_list:
                    pname = p.get("name", "")
                    if pname in ["Windows PowerShell", "PowerShell", "命令提示符", "Command Prompt"]:
                        if "icon" in p:
                            del p["icon"]
                            changed = True
                if changed:
                    with open(sp, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                break
    except Exception:
        pass


def clear_screen():
    """Clear terminal screen."""
    global _BANNER_SFX_BUF_Y, _BANNER_SFX_COL0, _BANNER_SFX_COL1, _BANNER_VP_OFFSET
    _BANNER_SFX_BUF_Y = None
    _BANNER_SFX_COL0 = None
    _BANNER_SFX_COL1 = None
    _BANNER_VP_OFFSET = 0
    os.system("cls" if os.name == "nt" else "clear")


_custom_logger = None


def set_custom_logger(fn):
    global _custom_logger
    _custom_logger = fn


def get_custom_logger():
    return _custom_logger


_BANNER_ROWS: tuple[tuple[str, str], ...] = (
    ("██████╗ ██╗   ██╗██╗  ██╗██╗   ██╗ █████╗ ██╗", "bold #00FF00"),
    ("██╔══██╗╚██╗ ██╔╝██║ ██╔╝██║   ██║██╔══██╗██║", "bold #00FF00"),
    ("██████╔╝ ╚████╔╝ █████═╝ ██║   ██║███████║██║", "bold #10b981"),
    ("██╔═══╝   ╚██╔╝  ██╔═██╗ ██║   ██║██╔══██║██║", "bold #10b981"),
    ("██║        ██║   ██║  ██╗╚██████╔╝██║  ██║██║", "bold #047857"),
    ("╚═╝        ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝", "bold #047857"),
)

_BANNER_SFX_BUF_Y: Optional[int] = None
_BANNER_SFX_COL0: Optional[int] = None
_BANNER_SFX_COL1: Optional[int] = None
_BANNER_VP_OFFSET: int = 0
_console_restore_hook: Optional[Callable[[], None]] = None


def register_console_restore_hook(hook: Optional[Callable[[], None]]) -> None:
    """Register or clear an idempotent raw-console mode restore callback."""
    global _console_restore_hook
    _console_restore_hook = hook


def calibrate_banner_viewport_offset(delta: int) -> None:
    """Store DSR-measured viewport row offset for accurate VT mouse hit-testing."""
    global _BANNER_VP_OFFSET
    _BANNER_VP_OFFSET = delta


class _Win32Coord(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class _Win32SmallRect(ctypes.Structure):
    _fields_ = [
        ("Left", ctypes.c_short),
        ("Top", ctypes.c_short),
        ("Right", ctypes.c_short),
        ("Bottom", ctypes.c_short),
    ]


class _Win32CSBI(ctypes.Structure):
    _fields_ = [
        ("dwSize", _Win32Coord),
        ("dwCursorPosition", _Win32Coord),
        ("wAttributes", ctypes.c_ushort),
        ("srWindow", _Win32SmallRect),
        ("dwMaximumWindowSize", _Win32Coord),
    ]


def _get_win32_stdout_handle():
    """Return Win32 STD_OUTPUT_HANDLE when running under a Windows console."""
    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetStdHandle.argtypes = [ctypes.c_uint32]
        kernel32.GetStdHandle.restype = ctypes.c_void_p
        h_out = kernel32.GetStdHandle(ctypes.c_uint32(-11).value)
        if not h_out or h_out == ctypes.c_void_p(-1).value:
            return None
        return kernel32, h_out
    except Exception:
        return None


def get_win32_csbi() -> Optional[_Win32CSBI]:
    """Query Win32 console cursor & visible viewport bounds without touching stdin."""
    res = _get_win32_stdout_handle()
    if res is None:
        return None
    kernel32, h_out = res
    try:
        kernel32.GetConsoleScreenBufferInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Win32CSBI)]
        kernel32.GetConsoleScreenBufferInfo.restype = ctypes.c_int
        csbi = _Win32CSBI()
        if not kernel32.GetConsoleScreenBufferInfo(h_out, ctypes.byref(csbi)):
            return None
        return csbi
    except Exception:
        return None


_get_win32_csbi = get_win32_csbi


def _read_console_chars(kernel32, h_out, x: int, y: int, count: int) -> Optional[str]:
    """Read `count` wide characters from console screen buffer coordinates `(x, y)`."""
    try:
        kernel32.ReadConsoleOutputCharacterW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            _Win32Coord,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        kernel32.ReadConsoleOutputCharacterW.restype = ctypes.c_int
        buf = ctypes.create_unicode_buffer(count + 1)
        read = ctypes.c_uint32(0)
        if not kernel32.ReadConsoleOutputCharacterW(h_out, buf, count, _Win32Coord(x, y), ctypes.byref(read)):
            return None
        return buf.value[: int(read.value)]
    except Exception:
        return None


def _scan_live_banner_sfx_y(csbi: _Win32CSBI, col0: int) -> tuple[bool, Optional[int]]:
    """Scan visible console rows bottom-up for the banner SFX pill; returns `(read_ok, y)`."""
    res = _get_win32_stdout_handle()
    if res is None:
        return False, None
    kernel32, h_out = res
    top = int(csbi.srWindow.Top)
    bottom = min(int(csbi.srWindow.Bottom), int(csbi.dwCursorPosition.Y))
    if bottom < top:
        return False, None

    x_start = max(0, col0 - 1)
    read_ok = False
    for y in range(bottom, top - 1, -1):
        pill_text = _read_console_chars(kernel32, h_out, x_start, y, 26)
        if pill_text is None:
            continue
        read_ok = True
        if "SFX ON   click" in pill_text or "SFX OFF  click" in pill_text:
            if col0 > 1:
                prefix = _read_console_chars(kernel32, h_out, 0, y, 3)
                if prefix != "╚═╝":
                    continue
            return True, y
    return read_ok, None


def _build_sfx_pill_text(enabled: bool) -> Text:
    """Build fixed-width clickable global SFX toggle badge + subtle affordance."""
    badge = " 🔊 SFX ON  " if enabled else " 🔇 SFX OFF "
    style = "bold #00FF00 on #0b2e1c" if enabled else "bold #FF5252 on #2b1414"
    return Text.assemble((badge, style), (" click", "#666666"))


def _render_sfx_pill_ansi(enabled: bool) -> str:
    """Render the SFX pill to truecolor ANSI using Rich so it matches banner colors verbatim."""
    buf = io.StringIO()
    tmp = Console(file=buf, force_terminal=True, color_system="truecolor", legacy_windows=False, width=40)
    tmp.print(_build_sfx_pill_text(enabled), end="")
    return buf.getvalue()


def _build_banner_info_rows(enabled: bool) -> list[Text]:
    """Build the 6 right-column metadata & global settings rows displayed beside PYKUAI."""
    return [
        Text.assemble(("pykuai", "bold #00FF00"), (f"  v{__version__}", "bold #FF9800")),
        Text.assemble(("Author: ", "#666666"), ("TuKuai", "bold #FF9800"), (" | ", "#666666"), ("GallantTarry", "bold #10b981")),
        Text('"The Lord is my shepherd."', style="italic #FF9800"),
        Text("Audio:  Kenney & CC0 SFX", style="#666666"),
        Text(""),
        _build_sfx_pill_text(enabled),
    ]


def get_sfx_button_viewport_box() -> Optional[tuple[int, int, int]]:
    """Return 1-based `(vp_row, col0, col1)` when the banner SFX toggle is currently on screen."""
    global _BANNER_SFX_BUF_Y
    if _BANNER_SFX_BUF_Y is None or _BANNER_SFX_COL0 is None or _BANNER_SFX_COL1 is None:
        return None
    csbi = get_win32_csbi()
    if csbi is None:
        return None

    live_y = _BANNER_SFX_BUF_Y
    read_ok, scanned_y = _scan_live_banner_sfx_y(csbi, _BANNER_SFX_COL0)
    if scanned_y is not None:
        live_y = scanned_y
        _BANNER_SFX_BUF_Y = scanned_y
    elif read_ok:
        return None

    vis_h = (csbi.srWindow.Bottom - csbi.srWindow.Top) + 1
    vp_row = (live_y - csbi.srWindow.Top) + 1 + _BANNER_VP_OFFSET
    if 1 <= vp_row <= vis_h:
        return vp_row, _BANNER_SFX_COL0, _BANNER_SFX_COL1
    return None


def toggle_banner_sfx() -> bool:
    """Toggle global retro SFX state and repaint the banner SFX button in-place."""
    new_state = toggle_sfx()
    box_rect = get_sfx_button_viewport_box()
    if box_rect is not None and sys.stdout and sys.stdout.isatty():
        vp_row, col0, _ = box_rect
        pill_ansi = _render_sfx_pill_ansi(new_state)
        try:
            sys.stdout.write(f"\x1b7\x1b[{vp_row};{col0}H{pill_ansi}\x1b8")
            sys.stdout.flush()
        except Exception:
            pass
    return new_state


def _capture_banner_sfx_row(col_start: int, pill_len: int) -> None:
    """Flush stdout and capture the exact screen-buffer Y coordinate of row 6."""
    global _BANNER_SFX_BUF_Y, _BANNER_SFX_COL0, _BANNER_SFX_COL1
    for stream in (console.file, sys.stdout):
        try:
            stream.flush()
        except Exception:
            pass
    csbi = get_win32_csbi()
    if csbi is not None:
        _BANNER_SFX_BUF_Y = csbi.dwCursorPosition.Y
        _BANNER_SFX_COL0 = col_start
        _BANNER_SFX_COL1 = col_start + pill_len - 1


def print_banner():
    """Print Cyber-Dark ASCII banner with right-side version metadata & global SFX switch."""
    global _BANNER_SFX_BUF_Y, _BANNER_SFX_COL0, _BANNER_SFX_COL1, _BANNER_VP_OFFSET

    _BANNER_SFX_BUF_Y = None
    _BANNER_SFX_COL0 = None
    _BANNER_SFX_COL1 = None
    _BANNER_VP_OFFSET = 0

    info_rows = _build_banner_info_rows(is_sfx_enabled())
    pill_len = cell_len(info_rows[-1].plain)
    term_w = console.size.width

    console.print()
    if term_w >= 78:
        gap = "   "
        col_start = cell_len(_BANNER_ROWS[0][0]) + len(gap) + 1
        for idx, ((art_str, art_style), info_txt) in enumerate(zip(_BANNER_ROWS, info_rows)):
            row = Text.assemble((art_str, art_style), gap, info_txt)
            is_last = idx == len(_BANNER_ROWS) - 1
            console.print(row, soft_wrap=True, end="" if is_last else "\n")
            if is_last:
                _capture_banner_sfx_row(col_start, pill_len)
                console.print()
    else:
        for art_str, art_style in _BANNER_ROWS:
            console.print(Text(art_str, style=art_style))
        for idx, info_txt in enumerate(info_rows):
            is_last = idx == len(info_rows) - 1
            console.print(info_txt, end="" if is_last else "\n")
            if is_last:
                _capture_banner_sfx_row(1, pill_len)
                console.print()
    console.print()


def _build_console_greeting() -> tuple[Text, Text]:
    """Build the playful two-line encounter prompt shown on console startup."""
    line1 = Text.assemble(
        ("Whoa! ", "bold #FF9800"),
        ("pykuai", "bold #00FF00"),
        (" just slithered into your console!", "#E0E0E0"),
    )
    line2 = Text.assemble(
        ("Type ", "#9ca3af"),
        ("help", "bold #00FF00"),
        (" for commands — or ", "#9ca3af"),
        ("gg", "bold #FF5252"),
        (" to quit.", "#9ca3af"),
    )
    return line1, line2


def _has_pending_keypress() -> bool:
    """Non-destructively peek whether a key is buffered on Windows."""
    if os.name != "nt":
        return False
    try:
        import msvcrt
        return bool(msvcrt.kbhit())
    except Exception:
        return False


def play_console_greeting(skip_animation: bool = False) -> None:
    """Type out the playful opening prompt with pixel-telegraph cadence."""
    line1, line2 = _build_console_greeting()
    is_tty = sys.stdout.isatty() and sys.stdin.isatty()
    if skip_animation or not is_tty:
        console.print(line1)
        console.print(line2)
        console.print()
        return

    from rich.live import Live
    from pykuai.core.audio import play_sfx

    def _wait_or_skip(seconds: float) -> bool:
        if _has_pending_keypress():
            return True
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(min(0.012, max(0.0, deadline - time.monotonic())))
            if _has_pending_keypress():
                return True
        return False

    cursor = Text("▌", style="bold #00FF00")
    try:
        with Live(Text("\n "), console=console, refresh_per_second=60, transient=False) as live:
            try:
                skipped = False
                for idx in range(1, len(line1.plain) + 1):
                    ch = line1.plain[idx - 1]
                    live.update(Text.assemble(line1[:idx], cursor, "\n "), refresh=True)
                    if not ch.isspace():
                        play_sfx("type")
                    if _wait_or_skip(0.028):
                        skipped = True
                        break

                if not skipped:
                    skipped = _wait_or_skip(0.22)

                if not skipped:
                    for idx in range(1, len(line2.plain) + 1):
                        ch = line2.plain[idx - 1]
                        live.update(Text.assemble(line1, "\n", line2[:idx], cursor), refresh=True)
                        if not ch.isspace():
                            play_sfx("type")
                        if _wait_or_skip(0.025):
                            break
            except KeyboardInterrupt:
                pass
            live.update(Text.assemble(line1, "\n", line2), refresh=True)
    except Exception:
        console.print(line1)
        console.print(line2)
    console.print()


def print_success(msg: str):
    if _custom_logger:
        _custom_logger(f"[bold #00FF00]✅ {msg}[/bold #00FF00]")
    else:
        console.print(f"[bold #00FF00]✅ {msg}[/bold #00FF00]")


def print_error(msg: str):
    if _custom_logger:
        _custom_logger(f"[bold #FF5252]❌ {msg}[/bold #FF5252]")
    else:
        console.print(f"[bold #FF5252]❌ {msg}[/bold #FF5252]")


def print_warning(msg: str):
    if _custom_logger:
        _custom_logger(f"[bold #FF9800]⚠️ {msg}[/bold #FF9800]")
    else:
        console.print(f"[bold #FF9800]⚠️ {msg}[/bold #FF9800]")


def print_info(msg: str):
    if _custom_logger:
        _custom_logger(f"[#38BDF8]ℹ️ {msg}[/#38BDF8]")
    else:
        console.print(f"[#38BDF8]ℹ️ {msg}[/#38BDF8]")


def print_step(msg: str):
    if _custom_logger:
        _custom_logger(f"[dim]>[/dim] [#10b981]{msg}[/#10b981]")
    else:
        console.print(f"[dim]>[/dim] [#10b981]{msg}[/#10b981]")


def create_progress():
    """Create a unified cyber-emerald Rich progress bar."""
    return Progress(
        SpinnerColumn(spinner_name="dots", style="#10b981"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(
            bar_width=40,
            style="#222222",
            complete_style="#00FF00",
            finished_style="#10b981"
        ),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console
    )
