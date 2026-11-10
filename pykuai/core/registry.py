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
_ALIASES_MAP: dict[str, str] = {}


def load_all_engines() -> dict[str, BaseEngine]:
    """
    自动扫描 engines/ 目录下的所有模块，实例化并注册 BaseEngine 派生类。
    """
    global _ENGINES_CACHE, _ALIASES_MAP
    if _ENGINES_CACHE:
        return _ENGINES_CACHE

    engines_dir = Path(__file__).resolve().parent.parent / "engines"
    if not engines_dir.exists():
        return {}

    for file_path in engines_dir.glob("*.py"):
        if file_path.name.startswith("__"):
            continue

        module_name = f"pykuai.engines.{file_path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # 寻找该模块中所有继承自 BaseEngine 的非抽象类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, BaseEngine)
                        and attr is not BaseEngine
                        and getattr(attr, "name", "")
                    ):
                        engine_inst = attr()
                        _ENGINES_CACHE[engine_inst.name] = engine_inst
                        for alias in getattr(engine_inst, "aliases", []):
                            _ALIASES_MAP[alias] = engine_inst.name
        except Exception as e:
            # 容错：个别引擎加载失败不应拖垮整个 CLI
            from pykuai.core.ui import console
            console.print(f"[dim yellow]⚠️ 引擎 [{file_path.stem}] 加载跳过: {e}[/dim yellow]")

    return _ENGINES_CACHE


def get_engine(identifier: str) -> BaseEngine | None:
    """根据名称或别名查找引擎"""
    engines = load_all_engines()
    if identifier in engines:
        return engines[identifier]
    if identifier in _ALIASES_MAP:
        real_name = _ALIASES_MAP[identifier]
        return engines.get(real_name)
    return None


def get_categories() -> dict[str, list[BaseEngine]]:
    """将所有引擎按类别分组"""
    engines = load_all_engines()
    categories: dict[str, list[BaseEngine]] = {}
    for engine in engines.values():
        cat = getattr(engine, "category", "通用")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(engine)
    return categories
