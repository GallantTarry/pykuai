# -*- coding: utf-8 -*-
"""
PyKuai Master Console & Task Dispatcher (CLI Entrypoint)
"""
import os
import sys
import shlex
import atexit
import signal
from rich.table import Table
from rich.prompt import Prompt
from rich import box
from pykuai import __version__
from pykuai.core.audio import play_sfx, stop_sfx, warmup_sfx
from pykuai.core.ui import (
    console,
    print_banner,
    play_console_greeting,
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
    """Print built-in console commands."""
    table = Table(
        box=box.SIMPLE_HEAD,
        header_style="bold #10b981",
        border_style="#333333",
        show_edge=False,
        pad_edge=False
    )
    table.add_column("Command", style="bold #00FF00", width=10, no_wrap=True)
    table.add_column("Description", style="#E0E0E0")

    table.add_row("tt", "Tool Tray")
    table.add_row("pp", "Pull Packages")
    table.add_row("vv", "View Version")
    table.add_row("cc", "Clear Console")
    table.add_row("hh", "Help Hub")
    table.add_row("gg", "Good Game")

    console.print()
    console.print(table)
    console.print()


def show_version_info():
    """Print version, author, motto, and retro audio attribution."""
    console.print()
    console.print(f"[bold #00FF00]pykuai[/bold #00FF00]  [bold #FF9800]v{__version__}[/bold #FF9800]")
    console.print("[dim]Author:[/dim]  [bold #FF9800]TuKuai[/bold #FF9800] | [bold #10b981]GallantTarry[/bold #10b981]")
    console.print('[italic #FF9800]"The Lord is my shepherd."[/italic #FF9800]')
    console.print("[dim]Audio:   Kenney Audio & CC0 SFX (CC0 1.0)[/dim]")
    console.print()


def _read_clipboard_text() -> str:
    """Read single-line Unicode clipboard text on Windows without spawning UI."""
    if os.name != "nt":
        return ""
    try:
        import ctypes

        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.GetClipboardData.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        if not user32.OpenClipboard(None):
            return ""
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                text = ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
        return text.replace("\r\n", "\n").split("\n")[0]
    except Exception:
        return ""


def _redraw_input_buffer(old_prefix_cols: int, buf: list[str], new_pos: int) -> None:
    """Rewrite edited REPL input buffer from old cursor column and restore cursor at new_pos."""
    from rich.cells import cell_len

    seq: list[str] = []
    if old_prefix_cols > 0:
        seq.append(f"\x1b[{old_prefix_cols}D")
    seq.append("\x1b[K")
    seq.append("".join(buf))
    tail_cols = cell_len("".join(buf[new_pos:])) if new_pos < len(buf) else 0
    if tail_cols > 0:
        seq.append(f"\x1b[{tail_cols}D")
    sys.stdout.write("".join(seq))
    sys.stdout.flush()


def _move_cursor_cols(buf: list[str], pos: int, new_pos: int) -> int:
    """Move terminal cursor cleanly across single- and double-width characters."""
    from rich.cells import cell_len

    if new_pos < pos:
        cols = cell_len("".join(buf[new_pos:pos]))
        if cols > 0:
            sys.stdout.write(f"\x1b[{cols}D")
    elif new_pos > pos:
        cols = cell_len("".join(buf[pos:new_pos]))
        if cols > 0:
            sys.stdout.write(f"\x1b[{cols}C")
    sys.stdout.flush()
    return new_pos


def _insert_input_text(buf: list[str], pos: int, text: str, is_paste: bool) -> int:
    """Insert typed or pasted text into REPL buffer, echo cleanly, and trigger retro SFX."""
    from rich.cells import cell_len

    if not text:
        return pos
    if pos == len(buf):
        buf.extend(text)
        sys.stdout.write(text)
        sys.stdout.flush()
        new_pos = len(buf)
    else:
        old_cols = cell_len("".join(buf[:pos]))
        for idx, ch in enumerate(text):
            buf.insert(pos + idx, ch)
        new_pos = pos + len(text)
        _redraw_input_buffer(old_cols, buf, new_pos)
    play_sfx("paste" if is_paste else "key")
    return new_pos


def _read_console_command(history: list[str]) -> str:
    """Read a REPL command with per-keystroke, paste-burst, and Enter retro SFX on Windows TTY."""
    if os.name != "nt" or not (sys.stdin.isatty() and sys.stdout.isatty()):
        return Prompt.ask("[bold #10b981]pykuai[/bold #10b981] [bold #00FF00]❯[/bold #00FF00]")

    import msvcrt
    from rich.cells import cell_len

    console.print("[bold #10b981]pykuai[/bold #10b981] [bold #00FF00]❯[/bold #00FF00]: ", end="", highlight=False)
    sys.stdout.flush()

    buf: list[str] = []
    pos = 0
    hist_idx = len(history)
    draft = ""

    while True:
        ch = msvcrt.getwch()

        if ch in ("\r", "\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            play_sfx("enter")
            line = "".join(buf)
            if line.strip() and (not history or history[-1] != line):
                history.append(line)
            return line

        if ch == "\x03":
            raise KeyboardInterrupt

        if ch in ("\x04", "\x1a") and not buf:
            raise EOFError

        if ch in ("\x00", "\xe0"):
            ext = msvcrt.getwch()
            if ext == "K" and pos > 0:
                pos = _move_cursor_cols(buf, pos, pos - 1)
            elif ext == "M" and pos < len(buf):
                pos = _move_cursor_cols(buf, pos, pos + 1)
            elif ext == "G":
                pos = _move_cursor_cols(buf, pos, 0)
            elif ext == "O":
                pos = _move_cursor_cols(buf, pos, len(buf))
            elif ext == "H" and history:
                if hist_idx == len(history):
                    draft = "".join(buf)
                if hist_idx > 0:
                    old_cols = cell_len("".join(buf[:pos]))
                    hist_idx -= 1
                    buf = list(history[hist_idx])
                    pos = len(buf)
                    _redraw_input_buffer(old_cols, buf, pos)
                    play_sfx("key")
            elif ext == "P" and hist_idx < len(history):
                old_cols = cell_len("".join(buf[:pos]))
                hist_idx += 1
                target = draft if hist_idx == len(history) else history[hist_idx]
                buf = list(target)
                pos = len(buf)
                _redraw_input_buffer(old_cols, buf, pos)
                play_sfx("key")
            elif ext == "S" and pos < len(buf):
                old_cols = cell_len("".join(buf[:pos]))
                del buf[pos]
                _redraw_input_buffer(old_cols, buf, pos)
                play_sfx("key")
            continue

        if ch in ("\x08", "\x7f"):
            if pos > 0:
                if pos == len(buf):
                    removed = buf.pop()
                    pos -= 1
                    w = max(1, cell_len(removed))
                    sys.stdout.write("\b" * w + " " * w + "\b" * w)
                    sys.stdout.flush()
                else:
                    old_cols = cell_len("".join(buf[:pos]))
                    del buf[pos - 1]
                    pos -= 1
                    _redraw_input_buffer(old_cols, buf, pos)
                play_sfx("key")
            continue

        if ch in ("\x15", "\x1b"):
            if buf:
                old_cols = cell_len("".join(buf[:pos]))
                buf = []
                pos = 0
                _redraw_input_buffer(old_cols, buf, 0)
                play_sfx("key")
            continue

        if ch == "\x16":
            pos = _insert_input_text(buf, pos, _read_clipboard_text(), is_paste=True)
            continue

        if ch.isprintable():
            chunk = [ch]
            while msvcrt.kbhit():
                nxt = msvcrt.getwch()
                if nxt in ("\x00", "\xe0"):
                    if msvcrt.kbhit():
                        msvcrt.getwch()
                    continue
                if nxt.isprintable():
                    chunk.append(nxt)
                else:
                    msvcrt.ungetwch(nxt)
                    break
            pos = _insert_input_text(buf, pos, "".join(chunk), is_paste=(len(chunk) > 1))


def run_interactive_console(skip_intro: bool = False):
    """Minimal Cyber-Dark interactive REPL console."""
    try:
        warmup_sfx()
        intro_played = False
        if not skip_intro:
            try:
                from pykuai.core.intro import play_cinematic_intro
                play_cinematic_intro()
                intro_played = True
            except Exception:
                pass

        clear_screen()
        apply_terminal_identity("pykuai")
        if not skip_intro and not intro_played:
            play_sfx("snake")
        print_banner()
        play_console_greeting(skip_animation=skip_intro)

        history: list[str] = []
        while True:
            try:
                line = _read_console_command(history)
            except (KeyboardInterrupt, EOFError):
                stop_sfx()
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
                console.print("[dim][bold #00FF00]hh[/bold #00FF00] help · [bold #00FF00]tt[/bold #00FF00] tools · [bold red]gg[/bold red] exit[/dim]\n")
                continue

            if cmd_lower == "hh":
                show_help_table()
                continue

            if cmd_lower == "vv":
                show_version_info()
                continue

            if cmd_lower == "tt" or cmd_lower.startswith("tt "):
                from pykuai.core.tray import run_tool_tray

                try:
                    tt_args = [_strip_quotes(tok) for tok in shlex.split(cmd, posix=(os.name != "nt"))[1:]]
                except Exception:
                    tt_args = [_strip_quotes(tok) for tok in cmd.split()[1:]]
                run_tool_tray(console, cli_args=tt_args or None, interactive=True)
                console.print()
                continue

            if cmd_lower == "pp" or cmd_lower.startswith("pp "):
                from pykuai.core.deps import run_pull_packages

                pp_args = shlex.split(cmd, posix=(os.name != "nt"))[1:]
                run_pull_packages(console, cli_args=pp_args or None, interactive=True)
                console.print()
                continue

            # Auto drag-and-drop detection: dropping an image triggers Image Format Converter (`ifc`)
            raw_path = _strip_quotes(cmd)
            image_drop_exts = (
                ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico",
                ".tiff", ".tif", ".gif", ".avif", ".icns", ".tga", ".ppm", ".dds", ".psd",
            )
            if any(raw_path.lower().endswith(ext) for ext in image_drop_exts):
                if os.path.exists(raw_path):
                    eng = get_engine("ifc")
                    if eng:
                        from pykuai.core.tray import run_tool_tray

                        console.print("[dim]› Image drop detected, opening ifc (Image Format Converter)...[/dim]")
                        run_tool_tray(console, cli_args=["ifc", raw_path], interactive=True)
                        console.print()
                        continue

            try:
                tokens = [_strip_quotes(tok) for tok in shlex.split(cmd, posix=(os.name != "nt"))]
            except Exception:
                tokens = [_strip_quotes(tok) for tok in cmd.split()]

            if not tokens:
                continue

            subcmd = tokens[0].lower()

            eng = get_engine(subcmd)
            if eng:
                console.print(
                    f"[dim]› '[bold]{eng.name}[/bold]' lives inside Tool Tray. "
                    f"Type [bold #00FF00]tt[/bold #00FF00] (visual) or "
                    f"[bold #00FF00]tt {eng.name}[/bold #00FF00].[/dim]\n"
                )
            else:
                console.print(
                    f"[dim]Unknown command: '{tokens[0]}'. Type [bold #00FF00]hh[/bold #00FF00] for usage, "
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

        if first_arg == "vv":
            apply_terminal_identity("pykuai")
            show_version_info()
            return

        if first_arg in ["-h", "--help", "hh"]:
            apply_terminal_identity("pykuai")
            print_banner()
            show_help_table()
            return

        if first_arg == "tt":
            from pykuai.core.tray import run_tool_tray

            apply_terminal_identity("pykuai")
            try:
                exit_code = run_tool_tray(console, cli_args=sys.argv[2:] or None, interactive=False)
                sys.exit(exit_code)
            except KeyboardInterrupt:
                console.print("\n[bold yellow]⚠️ Operation cancelled by user.[/bold yellow]")
                sys.exit(130)

        if first_arg == "pp":
            from pykuai.core.deps import run_pull_packages

            apply_terminal_identity("pykuai")
            try:
                exit_code = run_pull_packages(console, cli_args=sys.argv[2:] or None, interactive=True)
                sys.exit(exit_code)
            except KeyboardInterrupt:
                console.print("\n[bold yellow]⚠️ Operation cancelled by user.[/bold yellow]")
                sys.exit(130)

        engine = get_engine(first_arg)
        if engine:
            print_error(
                f"Tool [bold]{engine.name}[/bold] lives inside Tool Tray ([bold #00FF00]tt[/bold #00FF00])."
            )
            console.print(
                f"[dim]Run [bold #00FF00]pykuai tt[/bold #00FF00] (visual) or "
                f"[bold #00FF00]pykuai tt {engine.name} ...[/bold #00FF00].[/dim]"
            )
            sys.exit(1)

        print_error(f"Unknown command: [bold]{first_arg}[/bold]")
        console.print("[dim]Run [bold #00FF00]pykuai hh[/bold #00FF00] or [bold #00FF00]pykuai --help[/bold #00FF00] to list all available commands.[/dim]")
        sys.exit(1)
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
