# -*- coding: utf-8 -*-
"""
万能图片压缩引擎 (尺寸重采样 + 画质压缩 + 格式兼容)
"""
import os
import argparse
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from pykuai.core.base import BaseEngine
from pykuai.core.ui import print_success, print_error, print_warning, print_info, print_step, create_progress


def format_size(size_bytes: int) -> str:
    if size_bytes > 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    return f"{size_bytes / 1024:.2f} KB"


class ImgCompressEngine(BaseEngine):
    name = "img-compress"
    aliases = ["compress-img", "pic-min"]
    description = "万能图片压缩引擎 (智能高保真下采样 + 画质压缩 + 格式自适应)"
    category = "多媒体与图像"

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("path", help="待压缩的图片文件或目录路径")
        parser.add_argument("-s", "--scale", type=int, default=100, help="尺寸缩放百分比 (10-100，默认 100)")
        parser.add_argument("-q", "--quality", type=int, default=80, help="输出画质百分比 (1-100，默认 80)")
        parser.add_argument("-o", "--output", help="输出路径 (文件或目录)")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        target_path = os.path.abspath(args.path.strip('\"\''))
        return self._compress(target_path, args.scale, args.quality, args.output, console)

    def run_interactive(self, console: Console) -> int:
        console.print("[bold #FF9800]🖼️ 启动万能图片压缩引擎[/bold #FF9800]")
        console.print("[dim]基于 Lanczos 重采样高保真算法，支持按比例缩放及画质无损微调。[/dim]\n")

        path_input = Prompt.ask("[#10b981]?[/#10b981] 请输入图片文件或目录路径")
        target_path = os.path.abspath(path_input.strip('\"\''))

        scale_str = Prompt.ask("[#10b981]?[/#10b981] 请输入缩放比例 (10 ~ 100 %)", default="100")
        quality_str = Prompt.ask("[#10b981]?[/#10b981] 请输入压缩画质 (1 ~ 100 %)", default="80")

        scale = int(scale_str) if scale_str.isdigit() else 100
        quality = int(quality_str) if quality_str.isdigit() else 80

        return self._compress(target_path, scale, quality, None, console)

    def _compress(self, target_path: str, scale: int, quality: int, out_dest: str | None, console: Console) -> int:
        try:
            from PIL import Image
        except ImportError:
            print_error("缺少 pillow 依赖库！请运行: pip install pillow")
            return 1

        Image.MAX_IMAGE_PIXELS = None
        img_exts = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff')

        files_to_process = []
        if os.path.isfile(target_path) and target_path.lower().endswith(img_exts):
            files_to_process.append(target_path)
        elif os.path.isdir(target_path):
            for root, _, files in os.walk(target_path):
                for f in files:
                    if f.lower().endswith(img_exts) and "_min" not in f:
                        files_to_process.append(os.path.join(root, f))

        if not files_to_process:
            print_warning("未找到任何待压缩的图片文件。")
            return 0

        scale_ratio = max(0.1, min(1.0, scale / 100.0))
        quality_val = max(1, min(100, quality))

        print_step(f"共锁定 [bold #00FF00]{len(files_to_process)}[/bold #00FF00] 张图片 | 缩放: {int(scale_ratio*100)}% | 画质: {quality_val}%")
        total_orig_bytes = 0
        total_new_bytes = 0

        with create_progress() as progress:
            task = progress.add_task("[#10b981]压缩推进中...", total=len(files_to_process))

            for img_path in files_to_process:
                progress.update(task, description=f"[#10b981]压缩:[/#10b981] {os.path.basename(img_path)[:20]}")
                try:
                    orig_size = os.path.getsize(img_path)
                    total_orig_bytes += orig_size

                    base_dir = os.path.dirname(img_path)
                    base_name, ext = os.path.splitext(os.path.basename(img_path))

                    if out_dest and os.path.isdir(out_dest):
                        out_file = os.path.join(out_dest, f"{base_name}_min{ext}")
                    elif out_dest and not os.path.isdir(out_dest) and len(files_to_process) == 1:
                        out_file = out_dest
                    else:
                        out_file = os.path.join(base_dir, f"{base_name}_min{ext}")

                    with Image.open(img_path) as img:
                        out_ext = os.path.splitext(out_file)[1].lower()
                        # RGBA 兼容
                        if out_ext in ['.jpg', '.jpeg'] and img.mode in ('RGBA', 'P', 'LA'):
                            bg = Image.new("RGB", img.size, (255, 255, 255))
                            if img.mode == 'RGBA':
                                bg.paste(img, mask=img.split()[3])
                            else:
                                bg.paste(img)
                            img = bg

                        # 尺寸缩放
                        if scale_ratio < 1.0:
                            new_w = max(1, int(img.width * scale_ratio))
                            new_h = max(1, int(img.height * scale_ratio))
                            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                        # 保存并压缩
                        if out_ext in ['.jpg', '.jpeg']:
                            img.save(out_file, quality=quality_val, optimize=True)
                        elif out_ext == '.png':
                            img.save(out_file, optimize=True)
                        elif out_ext == '.webp':
                            img.save(out_file, quality=quality_val, method=6)
                        else:
                            img.save(out_file, quality=quality_val)

                    new_size = os.path.getsize(out_file)
                    total_new_bytes += new_size
                except Exception as e:
                    console.print(f"[red]❌ 压缩失败: {os.path.basename(img_path)} -> {e}[/red]")

                progress.advance(task)

        console.print()
        diff = total_orig_bytes - total_new_bytes
        ratio = (diff / total_orig_bytes * 100) if total_orig_bytes > 0 else 0
        print_success("万能图片压缩任务执行完毕！")
        print_info(f"原体积: [dim]{format_size(total_orig_bytes)}[/dim] -> 压缩后: [bold #00FF00]{format_size(total_new_bytes)}[/bold #00FF00] (节约 {ratio:.1f}%)")
        return 0
