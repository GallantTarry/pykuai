# -*- coding: utf-8 -*-
"""
PyKuai Base Engine Definition
"""
from abc import ABC, abstractmethod
import argparse
from rich.console import Console


class BaseEngine(ABC):
    """
    所有插拔式脚本引擎的基类规范。
    引擎放入 engines/ 目录后会被自动注册。
    """
    name: str = ""
    aliases: list[str] = []
    description: str = ""
    category: str = "通用办公"

    @abstractmethod
    def register_args(self, parser: argparse.ArgumentParser) -> None:
        """
        在直接命令模式下，为子命令注册命令行参数。
        """
        pass

    @abstractmethod
    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        """
        一击脱离模式 (Direct Command):
        接收解析后的命令行参数并执行，返回状态码 (0 表示成功)。
        """
        pass

    @abstractmethod
    def run_interactive(self, console: Console) -> int:
        """
        沉浸式终端模式 (Interactive Console):
        通过 rich 交互式提问获取参数并执行，返回状态码 (0 表示成功)。
        """
        pass
