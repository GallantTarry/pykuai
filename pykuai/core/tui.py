# -*- coding: utf-8 -*-
"""
PyKuai Interactive Console UI Toolkit
Reusable Cyber-Dark mouse-clickable & keyboard-navigable terminal components powered by Textual,
with automatic Rich Prompt fallback for non-TTY / piped environments.
"""
from __future__ import annotations

import sys
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import Button, Input, Static


def is_interactive_tty() -> bool:
    """Return True when both stdin and stdout are attached to an interactive terminal."""
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


CYBER_TUI_CSS = """
Screen {
    align: center middle;
    background: #070a08;
    color: #e0e0e0;
}

#studio-card {
    width: 78;
    max-width: 96%;
    height: auto;
    max-height: 96%;
    background: #0d120f;
    border: round #10b981;
    padding: 0 2;
}

#studio-scroll {
    height: auto;
    max-height: 100%;
    scrollbar-size: 1 1;
}

.studio-title {
    color: #FF9800;
    text-style: bold;
    height: 1;
    margin-top: 1;
}

.studio-subtitle {
    color: #6b7280;
    height: 1;
    margin-bottom: 1;
}

.field-header {
    height: 1;
    margin-top: 0;
}

.field-label {
    color: #10b981;
    text-style: bold;
    width: auto;
    margin-right: 1;
}

.status-ok {
    color: #00FF00;
    text-style: bold;
}

.status-dim {
    color: #6b7280;
}

.status-err {
    color: #FF5252;
    text-style: bold;
}

Input.cyber-input {
    height: 3;
    border: round #1f3328;
    background: #080c0a;
    color: #e0e0e0;
    padding: 0 1;
    margin-bottom: 1;
}

Input.cyber-input:focus {
    border: round #00FF00;
    background: #0b110e;
}

Input.cyber-slim {
    height: 1;
    width: 1fr;
    border: none;
    background: #141c18;
    color: #e0e0e0;
    padding: 0 1;
}

Input.cyber-slim:focus {
    background: #1a2921;
    color: #00FF00;
}

.chip-row {
    height: auto;
    min-height: 1;
    layout: horizontal;
    margin-bottom: 1;
}

.compact-row {
    height: 1;
    layout: horizontal;
    margin-bottom: 1;
}

.compact-tight {
    height: 1;
    layout: horizontal;
    margin-bottom: 0;
}

.hidden-err {
    display: none;
}

.shown-err {
    display: block;
    color: #FF5252;
    text-style: bold;
    height: 1;
}

ToggleChip, ActionChip {
    border: none;
    height: 1;
    min-width: 8;
    width: auto;
    background: #161f1b;
    color: #9ca3af;
    padding: 0 1;
    margin-right: 1;
}

ToggleChip:hover, ActionChip:hover {
    background: #1f2e27;
    color: #ffffff;
}

ToggleChip:focus, ActionChip:focus {
    text-style: underline bold;
}

ToggleChip.-checked {
    background: #064e3b;
    color: #00FF00;
    text-style: bold;
}

ToggleChip.-checked:hover {
    background: #047857;
    color: #ffffff;
}

.grid-chip {
    width: 23;
}

.pkg-scroll {
    max-height: 10;
    height: auto;
    margin-bottom: 1;
}

ActionChip.-preset {
    background: #1c1917;
    color: #FF9800;
}

ActionChip.-preset:hover {
    background: #431407;
    color: #fbbf24;
}

ActionChip.-file {
    background: #0f172a;
    color: #38BDF8;
}

ActionChip.-file:hover {
    background: #1e293b;
    color: #7dd3fc;
}

ActionChip.-primary {
    background: #059669;
    color: #000000;
    text-style: bold;
    padding: 0 2;
}

ActionChip.-primary:hover {
    background: #00FF00;
    color: #000000;
}

ActionChip.-danger {
    background: #2b1414;
    color: #FF5252;
    padding: 0 2;
}

ActionChip.-danger:hover {
    background: #7f1d1d;
    color: #ffffff;
}

.action-bar {
    height: 1;
    layout: horizontal;
    margin-top: 1;
    margin-bottom: 1;
}

.hint-footer {
    color: #6b7280;
    height: 1;
    margin-top: 1;
}
"""


class ToggleChip(Button):
    """Clickable 1-row toggle pill with active/inactive cyber checkmark styling."""

    def __init__(self, label: str, value: Any = None, active: bool = False, **kwargs) -> None:
        self._base_label = label
        self.value = label if value is None else value
        self._active = active
        super().__init__(self._format_label(), **kwargs)
        self.set_class(self._active, "-checked")

    def _format_label(self) -> Content:
        mark = "✓" if self._active else " "
        return Content(f"[{mark} {self._base_label}]")

    @property
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, state: bool) -> None:
        self._active = bool(state)
        self.label = self._format_label()
        self.set_class(self._active, "-checked")


class ActionChip(Button):
    """Clickable 1-row cyber pill button for presets, quick picks, and actions."""

    def __init__(self, label: str, value: Any = None, variant_class: str = "", **kwargs) -> None:
        self.value = label if value is None else value
        super().__init__(label, **kwargs)
        if variant_class:
            self.add_class(variant_class)


class PyKuaiStudioApp(App):
    """Base interactive studio App styled in PyKuai Cyber-Dark aesthetics."""

    CSS = CYBER_TUI_CSS
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def action_cancel(self) -> None:
        self.exit(None)


def pick_multi(
    title: str,
    options: list[tuple[str, Any]],
    defaults: set[Any] | None = None,
    subtitle: str = "Click items to toggle, or use Tab / Space / Enter.",
    per_row: int = 4,
) -> list[Any] | None:
    """
    Display a reusable clickable multi-select grid inside the terminal.
    Falls back to a Rich text prompt automatically when stdin/stdout is not a TTY.
    """
    if not is_interactive_tty():
        from rich.prompt import Prompt

        labels = ", ".join(str(v) for _, v in options)
        default_str = ",".join(str(v) for _, v in options if defaults and v in defaults)
        raw = Prompt.ask(f"[#10b981]?[/#10b981] {title} ({labels})", default=default_str)
        picked = {x.strip() for x in raw.split(",") if x.strip()}
        return [val for _, val in options if str(val) in picked]

    default_set = defaults if defaults is not None else set()

    class _MultiSelectApp(PyKuaiStudioApp):
        def compose(self) -> ComposeResult:
            with Container(id="studio-card"):
                with VerticalScroll(id="studio-scroll"):
                    yield Static(title, classes="studio-title")
                    if subtitle:
                        yield Static(subtitle, classes="studio-subtitle")

                    with Horizontal(classes="compact-row"):
                        yield ActionChip("All", variant_class="-preset", id="preset-all")
                        yield ActionChip("None", variant_class="-preset", id="preset-none")

                    for idx in range(0, len(options), per_row):
                        chunk = options[idx : idx + per_row]
                        with Horizontal(classes="compact-row"):
                            for opt_label, opt_val in chunk:
                                yield ToggleChip(opt_label, value=opt_val, active=(opt_val in default_set))

                    with Horizontal(classes="action-bar"):
                        yield ActionChip("⚡ Confirm", variant_class="-primary", id="btn-confirm")
                        yield ActionChip("✕ Cancel", variant_class="-danger", id="btn-cancel")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            btn = event.button
            if isinstance(btn, ToggleChip):
                btn.active = not btn.active
            elif btn.id == "preset-all":
                for chip in self.query(ToggleChip):
                    chip.active = True
            elif btn.id == "preset-none":
                for chip in self.query(ToggleChip):
                    chip.active = False
            elif btn.id == "btn-confirm":
                selected = [chip.value for chip in self.query(ToggleChip) if chip.active]
                self.exit(selected)
            elif btn.id == "btn-cancel":
                self.exit(None)

    result = _MultiSelectApp().run(mouse=True)
    sys.stdout.flush()
    return result


def pick_one(
    title: str,
    options: list[tuple[str, Any]],
    subtitle: str = "Click an option to continue, or press Esc to cancel.",
) -> Any | None:
    """Display a reusable clickable single-choice selector inside the terminal."""
    if not is_interactive_tty():
        from rich.prompt import Prompt

        for idx, (lbl, _) in enumerate(options, 1):
            print(f"  {idx}. {lbl}")
        choice = Prompt.ask(f"[#10b981]?[/#10b981] {title}", default="1")
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1][1]
        return None

    class _SingleSelectApp(PyKuaiStudioApp):
        def compose(self) -> ComposeResult:
            with Container(id="studio-card"):
                with VerticalScroll(id="studio-scroll"):
                    yield Static(title, classes="studio-title")
                    if subtitle:
                        yield Static(subtitle, classes="studio-subtitle")

                    for idx, (opt_label, opt_val) in enumerate(options):
                        with Horizontal(classes="compact-row"):
                            yield ActionChip(f"› {opt_label}", value=opt_val, variant_class="-file", id=f"opt-{idx}")

                    with Horizontal(classes="action-bar"):
                        yield ActionChip("✕ Cancel (Esc)", variant_class="-danger", id="btn-cancel")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            btn = event.button
            if btn.id == "btn-cancel":
                self.exit(None)
            elif isinstance(btn, ActionChip):
                self.exit(btn.value)

    result = _SingleSelectApp().run(mouse=True)
    sys.stdout.flush()
    return result


def start_tui_console():
    from pykuai.core.ui import console

    console.print("[dim]Interactive Cyber-Dark TUI toolkit ready.[/dim]")
