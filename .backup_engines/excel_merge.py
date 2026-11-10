# -*- coding: utf-8 -*-
"""
Excel 多表垂直合并引擎 (智能对齐表头 + 防长数字截断)
"""
import os
import argparse
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from pykuai.core.base import BaseEngine
from pykuai.core.ui import print_success, print_error, print_warning, print_info, print_step, create_progress


class ExcelMergeEngine(BaseEngine):
    name = "excel-merge"
    aliases = ["merge-excel", "mexcel"]
    description = "Excel 多表垂直合并工具 (智能对齐消除表头空格 + 防长数字截断)"
    category = "通用办公"

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("folder", nargs="?", default=".", help="待合并 Excel 所在文件夹 (默认当前目录)")
        parser.add_argument("-o", "--output", default="汇总表_合并结果.xlsx", help="合并生成的汇总文件名")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        folder_path = os.path.abspath(args.folder)
        return self._merge(folder_path, args.output, console)

    def run_interactive(self, console: Console) -> int:
        console.print("[bold #FF9800]📊 启动 Excel 多表垂直合并引擎[/bold #FF9800]")
        console.print("[dim]自动扫描目录下所有 Excel 文件，按列名智能对齐堆叠，锁定文本格式防丢失。[/dim]\n")

        folder_input = Prompt.ask("[#10b981]?[/#10b981] 请输入存放待合并 Excel 的文件夹路径", default=".")
        folder_path = os.path.abspath(folder_input)

        out_name = Prompt.ask("[#10b981]?[/#10b981] 请输入输出汇总表文件名", default="汇总表_合并结果.xlsx")
        return self._merge(folder_path, out_name, console)

    def _merge(self, folder_path: str, output_name: str, console: Console) -> int:
        try:
            import pandas as pd
        except ImportError:
            print_error("缺少 pandas 依赖库！请在终端运行: pip install pandas openpyxl")
            return 1

        if not os.path.isdir(folder_path):
            print_error(f"指定的目录不存在: {folder_path}")
            return 1

        excel_files = [
            f for f in os.listdir(folder_path)
            if (f.endswith('.xlsx') or f.endswith('.xls'))
            and not f.startswith('~$')
            and output_name not in f
        ]

        if not excel_files:
            print_warning(f"在目录 [{folder_path}] 中未找到可合并的 Excel 文件。")
            return 0

        print_step(f"共发现 [bold #00FF00]{len(excel_files)}[/bold #00FF00] 个 Excel 文件，开始解析数据流...")

        all_data = []
        error_files = []

        with create_progress() as progress:
            task = progress.add_task("[#10b981]正在提取数据...", total=len(excel_files))

            for file in excel_files:
                file_path = os.path.join(folder_path, file)
                progress.update(task, description=f"[#10b981]提取:[/#10b981] {file[:25]}")
                try:
                    sheet_dict = pd.read_excel(file_path, sheet_name=None, dtype=str)
                    for sheet_name, df in sheet_dict.items():
                        df.columns = df.columns.astype(str).str.strip()
                        df.dropna(how='all', axis=0, inplace=True)
                        df.dropna(how='all', axis=1, inplace=True)
                        if not df.empty:
                            df.insert(0, '数据来源_Sheet名', sheet_name)
                            df.insert(0, '数据来源_源文件名', file)
                            all_data.append(df)
                except Exception as e:
                    error_files.append((file, str(e)))
                progress.advance(task)

        if not all_data:
            print_error("未从任何文件中提取到有效数据行。")
            return 1

        print_step("正在进行底层数据垂直堆叠与去空规整...")
        merged_df = pd.concat(all_data, ignore_index=True)
        merged_df.fillna("", inplace=True)

        output_path = os.path.join(folder_path, output_name)
        merged_df.to_excel(output_path, index=False)

        print_success(f"合并圆满完成！共汇总 [bold #00FF00]{len(merged_df)}[/bold #00FF00] 行明细数据。")
        print_info(f"汇总文件已导出至: [bold]{output_path}[/bold]")
        if error_files:
            print_warning(f"另有 {len(error_files)} 个文件因异常跳过，例如: {error_files[0][0]} -> {error_files[0][1]}")
        return 0
