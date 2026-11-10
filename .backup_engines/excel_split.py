# -*- coding: utf-8 -*-
"""
Excel 总表条件拆分引擎 (按指定列分组散列拆分)
"""
import os
import re
import argparse
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from pykuai.core.base import BaseEngine
from pykuai.core.ui import print_success, print_error, print_warning, print_info, print_step, create_progress


def clean_filename(filename):
    if filename is None or str(filename).strip() == "" or str(filename).lower() == "nan":
        return "空值或未指定"
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', str(filename))
    return safe_name.strip()


class ExcelSplitEngine(BaseEngine):
    name = "excel-split"
    aliases = ["split-excel", "sexcel"]
    description = "Excel 总表条件拆分 (按指定列值自动分组散列导出为多个文件)"
    category = "通用办公"

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="待拆分的总表 Excel 文件路径")
        parser.add_argument("-c", "--column", help="拆分依据的列名 (不传则在命令行交互选择)")
        parser.add_argument("-o", "--output-dir", help="自定义输出目录路径")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        file_path = os.path.abspath(args.file)
        return self._split(file_path, args.column, args.output_dir, console)

    def run_interactive(self, console: Console) -> int:
        console.print("[bold #FF9800]✂️ 启动 Excel 总表条件拆分引擎[/bold #FF9800]")
        console.print("[dim]读取总表表头，按指定列中的不同取值，自动分组拆分成独立的 Excel 文件。[/dim]\n")

        file_input = Prompt.ask("[#10b981]?[/#10b981] 请输入待拆分的总表 Excel 路径")
        file_path = os.path.abspath(file_input.strip('\"\''))
        return self._split(file_path, None, None, console)

    def _split(self, file_path: str, split_col: str | None, out_dir: str | None, console: Console) -> int:
        try:
            import pandas as pd
        except ImportError:
            print_error("缺少 pandas 依赖库！请在终端运行: pip install pandas openpyxl")
            return 1

        if not os.path.isfile(file_path):
            print_error(f"指定的文件不存在: {file_path}")
            return 1

        print_step(f"正在快速解析表头结构: [bold]{os.path.basename(file_path)}[/bold]")
        try:
            df_headers = pd.read_excel(file_path, nrows=0)
            columns = [str(c).strip() for c in df_headers.columns]
        except Exception as e:
            print_error(f"解析表头失败: {e}")
            return 1

        if not columns:
            print_error("该 Excel 表格未检测到任何有效表头列。")
            return 1

        # 若未指定拆分列，进入交互式选择
        if not split_col or split_col not in columns:
            console.print("\n[bold #10b981]请选择拆分依据列:[/bold #10b981]")
            for idx, col in enumerate(columns, 1):
                console.print(f"  [bold #FF9800]{idx:>2}.[/bold #FF9800] {col}")
            console.print()

            while True:
                choice = Prompt.ask(f"[#10b981]?[/#10b981] 请输入列序号 (1-{len(columns)}) 或列名")
                if choice.isdigit() and 1 <= int(choice) <= len(columns):
                    split_col = columns[int(choice) - 1]
                    break
                elif choice in columns:
                    split_col = choice
                    break
                console.print("[red]无效的列选择，请重新输入。[/red]")

        print_info(f"已锁定拆分依据列: [bold #00FF00]【{split_col}】[/bold #00FF00]")
        print_step("正在全量装载表格数据进内存...")
        df = pd.read_excel(file_path)

        base_dir = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_dir = out_dir or os.path.join(base_dir, f"{base_name}_按【{split_col}】拆分结果")
        os.makedirs(output_dir, exist_ok=True)

        grouped = df.groupby(split_col, dropna=False)
        total_groups = len(grouped)
        print_info(f"共发现 [bold #00FF00]{total_groups}[/bold #00FF00] 个独立子组，准备散列导出...")

        success_count = 0
        with create_progress() as progress:
            task = progress.add_task("[#10b981]正在切片导出...", total=total_groups)
            for name, group in grouped:
                safe_name = clean_filename(name)
                output_file = os.path.join(output_dir, f"{safe_name}.xlsx")
                progress.update(task, description=f"[#10b981]导出:[/#10b981] {safe_name[:20]}")
                try:
                    group.to_excel(output_file, index=False)
                    success_count += 1
                except Exception as e:
                    console.print(f"[red]❌ 导出分组 {safe_name} 失败: {e}[/red]")
                progress.advance(task)

        console.print()
        print_success(f"拆分顺利完成！成功导出 [bold #00FF00]{success_count}/{total_groups}[/bold #00FF00] 个文件。")
        print_info(f"全部保存在目录: [bold]{output_dir}[/bold]")
        return 0
