# -*- coding: utf-8 -*-
"""
PyKuai Terminal UI & Cyber-Dark Aesthetics
"""
import os
import sys
import time
import shutil

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
    1. Remove temporary icon override from Windows Terminal settings.json
    2. Restore terminal window title
    """
    global _wt_settings_path
    import ctypes

    # 1. Restore terminal title
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
    os.system("cls" if os.name == "nt" else "clear")


_custom_logger = None


def set_custom_logger(fn):
    global _custom_logger
    _custom_logger = fn


def get_custom_logger():
    return _custom_logger


def print_banner():
    """Print Cyber-Dark ASCII banner and brand identity."""
    console.print()
    console.print(get_banner())
    console.print()


def _build_console_greeting() -> tuple[Text, Text]:
    """Build the playful two-line encounter prompt shown on console startup."""
    line1 = Text.assemble(
        ("🐍 ", ""),
        ("Whoa! ", "bold #FF9800"),
        ("pykuai", "bold #00FF00"),
        (" just slithered into your console!", "#E0E0E0"),
    )
    line2 = Text.assemble(
        ("   Type ", "#9ca3af"),
        ("hh", "bold #00FF00"),
        (" for backup & tools — or ", "#9ca3af"),
        ("gg", "bold #FF5252"),
        (" to quit the game.", "#9ca3af"),
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
                    for idx in range(4, len(line2.plain) + 1):
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
