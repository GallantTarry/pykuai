# -*- coding: utf-8 -*-
"""
PyKuai Base Engine Definition
"""
from abc import ABC, abstractmethod
import argparse
from rich.console import Console


class BaseEngine(ABC):
    """
    Base class specification for all plug-in script engines.
    Any engine placed in engines/ is automatically discovered and registered.
    """
    name: str = ""
    description: str = ""
    usage: str = ""
    category: str = "General"
    requires: list[str] = []

    @abstractmethod
    def register_args(self, parser: argparse.ArgumentParser) -> None:
        """Register CLI arguments for direct command execution."""
        pass

    @abstractmethod
    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        """Direct mode: execute with parsed CLI arguments and return exit code (0 for success)."""
        pass

    @abstractmethod
    def run_interactive(self, console: Console) -> int:
        """Interactive mode: prompt for inputs via Rich console and return exit code (0 for success)."""
        pass
