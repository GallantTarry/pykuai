# -*- coding: utf-8 -*-
"""
PyKuai Master Console & Task Dispatcher (CLI Entrypoint)
"""
import atexit
import ctypes
import os
import shlex
import signal
import sys
import time
from collections import deque
from typing import Optional

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
    get_sfx_button_viewport_box,
    toggle_banner_sfx,
    get_win32_csbi,
    calibrate_banner_viewport_offset,
    register_console_restore_hook,
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
    table.add_row("xp", "XP Playground")
    table.add_row("cc", "Clear Console")

    console.print()
    console.print(table)
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


_STD_INPUT_HANDLE = 0xFFFFFFF6
_STD_OUTPUT_HANDLE = 0xFFFFFFF5
_ENABLE_MOUSE_INPUT = 0x0010
_ENABLE_EXTENDED_FLAGS = 0x0080
_ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
_RAW_IN_MODE = _ENABLE_VIRTUAL_TERMINAL_INPUT | _ENABLE_MOUSE_INPUT | _ENABLE_EXTENDED_FLAGS
_KEY_EVENT = 0x0001
_MOUSE_EVENT = 0x0002
_WAIT_OBJECT_0 = 0x00000000

_WIN32_VK_NAV_MAP = {
    0x25: "left",
    0x27: "right",
    0x26: "up",
    0x28: "down",
    0x24: "home",
    0x23: "end",
    0x2E: "del",
}
_VT_CSI_NAV_MAP = {
    "D": "left",
    "C": "right",
    "H": "home",
    "1~": "home",
    "F": "end",
    "4~": "end",
    "A": "up",
    "B": "down",
    "3~": "del",
}


class _Win32Coord(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class _Win32UChar(ctypes.Union):
    _fields_ = [("UnicodeChar", ctypes.c_wchar), ("AsciiChar", ctypes.c_char)]


class _Win32KeyEvent(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", ctypes.c_int),
        ("wRepeatCount", ctypes.c_ushort),
        ("wVirtualKeyCode", ctypes.c_ushort),
        ("wVirtualScanCode", ctypes.c_ushort),
        ("uChar", _Win32UChar),
        ("dwControlKeyState", ctypes.c_uint32),
    ]


class _Win32MouseEvent(ctypes.Structure):
    _fields_ = [
        ("dwMousePosition", _Win32Coord),
        ("dwButtonState", ctypes.c_uint32),
        ("dwControlKeyState", ctypes.c_uint32),
        ("dwEventFlags", ctypes.c_uint32),
    ]


class _Win32WinBufSizeEvent(ctypes.Structure):
    _fields_ = [("dwSize", _Win32Coord)]


class _Win32MenuEvent(ctypes.Structure):
    _fields_ = [("dwCommandId", ctypes.c_uint32)]


class _Win32FocusEvent(ctypes.Structure):
    _fields_ = [("bSetFocus", ctypes.c_int)]


class _Win32InputUnion(ctypes.Union):
    _fields_ = [
        ("KeyEvent", _Win32KeyEvent),
        ("MouseEvent", _Win32MouseEvent),
        ("WindowBufferSizeEvent", _Win32WinBufSizeEvent),
        ("MenuEvent", _Win32MenuEvent),
        ("FocusEvent", _Win32FocusEvent),
    ]


class _Win32InputRecord(ctypes.Structure):
    _fields_ = [("EventType", ctypes.c_ushort), ("Event", _Win32InputUnion)]


class _Win32ConsoleSession:
    """Manage Win32 raw VT + mouse input console modes and ReadConsoleInputW queueing."""

    def __init__(self) -> None:
        self._kernel32 = None
        self._h_in = None
        self._h_out = None
        self._orig_in_mode: Optional[int] = None
        self._orig_out_mode: Optional[int] = None
        self._vt_mouse_on = False
        self._restored = False
        self._queue: deque[tuple] = deque()

    def open(self) -> bool:
        """Switch console to raw VT+mouse input mode (disabling QuickEdit); return False if unavailable."""
        if os.name != "nt":
            return False
        try:
            k32 = ctypes.windll.kernel32
            k32.GetStdHandle.argtypes = [ctypes.c_uint32]
            k32.GetStdHandle.restype = ctypes.c_void_p
            k32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
            k32.GetConsoleMode.restype = ctypes.c_int
            k32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            k32.SetConsoleMode.restype = ctypes.c_int
            k32.GetNumberOfConsoleInputEvents.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
            k32.GetNumberOfConsoleInputEvents.restype = ctypes.c_int
            k32.ReadConsoleInputW.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_Win32InputRecord),
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_uint32),
            ]
            k32.ReadConsoleInputW.restype = ctypes.c_int
            k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            k32.WaitForSingleObject.restype = ctypes.c_uint32

            invalid = ctypes.c_void_p(-1).value
            h_in = k32.GetStdHandle(_STD_INPUT_HANDLE)
            h_out = k32.GetStdHandle(_STD_OUTPUT_HANDLE)
            if not h_in or h_in == invalid or not h_out or h_out == invalid:
                return False

            in_mode = ctypes.c_uint32()
            out_mode = ctypes.c_uint32()
            if not k32.GetConsoleMode(h_in, ctypes.byref(in_mode)):
                return False
            if not k32.GetConsoleMode(h_out, ctypes.byref(out_mode)):
                return False

            self._kernel32 = k32
            self._h_in = h_in
            self._h_out = h_out
            self._orig_in_mode = int(in_mode.value)
            self._orig_out_mode = int(out_mode.value)
            self._restored = False

            register_console_restore_hook(self.restore)
            k32.SetConsoleMode(h_in, _RAW_IN_MODE)
            k32.SetConsoleMode(h_out, self._orig_out_mode | _ENABLE_VIRTUAL_TERMINAL_PROCESSING)
            return True
        except Exception:
            self.restore()
            return False

    def set_vt_mouse(self, enabled: bool) -> None:
        """Enable or disable SGR XT mouse tracking cleanly."""
        if enabled == self._vt_mouse_on:
            return
        self._vt_mouse_on = enabled
        seq = "\x1b[?1000h\x1b[?1006h" if enabled else "\x1b[?1000l\x1b[?1006l"
        try:
            sys.stdout.write(seq)
            sys.stdout.flush()
        except Exception:
            pass

    def has_queued(self) -> bool:
        """Return True when unread decoded events are buffered in the local queue."""
        return bool(self._queue)

    def push_front(self, item: tuple) -> None:
        """Push an unread event back to the front of the local queue."""
        self._queue.appendleft(item)

    def _pump_once(self, wait_ms: int) -> bool:
        avail = ctypes.c_uint32(0)
        if not self._kernel32.GetNumberOfConsoleInputEvents(self._h_in, ctypes.byref(avail)):
            return False
        if avail.value == 0:
            if wait_ms == 0:
                return False
            if self._kernel32.WaitForSingleObject(self._h_in, wait_ms) != _WAIT_OBJECT_0:
                return False
            if not self._kernel32.GetNumberOfConsoleInputEvents(self._h_in, ctypes.byref(avail)):
                return False
            if avail.value == 0:
                return False

        count = min(int(avail.value), 64)
        buf = (_Win32InputRecord * count)()
        read = ctypes.c_uint32(0)
        if not self._kernel32.ReadConsoleInputW(self._h_in, buf, count, ctypes.byref(read)) or read.value == 0:
            return False

        added = False
        for idx in range(int(read.value)):
            rec = buf[idx]
            if rec.EventType == _KEY_EVENT:
                ke = rec.Event.KeyEvent
                if not ke.bKeyDown:
                    continue
                ch = ke.uChar.UnicodeChar or "\x00"
                vk = int(ke.wVirtualKeyCode)
                repeat = 1 if ch == "\x1b" else max(1, min(int(ke.wRepeatCount), 16))
                for _ in range(repeat):
                    self._queue.append(("key", ch, vk))
                    added = True
            elif rec.EventType == _MOUSE_EVENT:
                me = rec.Event.MouseEvent
                # Ignore noisy mouse-move/wheel events; only click (0) and double-click (2) matter here.
                if int(me.dwEventFlags) not in (0, 2):
                    continue
                self._queue.append(
                    (
                        "mouse",
                        (
                            int(me.dwMousePosition.X),
                            int(me.dwMousePosition.Y),
                            int(me.dwButtonState),
                            int(me.dwEventFlags),
                        ),
                    )
                )
                added = True
        return added

    def read_event(self, timeout_ms: Optional[int] = None) -> Optional[tuple]:
        """Read next decoded key or mouse event, waiting up to `timeout_ms` if provided."""
        if self._queue:
            return self._queue.popleft()
        if timeout_ms is None:
            while not self._queue:
                self._pump_once(150)
            return self._queue.popleft()

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while not self._queue:
            rem_ms = 0 if timeout_ms <= 0 else max(0, int((deadline - time.monotonic()) * 1000))
            if not self._pump_once(rem_ms) and (timeout_ms <= 0 or time.monotonic() >= deadline):
                break
        return self._queue.popleft() if self._queue else None

    def restore(self) -> None:
        """Restore saved Win32 stdin/stdout modes and turn off SGR mouse reporting (idempotent)."""
        if self._restored:
            return
        self._restored = True
        register_console_restore_hook(None)
        self.set_vt_mouse(False)
        if self._kernel32 is not None:
            if self._h_in is not None and self._orig_in_mode is not None:
                try:
                    self._kernel32.SetConsoleMode(self._h_in, self._orig_in_mode)
                except Exception:
                    pass
            if self._h_out is not None and self._orig_out_mode is not None:
                try:
                    self._kernel32.SetConsoleMode(self._h_out, self._orig_out_mode)
                except Exception:
                    pass


def _parse_sgr_mouse(seq: str) -> Optional[tuple[int, int, int, str]]:
    """Parse an SGR mouse CSI payload such as `<0;52;7M` into `(button, col, row, kind)`."""
    if not seq.startswith("<") or len(seq) < 6 or seq[-1] not in ("M", "m"):
        return None
    parts = seq[1:-1].split(";")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2]), seq[-1]
    except ValueError:
        return None


def _parse_dsr_cpr(seq: str) -> Optional[tuple[int, int]]:
    """Parse a VT Cursor Position Report CSI payload such as `14;11R` into `(row, col)`."""
    if not seq.endswith("R"):
        return None
    body = seq[:-1].lstrip("?")
    parts = body.split(";")
    if len(parts) != 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        return None
    return int(parts[0]), int(parts[1])


def _handle_pointer_press(
    button: str,
    col: int,
    row: int,
    buf: list[str],
    pos: int,
    sfx_box_fn=get_sfx_button_viewport_box,
    toggle_fn=toggle_banner_sfx,
) -> int:
    """Dispatch a normalized left/right click at 1-based viewport coords `(col, row)`."""
    if button == "left":
        box_rect = sfx_box_fn()
        if box_rect is not None:
            vp_row, col0, col1 = box_rect
            if row == vp_row and col0 <= col <= col1:
                toggle_fn()
        return pos
    if button == "right":
        return _insert_input_text(buf, pos, _read_clipboard_text(), is_paste=True)
    return pos


def _handle_sgr_mouse(
    seq: str,
    buf: list[str],
    pos: int,
    sfx_box_fn=get_sfx_button_viewport_box,
    toggle_fn=toggle_banner_sfx,
) -> Optional[int]:
    """Process an SGR mouse event; return updated cursor pos if handled cleanly."""
    parsed = _parse_sgr_mouse(seq)
    if parsed is None:
        return None
    btn, col, row, kind = parsed
    if kind == "M":
        base = btn & ~28
        if base == 0:
            return _handle_pointer_press("left", col, row, buf, pos, sfx_box_fn, toggle_fn)
        if base == 2:
            return _handle_pointer_press("right", col, row, buf, pos, sfx_box_fn, toggle_fn)
    return pos


def _handle_win32_mouse_record(
    x: int,
    y: int,
    btn_state: int,
    event_flags: int,
    sr_top: int,
    vp_offset: int,
    buf: list[str],
    pos: int,
    sfx_box_fn=get_sfx_button_viewport_box,
    toggle_fn=toggle_banner_sfx,
) -> int:
    """Process a Win32 MOUSE_EVENT (single click or double-click) in viewport coords."""
    if event_flags not in (0, 2):
        return pos
    col = x + 1
    row = (y - sr_top) + 1 + vp_offset
    if btn_state & 0x0001:
        return _handle_pointer_press("left", col, row, buf, pos, sfx_box_fn, toggle_fn)
    if btn_state & 0x0002:
        return _handle_pointer_press("right", col, row, buf, pos, sfx_box_fn, toggle_fn)
    return pos


def _read_csi_sequence(session, timeout_ms: int = 15) -> str:
    """Read a trailing VT CSI payload after `\\x1b[` until its final byte, preserving non-key events."""
    chars: list[str] = []
    interleaved: list[tuple] = []
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while len(chars) < 32:
        rem_ms = max(0, int((deadline - time.monotonic()) * 1000))
        ev = session.read_event(rem_ms)
        if ev is None:
            break
        if ev[0] != "key":
            interleaved.append(ev)
            continue
        c = ev[1]
        if not c or c == "\x00":
            continue
        chars.append(c)
        if 0x40 <= ord(c) <= 0x7E:
            break
    for item in reversed(interleaved):
        session.push_front(item)
    return "".join(chars)


def _calibrate_dsr_row(session, win32_vp_row: Optional[int], write_fn=None) -> int:
    """Probe terminal CPR (`\\x1b[6n`) once to compute ConPTY viewport offset without losing input."""
    if win32_vp_row is None:
        calibrate_banner_viewport_offset(0)
        return 0
    sender = write_fn or (lambda s: (sys.stdout.write(s), sys.stdout.flush()))
    sender("\x1b[6n")

    stashed: list[tuple] = []
    deadline = time.monotonic() + 0.12
    delta = 0
    for _ in range(64):
        rem_ms = max(0, int((deadline - time.monotonic()) * 1000))
        if rem_ms == 0 and not session.has_queued():
            break
        ev = session.read_event(rem_ms)
        if ev is None:
            break
        if ev[0] == "key" and ev[1] == "\x1b":
            nxt = session.read_event(15)
            if nxt is not None and nxt[0] == "key" and nxt[1] == "[":
                seq = _read_csi_sequence(session, 15)
                cpr = _parse_dsr_cpr(seq)
                if cpr is not None:
                    delta = cpr[0] - win32_vp_row
                    break
                stashed.extend([ev, nxt, *[("key", ch, 0) for ch in seq]])
                continue
            stashed.append(ev)
            if nxt is not None:
                stashed.append(nxt)
            continue
        stashed.append(ev)

    for item in reversed(stashed):
        session.push_front(item)
    calibrate_banner_viewport_offset(delta)
    return delta


def _read_console_command(history: list[str]) -> str:
    """Read a REPL command with keystroke SFX, history navigation, and clickable banner SFX on Windows TTY."""
    if os.name != "nt" or not (sys.stdin.isatty() and sys.stdout.isatty()):
        return Prompt.ask("[bold #10b981]pykuai[/bold #10b981] [bold #00FF00]❯[/bold #00FF00]")

    session = _Win32ConsoleSession()
    if not session.open():
        return Prompt.ask("[bold #10b981]pykuai[/bold #10b981] [bold #00FF00]❯[/bold #00FF00]")

    from rich.cells import cell_len

    console.print("[bold #10b981]pykuai[/bold #10b981] [bold #00FF00]❯[/bold #00FF00]: ", end="", highlight=False)
    sys.stdout.flush()

    csbi_prompt = get_win32_csbi()
    prompt_vp_row = (
        (csbi_prompt.dwCursorPosition.Y - csbi_prompt.srWindow.Top) + 1
        if csbi_prompt is not None
        else None
    )
    vp_offset = _calibrate_dsr_row(session, prompt_vp_row)
    mouse_active = get_sfx_button_viewport_box() is not None
    if mouse_active:
        session.set_vt_mouse(True)

    buf: list[str] = []
    pos = 0
    hist_idx = len(history)
    draft = ""

    def _clear_line() -> None:
        nonlocal buf, pos
        if buf:
            old_cols = cell_len("".join(buf[:pos]))
            buf = []
            pos = 0
            _redraw_input_buffer(old_cols, buf, 0)
            play_sfx("key")

    def _replace_buffer(new_text: str) -> None:
        nonlocal buf, pos
        old_cols = cell_len("".join(buf[:pos]))
        buf = list(new_text)
        pos = len(buf)
        _redraw_input_buffer(old_cols, buf, pos)
        play_sfx("key")

    def _handle_nav(nav: str) -> None:
        nonlocal buf, pos, hist_idx, draft
        if nav == "left" and pos > 0:
            pos = _move_cursor_cols(buf, pos, pos - 1)
        elif nav == "right" and pos < len(buf):
            pos = _move_cursor_cols(buf, pos, pos + 1)
        elif nav == "home":
            pos = _move_cursor_cols(buf, pos, 0)
        elif nav == "end":
            pos = _move_cursor_cols(buf, pos, len(buf))
        elif nav == "up" and history:
            if hist_idx == len(history):
                draft = "".join(buf)
            if hist_idx > 0:
                hist_idx -= 1
                _replace_buffer(history[hist_idx])
        elif nav == "down" and hist_idx < len(history):
            hist_idx += 1
            _replace_buffer(draft if hist_idx == len(history) else history[hist_idx])
        elif nav == "del" and pos < len(buf):
            old_cols = cell_len("".join(buf[:pos]))
            del buf[pos]
            _redraw_input_buffer(old_cols, buf, pos)
            play_sfx("key")

    try:
        while True:
            ev = session.read_event(None)
            if ev is None:
                continue

            if ev[0] == "mouse":
                if mouse_active:
                    x, y, btn_state, event_flags = ev[1]
                    csbi_now = get_win32_csbi()
                    sr_top = csbi_now.srWindow.Top if csbi_now is not None else 0
                    pos = _handle_win32_mouse_record(
                        x, y, btn_state, event_flags, sr_top, vp_offset, buf, pos
                    )
                continue

            _, ch, vk = ev

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

            if ch == "\x00":
                nav = _WIN32_VK_NAV_MAP.get(vk)
                if nav:
                    _handle_nav(nav)
                continue

            if ch == "\x1b":
                nxt = session.read_event(15)
                if nxt is None:
                    _clear_line()
                    continue
                if nxt[0] != "key":
                    session.push_front(nxt)
                    _clear_line()
                    continue
                if nxt[1] == "[":
                    seq = _read_csi_sequence(session, 15)
                    if seq.startswith("<"):
                        new_pos = _handle_sgr_mouse(seq, buf, pos)
                        if new_pos is not None:
                            pos = new_pos
                    else:
                        nav = _VT_CSI_NAV_MAP.get(seq)
                        if nav:
                            _handle_nav(nav)
                elif nxt[1] == "O":
                    nxt2 = session.read_event(15)
                    if nxt2 is not None and nxt2[0] == "key":
                        nav = _VT_CSI_NAV_MAP.get(nxt2[1])
                        if nav:
                            _handle_nav(nav)
                else:
                    session.push_front(nxt)
                    _clear_line()
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

            if ch == "\x15":
                _clear_line()
                continue

            if ch == "\x16":
                pos = _insert_input_text(buf, pos, _read_clipboard_text(), is_paste=True)
                continue

            if ch.isprintable():
                chunk = [ch]
                for _ in range(255):
                    nxt = session.read_event(0)
                    if nxt is None:
                        break
                    if nxt[0] != "key" or nxt[1] in ("\x00", "\x1b") or not nxt[1].isprintable():
                        session.push_front(nxt)
                        break
                    chunk.append(nxt[1])
                pos = _insert_input_text(buf, pos, "".join(chunk), is_paste=(len(chunk) > 1))
    finally:
        session.restore()


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
                play_console_greeting(skip_animation=True)
                continue

            if cmd_lower == "help":
                show_help_table()
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

            if cmd_lower == "xp" or cmd_lower.startswith("xp "):
                from pykuai.arcade.launcher import run_xp_playground

                try:
                    xp_args = [_strip_quotes(tok) for tok in shlex.split(cmd, posix=(os.name != "nt"))[1:]]
                except Exception:
                    xp_args = [_strip_quotes(tok) for tok in cmd.split()[1:]]
                run_xp_playground(console, cli_args=xp_args or None, interactive=True)
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
                    f"[dim]Unknown command: '{tokens[0]}'. Type [bold #00FF00]help[/bold #00FF00] for commands, "
                    "or [bold red]gg[/bold red] to quit.[/dim]\n"
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

        if first_arg == "xp":
            from pykuai.arcade.launcher import run_xp_playground

            apply_terminal_identity("pykuai")
            try:
                exit_code = run_xp_playground(
                    console,
                    cli_args=sys.argv[2:] or None,
                    interactive=(len(sys.argv) <= 2),
                )
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
        console.print("[dim]Run [bold #00FF00]pykuai help[/bold #00FF00] or [bold #00FF00]pykuai --help[/bold #00FF00] to list all available commands.[/dim]")
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
