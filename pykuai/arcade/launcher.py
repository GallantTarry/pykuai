# -*- coding: utf-8 -*-
"""
XP Playground (`xp`) 3D Cutscene & Virtual Windows XP CRT Launcher.

Entry point for `xp`:
  • `xp` (interactive TTY): Plays the 3D sneak-in bedtime cutscene and boots into the
    simulated Vintage CRT Windows XP Desktop (`HEX 3D`).
  • `xp hex`: Boots directly into the built-in `HEX 3D` game window on the CRT.
  • `xp help` / `xp --help` (or non-TTY): Displays the XP Playground game summary table.
"""
from __future__ import annotations

from typing import Optional

from rich import box
from rich.console import Console
from rich.table import Table

from pykuai.arcade import get_game, get_high_score, load_all_games
from pykuai.arcade.room3d import ROOM3D_HELP_TEXT, ROOM3D_HELP_TITLE, build_arcade_room_app
from pykuai.core.ui import print_error, print_info


XP_HELP_TITLE = ROOM3D_HELP_TITLE
XP_HELP_TEXT = ROOM3D_HELP_TEXT
AA_HELP_TITLE = ROOM3D_HELP_TITLE
AA_HELP_TEXT = ROOM3D_HELP_TEXT


def print_xp_table(console: Console) -> None:
    """Render a summary table of built-in XP Playground games and personal best scores."""
    games = load_all_games()
    table = Table(
        title="XP Playground (xp) · Virtual Windows XP CRT",
        box=box.ROUNDED,
        border_style="#00AA00",
        header_style="bold #00FF00",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Code", style="bold #00FF00", no_wrap=True)
    table.add_column("Title", style="bold #FF9800", no_wrap=True)
    table.add_column("Description", style="#E0E0E0")
    table.add_column("Best Score", style="#10b981", justify="right", no_wrap=True)

    for code, game in games.items():
        best = get_high_score(code)
        table.add_row(
            code,
            game.title,
            game.tagline,
            str(best) if best > 0 else "—",
        )

    console.print()
    console.print(table)
    console.print(
        "[dim]• Run [bold #00FF00]xp[/bold #00FF00] to play the 3D cutscene & enter Windows XP CRT · "
        "[bold #00FF00]xp hex[/bold #00FF00] to jump straight into Hex 3D.[/dim]\n"
    )


def print_arcade_table(console: Console) -> None:
    """Backward-compatible alias for `print_xp_table`."""
    print_xp_table(console)


def run_xp_playground(
    console: Console,
    cli_args: Optional[list[str]] = None,
    interactive: bool = True,
) -> int:
    """
    Entry point for `xp`:
      • `xp` in TTY: opens the 3D Cutscene & Virtual Windows XP CRT (`HEX 3D`)
      • `xp hex`: boots straight into `HEX 3D` inside the CRT monitor
      • `xp help` / `xp --help` (or non-TTY): prints the built-in games summary table
    """
    load_all_games()
    auto_boot_hex = False

    if cli_args:
        first = cli_args[0].strip().lower()
        if first in ("-h", "--help", "help", "list", "ls"):
            print_xp_table(console)
            return 0

        game = get_game(first)
        if not game:
            print_error(f"Unknown entry [bold]{cli_args[0]}[/bold] in XP Playground.")
            console.print(
                "[dim]Run [bold #00FF00]xp[/bold #00FF00] to open Windows XP CRT, or [bold #00FF00]xp hex[/bold #00FF00].[/dim]"
            )
            return 1
        if game.code == "hex":
            auto_boot_hex = True
        else:
            return game.run(console)

    from pykuai.core.tui import is_interactive_tty

    if not is_interactive_tty():
        if auto_boot_hex:
            print_info("`hex` (Hex 3D) requires an interactive terminal (TTY) to run.")
        else:
            print_xp_table(console)
        return 0

    res = build_arcade_room_app(auto_boot_hex=auto_boot_hex).run(mouse=True)
    return 0 if res is None else int(res)


def run_arcade_arena(
    console: Console,
    cli_args: Optional[list[str]] = None,
    interactive: bool = True,
) -> int:
    """Backward-compatible alias for `run_xp_playground`."""
    return run_xp_playground(console, cli_args=cli_args, interactive=interactive)
