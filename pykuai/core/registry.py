# -*- coding: utf-8 -*-
"""
PyKuai Engine Dynamic Auto-Discovery & Registry
"""
import os
import sys
import inspect
import importlib.util
from pathlib import Path
from pykuai.core.base import BaseEngine

_ENGINES_CACHE: dict[str, BaseEngine] = {}


def load_all_engines() -> dict[str, BaseEngine]:
    """Scan engines/ directory, instantiate and register all BaseEngine subclasses."""
    global _ENGINES_CACHE
    if _ENGINES_CACHE:
        return _ENGINES_CACHE

    engines_dir = Path(__file__).resolve().parent.parent / "engines"
    if not engines_dir.exists():
        return {}

    for file_path in sorted(engines_dir.glob("*.py")):
        if file_path.name.startswith("__"):
            continue

        module_name = f"pykuai.engines.{file_path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Discover all concrete subclasses of BaseEngine in this module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, BaseEngine)
                        and attr is not BaseEngine
                        and getattr(attr, "name", "")
                    ):
                        engine_inst = attr()
                        if engine_inst.name in _ENGINES_CACHE:
                            from pykuai.core.ui import console
                            console.print(
                                f"[dim yellow]⚠️ Duplicate command '{engine_inst.name}' "
                                f"in [{file_path.stem}] skipped.[/dim yellow]"
                            )
                            continue
                        _ENGINES_CACHE[engine_inst.name] = engine_inst
        except Exception as e:
            # Isolate engine loading failures so a broken script never crashes the CLI
            from pykuai.core.ui import console
            console.print(f"[dim yellow]⚠️ Skipped engine [{file_path.stem}]: {e}[/dim yellow]")

    return _ENGINES_CACHE


def get_engine(identifier: str) -> BaseEngine | None:
    """Look up an engine by its unique command name."""
    engines = load_all_engines()
    return engines.get(identifier)


def get_categories() -> dict[str, list[BaseEngine]]:
    """Group all registered engines by category."""
    engines = load_all_engines()
    categories: dict[str, list[BaseEngine]] = {}
    for engine in engines.values():
        cat = getattr(engine, "category", "General")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(engine)
    return categories
