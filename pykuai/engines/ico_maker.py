# -*- coding: utf-8 -*-
"""
PNG to Multi-Resolution Windows ICO Container Engine
"""
import os
import argparse
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich import box
from pykuai.core.base import BaseEngine
from pykuai.core.ui import print_error, print_step


class IcoMakerEngine(BaseEngine):
    name = "ico"
    description = "Convert PNG to multi-resolution Windows ICO container"
    usage = "ico <image> [-s sizes] [-o output]"
    category = "Media & Image"

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("image", nargs="?", default="", help="Source image path (high-res transparent PNG recommended)")
        parser.add_argument("-s", "--sizes", default="16,32,48,64,128,256", help="Comma-separated ICO layer sizes")
        parser.add_argument("-o", "--output", help="Output .ico file path (defaults to source filename)")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        img_path = getattr(args, "image", "") or ""
        img_path = img_path.strip('\"\'')
        if not img_path:
            return self.run_interactive(console)

        img_path = os.path.abspath(img_path)
        try:
            sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip().isdigit()]
        except Exception:
            sizes = [16, 32, 48, 64, 128, 256]
        return self._make_ico(img_path, sizes, getattr(args, "output", None), console)

    def run_interactive(self, console: Console) -> int:
        console.print("[bold #FF9800]🎨 Launch PNG to Multi-size ICO Container Engine[/bold #FF9800]")
        console.print("[dim]Resample and package 16x16 to 256x256 full layers for Windows High-DPI display.[/dim]\n")

        img_input = Prompt.ask("[#10b981]?[/#10b981] Source image path (drag & drop supported)")
        img_path = os.path.abspath(img_input.strip('\"\''))

        sizes_input = Prompt.ask(
            "[#10b981]?[/#10b981] Packaging sizes (comma-separated)",
            default="16,32,48,64,128,256"
        )
        try:
            sizes = [int(s.strip()) for s in sizes_input.split(",") if s.strip().isdigit()]
        except Exception:
            sizes = [16, 32, 48, 64, 128, 256]

        return self._make_ico(img_path, sizes, None, console)

    def _make_ico(self, img_path: str, sizes: list[int], out_path: str | None, console: Console) -> int:
        try:
            from PIL import Image
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

        icon_sizes = [(s, s) for s in sorted(sizes)]
        print_step(f"Reading image: [bold]{os.path.basename(img_path)}[/bold]")

        try:
            with console.status("[bold #10b981]Resampling layers and packaging ICO container...[/bold #10b981]"):
                img = Image.open(img_path).convert("RGBA")
                img.save(out_path, format="ICO", sizes=icon_sizes)

            file_size_kb = os.path.getsize(out_path) / 1024

            card = (
                "[bold #00FF00]✅ ICO Container Packaged Successfully[/bold #00FF00]\n\n"
                f"  [dim]•[/dim] [bold #E0E0E0]Source File:[/bold #E0E0E0]   [dim]{img_path}[/dim]\n"
                f"  [dim]•[/dim] [bold #E0E0E0]Export Path:[/bold #E0E0E0] [bold #00FF00]{out_path}[/bold #00FF00]\n"
                f"  [dim]•[/dim] [bold #E0E0E0]Layer Sizes:[/bold #E0E0E0] [bold #FF9800]{', '.join(f'{s}x{s}' for s in sorted(sizes))}[/bold #FF9800]\n"
                f"  [dim]•[/dim] [bold #E0E0E0]File Size:[/bold #E0E0E0] [bold #38BDF8]{file_size_kb:.1f} KB[/bold #38BDF8]"
            )
            console.print()
            console.print(Panel(card, border_style="#10b981", box=box.ROUNDED, expand=False))
            return 0
        except Exception as e:
            print_error(f"Packaging failed: {e}")
            return 1
