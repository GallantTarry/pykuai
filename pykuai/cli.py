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
from rich.prompt import Prompt
from rich import box
from pykuai import __version__
from pykuai.core.ui import (
    console,
    print_banner,
    clear_screen,
    print_error,
    apply_terminal_identity,
    restore_terminal_identity,
)
from pykuai.core.registry import load_all_engines, get_engine

# Ensure terminal icon & title are always restored on exit
atexit.register(restore_terminal_identity)


def _signal_handler(sig, frame):
    restore_terminal_identity()
    sys.exit(0)


try:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
except Exception:
    pass


def _strip_quotes(text: str) -> str:
    """Strip surrounding single or double quotes from a CLI token."""
    s = text.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


def show_help_table():
    """Print registered engine commands and built-in console syntax."""
    table = Table(
        box=box.SIMPLE_HEAD,
        header_style="bold #10b981",
        border_style="#333333",
        show_edge=False,
        pad_edge=False
    )
    table.add_column("Command", style="bold #00FF00", width=14, no_wrap=True)
    table.add_column("Description", style="#E0E0E0")
    table.add_column("Syntax", style="dim #38BDF8")

    engines = load_all_engines()
    for engine in engines.values():
        usage = getattr(engine, "usage", "") or f"{engine.name} [options]"
        table.add_row(engine.name, engine.description, usage)

    table.add_row("cc", "Clear console", "cc")
    table.add_row("help", "Show available commands and syntax", "help")
    table.add_row("gg", "Exit safely", "gg")

    console.print()
    console.print(table)
    console.print()


def run_interactive_console(skip_intro: bool = False):
    """Minimal Cyber-Dark interactive REPL console."""
    try:
        if not skip_intro:
            try:
                from pykuai.core.intro import play_cinematic_intro
                play_cinematic_intro()
            except Exception:
                pass

        clear_screen()
        apply_terminal_identity("pykuai")
        print_banner()

        console.print("[dim]💡 Type [bold #00FF00]help[/bold #00FF00] to see commands & syntax, or [bold red]gg[/bold red] to exit[/dim]\n")

        while True:
            try:
                line = Prompt.ask("[bold #10b981]pykuai[/bold #10b981] [bold #00FF00]❯[/bold #00FF00]")
            except (KeyboardInterrupt, EOFError):
                console.print('\n[dim]"The Lord is my shepherd." Safe exit completed.[/dim]\n')
                break

            cmd = line.strip()
            if not cmd:
                continue

            cmd_lower = cmd.lower()
            if cmd_lower == "gg":
                console.print('[dim]"The Lord is my shepherd." Safe exit completed.[/dim]\n')
                break

            if cmd_lower == "cc":
                clear_screen()
                apply_terminal_identity("pykuai")
                print_banner()
                console.print("[dim]💡 Type [bold #00FF00]help[/bold #00FF00] to see commands & syntax, or [bold red]gg[/bold red] to exit[/dim]\n")
                continue

            if cmd_lower == "help":
                show_help_table()
                continue

            # Auto drag-and-drop detection: dropping an image triggers the ICO engine
            raw_path = _strip_quotes(cmd)
            if any(raw_path.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]):
                if os.path.exists(raw_path):
                    eng = get_engine("ico")
                    if eng:
                        console.print("[dim]› Image drop detected, running ICO engine...[/dim]")
                        args = argparse.Namespace(image=raw_path, sizes="16,32,48,64,128,256", output=None)
                        eng.run_direct(args, console)
                        console.print()
                        continue

            try:
                tokens = [_strip_quotes(tok) for tok in shlex.split(cmd, posix=(os.name != "nt"))]
            except Exception:
                tokens = [_strip_quotes(tok) for tok in cmd.split()]

            if not tokens:
                continue

            subcmd = tokens[0].lower()
            subargs = tokens[1:]

            eng = get_engine(subcmd)
            if eng:
                if subargs:
                    parser = argparse.ArgumentParser(
                        prog=f"pykuai {eng.name}",
                        description=eng.description
                    )
                    eng.register_args(parser)
                    try:
                        args = parser.parse_args(subargs)
                    except SystemExit:
                        console.print()
                        continue
                    eng.run_direct(args, console)
                else:
                    eng.run_interactive(console)
                console.print()
            else:
                console.print(
                    f"[dim]Unknown command: '{tokens[0]}'. Type [bold #00FF00]help[/bold #00FF00] for usage, "
                    "or [bold red]gg[/bold red] to exit.[/dim]\n"
                )
    finally:
        restore_terminal_identity()


def run_direct_cli():
    """Direct CLI execution mode (run command and exit)."""
    try:
        first_arg = sys.argv[1].lower()

        if first_arg in ["-v", "--version"]:
            console.print(f"[bold #FF9800]pykuai[/bold #FF9800] version [bold #00FF00]{__version__}[/bold #00FF00]")
            return

        if first_arg in ["-h", "--help", "help"]:
            apply_terminal_identity("pykuai")
            print_banner()
            show_help_table()
            return

        engine = get_engine(first_arg)
        if not engine:
            print_error(f"Unknown engine command: [bold]{first_arg}[/bold]")
            console.print("[dim]Run [bold #00FF00]pykuai --help[/bold #00FF00] to list all available commands.[/dim]")
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
            console.print("\n[bold yellow]⚠️ Operation cancelled by user.[/bold yellow]")
            sys.exit(130)
    finally:
        restore_terminal_identity()


def main():
    """Main CLI entrypoint."""
    load_all_engines()

    if len(sys.argv) == 1:
        run_interactive_console()
    elif len(sys.argv) == 2 and sys.argv[1] in ("--no-intro", "--fast", "-f"):
        run_interactive_console(skip_intro=True)
    else:
        run_direct_cli()


if __name__ == "__main__":
    main()
