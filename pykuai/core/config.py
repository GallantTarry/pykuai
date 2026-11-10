# -*- coding: utf-8 -*-
"""
PyKuai User Configuration & Persistence
存储路径: ~/.pykuai/config.json
"""
import os
import json
import locale

CONFIG_DIR = os.path.expanduser("~/.pykuai")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def get_system_default_lang() -> str:
    """自动获取系统默认语言"""
    try:
        sys_lang, _ = locale.getdefaultlocale()
        if sys_lang and "zh" in sys_lang.lower():
            return "zh"
    except Exception:
        pass
    return "zh"


def load_config() -> dict:
    """读取用户全局配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"lang": get_system_default_lang()}


def save_config(cfg: dict) -> None:
    """持久化保存用户配置"""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception:
        pass


def get_saved_language() -> str:
    """获取当前已记录的语言 ('zh' 或 'en')"""
    cfg = load_config()
    return cfg.get("lang", "zh")


def set_saved_language(lang: str) -> None:
    """设置并记录语言到配置文件"""
    cfg = load_config()
    clean_lang = "en" if str(lang).strip().lower() in ["2", "en", "english"] else "zh"
    cfg["lang"] = clean_lang
    save_config(cfg)
