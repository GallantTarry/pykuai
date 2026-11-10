# -*- coding: utf-8 -*-
"""
采购报价多表定式合并引擎 (20 列严格模板规范与特征表头动态扫描)
"""
import os
import argparse
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from pykuai.core.base import BaseEngine
from pykuai.core.ui import print_success, print_error, print_warning, print_info, print_step, create_progress

TARGET_COLUMNS = [
    "序号", "标包号", "物料编码", "规格及描述", "参考数量（只）", "品牌要求",
    "有偏差的应答规格型号", "*人民币60天账期单价（元）", "*正常交货期（周）",
    "*原厂最小包装数量", "*原厂最小起订数量", "*原厂包装方式",
    "*生命周期（即将停产/已停产）", "*原厂质保期（年）", "*是否接收承兑（是/否）",
    "型号偏差说明", "渠道性质", "备注", "应答单位", "应答轮次"
]


class OfficeFixedEngine(BaseEngine):
    name = "office-fixed"
    aliases = ["nari-merge", "fixed-merge", "bid-merge"]
    description = "采购多表定式合并 (严格 20 列特征表头动态扫描 + 规整导出)"
    category = "针对性专精"

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("folder", nargs="?", default=".", help="存放采购报价子表的文件夹路径")
        parser.add_argument("-o", "--output", default="采购报价总汇总_合并结果.xlsx", help="合并生成的总表文件名")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        folder_path = os.path.abspath(args.folder.strip('\"\''))
        return self._merge(folder_path, args.output, console)

    def run_interactive(self, console: Console) -> int:
        console.print("[bold #FF9800]📋 启动采购报价多表定式合并引擎[/bold #FF9800]")
        console.print("[dim]动态穿透扫描前 30 行定位真实表头，规整 20 列标准字段并自动补齐对齐。[/dim]\n")

        folder_input = Prompt.ask("[#10b981]?[/#10b981] 请输入包含采购报价子表的文件夹路径", default=".")
        folder_path = os.path.abspath(folder_input.strip('\"\''))

        out_name = Prompt.ask("[#10b981]?[/#10b981] 请输入输出文件名", default="采购报价总汇总_合并结果.xlsx")
        return self._merge(folder_path, out_name, console)

    def _merge(self, folder_path: str, output_name: str, console: Console) -> int:
        try:
            import pandas as pd
            from openpyxl.styles import Alignment, Font, Border, Side
        except ImportError:
            print_error("缺少 pandas 或 openpyxl 依赖库！请运行: pip install pandas openpyxl")
            return 1

        if not os.path.isdir(folder_path):
            print_error(f"指定的目录不存在: {folder_path}")
            return 1

        files = [
            f for f in os.listdir(folder_path)
            if f.endswith(('.xlsx', '.xls'))
            and not f.startswith('~')
            and output_name not in f
        ]

        if not files:
            print_warning(f"目录 [{folder_path}] 中未找到可供合并的 Excel 表格。")
            return 0

        print_step(f"发现 [bold #00FF00]{len(files)}[/bold #00FF00] 份采购子表，启动特征行雷达扫描...")
        df_list = []
        error_files = []

        with create_progress() as progress:
            task = progress.add_task("[#10b981]定式解析中...", total=len(files))

            for file in files:
                file_path = os.path.join(folder_path, file)
                progress.update(task, description=f"[#10b981]扫描:[/#10b981] {file[:20]}")
                try:
                    df_raw = pd.read_excel(file_path, header=None)
                    df_raw = df_raw.reindex(columns=range(20))

                    header_index = -1
                    search_limit = min(30, len(df_raw))
                    for i in range(search_limit):
                        row_str = " ".join([str(v).strip() for v in df_raw.iloc[i].values if pd.notna(v)])
                        if any(k in row_str for k in ["物料编码", "规格及描述", "参考数量", "账期单价"]):
                            header_index = i
                            break

                    if header_index != -1 and header_index + 1 < len(df_raw):
                        data_part = df_raw.iloc[header_index + 1:].copy()
                        data_part.columns = TARGET_COLUMNS
                        data_part.dropna(how='all', inplace=True)
                        if not data_part.empty:
                            df_list.append(data_part)
                except Exception as e:
                    error_files.append((file, str(e)))

                progress.advance(task)

        if not df_list:
            print_error("未能从任何文件中匹配到符合特征的有效数据行！")
            return 1

        print_step("正在执行多源垂直重组与 openpyxl 样式渲染...")
        final_df = pd.concat(df_list, ignore_index=True)
        final_df.fillna("", inplace=True)

        # 重新顺排序号
        final_df["序号"] = range(1, len(final_df) + 1)

        out_path = os.path.join(folder_path, output_name)
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            final_df.to_excel(writer, index=False, sheet_name="合并总表")
            ws = writer.sheets["合并总表"]

            thin_border = Border(
                left=Side(style='thin', color='D3D3D3'),
                right=Side(style='thin', color='D3D3D3'),
                top=Side(style='thin', color='D3D3D3'),
                bottom=Side(style='thin', color='D3D3D3')
            )

            for col in ws.columns:
                for cell in col:
                    cell.border = thin_border
                    cell.alignment = Alignment(horizontal='center', vertical='center')

        print_success(f"采购定式多表合并成功！共汇总 [bold #00FF00]{len(final_df)}[/bold #00FF00] 行明细。")
        print_info(f"保存至: [bold]{out_path}[/bold]")
        if error_files:
            print_warning(f"另有 {len(error_files)} 个文件格式不符被跳过。")
        return 0
