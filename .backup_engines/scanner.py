# -*- coding: utf-8 -*-
"""
图片转纯净黑白扫描件 PDF 引擎 (高斯自适应二值化 + 边缘保留)
"""
import os
import argparse
import tempfile
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from pykuai.core.base import BaseEngine
from pykuai.core.ui import print_success, print_error, print_warning, print_info, print_step, create_progress


class ScannerEngine(BaseEngine):
    name = "scanner"
    aliases = ["scan", "scan-img"]
    description = "图片转黑白扫描件 (高斯自适应二值化纯净除底灰 + 转换为PDF)"
    category = "多媒体与图像"

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("path", help="待转换的图片文件或包含图片的文件夹路径")
        parser.add_argument("-o", "--output-dir", help="PDF 导出目标文件夹 (默认源文件所在目录)")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        target_path = os.path.abspath(args.path.strip('\"\''))
        return self._process(target_path, args.output_dir, console)

    def run_interactive(self, console: Console) -> int:
        console.print("[bold #FF9800]📄 启动图片转黑白扫描件引擎[/bold #FF9800]")
        console.print("[dim]纯净高斯自适应二值化处理，完全保留笔迹结构并滤除底灰，单图独立封存为 PDF 容器。[/dim]\n")

        path_input = Prompt.ask("[#10b981]?[/#10b981] 请输入图片文件路径或文件夹路径")
        target_path = os.path.abspath(path_input.strip('\"\''))
        out_input = Prompt.ask("[#10b981]?[/#10b981] 请输入导出目录 (直接回车保持源目录)", default="")
        out_dir = os.path.abspath(out_input.strip('\"\'')) if out_input else None
        return self._process(target_path, out_dir, console)

    def _process(self, target_path: str, out_dir: str | None, console: Console) -> int:
        try:
            import cv2
            import numpy as np
            from PIL import Image
        except ImportError:
            print_error("缺少 opencv 或 pillow 依赖库！请运行: pip install opencv-python pillow img2pdf")
            return 1

        img_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff')
        target_files = []

        if os.path.isfile(target_path):
            if target_path.lower().endswith(img_exts):
                target_files.append(target_path)
        elif os.path.isdir(target_path):
            for root, _, files in os.walk(target_path):
                for f in files:
                    if f.lower().endswith(img_exts):
                        target_files.append(os.path.join(root, f))

        if not target_files:
            print_warning("未找到任何支持的图片文件。")
            return 0

        save_dir = out_dir or (os.path.dirname(target_path) if os.path.isfile(target_path) else target_path)
        os.makedirs(save_dir, exist_ok=True)

        print_step(f"共锁定 [bold #00FF00]{len(target_files)}[/bold #00FF00] 张母图，执行纯净二值化扫描序列...")
        success_count = 0
        fail_count = 0

        try:
            import img2pdf
            has_img2pdf = True
        except ImportError:
            has_img2pdf = False

        with tempfile.TemporaryDirectory() as temp_dir:
            with create_progress() as progress:
                task = progress.add_task("[#10b981]扫描件处理中...", total=len(target_files))

                for img_path in target_files:
                    file_name = os.path.basename(img_path)
                    progress.update(task, description=f"[#10b981]处理:[/#10b981] {file_name[:20]}")

                    try:
                        # 纯净读取防中文路径异常
                        img_data = np.fromfile(img_path, dtype=np.uint8)
                        img = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
                        if img is None:
                            fail_count += 1
                            continue

                        # 高斯自适应二值化
                        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        binary = cv2.adaptiveThreshold(
                            gray, 255,
                            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                            cv2.THRESH_BINARY,
                            21, 15
                        )

                        base_name = os.path.splitext(file_name)[0]
                        pdf_path = os.path.join(save_dir, f"{base_name}_扫描件.pdf")
                        temp_png = os.path.join(temp_dir, f"{base_name}_temp.png")

                        cv2.imencode('.png', binary)[1].tofile(temp_png)

                        if has_img2pdf:
                            with Image.open(temp_png) as pure_img:
                                pdf_bytes = img2pdf.convert(pure_img.filename)
                            with open(pdf_path, "wb") as f:
                                f.write(pdf_bytes)
                        else:
                            with Image.open(temp_png) as pure_img:
                                pure_img.save(pdf_path, "PDF")

                        success_count += 1
                    except Exception as e:
                        console.print(f"[red]❌ 处理失败: {file_name} -> {e}[/red]")
                        fail_count += 1

                    progress.advance(task)

        console.print()
        print_success(f"扫描件矩阵转换完毕！成功: [bold #00FF00]{success_count}[/] 张，失败: [bold #FF5252]{fail_count}[/] 张。")
        print_info(f"保存目录: [bold]{save_dir}[/bold]")
        return 0 if fail_count == 0 else 1
