# -*- coding: utf-8 -*-
"""
RAR/ZIP 矩阵解压引擎 (递归子目录穿透 + 密码解密)
"""
import os
import sys
import zipfile
import argparse
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from pykuai.core.base import BaseEngine
from pykuai.core.tools import get_unrar
from pykuai.core.ui import print_success, print_error, print_warning, print_info, print_step, create_progress

try:
    import rarfile
    unrar_path = get_unrar()
    if unrar_path and os.path.exists(unrar_path):
        rarfile.UNRAR_TOOL = unrar_path
except ImportError:
    rarfile = None


class ArchiveEngine(BaseEngine):
    name = "archive"
    aliases = ["extract", "unrar", "zip"]
    description = "RAR/ZIP 矩阵解压引擎 (递归多层级穿透与智能解密)"
    category = "通用办公"

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("folder", nargs="?", default=".", help="需要批量解压的目标文件夹路径 (默认当前目录)")
        parser.add_argument("-p", "--password", default="", help="全局解压密码 (针对加密包)")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        folder_path = os.path.abspath(args.folder)
        return self._extract(folder_path, args.password, console)

    def run_interactive(self, console: Console) -> int:
        console.print("[bold #FF9800]📦 启动 RAR/ZIP 矩阵解压引擎[/bold #FF9800]")
        console.print("[dim]支持无限层级子目录穿透，自动修复 ZIP 中文乱码，支持全局密码注入。[/dim]\n")

        folder_input = Prompt.ask("[#10b981]?[/#10b981] 请输入目标工作区文件夹路径", default=".")
        folder_path = os.path.abspath(folder_input)

        password = Prompt.ask("[#10b981]?[/#10b981] 请输入解压密码 (若无加密包直接回车留空)", default="")
        return self._extract(folder_path, password, console)

    def _extract(self, folder_path: str, password: str, console: Console) -> int:
        if not os.path.isdir(folder_path):
            print_error(f"指定的目录不存在: {folder_path}")
            return 1

        print_step(f"正在全盘雷达扫描目录: [bold]{folder_path}[/bold]")
        archive_files = []
        for root_dir, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(('.rar', '.zip')):
                    archive_files.append(os.path.join(root_dir, file))

        if not archive_files:
            print_warning("未在当前目录及任何子目录中找到 .rar 或 .zip 压缩包。")
            return 0

        print_info(f"共在各层级发现 [bold #00FF00]{len(archive_files)}[/bold #00FF00] 个压缩包，开始执行解压矩阵...")

        success_count = 0
        fail_count = 0

        with create_progress() as progress:
            task = progress.add_task("[#10b981]解压矩阵推进中...", total=len(archive_files))

            for file_path in archive_files:
                file_name = os.path.basename(file_path)
                base_dir = os.path.dirname(file_path)
                folder_name = os.path.splitext(file_name)[0]
                target_dir = os.path.join(base_dir, folder_name)
                ext = file_name.lower().split('.')[-1]

                progress.update(task, description=f"[#10b981]解压:[/#10b981] {file_name[:25]}")

                try:
                    os.makedirs(target_dir, exist_ok=True)
                    if ext == "rar":
                        if rarfile is None:
                            console.print(f"[bold red]❌ 依赖缺失: 缺少 rarfile 库，请 pip install rarfile[/]")
                            fail_count += 1
                            continue
                        with rarfile.RarFile(file_path, 'r') as rf:
                            if rf.needs_password() and not password:
                                raise Exception("该压缩包已加密，但未提供解压密码！")
                            rf.extractall(target_dir, pwd=password if password else None)

                    elif ext == "zip":
                        with zipfile.ZipFile(file_path, 'r') as zf:
                            pwd_bytes = password.encode('utf-8') if password else None
                            # 修复 Windows 中文编码
                            for zip_info in zf.infolist():
                                try:
                                    zip_info.filename = zip_info.filename.encode('cp437').decode('gbk')
                                except Exception:
                                    pass
                                try:
                                    zf.extract(zip_info, target_dir, pwd=pwd_bytes)
                                except RuntimeError as e:
                                    if 'password' in str(e).lower() or 'encrypted' in str(e).lower():
                                        raise Exception("ZIP 密码错误或未提供密码！")
                                    raise
                    success_count += 1
                except Exception as e:
                    console.print(f"[bold red]❌ 解压失败: {file_name} -> {e}[/]")
                    fail_count += 1

                progress.advance(task)

        console.print()
        print_success(f"深度批量解压行动完毕！成功: [bold #00FF00]{success_count}[/] 个，失败/跳过: [bold #FF5252]{fail_count}[/] 个。")
        return 0 if fail_count == 0 else 1
