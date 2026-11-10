# -*- coding: utf-8 -*-
"""
PyKuai Terminal UI & Cyber-Dark Aesthetics
"""
import os
import sys
import time
import shutil

# 强制终端输出为 UTF-8 编码，防止 Windows 默认 GBK 报错
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

from pykuai.core.i18n import t

# 极客暗黑主题 (Cyber-Dark Theme)
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
    """动态生成双语点阵 Banner"""
    author_label = t("author_label")
    return (
        "[bold #00FF00]██████╗ ██╗   ██╗██╗  ██╗██╗   ██╗ █████╗ ██╗[/]\n"
        "[bold #00FF00]██╔══██╗╚██╗ ██╔╝██║ ██╔╝██║   ██║██╔══██╗██║[/]   [bold #FF9800]v1.2.7[/bold #FF9800]\n"
        f"[bold #10b981]██████╔╝ ╚████╔╝ █████═╝ ██║   ██║███████║██║[/]   [dim]{author_label}:[/dim] [bold #FF9800]土块[/bold #FF9800] | [bold #10b981]GallantTarry[/bold #10b981]\n"
        "[bold #10b981]██╔═══╝   ╚██╔╝  ██╔═██╗ ██║   ██║██╔══██║██║[/]   [italic #FF9800]\"The Lord is my shepherd.\"[/italic #FF9800]\n"
        "[bold #047857]██║        ██║   ██║  ██╗╚██████╔╝██║  ██║██║[/]\n"
        "[bold #047857]╚═╝        ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝[/]"
    )


_watchdog_spawned = False
_wt_settings_path = None


def _spawn_watchdog(settings_path: str):
    """启动外部独立看门狗进程：一旦主控制台死掉（包括用户直接叉掉窗口），5毫秒内自动洗净配置文件"""
    global _watchdog_spawned
    if _watchdog_spawned:
        return
    try:
        import subprocess
        CREATE_NO_WINDOW = 0x08000000
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            [sys.executable, "-m", "pykuai.core.watchdog", str(os.getpid()), settings_path],
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            close_fds=True
        )
        _watchdog_spawned = True
    except Exception:
        pass


def apply_terminal_identity(title: str = "pykuai"):
    """
    动态注入终端身份标识：
    1. 刷新标签页与窗口标题为 pykuai
    2. 加载高分多分辨率 icon.ico 并注入 Win32 终端原生窗口图标以及 Windows Terminal 标签图标
    3. 启动后台自毁看门狗，确保无论正常退出还是强关窗口，都 100% 自动还原默认终端图标！
    """
    global _wt_settings_path
    import ctypes

    # 1. 设置当前标签页标题
    try:
        sys.stdout.write(f"\033]0;{title}\007")
        sys.stdout.flush()
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass

    ico_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icon.ico"))
    if not os.path.exists(ico_path):
        return

    # 2. 注入 Windows Terminal 标签图标 (配合看门狗，安全无残留)
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

    # 3. 注入 Win32 原生控制台窗口图标 (conhost)
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
    程序退出或中断时彻底还原终端状态：
    1. 还原 Windows Terminal 配置文件中的图标（删除临时 icon 字段）
    2. 还原终端标题为原始名称
    """
    global _wt_settings_path
    import ctypes

    # 1. 还原终端标题
    try:
        sys.stdout.write(f"\033]0;{original_title}\007")
        sys.stdout.flush()
        ctypes.windll.kernel32.SetConsoleTitleW(original_title)
    except Exception:
        pass

    # 2. 立即还原 Windows Terminal 配置文件
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
    """清除终端屏幕"""
    os.system("cls" if os.name == "nt" else "clear")


_custom_logger = None


def set_custom_logger(fn):
    global _custom_logger
    _custom_logger = fn


def get_custom_logger():
    return _custom_logger


def print_banner():
    """打印控制台无挤压 Cyber Banner 与极简元信息"""
    console.print()
    console.print(get_banner())
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
    """创建统一的极客翠绿动态进度条"""
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
