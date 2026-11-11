# -*- coding: utf-8 -*-
"""
PNG / Image to Multi-Resolution Windows ICO Container Engine
"""
from __future__ import annotations

import argparse
import os
import sys
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from pykuai.core.base import BaseEngine
from pykuai.core.ui import print_error, print_step

ALL_ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
STANDARD_ICO_SIZES = [16, 32, 48, 64, 128, 256]
FAVICON_ICO_SIZES = [16, 32, 48]
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def _clean_path(raw: str) -> str:
    """Clean dragged/pasted paths by stripping whitespace and surrounding quotes."""
    return raw.strip().strip("\"'")


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
    """Inspect image metadata lazily without full pixel decoding."""
    clean = _clean_path(path)
    if not clean:
        return False, "Drop, paste, or pick an image"
    abs_p = os.path.abspath(clean)
    if not os.path.isfile(abs_p):
        return False, "File not found"
    try:
        from PIL import Image

        with Image.open(abs_p) as im:
            fmt = im.format or "IMG"
            return True, f"✓ {im.width}×{im.height} · {im.mode} · {fmt}"
    except Exception:
        return False, "Unreadable image format"


def _build_ico_studio_app(initial_path: str = ""):
    """Construct the Cyber-Dark clickable ICO Studio Textual App (lazy-loaded)."""
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal, VerticalScroll
    from textual.widgets import Button, Input, Static
    from pykuai.core.tui import ActionChip, PyKuaiStudioApp, ToggleChip

    local_images = _discover_local_images(limit=5)
    init_clean = os.path.abspath(_clean_path(initial_path)) if _clean_path(initial_path) else ""

    class IcoStudioApp(PyKuaiStudioApp):
        def compose(self) -> ComposeResult:
            ok, status_text = _inspect_image(init_clean)
            status_cls = "status-ok" if ok else ("status-err" if init_clean else "status-dim")

            with Container(id="studio-card"):
                with VerticalScroll(id="studio-scroll"):
                    yield Static(
                        "🎨 ICO Container Studio  [dim #6b7280]•  Click sizes & presets  •  Drop or pick image[/]",
                        classes="studio-title",
                    )

                    with Horizontal(classes="field-header"):
                        yield Static("Source Image", classes="field-label")
                        yield Static(status_text, id="img-status", classes=status_cls)

                    yield Input(
                        value=init_clean,
                        placeholder="Drag & drop image path here or type file path...",
                        id="src-input",
                        classes="cyber-input",
                    )

                    if local_images:
                        with Horizontal(classes="compact-row"):
                            yield Static("Quick Pick:", classes="field-label")
                            for idx, img_p in enumerate(local_images):
                                yield ActionChip(
                                    f"📄 {os.path.basename(img_p)}",
                                    value=img_p,
                                    variant_class="-file",
                                    id=f"pick-{idx}",
                                )

                    with Horizontal(classes="compact-row"):
                        yield Static("Presets:", classes="field-label")
                        yield ActionChip("Standard (6)", value=STANDARD_ICO_SIZES, variant_class="-preset", id="pre-std")
                        yield ActionChip("High-DPI (9)", value=ALL_ICO_SIZES, variant_class="-preset", id="pre-all")
                        yield ActionChip("Favicon (3)", value=FAVICON_ICO_SIZES, variant_class="-preset", id="pre-fav")
                        yield ActionChip("Clear", value=[], variant_class="-preset", id="pre-clr")

                    with Horizontal(classes="field-header"):
                        yield Static("Layer Sizes:", classes="field-label")
                        yield Static(f"Selected: {len(STANDARD_ICO_SIZES)} layers", id="layer-count", classes="status-ok")

                    default_set = set(STANDARD_ICO_SIZES)
                    with Horizontal(classes="compact-tight"):
                        for s in ALL_ICO_SIZES[:5]:
                            yield ToggleChip(f"{s}×{s}", value=s, active=(s in default_set), id=f"sz-{s}")
                    with Horizontal(classes="compact-row"):
                        for s in ALL_ICO_SIZES[5:]:
                            yield ToggleChip(f"{s}×{s}", value=s, active=(s in default_set), id=f"sz-{s}")

                    with Horizontal(classes="compact-row"):
                        yield Static("Options:", classes="field-label")
                        yield ToggleChip(
                            "Crisp Edge Sharpening (≤32px)",
                            value="sharpen",
                            active=True,
                            id="opt-sharpen",
                        )

                    with Horizontal(classes="compact-tight"):
                        yield Static("Output Path:", classes="field-label")
                        yield Input(
                            placeholder="(Auto: <source>.ico — optional custom path)",
                            id="out-input",
                            classes="cyber-slim",
                        )

                yield Static("", id="form-error", classes="hidden-err")

                with Horizontal(classes="action-bar"):
                    yield ActionChip("⚡ Package ICO", variant_class="-primary", id="btn-run")
                    yield ActionChip("✕ Cancel (Esc)", variant_class="-danger", id="btn-cancel")

        def on_mount(self) -> None:
            if init_clean:
                self.query_one("#btn-run", ActionChip).focus()

        def _update_layer_count(self) -> list[int]:
            selected = [
                chip.value
                for chip in self.query(ToggleChip)
                if chip.id and chip.id.startswith("sz-") and chip.active
            ]
            counter = self.query_one("#layer-count", Static)
            if selected:
                counter.update(f"Selected: {len(selected)} layer(s)")
                counter.set_classes("status-ok")
            else:
                counter.update("Select at least 1 size")
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
            self._set_error("")

            if isinstance(btn, ToggleChip):
                btn.active = not btn.active
                if btn.id and btn.id.startswith("sz-"):
                    self._update_layer_count()
            elif btn.id and btn.id.startswith("pick-"):
                src_input = self.query_one("#src-input", Input)
                src_input.value = btn.value
                self._refresh_image_status(btn.value)
            elif btn.id and btn.id.startswith("pre-"):
                preset_set = set(btn.value)
                for chip in self.query(ToggleChip):
                    if chip.id and chip.id.startswith("sz-"):
                        chip.active = chip.value in preset_set
                self._update_layer_count()
            elif btn.id == "btn-run":
                self._submit()
            elif btn.id == "btn-cancel":
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

            selected_sizes = self._update_layer_count()
            if not selected_sizes:
                self._set_error("Select at least one ICO layer size.")
                return

            sharpen_chip = self.query_one("#opt-sharpen", ToggleChip)
            raw_out = _clean_path(self.query_one("#out-input", Input).value)
            out_path = os.path.abspath(raw_out) if raw_out else None
            self.exit((os.path.abspath(clean_src), selected_sizes, out_path, sharpen_chip.active))

    return IcoStudioApp()


def _launch_ico_studio(initial_path: str = "") -> tuple[str, list[int], str | None, bool] | None:
    """Launch the Cyber-Dark clickable ICO Studio inside the terminal."""
    app = _build_ico_studio_app(initial_path=initial_path)
    result = app.run(mouse=True)
    sys.stdout.flush()
    return result


class IcoMakerEngine(BaseEngine):
    name = "ico"
    description = "Convert PNG/image to multi-resolution Windows ICO container"
    usage = "tt ico | tt ico <image> [-s sizes] [-o output]"
    category = "Media & Image"
    requires = ["Pillow>=9.0.0"]

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("image", nargs="?", default="", help="Source image path (high-res transparent PNG recommended)")
        parser.add_argument("-s", "--sizes", default="16,32,48,64,128,256", help="Comma-separated ICO layer sizes")
        parser.add_argument("-o", "--output", help="Output .ico file path (defaults to source filename)")
        parser.add_argument("--no-sharpen", action="store_true", help="Disable edge sharpening on small layers (<=32px)")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        img_path = _clean_path(getattr(args, "image", "") or "")
        if not img_path:
            return self.run_interactive(console)

        img_path = os.path.abspath(img_path)
        try:
            sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip().isdigit()]
        except Exception:
            sizes = list(STANDARD_ICO_SIZES)
        if not sizes:
            sizes = list(STANDARD_ICO_SIZES)

        sharpen = not getattr(args, "no_sharpen", False)
        return self._make_ico(img_path, sizes, getattr(args, "output", None), sharpen, console)

    def launch_with_path(self, console: Console, path: str) -> int:
        """Open interactive clickable Studio pre-loaded with a dropped or positional image."""
        from pykuai.core.tui import is_interactive_tty

        if is_interactive_tty():
            return self.run_interactive(console, initial_path=path)
        return self._make_ico(os.path.abspath(_clean_path(path)), list(STANDARD_ICO_SIZES), None, True, console)

    def run_interactive(self, console: Console, initial_path: str = "") -> int:
        from pykuai.core.tui import is_interactive_tty

        if is_interactive_tty():
            selection = _launch_ico_studio(initial_path=initial_path)
            if not selection:
                console.print("[dim]› Cancelled.[/dim]")
                return 0
            img_path, sizes, out_path, sharpen = selection
            return self._make_ico(img_path, sizes, out_path, sharpen, console)

        # Fallback text prompt for non-TTY / piped test environments
        console.print("[bold #FF9800]🎨 Launch PNG to Multi-size ICO Container Engine[/bold #FF9800]")
        img_input = initial_path or Prompt.ask("[#10b981]?[/#10b981] Source image path")
        img_path = os.path.abspath(_clean_path(img_input))

        sizes_input = Prompt.ask(
            "[#10b981]?[/#10b981] Packaging sizes (comma-separated)",
            default="16,32,48,64,128,256",
        )
        try:
            sizes = [int(s.strip()) for s in sizes_input.split(",") if s.strip().isdigit()]
        except Exception:
            sizes = list(STANDARD_ICO_SIZES)
        if not sizes:
            sizes = list(STANDARD_ICO_SIZES)

        return self._make_ico(img_path, sizes, None, True, console)

    def _make_ico(
        self,
        img_path: str,
        sizes: list[int],
        out_path: str | None,
        sharpen: bool,
        console: Console,
    ) -> int:
        try:
            from PIL import Image, ImageFilter
        except ImportError:
            print_error("Missing dependency 'pillow'. Run: pip install pillow")
            return 1

        if not os.path.isfile(img_path):
            print_error(f"File not found: {img_path}")
            return 1

        if not out_path:
            base_dir = os.path.dirname(img_path)
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            out_path = os.path.join(base_dir, f"{base_name}.ico")
        else:
            out_path = os.path.abspath(_clean_path(out_path))

        sorted_sizes = sorted(set(s for s in sizes if 8 <= s <= 512))
        if not sorted_sizes:
            sorted_sizes = list(STANDARD_ICO_SIZES)

        print_step(f"Reading image: [bold]{os.path.basename(img_path)}[/bold]")

        try:
            with console.status("[bold #10b981]Resampling layers and packaging ICO container...[/bold #10b981]"):
                with Image.open(img_path) as raw:
                    im = raw.convert("RGBA")

                # Preserve aspect ratio by centering non-square images on a transparent square canvas
                if im.width != im.height:
                    side = max(im.size)
                    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                    square.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
                else:
                    square = im

                # Generate largest layer first so Pillow's ICO writer retains every selected dimension
                layers = []
                for s in sorted(sorted_sizes, reverse=True):
                    layer = square.resize((s, s), Image.Resampling.LANCZOS)
                    if sharpen and s <= 32:
                        layer = layer.filter(ImageFilter.UnsharpMask(radius=0.8, percent=80, threshold=2))
                    layers.append(layer)

                icon_sizes = [(s, s) for s in sorted_sizes]
                layers[0].save(
                    out_path,
                    format="ICO",
                    sizes=icon_sizes,
                    append_images=layers[1:],
                )

            file_size_kb = os.path.getsize(out_path) / 1024
            filter_label = "Lanczos + Edge Sharpen (≤32px)" if sharpen else "Lanczos Clean"

            card = (
                "[bold #00FF00]✅ ICO Container Packaged Successfully[/bold #00FF00]\n\n"
                f"  [dim]•[/dim] [bold #E0E0E0]Source File:[/bold #E0E0E0]  [dim]{img_path}[/dim]\n"
                f"  [dim]•[/dim] [bold #E0E0E0]Export Path:[/bold #E0E0E0]  [bold #00FF00]{out_path}[/bold #00FF00]\n"
                f"  [dim]•[/dim] [bold #E0E0E0]Layer Sizes:[/bold #E0E0E0]  [bold #FF9800]{', '.join(f'{s}x{s}' for s in sorted_sizes)}[/bold #FF9800]\n"
                f"  [dim]•[/dim] [bold #E0E0E0]Resampling:[/bold #E0E0E0]   [bold #10b981]{filter_label}[/bold #10b981]\n"
                f"  [dim]•[/dim] [bold #E0E0E0]File Size:[/bold #E0E0E0]    [bold #38BDF8]{file_size_kb:.1f} KB[/bold #38BDF8]"
            )
            console.print()
            console.print(Panel(card, border_style="#10b981", box=box.ROUNDED, expand=False))
            return 0
        except Exception as e:
            print_error(f"Packaging failed: {e}")
            return 1
