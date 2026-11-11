# -*- coding: utf-8 -*-
"""
Image Format Converter Engine (`ifc`)
Powered by Pillow — converts between PNG, JPG, WEBP, BMP, TIFF, GIF, AVIF, and multi-res Windows ICO.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass
from typing import Optional

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt

from pykuai.core.base import BaseEngine
from pykuai.core.ui import print_error, print_step, print_warning


@dataclass(frozen=True)
class FormatSpec:
    key: str
    label: str
    ext: str
    pillow_fmt: str
    supports_alpha: bool
    supports_quality: bool


FORMAT_SPECS: dict[str, FormatSpec] = {
    "ico": FormatSpec("ico", "ICO", ".ico", "ICO", True, False),
    "png": FormatSpec("png", "PNG", ".png", "PNG", True, False),
    "jpg": FormatSpec("jpg", "JPG", ".jpg", "JPEG", False, True),
    "webp": FormatSpec("webp", "WEBP", ".webp", "WEBP", True, True),
    "bmp": FormatSpec("bmp", "BMP", ".bmp", "BMP", False, False),
    "gif": FormatSpec("gif", "GIF", ".gif", "GIF", True, False),
    "tiff": FormatSpec("tiff", "TIFF", ".tiff", "TIFF", True, False),
    "avif": FormatSpec("avif", "AVIF", ".avif", "AVIF", True, True),
}

FORMAT_ALIASES: dict[str, str] = {
    "jpeg": "jpg",
    "tif": "tiff",
}

ALL_ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
STANDARD_ICO_SIZES = [16, 32, 48, 64, 128, 256]
FAVICON_ICO_SIZES = [16, 32, 48]

IMAGE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico",
    ".tiff", ".tif", ".gif", ".avif", ".icns", ".tga", ".ppm", ".dds", ".psd",
)


def _clean_path(raw: str) -> str:
    """Clean dragged/pasted paths by stripping whitespace and surrounding quotes."""
    clean = raw.strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in "\"'":
        clean = clean[1:-1]
    return os.path.expanduser(clean)


def _validate_ico_sizes(sizes: list[int]) -> list[int]:
    """Reject layers Pillow cannot encode instead of silently omitting them."""
    if not sizes or any(not isinstance(size, int) or not 8 <= size <= 256 for size in sizes):
        raise ValueError("ICO sizes must be whole numbers between 8 and 256 pixels.")
    return sorted(set(sizes))


def _parse_ico_sizes(raw: str) -> list[int]:
    try:
        return _validate_ico_sizes([int(part.strip()) for part in raw.split(",")])
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("ICO sizes must be comma-separated whole numbers between 8 and 256.") from exc


def _same_file(first: str, second: str) -> bool:
    if os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second)):
        return True
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _normalize_format(fmt: str) -> str:
    clean = fmt.strip().lower().lstrip(".")
    return FORMAT_ALIASES.get(clean, clean)


def _discover_local_images(limit: int = 5) -> list[str]:
    """Scan current working directory for nearby image files for 1-click selection."""
    try:
        entries = []
        for name in sorted(os.listdir(os.getcwd())):
            if name.lower().endswith(IMAGE_EXTENSIONS) and os.path.isfile(name):
                entries.append(os.path.abspath(name))
                if len(entries) >= limit:
                    break
        return entries
    except Exception:
        return []


def _inspect_image(path: str) -> tuple[bool, str]:
    """Inspect image dimensions and format lazily without decoding full pixels."""
    clean = _clean_path(path)
    if not clean:
        return False, ""
    abs_p = os.path.abspath(clean)
    if not os.path.isfile(abs_p):
        return False, "Not found"
    try:
        from PIL import Image

        with Image.open(abs_p) as im:
            fmt = im.format or "IMG"
            return True, f"✓ {im.width}×{im.height} · {fmt}"
    except Exception:
        return False, "Invalid image"


def _flatten_rgba_to_rgb(im):
    """Composite alpha or palette transparency onto solid white before RGB-only saves."""
    from PIL import Image

    if im.mode == "P" and "transparency" in im.info:
        im = im.convert("RGBA")
    if im.mode in ("RGBA", "LA") or ("transparency" in im.info):
        rgba = im.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        return canvas
    return im.convert("RGB") if im.mode != "RGB" else im


def _pick_highest_res_frame(im):
    """Select and eagerly decode the highest-resolution frame before file close."""
    from PIL import Image

    if im.format == "ICO" and hasattr(im, "ico"):
        sizes = getattr(im.ico, "sizes", None)
        if callable(sizes):
            available = sorted(sizes(), key=lambda wh: wh[0] * wh[1], reverse=True)
            if available:
                frame = im.ico.getimage(available[0])
                frame.load()
                return frame
    if getattr(im, "n_frames", 1) > 1 and im.format == "ICNS":
        im.load()
        best = im.copy()
        best_area = im.width * im.height
        for frame_idx in range(im.n_frames):
            im.seek(frame_idx)
            if im.width * im.height > best_area:
                im.load()
                best = im.copy()
                best_area = im.width * im.height
        return best
    if not isinstance(im, Image.Image):
        return im
    im.load()
    return im.copy()


IFC_HELP_TITLE = "ifc · Image Format Converter Guide"
IFC_HELP_TEXT = """[bold #FF9800]Overview[/]
Powered by Pillow (`PIL`), [bold #00FF00]ifc[/] converts images across 8 target formats and packages multi-resolution Windows `.ico` icon containers with atomic file writes.

[bold #FF9800]Supported Formats[/]
• [bold #00FF00]Target (`To:`)[/]: `ICO`, `PNG`, `JPG`, `WEBP`, `BMP`, `GIF`, `TIFF`, `AVIF`
• [bold #00FF00]Additional Input Sources[/]: `JPEG`, `TIF`, `ICNS`, `TGA`, `PPM`, `DDS`, `PSD`
• [bold #00FF00]Multi-Frame Sources[/]: Automatically extracts the highest-resolution layer from `ICO`/`ICNS` inputs; converts the first frame of multi-frame GIF/TIFF files.
• [bold #00FF00]Orientation & Alpha[/]: Applies EXIF orientation automatically; composites transparent pixels (`RGBA`/`LA`/`P`) onto solid white when saving to `JPG` or `BMP`.

[bold #FF9800]Source & Output Controls[/]
• [bold #00FF00]Image Input[/]: Type, paste, or drag-and-drop any image path (surrounding quotes and `~` are cleaned automatically). Live header probing shows `width × height · format`.
• [bold #00FF00]Files[/]: Lists up to 5 image files discovered in the current working directory for 1-click loading.
• [bold #00FF00]Out[/]: Optional output file path. Leave blank to save beside the source (`<source>.<ext>`, or `<source>_converted.<ext>` if the path matches the source). Writes via a temporary sibling file and atomically replaces on success.

[bold #FF9800]ICO Icon Packaging Options[/]
• [bold #00FF00]Presets[/]: `Std` (`16,32,48,64,128,256`), `All` (`16,20,24,32,40,48,64,128,256`), `Web` (`16,32,48`).
• [bold #00FF00]Sizes[/]: Toggle any combination of layers between `8` and `256` px. Non-square images are padded onto a transparent square canvas without distortion.
• [bold #00FF00]Sharpen ≤32px[/]: Applies subtle `UnsharpMask` edge sharpening to tiny layers (`<= 32px`) for sharper taskbar/favicon rendering.

[bold #FF9800]Lossy Quality (`JPG` / `WEBP` / `AVIF`)[/]
• [bold #00FF00]Qual[/]: Choose `80%`, `90%`, `92%`, `95%`, or `100%` (CLI `-q 1..100`, default `92`).

[bold #FF9800]CLI & REPL Usage[/]
• `pykuai tt ifc` — Open interactive Studio (falls back to Rich prompts in non-TUI TTY)
• `pykuai tt ifc <image> [-t fmt] [-s 16,32,...] [-q 92] [-o out] [--no-sharpen]`
• Tip: Drop or paste an image path directly into the `pykuai` REPL to open `ifc` pre-loaded.
• Shortcuts: `Esc` cancels · `F1` or `?` toggles this guide."""


def _build_ifc_studio_app(initial_path: str = ""):
    """Construct the Cyber-Dark clickable Image Format Converter Textual App (lazy-loaded)."""
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal, Vertical, VerticalScroll
    from textual.widgets import Button, Input, Static
    from pykuai.core.tui import ActionChip, PyKuaiStudioApp, StudioHeader, ToggleChip

    extra_css = """
    #studio-card {
        height: 24;
        padding: 0 1;
    }
    #studio-scroll {
        height: 1fr;
        min-height: 1;
    }
    .studio-title, .shown-err {
        height: auto;
    }
    .shown-err {
        max-height: 3;
    }
    .local-files {
        height: auto;
        margin-bottom: 1;
    }
    .local-files ActionChip {
        width: 100%;
        min-width: 0;
        content-align: left middle;
        margin-right: 0;
    }
    Screen.narrow .option-row {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr;
        grid-rows: 1;
        grid-gutter: 0 1;
        height: auto;
    }
    Screen.narrow .option-row .field-label,
    Screen.narrow #opt-sharpen {
        column-span: 2;
    }
    Screen.narrow #opt-sharpen {
        width: 100%;
    }
    Screen.narrow .option-row ToggleChip,
    Screen.narrow .option-row ActionChip {
        width: 1fr;
        min-width: 0;
        margin-right: 0;
    }
    .action-bar ActionChip {
        width: 1fr;
        min-width: 0;
        padding: 0 1;
    }
    #ico-section {
        height: auto;
    }
    .hidden-section {
        display: none;
    }
    """

    local_images = _discover_local_images(limit=5)
    init_clean = os.path.abspath(_clean_path(initial_path)) if _clean_path(initial_path) else ""

    class IfcStudioApp(PyKuaiStudioApp):
        CSS = PyKuaiStudioApp.CSS + extra_css
        HELP_TITLE = IFC_HELP_TITLE
        HELP_TEXT = IFC_HELP_TEXT

        def compose(self) -> ComposeResult:
            ok, status_text = _inspect_image(init_clean)
            status_cls = "status-ok" if ok else ("status-err" if init_clean else "status-dim")
            default_set = set(STANDARD_ICO_SIZES)

            with Container(id="studio-card"):
                yield StudioHeader("🎨 ifc  [dim #6b7280]·  Image Format Converter[/]")
                with VerticalScroll(id="studio-scroll"):

                    with Horizontal(classes="field-header"):
                        yield Static("Image", classes="field-label")
                        yield Static(status_text, id="img-status", classes=status_cls)

                    yield Input(
                        value=init_clean,
                        placeholder="Path or drop image (png, jpg, webp, bmp, gif, tiff, avif, ico)...",
                        id="src-input",
                        classes="cyber-input",
                    )

                    if local_images:
                        with Vertical(classes="local-files"):
                            yield Static("Files:", classes="field-label")
                            for idx, img_p in enumerate(local_images):
                                yield ActionChip(
                                    escape(os.path.basename(img_p)),
                                    value=img_p,
                                    variant_class="-file",
                                    id=f"pick-{idx}",
                                    tooltip=img_p,
                                )

                    fmt_keys = list(FORMAT_SPECS.keys())
                    with Horizontal(classes="compact-tight option-row"):
                        yield Static("To:   ", classes="field-label")
                        for key in fmt_keys[:4]:
                            spec = FORMAT_SPECS[key]
                            yield ToggleChip(spec.label, value=key, active=(key == "ico"), id=f"fmt-{key}")
                    with Horizontal(classes="compact-row option-row"):
                        yield Static("      ", classes="field-label")
                        for key in fmt_keys[4:]:
                            spec = FORMAT_SPECS[key]
                            yield ToggleChip(spec.label, value=key, active=False, id=f"fmt-{key}")

                    with Vertical(id="ico-section"):
                        with Horizontal(classes="compact-tight option-row"):
                            yield Static("ICO:  ", classes="field-label")
                            yield ActionChip("Std", value=STANDARD_ICO_SIZES, variant_class="-preset", id="pre-std")
                            yield ActionChip("All", value=ALL_ICO_SIZES, variant_class="-preset", id="pre-all")
                            yield ActionChip("Web", value=FAVICON_ICO_SIZES, variant_class="-preset", id="pre-fav")
                            yield ToggleChip("Sharpen ≤32px", value="sharpen", active=True, id="opt-sharpen")

                        with Horizontal(classes="compact-tight option-row"):
                            yield Static("Sizes:", classes="field-label")
                            for s in ALL_ICO_SIZES[:5]:
                                yield ToggleChip(str(s), value=s, active=(s in default_set), id=f"sz-{s}")
                        with Horizontal(classes="compact-row option-row"):
                            yield Static("      ", classes="field-label")
                            for s in ALL_ICO_SIZES[5:]:
                                yield ToggleChip(str(s), value=s, active=(s in default_set), id=f"sz-{s}")
                            yield Static(f"{len(STANDARD_ICO_SIZES)}", id="layer-count", classes="status-ok")

                    with Horizontal(id="quality-section", classes="compact-row option-row hidden-section"):
                        yield Static("Qual: ", classes="field-label")
                        for q in (80, 90, 92, 95, 100):
                            yield ToggleChip(f"{q}%", value=q, active=(q == 92), id=f"qual-{q}")

                    with Horizontal(classes="compact-tight"):
                        yield Static("Out:  ", classes="field-label")
                        yield Input(
                            placeholder="<source>.ico",
                            id="out-input",
                            classes="cyber-slim",
                        )

                yield Static("", id="form-error", classes="hidden-err", markup=False)

                with Horizontal(classes="action-bar"):
                    yield ActionChip("⚡ Convert", variant_class="-primary", id="btn-run")
                    yield ActionChip("✕ Cancel", variant_class="-danger", id="btn-cancel")

        def on_mount(self) -> None:
            self.screen.set_class(self.size.width < 76, "narrow")
            if init_clean:
                self.query_one("#btn-run", ActionChip).focus()

        def on_resize(self, event) -> None:
            self.screen.set_class(event.size.width < 76, "narrow")

        def _active_format(self) -> str:
            for chip in self.query(ToggleChip):
                if chip.id and chip.id.startswith("fmt-") and chip.active:
                    return str(chip.value)
            return "ico"

        def _active_quality(self) -> int:
            for chip in self.query(ToggleChip):
                if chip.id and chip.id.startswith("qual-") and chip.active:
                    return int(chip.value)
            return 92

        def _sync_mode_sections(self, target_fmt: str) -> None:
            spec = FORMAT_SPECS[target_fmt]
            ico_sec = self.query_one("#ico-section", Vertical)
            qual_sec = self.query_one("#quality-section", Horizontal)
            out_input = self.query_one("#out-input", Input)

            ico_sec.set_class(target_fmt != "ico", "hidden-section")
            qual_sec.set_class(not spec.supports_quality, "hidden-section")
            out_input.placeholder = f"<source>{spec.ext}"

        def _update_layer_count(self) -> list[int]:
            selected = [
                chip.value
                for chip in self.query(ToggleChip)
                if chip.id and chip.id.startswith("sz-") and chip.active
            ]
            counter = self.query_one("#layer-count", Static)
            if selected:
                counter.update(f"({len(selected)})")
                counter.set_classes("status-ok")
            else:
                counter.update("(0!)")
                counter.set_classes("status-err")
            return sorted(selected)

        def _refresh_image_status(self, path_val: str) -> None:
            ok, msg = _inspect_image(path_val)
            badge = self.query_one("#img-status", Static)
            badge.update(msg)
            if ok:
                badge.set_classes("status-ok")
            elif _clean_path(path_val):
                badge.set_classes("status-err")
            else:
                badge.set_classes("status-dim")

        def _set_error(self, message: str = "") -> None:
            err_widget = self.query_one("#form-error", Static)
            err_widget.update(message)
            err_widget.set_classes("shown-err" if message else "hidden-err")

        def on_input_changed(self, event: Input.Changed) -> None:
            if event.input.id == "src-input":
                self._refresh_image_status(event.value)
                self._set_error("")

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "src-input":
                ok, _ = _inspect_image(event.value)
                if ok:
                    self.query_one("#btn-run", ActionChip).focus()
            elif event.input.id == "out-input":
                self._submit()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            btn = event.button
            bid = btn.id or ""
            self._set_error("")

            if bid.startswith("fmt-"):
                for chip in self.query(ToggleChip):
                    if chip.id and chip.id.startswith("fmt-"):
                        chip.active = (chip.id == bid)
                self._sync_mode_sections(str(btn.value))
                return

            if bid.startswith("qual-"):
                for chip in self.query(ToggleChip):
                    if chip.id and chip.id.startswith("qual-"):
                        chip.active = (chip.id == bid)
                return

            if isinstance(btn, ToggleChip):
                btn.active = not btn.active
                if bid.startswith("sz-"):
                    self._update_layer_count()
                return

            if bid.startswith("pick-"):
                src_input = self.query_one("#src-input", Input)
                src_input.value = btn.value
                self._refresh_image_status(btn.value)
            elif bid.startswith("pre-"):
                preset_set = set(btn.value)
                for chip in self.query(ToggleChip):
                    if chip.id and chip.id.startswith("sz-"):
                        chip.active = chip.value in preset_set
                self._update_layer_count()
            elif bid == "btn-run":
                self._submit()
            elif bid == "btn-cancel":
                self.exit(None)

        def _submit(self) -> None:
            raw_src = self.query_one("#src-input", Input).value
            clean_src = _clean_path(raw_src)
            ok, msg = _inspect_image(clean_src)

            if not clean_src:
                self._set_error("Please enter, drop, or pick a source image.")
                self.query_one("#src-input", Input).focus()
                return
            if not ok:
                self._set_error(f"Invalid source image: {msg}")
                self.query_one("#src-input", Input).focus()
                return

            target_fmt = self._active_format()
            selected_sizes = self._update_layer_count()
            if target_fmt == "ico" and not selected_sizes:
                self._set_error("Select at least one ICO layer size.")
                return

            sharpen_chip = self.query_one("#opt-sharpen", ToggleChip)
            raw_out = _clean_path(self.query_one("#out-input", Input).value)
            out_path = os.path.abspath(raw_out) if raw_out else None
            if out_path:
                output_ext = _normalize_format(os.path.splitext(out_path)[1])
                if _same_file(clean_src, out_path):
                    self._set_error("Output path must differ from the source image.")
                elif os.path.isdir(out_path):
                    self._set_error("Choose an output file path, not a directory.")
                elif output_ext and output_ext != target_fmt:
                    self._set_error(f"Output extension must match the selected {target_fmt.upper()} format.")
                else:
                    self._set_error("")
                if self.query_one("#form-error", Static).has_class("shown-err"):
                    self.query_one("#out-input", Input).focus()
                    return
            self.exit(
                (
                    os.path.abspath(clean_src),
                    target_fmt,
                    selected_sizes,
                    out_path,
                    sharpen_chip.active,
                    self._active_quality(),
                )
            )

    return IfcStudioApp()


def _launch_ifc_studio(initial_path: str = "") -> tuple[str, str, list[int], str | None, bool, int] | None:
    """Launch the Cyber-Dark clickable Image Format Converter Studio inside the terminal."""
    app = _build_ifc_studio_app(initial_path=initial_path)
    result = app.run(mouse=True)
    sys.stdout.flush()
    return result


class IfcEngine(BaseEngine):
    name = "ifc"
    description = "Image Format Converter (Pillow)"
    usage = "tt ifc | tt ifc <image> [-t fmt] [-s sizes] [-o output]"
    category = "Media & Image"
    requires = ["Pillow>=9.0.0"]
    help_text = IFC_HELP_TEXT

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("image", nargs="?", default="", help="Source image path (png, jpg, webp, bmp, gif, tiff, avif, ico, ...)")
        parser.add_argument(
            "-t", "--to",
            default="",
            help="Target format: ico, png, jpg, webp, bmp, gif, tiff, avif (auto-detected from -o or defaults to ico)",
        )
        parser.add_argument("-s", "--sizes", default="16,32,48,64,128,256", help="Comma-separated ICO layer sizes, 8-256 pixels (when output is ico)")
        parser.add_argument("-q", "--quality", type=int, default=92, help="Output quality 1-100 for jpg/webp/avif (default: 92)")
        parser.add_argument("-o", "--output", help="Output file path")
        parser.add_argument("--no-sharpen", action="store_true", help="Disable edge sharpening on small ICO layers (<=32px)")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        img_path = _clean_path(getattr(args, "image", "") or "")
        if not img_path:
            return self.run_interactive(console)

        img_path = os.path.abspath(img_path)
        out_arg = _clean_path(getattr(args, "output", None) or "") or None
        explicit_to = _normalize_format(getattr(args, "to", "") or "")

        if explicit_to:
            if explicit_to not in FORMAT_SPECS:
                print_error(f"Unsupported format '{explicit_to}'. Supported: {', '.join(FORMAT_SPECS)}")
                return 1
            target_fmt = explicit_to
        elif out_arg:
            out_ext = _normalize_format(os.path.splitext(out_arg)[1])
            target_fmt = out_ext if out_ext in FORMAT_SPECS else "ico"
        else:
            target_fmt = "ico"

        sizes = list(STANDARD_ICO_SIZES)
        if target_fmt == "ico":
            try:
                sizes = _parse_ico_sizes(getattr(args, "sizes", "16,32,48,64,128,256"))
            except ValueError as exc:
                print_error(str(exc))
                return 1

        sharpen = not getattr(args, "no_sharpen", False)
        quality = getattr(args, "quality", 92)
        return self._convert_image(img_path, target_fmt, sizes, out_arg, sharpen, quality, console)

    def launch_with_path(self, console: Console, path: str) -> int:
        """Open interactive clickable Studio pre-loaded with a dropped or positional image."""
        from pykuai.core.tui import is_interactive_tty

        if is_interactive_tty():
            return self.run_interactive(console, initial_path=path)
        return self._convert_image(
            os.path.abspath(_clean_path(path)),
            "ico",
            list(STANDARD_ICO_SIZES),
            None,
            True,
            92,
            console,
        )

    def run_interactive(self, console: Console, initial_path: str = "") -> int:
        from pykuai.core.tui import is_interactive_tty

        if is_interactive_tty():
            selection = _launch_ifc_studio(initial_path=initial_path)
            if not selection:
                console.print("[dim]› Cancelled.[/dim]")
                return 0
            img_path, target_fmt, sizes, out_path, sharpen, quality = selection
            return self._convert_image(img_path, target_fmt, sizes, out_path, sharpen, quality, console)

        if sys.stdin is None or not sys.stdin.isatty():
            print_error("Interactive input is unavailable. Pass a source path and options: pykuai tt ifc <image> [-t format].")
            return 1

        # Rich prompts still work when stdin is a terminal and stdout is redirected.
        console.print("[bold #FF9800]🎨 Image Format Converter (ifc)[/bold #FF9800]")
        try:
            img_input = initial_path or Prompt.ask("[#10b981]?[/#10b981] Source image path")
            img_path = os.path.abspath(_clean_path(img_input))

            target_raw = Prompt.ask(
                "[#10b981]?[/#10b981] Target format",
                choices=list(FORMAT_SPECS.keys()),
                default="ico",
            )
            target_fmt = _normalize_format(target_raw)
            sizes = list(STANDARD_ICO_SIZES)
            if target_fmt == "ico":
                sizes_input = Prompt.ask(
                    "[#10b981]?[/#10b981] Packaging sizes (comma-separated)",
                    default="16,32,48,64,128,256",
                )
                sizes = _parse_ico_sizes(sizes_input)
        except EOFError:
            print_error("Input ended before conversion options were supplied.")
            return 1
        except ValueError as exc:
            print_error(str(exc))
            return 1

        return self._convert_image(img_path, target_fmt, sizes, None, True, 92, console)

    def _convert_image(
        self,
        img_path: str,
        target_fmt: str,
        sizes: list[int],
        out_path: Optional[str],
        sharpen: bool,
        quality: int,
        console: Console,
    ) -> int:
        try:
            from PIL import Image, ImageFilter, ImageOps
        except ImportError:
            print_error("Missing dependency 'pillow'. Run: pip install pillow")
            return 1

        spec = FORMAT_SPECS.get(_normalize_format(target_fmt))
        if not spec:
            print_error(f"Unsupported target format: {escape(target_fmt)}")
            return 1

        img_path = os.path.abspath(_clean_path(img_path))
        if not os.path.isfile(img_path):
            print_error(f"File not found: {escape(img_path)}")
            return 1

        Image.init()
        if spec.pillow_fmt not in Image.SAVE:
            print_error(f"Installed Pillow cannot write {spec.label}. Install a Pillow build with {spec.label} support.")
            return 1

        if not out_path:
            base_dir = os.path.dirname(img_path)
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            out_path = os.path.join(base_dir, f"{base_name}{spec.ext}")
            if _same_file(img_path, out_path):
                out_path = os.path.join(base_dir, f"{base_name}_converted{spec.ext}")
        else:
            out_path = os.path.abspath(_clean_path(out_path))

        if _same_file(img_path, out_path):
            print_error("Output path must differ from the source image.")
            return 1

        output_ext = _normalize_format(os.path.splitext(out_path)[1])
        raw_output_ext = os.path.splitext(out_path)[1]
        if raw_output_ext and output_ext != spec.key:
            print_error(f"Output extension '{escape(raw_output_ext)}' does not match target format '{spec.key}'.")
            return 1

        if not isinstance(quality, int) or not 1 <= quality <= 100:
            print_error("Quality must be a whole number between 1 and 100.")
            return 1
        try:
            sorted_sizes = _validate_ico_sizes(sizes) if spec.key == "ico" else []
        except ValueError as exc:
            print_error(str(exc))
            return 1

        out_dir = os.path.dirname(out_path)
        temporary_path = None

        print_step(f"Reading image: [bold]{escape(os.path.basename(img_path))}[/bold]")

        try:
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with console.status(f"[bold #10b981]Converting to {spec.label}...[/bold #10b981]"):
                with Image.open(img_path) as raw:
                    src_fmt = raw.format or "IMG"
                    if src_fmt not in {"ICO", "ICNS"} and getattr(raw, "n_frames", 1) > 1:
                        print_warning("Source contains multiple frames/pages; only the first will be converted.")
                    src_im = ImageOps.exif_transpose(_pick_highest_res_frame(raw))

                if spec.key == "ico":
                    rgba = src_im.convert("RGBA")
                    resampling = getattr(Image, "Resampling", Image).LANCZOS
                    layers = []
                    for s in sorted(sorted_sizes, reverse=True):
                        # Pad at output resolution, so a long thin source never
                        # allocates a source-width-squared intermediate image.
                        scale = s / max(rgba.size)
                        fitted_size = (max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale)))
                        fitted = rgba.resize(fitted_size, resampling)
                        layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
                        layer.paste(fitted, ((s - fitted.width) // 2, (s - fitted.height) // 2))
                        if sharpen and s <= 32:
                            layer = layer.filter(ImageFilter.UnsharpMask(radius=0.8, percent=80, threshold=2))
                        layers.append(layer)

                    out_im = layers[0]
                    save_kwargs: dict[str, object] = {
                        "format": "ICO",
                        "sizes": [(s, s) for s in sorted_sizes],
                        "append_images": layers[1:],
                    }
                    detail_line = f"Sizes:  [bold #FF9800]{', '.join(str(s) for s in sorted_sizes)}[/bold #FF9800]"
                else:
                    out_im = src_im.convert("RGBA") if spec.supports_alpha else _flatten_rgba_to_rgb(src_im)
                    save_kwargs = {"format": spec.pillow_fmt}
                    if spec.supports_quality:
                        save_kwargs["quality"] = quality
                    detail_line = f"Format: [bold #FF9800]{src_fmt} → {spec.label}[/bold #FF9800]"
                    if spec.supports_quality:
                        detail_line += f"  [dim](q={quality})[/dim]"

                # Encode completely beside the target before replacing it. A
                # failed encoder or interrupted conversion leaves old output intact.
                with tempfile.NamedTemporaryFile(
                    mode="w+b", prefix=".ifc-", suffix=spec.ext, dir=out_dir, delete=False,
                ) as temporary:
                    temporary_path = temporary.name
                    out_im.save(temporary, **save_kwargs)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                file_size_kb = os.path.getsize(temporary_path) / 1024
                os.replace(temporary_path, out_path)
                temporary_path = None

            card = (
                f"[bold #00FF00]✅ Converted to {spec.label}[/bold #00FF00]\n"
                f"  [bold #E0E0E0]Out:[/bold #E0E0E0]    [bold #00FF00]{escape(out_path)}[/bold #00FF00]\n"
                f"  [bold #E0E0E0]{detail_line}[/bold #E0E0E0]  [dim]({file_size_kb:.1f} KB)[/dim]"
            )
            console.print()
            console.print(Panel(card, border_style="#10b981", box=box.ROUNDED, expand=False))
            return 0
        except Exception as e:
            print_error(f"Conversion failed: {escape(str(e))}")
            return 1
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
