"""
Visual Tool Tray (tt) launcher and unified tool subcommand dispatcher.
Houses tool engines such as `ifc` and `ytd` under a single clean doubled-letter entry point.
"""

from __future__ import annotations

import argparse
from typing import Optional

from rich import box
from rich.console import Console
from rich.table import Table

from pykuai.core.base import BaseEngine
from pykuai.core.registry import get_engine, load_all_engines
from pykuai.core.ui import print_error


def _build_tt_app(engines: dict[str, BaseEngine]):
    """Build the clickable Textual Tool Tray launcher lazily."""
    from textual.app import ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import Button, Static

    from pykuai.core.tui import ActionChip, CYBER_TUI_CSS, PyKuaiStudioApp, SfxToggleChip

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

        def compose(self) -> ComposeResult:
            with Vertical(id="studio-card"):
                yield Static("🧰 Tools", classes="studio-title")
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
                    yield Static("", classes="action-spacer")
                    yield SfxToggleChip(id="btn-sfx")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            btn = event.button
            if isinstance(btn, SfxToggleChip):
                return
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


def _dispatch_engine(
    eng: BaseEngine,
    subargs: list[str],
    console: Console,
    interactive: bool,
) -> int:
    """Execute a selected tray engine with optional subarguments."""
    if subargs:
        if (
            interactive
            and len(subargs) == 1
            and not subargs[0].startswith("-")
            and hasattr(eng, "launch_with_path")
        ):
            return eng.launch_with_path(console, subargs[0])

        parser = argparse.ArgumentParser(
            prog=f"pykuai tt {eng.name}",
            description=eng.description,
        )
        eng.register_args(parser)
        try:
            args = parser.parse_args(subargs)
        except SystemExit as exc:
            code = exc.code
            return int(code) if isinstance(code, int) else (1 if code else 0)
        return eng.run_direct(args, console)

    return eng.run_interactive(console)


def run_tool_tray(
    console: Console,
    cli_args: Optional[list[str]] = None,
    interactive: bool = True,
) -> int:
    """
    Entry point for `tt`:
    - `tt` in TTY: opens clickable Tool Tray and launches the chosen tool
    - `tt` in non-TTY: prints the Tool Tray table
    - `tt <tool> [args...]`: runs `<tool>` directly under the tray
    """
    engines = load_all_engines()

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

        return _dispatch_engine(eng, cli_args[1:], console, interactive=interactive)

    from pykuai.core.tui import is_interactive_tty

    if not is_interactive_tty():
        print_tool_tray_table(engines, console)
        return 0

    selected = _build_tt_app(engines).run()
    if selected is None:
        return 0

    return selected.run_interactive(console)
