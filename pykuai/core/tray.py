"""
Visual Tool Tray (tt) launcher and unified tool subcommand dispatcher.
Houses tool engines such as `ifc` and `ytd` under a single clean doubled-letter entry point.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Optional

from rich import box
from rich.console import Console
from rich.table import Table

from pykuai.core.base import BaseEngine
from pykuai.core.registry import get_engine, load_all_engines
from pykuai.core.ui import print_error


TT_HELP_TITLE = "Tools  ·  PyKuai Tool Tray"
TT_HELP_TEXT = """\
[bold #00d2ff]Overview[/]
  Central launcher for all discovered PyKuai scripts and interactive Cyber-Dark Studios.

[bold #00d2ff]Auto-Discovery & Tool Cards[/]
  • Every engine inside [bold]pykuai/engines/[/] inheriting [bold]BaseEngine[/] appears here automatically.
  • Click any tool row (for example, [bold #10b981]ifc[/] or [bold #10b981]ytd[/]) to open its interactive Studio immediately.

[bold #00d2ff]Global Tray Controls[/]
  • [bold #e5e7eb]✕ Close[/] / [bold]Esc[/]        Dismiss the Tool Tray and return to the PyKuai prompt.
  • [bold #e5e7eb]?[/] / [bold]F1[/]               Open this Tool Tray feature guide.

[bold #00d2ff]CLI & REPL Commands[/]
  • [bold #e5e7eb]pykuai tt[/]                Open Tool Tray (or render a status table when output is piped).
  • [bold #e5e7eb]pykuai tt <name> \\[args][/] Jump directly into a tool's Studio or run its CLI mode.
  • [bold #e5e7eb]pykuai pp[/]                Open the Package Manager Studio (install or upgrade tool dependencies).
  • [bold #e5e7eb]pykuai vv[/] / [bold #e5e7eb]hh[/] / [bold #e5e7eb]gg[/]    Show version & runtime info, command cheat sheet, or exit."""


def _build_tt_app(engines: dict[str, BaseEngine]):
    """Build the clickable Textual Tool Tray launcher lazily."""
    from textual.app import ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import Button, Static

    from pykuai.core.tui import (
        ActionChip,
        CYBER_TUI_CSS,
        PyKuaiStudioApp,
        StudioHeader,
    )

    tray_css = CYBER_TUI_CSS + """
    .tray-scroll {
        height: auto;
        max-height: 12;
        border: round #1A3A1A;
        background: #0C0C0C;
        padding: 0 1;
        margin-bottom: 1;
    }

    ActionChip.tool-btn {
        width: 100%;
        min-height: 1;
        height: auto;
        content-align: left middle;
        margin-bottom: 1;
    }

    ActionChip.tool-btn:last-child {
        margin-bottom: 0;
    }
    """

    class ToolTrayApp(PyKuaiStudioApp):
        CSS = tray_css
        HELP_TITLE = TT_HELP_TITLE
        HELP_TEXT = TT_HELP_TEXT

        def compose(self) -> ComposeResult:
            with Vertical(id="studio-card"):
                yield StudioHeader("🧰 Tools")
                with VerticalScroll(classes="tray-scroll"):
                    if engines:
                        for eng in engines.values():
                            yield ActionChip(
                                f"{eng.name:<5} {eng.description}",
                                value=eng,
                                variant_class="-file",
                                id=f"tool-{eng.name}",
                                classes="tool-btn",
                            )
                    else:
                        yield Static("No tools registered.", classes="field-label")

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

    return ToolTrayApp()


def print_tool_tray_table(engines: dict[str, BaseEngine], console: Console) -> None:
    """Render a clean non-interactive summary table of tools inside Tool Tray."""
    table = Table(
        title="🧰 Tool Tray (tt)",
        box=box.ROUNDED,
        border_style="#00AA00",
        header_style="bold #00FF00",
        show_lines=True,
        padding=(0, 1),
    )
    table.add_column("Tool", style="bold #00FF00", no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("Usage", style="#88AA88")

    for eng in engines.values():
        usage = getattr(eng, "usage", "") or f"tt {eng.name} [options]"
        table.add_row(eng.name, eng.description, usage)

    console.print()
    console.print(table)
    console.print(
        "[dim]Run [bold #00FF00]tt[/bold #00FF00] in an interactive terminal to click & launch tools visually.[/dim]\n"
    )


@dataclass(frozen=True)
class _DispatchResult:
    exit_code: int
    launched: bool


def _dispatch_engine(
    eng: BaseEngine,
    subargs: list[str],
    console: Console,
    interactive: bool,
) -> _DispatchResult:
    """Execute a tool, distinguishing help/argument errors from tool completion."""
    if subargs:
        if (
            interactive
            and len(subargs) == 1
            and not subargs[0].startswith("-")
            and hasattr(eng, "launch_with_path")
        ):
            return _DispatchResult(eng.launch_with_path(console, subargs[0]), launched=True)

        parser = argparse.ArgumentParser(
            prog=f"pykuai tt {eng.name}",
            description=eng.description,
        )
        eng.register_args(parser)
        try:
            args = parser.parse_args(subargs)
        except SystemExit as exc:
            code = exc.code
            exit_code = int(code) if isinstance(code, int) else (1 if code else 0)
            return _DispatchResult(exit_code, launched=False)
        return _DispatchResult(eng.run_direct(args, console), launched=True)

    return _DispatchResult(eng.run_interactive(console), launched=True)


def run_tool_tray(
    console: Console,
    cli_args: Optional[list[str]] = None,
    interactive: bool = True,
) -> int:
    """
    Entry point for `tt`:
    - `tt` in TTY: keeps the Tool Tray open until its own Close/Esc action
    - `tt` in non-TTY: prints the Tool Tray table
    - Console `tt <tool> [args...]`: runs the tool, then returns to the tray
    - Direct CLI `tt <tool> [args...]`: runs once and returns its exit code
    """
    engines = load_all_engines()
    exit_code = 0

    if cli_args:
        first = cli_args[0]
        if first in ("-h", "--help", "hh"):
            print_tool_tray_table(engines, console)
            return 0

        eng = get_engine(first.lower())
        if not eng:
            print_error(f"Unknown tool [bold]{first}[/bold] in Tool Tray.")
            console.print(
                "[dim]Run [bold #00FF00]tt[/bold #00FF00] to view available tools, "
                "or [bold #00FF00]hh[/bold #00FF00] for global commands.[/dim]"
            )
            return 1

        result = _dispatch_engine(eng, cli_args[1:], console, interactive=interactive)
        if not interactive or not result.launched:
            return result.exit_code
        exit_code = result.exit_code

    from pykuai.core.tui import is_interactive_tty

    if not is_interactive_tty():
        if not cli_args:
            print_tool_tray_table(engines, console)
        return exit_code

    # The tray owns navigation: a tool returning must not also close its parent.
    # Recreate the Textual app each time; finished App instances are not reused.
    while True:
        selected = _build_tt_app(engines).run()
        if selected is None:
            return 0

        selected.run_interactive(console)
