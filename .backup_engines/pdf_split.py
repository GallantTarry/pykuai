# -*- coding: utf-8 -*-
"""
PDF 断点拆分引擎 (按指定页码分子重组切割为双卷)
"""
import os
import argparse
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from pykuai.core.base import BaseEngine
from pykuai.core.ui import print_success, print_error, print_warning, print_info, print_step


class PdfSplitEngine(BaseEngine):
    name = "pdf-split"
    aliases = ["split-pdf", "pdfsplit"]
    description = "PDF 断点拆分引擎 (在指定绝对页码处切断并独立封存上/下双卷)"
    category = "通用办公"

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="待拆分的源 PDF 文件路径")
        parser.add_argument("-p", "--page", type=int, help="断点页码 (第1页到第N-1页之间)")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        pdf_path = os.path.abspath(args.file.strip('\"\''))
        return self._split(pdf_path, args.page, console)

    def run_interactive(self, console: Console) -> int:
        console.print("[bold #FF9800]📑 启动 PDF 断点拆分引擎[/bold #FF9800]")
        console.print("[dim]指定一个精确的页码截断点，将 PDF 物理切割为前序卷与后续卷。[/dim]\n")

        pdf_input = Prompt.ask("[#10b981]?[/#10b981] 请输入源 PDF 文件路径")
        pdf_path = os.path.abspath(pdf_input.strip('\"\''))
        return self._split(pdf_path, None, console)

    def _split(self, pdf_path: str, split_page: int | None, console: Console) -> int:
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            print_error("缺少 pypdf 依赖库！请运行: pip install pypdf")
            return 1

        if not os.path.isfile(pdf_path):
            print_error(f"指定的 PDF 文件不存在: {pdf_path}")
            return 1

        print_step("正在装载并解析 PDF 拓扑结构...")
        try:
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)
        except Exception as e:
            print_error(f"解析 PDF 失败: {e}")
            return 1

        print_info(f"目标文档总页数: [bold #00FF00]{total_pages}[/bold #00FF00] 页")
        if total_pages < 2:
            print_warning("该 PDF 仅有 1 页，无需拆分。")
            return 0

        if split_page is None:
            while True:
                page_str = Prompt.ask(f"[#10b981]?[/#10b981] 请输入断点页码 (1 ~ {total_pages - 1})")
                if page_str.isdigit() and 1 <= int(page_str) < total_pages:
                    split_page = int(page_str)
                    break
                console.print(f"[red]页码超出范围，请输入 1 到 {total_pages - 1} 之间的正整数。[/red]")

        if split_page <= 0 or split_page >= total_pages:
            print_error(f"断点页码无效！必须在 1 到 {total_pages - 1} 之间。")
            return 1

        print_step(f"确认断点: 第 [bold #00FF00]{split_page}[/bold #00FF00] 页 | 开始执行重组写入...")
        writer1 = PdfWriter()
        writer2 = PdfWriter()

        for i in range(total_pages):
            if i < split_page:
                writer1.add_page(reader.pages[i])
            else:
                writer2.add_page(reader.pages[i])

        base_dir = os.path.dirname(pdf_path)
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        out_part1 = os.path.join(base_dir, f"{base_name}_第1至{split_page}页.pdf")
        out_part2 = os.path.join(base_dir, f"{base_name}_第{split_page + 1}页至末尾.pdf")

        try:
            with open(out_part1, "wb") as f1:
                writer1.write(f1)
            with open(out_part2, "wb") as f2:
                writer2.write(f2)

            print_success("PDF 分子重组切割成功！")
            print_info(f"上卷: [bold]{os.path.basename(out_part1)}[/bold] (共 {split_page} 页)")
            print_info(f"下卷: [bold]{os.path.basename(out_part2)}[/bold] (共 {total_pages - split_page} 页)")
            return 0
        except Exception as e:
            print_error(f"文件写入失败: {e}")
            return 1
