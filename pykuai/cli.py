# -*- coding: utf-8 -*-
"""
PyKuai Master Console & Task Dispatcher (CLI Entrypoint)
"""
import os
import sys
import shlex
import atexit
import signal
import argparse
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich import box
from pykuai import __version__
from pykuai.core.i18n import t, get_lang, set_lang
from pykuai.core.ui import (
    console,
    print_banner,
    clear_screen,
    print_error,
    print_info,
    print_success,
    apply_terminal_identity,
    restore_terminal_identity,
)
from pykuai.core.registry import load_all_engines, get_engine, get_categories

# 注册系统退出自动还原钩子：只要 pykuai 进程结束，100% 还原系统终端图标与标题！
atexit.register(restore_terminal_identity)


def _signal_handler(sig, frame):
    restore_terminal_identity()
    sys.exit(0)


try:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
except Exception:
    pass


def show_help_table():
    """打印代码写法与指令列表 (教用户如何写代码)"""
    table = Table(
        box=box.SIMPLE_HEAD,
        header_style="bold #10b981",
        border_style="#333333",
        show_edge=False,
        pad_edge=False
    )
    table.add_column(t("help_col_cmd"), style="bold #00FF00", width=14)
    table.add_column(t("help_col_desc"), style="#E0E0E0", width=32)
    table.add_column(t("help_col_syntax"), style="dim #38BDF8")

    table.add_row(
        "ico",
        t("help_ico_desc"),
        t("help_ico_syntax")
    )
    table.add_row("clear / cls", t("help_clear_desc"), t("help_clear_syntax"))
    table.add_row("lang", t("help_lang_desc"), t("help_lang_syntax"))
    table.add_row("help / ?", t("help_help_desc"), t("help_help_syntax"))
    table.add_row("q / exit", t("help_q_desc"), t("help_q_syntax"))

    console.print()
    console.print(table)
    console.print()


def run_interactive_console(skip_intro: bool = False):
    """极简现代交互控制台 (输入代码结合终端可视化，无多余按键弹窗)"""
    try:
        # 1. 播放青蛇钻入屏幕左上角开机动画 (1.0 秒轻量动效)
        if not skip_intro:
            try:
                from pykuai.core.intro import play_cinematic_intro
                play_cinematic_intro()
            except Exception:
                pass

        clear_screen()
        apply_terminal_identity("pykuai")
        print_banner()

        # 2. 启动时先让用户选择语言，并自动记录持久化保存
        cur_saved = get_lang()
        default_label = "1. 中文" if cur_saved == "zh" else "2. English"
        lang_prompt = t("lang_prompt", default=default_label)

        try:
            choice = Prompt.ask(lang_prompt, default="1" if cur_saved == "zh" else "2")
        except (KeyboardInterrupt, EOFError):
            restore_terminal_identity()
            sys.exit(0)

        # 记录用户选择
        if choice.strip() in ["2", "en", "en_US", "english"]:
            set_lang("en")
        else:
            set_lang("zh")

        # 刷新屏幕与 Banner 以应用最新选中的语言
        clear_screen()
        apply_terminal_identity("pykuai")
        print_banner()

        # 3. 极简一句话提示：就一句先输入 help
        console.print(f"[dim]{t('hint')}[/dim]\n")

        # 4. REPL 交互循环
        while True:
            try:
                line = Prompt.ask("[bold #10b981]pykuai[/bold #10b981] [bold #00FF00]❯[/bold #00FF00]")
            except (KeyboardInterrupt, EOFError):
                console.print(f"\n[dim]{t('exit_msg')}[/dim]\n")
                break

            cmd = line.strip()
            if not cmd:
                continue

            cmd_lower = cmd.lower()
            if cmd_lower in ["q", "exit", "quit", "0"]:
                console.print(f"[dim]{t('exit_msg')}[/dim]\n")
                break

            if cmd_lower in ["clear", "cls"]:
                clear_screen()
                apply_terminal_identity("pykuai")
                print_banner()
                console.print(f"[dim]{t('hint')}[/dim]\n")
                continue

            if cmd_lower in ["help", "?", "h"]:
                show_help_table()
                continue

            if cmd_lower.startswith("lang"):
                parts = cmd.split()
                if len(parts) > 1:
                    set_lang(parts[1])
                else:
                    new_l = "en" if get_lang() == "zh" else "zh"
                    set_lang(new_l)
                console.print(t("lang_switched"))
                console.print()
                continue

            # 智能拖拽识别：若用户直接拖入图片路径并回车，自动调用 ICO 引擎
            raw_path = cmd.strip('\"\'')
            if any(raw_path.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]):
                if os.path.exists(raw_path):
                    console.print(f"[dim]{t('auto_drag')}[/dim]")
                    eng = get_engine("ico")
                    args = argparse.Namespace(image=raw_path, sizes="16,32,48,64,128,256", output=None)
                    eng.run_direct(args, console)
                    console.print()
                    continue

            # 解析用户输入的指令和参数 (如 `ico test.png` 或 `ico`)
            try:
                tokens = shlex.split(cmd)
            except Exception:
                tokens = cmd.split()

            if not tokens:
                continue

            subcmd = tokens[0].lower()
            subargs = tokens[1:]

            # 支持 01 或 1 映射到 ico
            if subcmd in ["01", "1"]:
                subcmd = "ico"

            eng = get_engine(subcmd)
            if eng:
                if subargs:
                    if len(subargs) == 1 and not subargs[0].startswith("-"):
                        args = argparse.Namespace(image=subargs[0], sizes="16,32,48,64,128,256", output=None)
                    else:
                        parser = argparse.ArgumentParser(prog=f"pykuai {eng.name}")
                        eng.register_args(parser)
                        try:
                            args = parser.parse_args(subargs)
                        except SystemExit:
                            continue
                    eng.run_direct(args, console)
                else:
                    eng.run_interactive(console)
                console.print()
            else:
                console.print(f"[dim]{t('unknown_cmd', cmd=tokens[0])}[/dim]\n")
    finally:
        restore_terminal_identity()


def run_direct_cli():
    """一击脱离命令行模式 (带参数直接执行)"""
    try:
        first_arg = sys.argv[1].lower()

        if first_arg in ["-v", "--version", "version"]:
            console.print(f"[bold #FF9800]pykuai[/bold #FF9800] version [bold #00FF00]{__version__}[/bold #00FF00]")
            return

        if first_arg in ["-h", "--help", "help"]:
            apply_terminal_identity("pykuai")
            print_banner()
            show_help_table()
            return

        engine = get_engine(first_arg)
        if not engine:
            print_error(f"未知的引擎指令: [bold]{first_arg}[/bold]")
            console.print("[dim]运行 [bold #00FF00]pykuai --help[/bold #00FF00] 查看支持的所有引擎指令。[/dim]")
            sys.exit(1)

        parser = argparse.ArgumentParser(
            prog=f"pykuai {engine.name}",
            description=engine.description
        )
        engine.register_args(parser)

        try:
            args = parser.parse_args(sys.argv[2:])
            exit_code = engine.run_direct(args, console)
            sys.exit(exit_code)
        except KeyboardInterrupt:
            console.print("\n[bold yellow]⚠️ 用户中断操作。[/bold yellow]")
            sys.exit(130)
    finally:
        restore_terminal_identity()


def main():
    """主程序入口调度器"""
    load_all_engines()

    if len(sys.argv) == 1:
        run_interactive_console()
    elif len(sys.argv) == 2 and sys.argv[1] in ("--no-intro", "--fast", "-f"):
        run_interactive_console(skip_intro=True)
    else:
        run_direct_cli()


if __name__ == "__main__":
    main()
