"""Edit UTF-8 C source in the current terminal, then return to Build Bench."""

from __future__ import annotations

import codecs
import os
from pathlib import Path
import re
import sys
import tempfile

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TextArea


_EDITOR_HELP_TITLE = "bb / edit  ·  Build Bench C Editor"
_EDITOR_HELP_TEXT = """\
[bold #00d2ff]Editor Shortcuts[/]
  • [bold #00FF00]Ctrl+S[/]       Save file atomically (preserves UTF-8 & line endings)
  • [bold #00FF00]Esc / Ctrl+Q[/] Return to [bold]bb ❯[/] (prompts if unsaved changes exist)
  • [bold #00FF00]F1[/]           Toggle this help guide

[bold #00d2ff]Build Bench Workflow[/]
  • [bold #e5e7eb]edit hello.c[/]                  Open or create a UTF-8 C source file
  • [bold #e5e7eb]clang hello.c -o hello.exe[/]    Compile with pinned LLVM-MinGW x64 Clang
  • [bold #e5e7eb].\\hello.exe[/]                  Run in place (interactive scanf supported)
  • [bold #e5e7eb]gg[/]                            Leave Build Bench and return to [bold]pykuai ❯[/]"""


class _Unsaved(ModalScreen):
    BINDINGS = [
        Binding("s", "choose('save')", "Save and return"),
        Binding("d", "choose('discard')", "Discard"),
        Binding("escape", "choose('cancel')", "Keep editing"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(
            "Unsaved changes\n\n[S] Save and return\n[D] Discard changes\n[Esc] Keep editing",
            id="question", markup=False,
        )

    def action_choose(self, choice: str) -> None:
        self.dismiss(choice)


class _EditorHelp(ModalScreen):
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("f1", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold #00ff86]{_EDITOR_HELP_TITLE}[/]\n\n{_EDITOR_HELP_TEXT}\n\n[dim]Press Esc or F1 to close[/]",
            id="help-box",
            markup=True,
        )

    def action_close(self) -> None:
        self.dismiss(None)


class _SourceEditor(App):
    CSS = """
    Screen { background: #070a08; color: #e0e0e0; }
    #header { height: 1; background: #102319; }
    #filename { width: 1fr; height: 1; color: #00ff86; background: #102319; }
    TextArea { height: 1fr; border: solid #10b981; }
    #bar { height: 1; background: #0c1711; }
    #status { width: 1fr; height: 1; color: #aff4cc; padding: 0 1; }
    Button.bb-chip {
        min-width: 3; width: auto; height: 1; border: none; padding: 0 1;
        margin-left: 1; background: #13261d; color: #00ff86; text-style: bold;
    }
    Button.bb-chip:hover { background: #1e3a2f; color: #ffffff; }
    Button.bb-chip.-warn { color: #fca5a5; background: #261414; }
    Button.bb-chip.-warn:hover { background: #5c1c1c; color: #ffffff; }
    Button.bb-chip.-help { color: #38bdf8; }
    _Unsaved, _EditorHelp { align: center middle; }
    #question { width: 38; max-width: 100%; height: auto; padding: 1 2;
                border: round #10b981; background: #102319; }
    #help-box { width: 72; max-width: 96%; height: auto; padding: 1 2;
                border: round #10b981; background: #0b1410; }
    """
    BINDINGS = [
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("escape", "leave", "Return", priority=True),
        Binding("f1", "show_help", "Help", priority=True),
    ]

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path.resolve()
        self.initial_bytes = self._read_bytes()
        data = self.initial_bytes or b""
        self.encoding = "utf-8-sig" if data.startswith(codecs.BOM_UTF8) else "utf-8"
        try:
            source = data.decode(self.encoding)
        except UnicodeDecodeError as exc:
            raise ValueError(f"Cannot edit {path.name}: save it as UTF-8 first.") from exc
        newline = re.search(r"\r\n|\r|\n", source)
        self.newline = newline.group() if newline else os.linesep
        self.saved_text = source.replace("\r\n", "\n").replace("\r", "\n")

    def _read_bytes(self) -> bytes | None:
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Static(f" bb / edit   {self.path}", id="filename", markup=False)
            yield Button("?", id="btn-help", classes="bb-chip -help")
        yield TextArea(self.saved_text, id="source", show_line_numbers=True,
                       tab_behavior="indent")
        with Horizontal(id="bar"):
            yield Static("Ready", id="status", markup=False)
            yield Button("Ctrl+S Save", id="btn-save", classes="bb-chip")
            yield Button("Esc Return", id="btn-return", classes="bb-chip -warn")

    def on_mount(self) -> None:
        for btn in self.query(Button):
            btn.can_focus = False
        self.query_one(TextArea).focus()

    def _save(self) -> bool:
        source = self.query_one(TextArea).text
        data = source.replace("\n", self.newline).encode(self.encoding)
        status = self.query_one("#status", Static)
        try:
            if self._read_bytes() != self.initial_bytes:
                raise OSError("File changed outside this editor; reopen it before saving.")
            if self.initial_bytes is None or source != self.saved_text:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                # Keep the old source intact if a disk write fails mid-save.
                with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as out:
                    pending = Path(out.name)
                try:
                    pending.write_bytes(data)
                    pending.replace(self.path)
                finally:
                    pending.unlink(missing_ok=True)
                self.initial_bytes = data
                self.saved_text = source
        except OSError as exc:
            status.update(f"Save failed: {exc}")
            return False
        status.update(f"Saved {self.path.name}")
        return True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-save":
            self.action_save()
        elif bid == "btn-return":
            self.action_leave()
        elif bid == "btn-help":
            self.action_show_help()

    def action_show_help(self) -> None:
        if isinstance(self.screen, _EditorHelp):
            self.screen.dismiss(None)
        elif not isinstance(self.screen, _Unsaved):
            self.push_screen(_EditorHelp())

    def action_save(self) -> None:
        if isinstance(self.screen, _Unsaved):
            self.screen.dismiss("save")
        elif isinstance(self.screen, _EditorHelp):
            self.screen.dismiss(None)
        else:
            self._save()

    def action_leave(self) -> None:
        if isinstance(self.screen, _EditorHelp):
            self.screen.dismiss(None)
        elif isinstance(self.screen, _Unsaved):
            self.screen.dismiss("cancel")
        elif self.query_one(TextArea).text == self.saved_text:
            self.exit()
        else:
            self.push_screen(_Unsaved(), self._finish)

    def action_quit(self) -> None:
        # Textual's built-in Ctrl+Q must respect the same unsaved-edit guard.
        self.action_leave()

    def _finish(self, choice: str | None) -> None:
        if choice == "discard" or (choice == "save" and self._save()):
            self.exit()


def edit_file(path: Path) -> None:
    """Edit on the terminal's alternate screen; restore the bench on exit."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise ValueError("The editor needs an interactive terminal.")
    _SourceEditor(path).run()
