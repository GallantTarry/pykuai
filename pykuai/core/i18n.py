# -*- coding: utf-8 -*-
"""
PyKuai Static Bilingual Dictionary & Internationalization Engine
纯本地静态字典，0毫秒响应，零网络依赖，完美支持中英文全局切换与参数插值。
"""
from pykuai.core.config import get_saved_language, set_saved_language

# 静态中英双语对照字典
DICTIONARY = {
    "zh": {
        "author_label": "作者",
        "lang_prompt": "[#10b981]?[/#10b981] 请选择语言 / Select Language [bold #00FF00][1. 中文 / 2. English][/bold #00FF00] (默认: {default})",
        "hint": "💡 请先输入 [bold #00FF00]help[/bold #00FF00] 查看代码写法，输入 [bold red]q[/bold red] 退出",
        "help_col_cmd": "指令",
        "help_col_desc": "功能说明",
        "help_col_syntax": "代码写法与范例",
        "help_ico_desc": "PNG 转多尺寸 Windows ICO 图标容器",
        "help_ico_syntax": "ico 或 ico logo.png (亦可直接拖入任意图片)",
        "help_clear_desc": "清屏并重新呈现控制台",
        "help_clear_syntax": "clear 或 cls",
        "help_lang_desc": "切换中英文语言 (zh / en)",
        "help_lang_syntax": "lang zh 或 lang en",
        "help_help_desc": "查看代码写法与指令说明",
        "help_help_syntax": "help 或 ?",
        "help_q_desc": "安全退出系统",
        "help_q_syntax": "q 或 exit",
        "exit_msg": '"The Lord is my shepherd." 退出完成。',
        "auto_drag": "› 检测到图片拖入，自动切入 ICO 引擎...",
        "unknown_cmd": "未知指令: '{cmd}'。请先输入 [bold #00FF00]help[/bold #00FF00] 查看代码写法，或输入 [bold red]q[/bold red] 退出。",
        "lang_switched": "✅ 界面语言已切换并记录为: [bold #00FF00]中文[/bold #00FF00]",
        # ICO 引擎专用
        "ico_title": "🎨 启动 PNG 转多尺寸 ICO 容器引擎",
        "ico_desc": "重采样并封装 16x16 至 256x256 完整图层，适配 Windows 系统高清显示。",
        "ico_input_path": "[#10b981]?[/#10b981] 请输入源图片文件路径 (支持直接拖入图片)",
        "ico_input_sizes": "[#10b981]?[/#10b981] 请输入封装尺寸矩阵 (逗号分隔)",
        "ico_reading": "读取源图: [bold]{filename}[/bold]",
        "ico_status": "正在重采样图层并封装 ICO 容器...",
        "ico_success": "✅ ICO 图标容器封装成功",
        "ico_card_src": "源文件:",
        "ico_card_dst": "导出路径:",
        "ico_card_layers": "图层规格:",
        "ico_card_size": "文件体积:",
    },
    "en": {
        "author_label": "Author",
        "lang_prompt": "[#10b981]?[/#10b981] Select Language / 请选择语言 [bold #00FF00][1. 中文 / 2. English][/bold #00FF00] (Default: {default})",
        "hint": "💡 Please type [bold #00FF00]help[/bold #00FF00] to learn command syntax, type [bold red]q[/bold red] to exit",
        "help_col_cmd": "Command",
        "help_col_desc": "Description",
        "help_col_syntax": "Code Syntax & Examples",
        "help_ico_desc": "Convert PNG to multi-resolution Windows ICO container",
        "help_ico_syntax": "ico or ico logo.png (or drag & drop image directly)",
        "help_clear_desc": "Clear screen and reprint console",
        "help_clear_syntax": "clear or cls",
        "help_lang_desc": "Switch language (zh / en)",
        "help_lang_syntax": "lang zh or lang en",
        "help_help_desc": "Show code syntax and command manual",
        "help_help_syntax": "help or ?",
        "help_q_desc": "Safe exit",
        "help_q_syntax": "q or exit",
        "exit_msg": '"The Lord is my shepherd." Safe exit completed.',
        "auto_drag": "› Detected image drop, automatically running ICO engine...",
        "unknown_cmd": "Unknown command: '{cmd}'. Please type [bold #00FF00]help[/bold #00FF00] to learn command syntax, or type [bold red]q[/bold red] to exit.",
        "lang_switched": "✅ Interface language switched and recorded as: [bold #00FF00]English[/bold #00FF00]",
        # ICO Engine
        "ico_title": "🎨 Launch PNG to Multi-size ICO Container Engine",
        "ico_desc": "Resample and package 16x16 to 256x256 full layers for Windows High-DPI display.",
        "ico_input_path": "[#10b981]?[/#10b981] Please enter source image path (drag & drop supported)",
        "ico_input_sizes": "[#10b981]?[/#10b981] Please enter packaging sizes (comma-separated)",
        "ico_reading": "Reading image: [bold]{filename}[/bold]",
        "ico_status": "Resampling layers and packaging ICO container...",
        "ico_success": "✅ ICO Container Packaged Successfully",
        "ico_card_src": "Source File:",
        "ico_card_dst": "Export Path:",
        "ico_card_layers": "Layer Sizes:",
        "ico_card_size": "File Size:",
    }
}

_current_lang = get_saved_language()


def get_lang() -> str:
    """获取当前语言代码 ('zh' 或 'en')"""
    global _current_lang
    return _current_lang


def set_lang(lang_code: str) -> None:
    """设置全局语言并持久化记录到配置文件中"""
    global _current_lang
    clean_lang = "en" if str(lang_code).strip().lower() in ["2", "en", "english"] else "zh"
    _current_lang = clean_lang
    set_saved_language(clean_lang)


def t(key: str, **kwargs) -> str:
    """全局静态字典翻译函数，支持参数插值与安全回退"""
    lang_dict = DICTIONARY.get(_current_lang, DICTIONARY["zh"])
    text = lang_dict.get(key)
    if text is None:
        text = DICTIONARY["zh"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
