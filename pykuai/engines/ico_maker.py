# -*- coding: utf-8 -*-
"""
PNG 转多分辨率 Windows ICO 图标容器引擎 (多语言支持)
"""
import os
import argparse
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich import box
from pykuai.core.base import BaseEngine
from pykuai.core.i18n import t
from pykuai.core.ui import print_success, print_error, print_warning, print_info, print_step


class IcoMakerEngine(BaseEngine):
    name = "ico"
    aliases = ["make-ico", "to-ico", "png2ico"]
    category = "多媒体与图像"

    @property
    def description(self) -> str:
        return t("help_ico_desc")

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("image", nargs="?", default="", help="待封装的源图片路径 (建议高分辨率透明底 PNG)")
        parser.add_argument("-s", "--sizes", default="16,32,48,64,128,256", help="封装进 ICO 的尺寸列表，逗号分隔")
        parser.add_argument("-o", "--output", help="输出的 .ico 文件路径 (默认同名)")

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
        console.print(f"[bold #FF9800]{t('ico_title')}[/bold #FF9800]")
        console.print(f"[dim]{t('ico_desc')}[/dim]\n")

        img_input = Prompt.ask(t("ico_input_path"))
        img_path = os.path.abspath(img_input.strip('\"\''))

        sizes_input = Prompt.ask(
            t("ico_input_sizes"),
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
            print_error("缺少 pillow 依赖库！请运行: pip install pillow")
            return 1

        if not os.path.isfile(img_path):
            print_error(f"源图片不存在 / File not found: {img_path}")
            return 1

        if not out_path:
            base_dir = os.path.dirname(img_path)
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            out_path = os.path.join(base_dir, f"{base_name}.ico")

        icon_sizes = [(s, s) for s in sorted(sizes)]
        print_step(t("ico_reading", filename=os.path.basename(img_path)))

        try:
            with console.status(f"[bold #10b981]{t('ico_status')}[/bold #10b981]"):
                img = Image.open(img_path).convert("RGBA")
                img.save(out_path, format="ICO", sizes=icon_sizes)

            file_size_kb = os.path.getsize(out_path) / 1024

            card = (
                f"[bold #00FF00]{t('ico_success')}[/bold #00FF00]\n\n"
                f"  [dim]•[/dim] [bold #E0E0E0]{t('ico_card_src')}[/bold #E0E0E0]   [dim]{img_path}[/dim]\n"
                f"  [dim]•[/dim] [bold #E0E0E0]{t('ico_card_dst')}[/bold #E0E0E0] [bold #00FF00]{out_path}[/bold #00FF00]\n"
                f"  [dim]•[/dim] [bold #E0E0E0]{t('ico_card_layers')}[/bold #E0E0E0] [bold #FF9800]{', '.join(f'{s}x{s}' for s in sorted(sizes))}[/bold #FF9800]\n"
                f"  [dim]•[/dim] [bold #E0E0E0]{t('ico_card_size')}[/bold #E0E0E0] [bold #38BDF8]{file_size_kb:.1f} KB[/bold #38BDF8]"
            )
            console.print()
            console.print(Panel(card, border_style="#10b981", box=box.ROUNDED, expand=False))
            return 0
        except Exception as e:
            print_error(f"封装失败: {e}")
            return 1
