# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QMessageBox, QApplication)
from PySide6.QtCore import Qt


class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        # 初始化主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)

        # 核心复制按钮，直接居中显示
        self.btn_copy = QPushButton("⚡ 一键复制 JS 提取脚本")
        self.btn_copy.setFixedSize(250, 45)
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                color: #00FFFF; 
                border: 1px solid #00FFFF;
                font-weight: bold; 
                font-size: 15px; 
                border-radius: 6px; 
            }
            QPushButton:hover { background-color: rgba(0, 255, 255, 30); }
        """)
        self.btn_copy.clicked.connect(self.copy_js_to_clipboard)
        layout.addWidget(self.btn_copy, 0, Qt.AlignCenter)

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

        # 弹出成功提示
        QMessageBox.information(self, "执行完毕", "JS 代码已成功复制到系统剪贴板！\n\n请直接前往浏览器控制台粘贴运行。")


# =================================================================
# 独立调试机制
# =================================================================
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    window = PluginWidget()
    window.setWindowTitle("专家获取粘贴板 - 独立调试模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(300, 150)
    window.show()
    sys.exit(app.exec())