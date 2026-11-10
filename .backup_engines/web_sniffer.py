# -*- coding: utf-8 -*-
"""
网页动态节点嗅探脚本引擎 (生成与复制浏览器控制台注入 JS 脚本)
"""
import os
import subprocess
import argparse
from rich.console import Console
from rich.syntax import Syntax
from pykuai.core.base import BaseEngine
from pykuai.core.ui import print_success, print_error, print_warning, print_info, print_step

SNIFFER_JS = r"""
(function() {
    console.clear();
    console.log('%c>>> 正在强力穿透 DOM 树，启动全字段雷达嗅探...', 'color: #00FF00; font-size: 14px; font-weight: bold;');

    let headerThs = document.querySelectorAll('thead th, .el-table__header th, th');
    if (headerThs.length === 0) {
        alert('未在当前视图检测到表头！请确保弹窗或表格已完全加载。');
        return;
    }

    let columnClassMap = [];
    headerThs.forEach(th => {
        let text = th.innerText.trim();
        if (text && !text.includes('操作') && !text.includes('序号') && !text.includes('选择') && !text.includes('查看')) {
            let classList = Array.from(th.classList);
            let targetClass = classList.find(c => c.startsWith('el-table_') || c.includes('column') || c.includes('cell'));
            if (targetClass) {
                columnClassMap.push({ name: text, className: targetClass });
            }
        }
    });

    if (columnClassMap.length === 0) {
        alert('表头特征捕获失败！请检查当前上下文 frame。');
        return;
    }

    let maxRows = 0;
    let columnDataList = [];
    columnClassMap.forEach(col => {
        let elements = document.querySelectorAll('.' + col.className + ':not(th)');
        let singleColumn = [];
        elements.forEach(el => {
            let text = el.innerText.trim().replace(/\r\n|\r|\n/g, ' ');
            if (!text || text === 'null' || text === 'undefined') {
                text = '';
            } else if (/^\d{10,}$/.test(text) || text.length === 18) {
                text = "'" + text;
            }
            singleColumn.push(text);
        });
        columnDataList.push(singleColumn);
        if (singleColumn.length > maxRows) maxRows = singleColumn.length;
    });

    if (maxRows === 0) {
        alert('已定位表头，但数据行为空！');
        return;
    }

    let tsv = columnClassMap.map(c => c.name).join('\t') + '\n';
    for (let i = 0; i < maxRows; i++) {
        let row = [];
        for (let j = 0; j < columnClassMap.length; j++) {
            row.push(columnDataList[j][i] || '');
        }
        tsv += row.join('\t') + '\n';
    }

    let ta = document.createElement('textarea');
    ta.value = tsv;
    ta.style.position = 'fixed';
    ta.style.top = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);

    console.log(`%c🎉 成功捕获 ${maxRows} 条数据并注入系统剪贴板！可直接在 Excel 中 [Ctrl+V] 粘贴。`, 'color: #00FF00; font-weight: bold;');
    alert(`🎉 提取成功！共获取 ${maxRows} 条数据，已复制至剪贴板，可直接在 Excel 粘贴！`);
})();
"""


def copy_to_clipboard(text: str) -> bool:
    try:
        if os.name == 'nt':
            cmd = ['powershell', '-NoProfile', '-Command', '$input | Set-Clipboard']
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, text=True, encoding='utf-8')
            p.communicate(input=text)
            return p.returncode == 0
        else:
            return False
    except Exception:
        return False


class WebSnifferEngine(BaseEngine):
    name = "web-sniffer"
    aliases = ["sniffer", "js-dump", "table-dump"]
    description = "JS 动态节点嗅探脚本生成器 (一键复制到剪贴板，F12 控制台穿透反爬抓取表格)"
    category = "针对性专精"

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("-p", "--print", action="store_true", help="在终端直接打印出完整 JavaScript 代码")
        parser.add_argument("-o", "--output", help="将 JS 嗅探脚本保存至指定本地文件")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        return self._run(args.print, args.output, console)

    def run_interactive(self, console: Console) -> int:
        console.print("[bold #FF9800]🕷️ 启动 JS 动态节点嗅探与抓取引擎[/bold #FF9800]")
        console.print("[dim]纯净原生 JS，绕过前端加密，一键复制后在浏览器按 F12 粘贴回车即可。[/dim]\n")
        return self._run(False, None, console)

    def _run(self, print_code: bool, out_file: str | None, console: Console) -> int:
        if out_file:
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(SNIFFER_JS.strip())
            print_success(f"嗅探脚本已保存至本地: [bold]{out_file}[/bold]")
            return 0

        ok = copy_to_clipboard(SNIFFER_JS.strip())
        if ok:
            print_success("嗅探脚本已成功装载至【系统剪贴板】！")
        else:
            print_warning("自动写入剪贴板受限，请查阅下方代码。")
            print_code = True

        console.print(
            "\n[bold #10b981]战术使用指南:[/bold #10b981]\n"
            "  1. 进入目标动态数据网页 (如专家库、评审表格等)。\n"
            "  2. 按键盘 [bold #FF9800][F12][/bold #FF9800] 打开开发者工具，切换到 [bold #00FF00]Console[/bold #00FF00] (控制台)。\n"
            "  3. 在控制台直接按 [bold #FF9800][Ctrl + V][/bold #FF9800] 粘贴并回车执行。\n"
            "  4. 脚本将自动遍历穿透数据，弹窗提示复制成功后，打开任意 Excel 按 [Ctrl + V] 即可！\n"
        )

        if print_code:
            console.print(Syntax(SNIFFER_JS.strip(), "javascript", theme="monokai", line_numbers=True))

        return 0
