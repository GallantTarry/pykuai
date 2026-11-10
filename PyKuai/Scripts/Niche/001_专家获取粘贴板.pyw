# -*- coding: utf-8 -*-
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox, QApplication, QTextEdit)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont, QFontDatabase, QTextCursor


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget，适配 PyKuai
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        # 1. 标题 (统一极客橙色)
        title_lbl = QLabel("JS 动态节点嗅探与抓取引擎")
        title_lbl.setStyleSheet("color: #FF9800; font-size: 22px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 2. 功能说明
        desc_lbl = QLabel("绕过前端加密 | 纯净原生 JS | 一键注入浏览器控制台")
        desc_lbl.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        desc_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_lbl)

        layout.addSpacing(10)

        # 3. 透明实时终端日志框 (统一终端绿代码流风格)
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("""
            QTextEdit {
                background-color: rgba(10, 10, 10, 200);
                color: #00FF00;
                border: 1px solid #333;
                border-radius: 5px;
                padding: 10px;
                font-size: 13px;
            }
        """)
        self.log_console.setText(
            "等待提取指令...\n"
            ">_ 适用场景：提取网页上的动态加密表格 (专家、供应商库等)。\n"
            ">_ 战术规范：\n"
            "  1. 点击下方按钮，将底层 JS 嗅探代码装载至系统剪贴板。\n"
            "  2. 在目标网页按 [F12] 调出开发者工具 (Console)。\n"
            "  3. 粘贴代码并回车，系统将自动击穿反爬限制并提取数据。\n"
        )
        layout.addWidget(self.log_console)

        # 4. 核心执行按钮 (统一镂空霓虹绿特效)
        self.btn_copy = QPushButton("🚀 一键复制嗅探脚本")
        self.btn_copy.setFixedSize(260, 45)
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                color: #00FF00; 
                border: 1px solid #00FF00;
                font-weight: bold; 
                font-size: 15px; 
                border-radius: 6px; 
            }
            QPushButton:hover { background-color: rgba(0, 255, 0, 30); }
            QPushButton:disabled { color: #555; border: 1px solid #555; background-color: transparent; }
        """)
        self.btn_copy.clicked.connect(self.copy_js_to_clipboard)
        layout.addWidget(self.btn_copy, 0, Qt.AlignCenter)

    def append_log(self, text):
        self.log_console.append(text)
        self.log_console.moveCursor(QTextCursor.End)

    def copy_js_to_clipboard(self):
        # 核心 JS 代码，原生字符串保持原样
        js_code = r"""(function() {
    const targetHeaders = ['专家姓名', '身份证号码', '工作单位', '工作岗位', '专业名称', '联系方式', '角色名称', '是否出席'];

    // 用来存放“自动侦测”到的最新列代号
    let columnClassMap = [];

    let allThs = document.querySelectorAll('th');
    allThs.forEach(th => {
        let text = th.innerText.trim();
        if (targetHeaders.includes(text)) {
            // 在它的 class 里寻找包含 el-table 且包含 column 的那个动态代号
            let dynamicClass = Array.from(th.classList).find(cls => cls.includes('el-table_') && cls.includes('_column_'));
            if (dynamicClass) {
                columnClassMap.push({ name: text, className: dynamicClass });
            }
        }
    });

    if (columnClassMap.length === 0) {
        alert('这次连表头都没找到！请检查：\n1. 网页是不是弹窗还没完全加载出来？\n2. 开发者工具（Console）顶部的下拉菜单里，是不是选错了运行环境（如果是内网系统，可能要选对应名字的 iframe，而不是 top）。');
        return;
    }

    let columnDataList = []; 
    let maxRows = 0;         

    columnClassMap.forEach(col => {
        let elements = document.querySelectorAll('.' + col.className + ':not(th)');
        let singleColumnData = [];

        elements.forEach(el => {
            let text = el.innerText.trim().replace(/\r\n|\r|\n/g, ' '); 

            if (!text || text === 'null' || text === 'undefined') {
                text = '';
            } else if (/^\d{10,}$/.test(text) || text.length === 18) {
                text = "'" + text;
            }
            singleColumnData.push(text);
        });
        columnDataList.push(singleColumnData); 

        if (singleColumnData.length > maxRows) {
            maxRows = singleColumnData.length;
        }
    });

    if (maxRows === 0) {
        alert('代号找到了，但是底下没数据！请确认名单列表是不是空的？');
        return;
    }

    let tsvContent = columnClassMap.map(col => col.name).join('\t') + '\n';
    for (let i = 0; i < maxRows; i++) {
        let currentRow = [];
        for (let j = 0; j < columnClassMap.length; j++) {
            currentRow.push(columnDataList[j][i] || '');
        }
        tsvContent += currentRow.join('\t') + '\n';
    }

    let textArea = document.createElement("textarea");
    textArea.value = tsvContent;

    textArea.style.position = 'fixed';
    textArea.style.top = '10%';
    textArea.style.left = '10%';
    textArea.style.width = '80%';
    textArea.style.height = '80%';
    textArea.style.zIndex = '999999';
    textArea.style.padding = '20px';
    document.body.appendChild(textArea);

    textArea.select();
    try {
        document.execCommand('copy');
        alert(' 动态破解成功！\n\n不管它代号怎么变，数据已经全都乖乖进你的剪贴板了！\n\n请直接去空白 Excel，选中 A1 单元格，按 Ctrl + V 粘贴即可。\n（按 F5 刷新网页即可关闭大文本框）');
    } catch (err) {
        alert('请手动全选屏幕中间文本框里的内容 (Ctrl+A)，复制 (Ctrl+C) 后去 Excel 粘贴！');
    }
})();"""

        # 调用 PySide6 全局剪贴板
        clipboard = QApplication.clipboard()
        clipboard.setText(js_code)

        # 反馈打印到终端日志
        self.append_log("\n>_ 物理复制指令已触发...")
        self.append_log(f">_ 提取到 JS Payload 结构，总计 {len(js_code)} Bytes。")
        self.append_log(">_ ✅ 核心脚本已成功挂载至系统剪贴板！请切换至浏览器实施注入。")

        # 弹出成功提示
        QMessageBox.information(self, "挂载成功", "JS 代码已成功复制到系统剪贴板！\n\n请直接前往浏览器控制台粘贴运行。")


# =================================================================
# 独立调试机制：主程序挂载时会被无视
# =================================================================
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    current_dir = os.path.dirname(os.path.abspath(__file__))

    # 动态加载 ../../tools/zpix.ttf，保证独立运行测试时也是像素风
    tools_dir = os.path.abspath(os.path.join(current_dir, "../..", "tools"))
    font_path = os.path.join(tools_dir, "zpix.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            app.setFont(QFont(font_family, 10))

    icon_path = os.path.abspath(os.path.join(current_dir, "../..", "imgs", "script.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = PluginWidget()
    window.setWindowTitle("JS嗅探提取引擎 - 独立沙盒模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(600, 400)
    window.show()
    sys.exit(app.exec())