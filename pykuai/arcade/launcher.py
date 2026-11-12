# -*- coding: utf-8 -*-
"""
Arcade Arena (`aa`) visual launcher and subcommand dispatcher.
Houses built-in & user-added terminal mini-games cleanly outside the core `tt` efficiency tray.
"""
from __future__ import annotations

from typing import Optional

from rich import box
from rich.console import Console
from rich.table import Table

from pykuai.arcade import ArcadeGame, get_game, get_high_score, load_all_games
from pykuai.core.ui import print_error

AA_HELP_TITLE = "Arcade Arena (aa)  ·  Mini-Game Hub"
AA_HELP_TEXT = """\
[bold #00d2ff]Overview[/]
  [bold #00FF00]aa[/] (Arcade Arena) is PyKuai's dedicated break-time terminal arcade.
  Mini-games stay neatly separated here so your [bold #00FF00]tt[/] efficiency tray remains clean.

[bold #00d2ff]Plugging In More Games[/]
  • Drop any `.py` module into [bold]pykuai/arcade/[/] containing an [bold]ArcadeGame[/] subclass.
  • Set a unique 3-letter lowercase [bold]code[/] (`^[a-z]{3}$`, e.g. `snk`, `trs`), `title`, and `tagline`.
  • PyKuai discovers it automatically and tracks high scores atomically in [bold]~/.pykuai/settings.json[/].

[bold #00d2ff]Shortcuts[/]
  • [bold #e5e7eb]pykuai aa[/]         Open clickable Arcade Arena hub (`?` / `F1` help).
  • [bold #e5e7eb]pykuai aa hex[/]     Jump straight into [bold #00FF00]PyKuai: Hex 3D[/].
  • [bold #e5e7eb]Esc / Close[/]       Return to the PyKuai prompt."""


def _build_aa_app(games: dict[str, ArcadeGame]):
    """Build the clickable Textual Arcade Arena menu lazily."""
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import Button, Static

    from pykuai.core.tui import (
        ActionChip,
        CYBER_TUI_CSS,
        PyKuaiStudioApp,
        StudioHeader,
    )

    arena_css = CYBER_TUI_CSS + """
    #studio-card {
        width: 68;
        padding: 0 1;
    }

    .arena-scroll {
        height: auto;
        max-height: 14;
        border: round #1A3A1A;
        background: #0C0C0C;
        padding: 0 1;
        margin-bottom: 1;
    }

    ActionChip.game-btn {
        width: 100%;
        min-height: 1;
        height: auto;
        content-align: left middle;
        margin-bottom: 1;
    }

    ActionChip.game-btn:last-child {
        margin-bottom: 0;
    }
    """

    class ArcadeArenaApp(PyKuaiStudioApp):
        CSS = arena_css
        HELP_TITLE = AA_HELP_TITLE
        HELP_TEXT = AA_HELP_TEXT
        BINDINGS = [
            *PyKuaiStudioApp.BINDINGS,
            Binding("question_mark", "show_help", "Help", show=False),
        ]

        def compose(self) -> ComposeResult:
            with Vertical(id="studio-card"):
                yield StudioHeader("🕹️ Arcade Arena")
                yield Static(
                    "Select a mini-game below, or press ? / F1 for plugin docs.",
                    classes="studio-subtitle",
                )
                with VerticalScroll(classes="arena-scroll"):
                    if games:
                        for game in games.values():
                            best = get_high_score(game.code)
                            best_badge = f" · Best: {best}" if best > 0 else ""
                            yield ActionChip(
                                f"{game.code} · {game.title} — {game.tagline}{best_badge}",
                                value=game,
                                variant_class="-file",
                                id=f"game-{game.code}",
                                classes="game-btn",
                            )
                    else:
                        yield Static("No games discovered in pykuai/arcade/.", classes="field-label")

                with Horizontal(classes="action-bar"):
                    yield ActionChip(
                        "✕ Close",
                        value="__cancel__",
                        variant_class="-danger",
                        id="btn-cancel",
                    )

        def on_button_pressed(self, event: Button.Pressed) -> None:
            btn = event.button
            val = getattr(btn, "value", None)
            if btn.id == "btn-cancel" or val == "__cancel__":
                self.exit(None)
                return
            if val is not None:
                self.exit(val)

    return ArcadeArenaApp()


def print_arcade_table(games: dict[str, ArcadeGame], console: Console) -> None:
    """Render a clean summary table of Arcade Arena games and personal bests."""
    table = Table(
        title="🕹️ Arcade Arena (aa)",
        box=box.ROUNDED,
        border_style="#00AA00",
        header_style="bold #00FF00",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Code", style="bold #00FF00", no_wrap=True)
    table.add_column("Game", style="bold #FF9800", no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("Best", style="#10b981", justify="right", no_wrap=True)

    for game in games.values():
        best = get_high_score(game.code)
        table.add_row(game.code, game.title, game.tagline, str(best) if best > 0 else "—")

    console.print()
    console.print(table)
    console.print(
        "[dim]Run [bold #00FF00]aa[/bold #00FF00] in an interactive terminal or "
        "[bold #00FF00]pykuai aa <code_name>[/bold #00FF00] to play.[/dim]\n"
    )


def run_arcade_arena(
    console: Console,
    cli_args: Optional[list[str]] = None,
    interactive: bool = True,
) -> int:
    """
    Entry point for `aa`:
    - `aa` in TTY: opens clickable Arcade Arena game selector loop
    - `aa` in non-TTY / `aa hh` / `aa --help`: prints installed mini-games table
    - `aa <code_name>`: launches target game directly
    """
    games = load_all_games()
    exit_code = 0

    if cli_args:
        first = cli_args[0].strip().lower()
        if first in ("-h", "--help", "hh"):
            print_arcade_table(games, console)
            return 0

        game = get_game(first)
        if not game:
            print_error(f"Unknown game [bold]{cli_args[0]}[/bold] in Arcade Arena.")
            console.print(
                "[dim]Run [bold #00FF00]aa[/bold #00FF00] to view installed games, "
                "or [bold #00FF00]hh[/bold #00FF00] for global commands.[/dim]"
            )
            return 1

        exit_code = game.run(console)
        if not interactive:
            return exit_code

    from pykuai.core.tui import is_interactive_tty

    if not is_interactive_tty():
        if not cli_args:
            print_arcade_table(games, console)
        return exit_code

    while True:
        selected = _build_aa_app(games).run(mouse=True)
        if selected is None:
            return 0
        selected.run(console)
