# -*- coding: utf-8 -*-
"""
PyKuai Interactive Console UI Toolkit
Reusable Cyber-Dark mouse-clickable & keyboard-navigable terminal components powered by Textual,
with automatic Rich Prompt fallback for non-TTY / piped environments.
"""
from __future__ import annotations

import sys
from typing import Any

from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from pykuai.core.audio import is_sfx_enabled, play_sfx, toggle_sfx, warmup_sfx


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

.studio-header {
    height: 1;
    layout: horizontal;
    margin-top: 1;
    margin-bottom: 0;
}

.studio-header .studio-title {
    width: 1fr;
    margin-top: 0;
}

HelpChip {
    border: none;
    height: 1;
    min-width: 3;
    width: auto;
    background: #13261d;
    color: #38BDF8;
    text-style: bold;
    padding: 0 1;
    margin-left: 1;
}

HelpChip:hover {
    background: #1e3a2f;
    color: #00FF00;
}

HelpChip:focus {
    text-style: underline bold;
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
    min-width: 6;
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

.action-spacer {
    width: 1fr;
    height: 1;
}

SfxToggleChip {
    border: none;
    height: 1;
    min-width: 8;
    width: auto;
    background: #0b2e1c;
    color: #00FF00;
    text-style: bold;
    padding: 0 1;
}

SfxToggleChip:hover {
    background: #064e3b;
    color: #ffffff;
}

SfxToggleChip.-sfx-off {
    background: #2b1414;
    color: #FF5252;
    text-style: none;
}

SfxToggleChip.-sfx-off:hover {
    background: #451a1a;
    color: #fca5a5;
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


class HelpChip(Button):
    """Compact top-right clickable '?' button opening the current studio's feature guide."""

    def __init__(self, tooltip: str = "Feature Guide (F1)", **kwargs) -> None:
        kwargs.setdefault("id", "btn-help")
        kwargs.setdefault("action", "app.show_help")
        super().__init__("?", tooltip=tooltip, **kwargs)


class StudioHeader(Horizontal):
    """Standard studio header row with left-aligned title and top-right clickable '?' guide."""

    def __init__(self, title: str, show_help: bool = True, **kwargs) -> None:
        self._title = title
        self._show_help = show_help
        kwargs.setdefault("classes", "studio-header")
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static(self._title, classes="studio-title")
        if self._show_help:
            yield HelpChip()


class HelpModalScreen(ModalScreen[None]):
    """Scrollable Cyber-Dark modal displaying a script's complete English feature guide."""

    DEFAULT_CSS = """
    HelpModalScreen {
        align: center middle;
        background: rgba(4, 8, 6, 0.82);
    }

    #help-card {
        width: 78;
        max-width: 96%;
        height: auto;
        max-height: 92%;
        background: #0d120f;
        border: round #38BDF8;
        padding: 0 2;
    }

    #help-scroll {
        height: auto;
        max-height: 55vh;
        scrollbar-size: 1 1;
        margin-top: 1;
        border: round #1A3A1A;
        background: #080c0a;
        padding: 0 1;
    }

    .help-body {
        color: #e0e0e0;
        width: 100%;
    }

    .help-hint {
        width: 1fr;
        height: 1;
        color: #6b7280;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_help", "Close", show=False),
        Binding("f1", "dismiss_help", "Close", show=False),
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
    ]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self._help_title = title
        self._help_body = body

    def compose(self) -> ComposeResult:
        with Container(id="help-card"):
            yield Static(f"📘 {self._help_title}", classes="studio-title")
            with VerticalScroll(id="help-scroll"):
                yield Static(self._help_body, classes="help-body", markup=True)
            with Horizontal(classes="action-bar"):
                yield Static("↑↓ / wheel scroll · Esc / F1 close", classes="help-hint")
                yield ActionChip("✕ Close", variant_class="-danger", id="btn-help-close")

    def on_mount(self) -> None:
        self.query_one("#btn-help-close", ActionChip).focus()

    def action_dismiss_help(self) -> None:
        play_sfx("click")
        self.dismiss(None)

    def action_scroll_up(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_up(animate=False)

    def action_scroll_down(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_down(animate=False)

    def action_page_up(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_page_up(animate=False)

    def action_page_down(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_page_down(animate=False)

    def on_click(self, event: events.Click) -> None:
        if event.widget is self:
            self.action_dismiss_help()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-help-close":
            event.stop()
            self.dismiss(None)


class SfxToggleChip(Button):
    """Clickable 1-row retro SFX mute/unmute toggle placed in Tool Tray bottom-right."""

    def __init__(self, **kwargs) -> None:
        enabled = is_sfx_enabled()
        super().__init__(self._format_state(enabled), **kwargs)
        self.set_class(not enabled, "-sfx-off")

    @staticmethod
    def _format_state(enabled: bool) -> Content:
        return Content("🔊 SFX ON" if enabled else "🔇 SFX OFF")

    def sync(self) -> None:
        enabled = is_sfx_enabled()
        self.label = self._format_state(enabled)
        self.set_class(not enabled, "-sfx-off")

    def press(self):
        if self.disabled or not self.display:
            return self
        toggle_sfx()
        self.sync()
        return self


_SFX_HOOKS_INSTALLED = False


def _install_tui_sfx_hooks() -> None:
    """Install invisible global click, keystroke, enter & paste retro SFX hooks for PyKuaiStudioApp once."""
    global _SFX_HOOKS_INSTALLED
    if _SFX_HOOKS_INSTALLED:
        return
    _SFX_HOOKS_INSTALLED = True

    orig_press = Button.press
    orig_action_press = Button.action_press
    orig_on_key = Input._on_key
    orig_delete_left = Input.action_delete_left
    orig_delete_right = Input.action_delete_right
    orig_action_submit = Input.action_submit
    orig_on_paste = Input._on_paste
    orig_action_paste = Input.action_paste

    suppress_press_click = False

    def _is_studio(widget: Any) -> bool:
        try:
            return isinstance(widget.app, PyKuaiStudioApp)
        except Exception:
            return False

    def _press_with_sfx(btn: Button, *args: Any, **kwargs: Any):
        if not suppress_press_click and not isinstance(btn, SfxToggleChip) and not btn.disabled and btn.display and _is_studio(btn):
            play_sfx("click")
        return orig_press(btn, *args, **kwargs)

    def _action_press_with_sfx(btn: Button):
        nonlocal suppress_press_click
        if not isinstance(btn, SfxToggleChip) and not btn.disabled and btn.display and not btn.has_class("-active") and _is_studio(btn):
            play_sfx("enter")
            suppress_press_click = True
            try:
                return orig_action_press(btn)
            finally:
                suppress_press_click = False
        return orig_action_press(btn)

    async def _on_key_with_sfx(inp: Input, event: events.Key):
        if event.is_printable and _is_studio(inp):
            play_sfx("key")
        return await orig_on_key(inp, event)

    def _delete_left_with_sfx(inp: Input):
        if _is_studio(inp) and (inp.cursor_position > 0 or not inp.selection.is_empty):
            play_sfx("key")
        return orig_delete_left(inp)

    def _delete_right_with_sfx(inp: Input):
        if _is_studio(inp) and (inp.cursor_position < len(inp.value) or not inp.selection.is_empty):
            play_sfx("key")
        return orig_delete_right(inp)

    async def _action_submit_with_sfx(inp: Input):
        if _is_studio(inp):
            play_sfx("enter")
        return await orig_action_submit(inp)

    def _on_paste_with_sfx(inp: Input, event: events.Paste):
        if event.text and _is_studio(inp):
            play_sfx("paste")
        return orig_on_paste(inp, event)

    def _action_paste_with_sfx(inp: Input):
        if _is_studio(inp) and inp.app.clipboard:
            play_sfx("paste")
        return orig_action_paste(inp)

    Button.press = _press_with_sfx  # type: ignore[method-assign]
    Button.action_press = _action_press_with_sfx  # type: ignore[method-assign]
    Input._on_key = _on_key_with_sfx  # type: ignore[method-assign]
    Input.action_delete_left = _delete_left_with_sfx  # type: ignore[method-assign]
    Input.action_delete_right = _delete_right_with_sfx  # type: ignore[method-assign]
    Input.action_submit = _action_submit_with_sfx  # type: ignore[method-assign]
    Input._on_paste = _on_paste_with_sfx  # type: ignore[method-assign]
    Input.action_paste = _action_paste_with_sfx  # type: ignore[method-assign]


class PyKuaiStudioApp(App):
    """Base interactive studio App styled in PyKuai Cyber-Dark aesthetics."""

    CSS = CYBER_TUI_CSS
    HELP_TITLE: str = ""
    HELP_TEXT: str = ""
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("f1", "show_help", "Help", show=False),
    ]

    def __init__(
        self,
        *args: Any,
        help_title: str | None = None,
        help_text: str | None = None,
        **kwargs: Any,
    ) -> None:
        _install_tui_sfx_hooks()
        warmup_sfx()
        super().__init__(*args, **kwargs)
        if help_title is not None:
            self.HELP_TITLE = help_title
        if help_text is not None:
            self.HELP_TEXT = help_text

    @on(events.Paste)
    def _play_fallback_paste_sfx(self, event: events.Paste) -> None:
        if event.text:
            play_sfx("paste")

    def action_show_help(self) -> None:
        if isinstance(self.screen, HelpModalScreen):
            self.screen.action_dismiss_help()
            return
        if not self.HELP_TEXT:
            return
        self.push_screen(HelpModalScreen(self.HELP_TITLE or "Feature Guide", self.HELP_TEXT))

    def action_cancel(self) -> None:
        play_sfx("click")
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
