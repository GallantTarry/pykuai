# -*- coding: utf-8 -*-
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QIntValidator

try:
    from pypdf import PdfReader, PdfWriter
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        # 初始化主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        # 预留顶部空间，使整体视觉重心微靠上
        layout.addSpacing(30)

        # 1. 标题与说明区域
        title_lbl = QLabel("PDF 极速断点拆分引擎")
        title_lbl.setStyleSheet("color: #00FFFF; font-size: 22px; font-weight: bold; font-family: 'Microsoft YaHei';")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("无损分割 PDF | 毫秒级断点切分 | 原地生成双卷")
        desc_lbl.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        desc_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_lbl)
        
        layout.addSpacing(10)

        # 2. 文件选择交互区
        file_layout = QHBoxLayout()
        self.lbl_file = QLabel("1. 目标 PDF:")
        self.lbl_file.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")

        self.entry_file = QLineEdit()
        self.entry_file.setReadOnly(True)
        self.entry_file.setPlaceholderText("请选择需要拆分的 PDF 文件...")
        self.entry_file.setStyleSheet("""
            QLineEdit { background-color: rgba(0, 0, 0, 100); color: #00FF00; border: 1px solid #555; border-radius: 5px; padding: 8px; font-family: Consolas; }
        """)

        self.btn_browse = QPushButton("检索...")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.setStyleSheet("QPushButton { background-color: #444; color: white; border-radius: 5px; padding: 8px 15px; font-weight: bold; } QPushButton:hover { background-color: #666; }")
        self.btn_browse.clicked.connect(self.select_file)

        file_layout.addWidget(self.lbl_file)
        file_layout.addWidget(self.entry_file)
        file_layout.addWidget(self.btn_browse)
        layout.addLayout(file_layout)

        # 3. 拆分节点设置区
        page_layout = QHBoxLayout()
        self.lbl_page = QLabel("2. 拆分节点:")
        self.lbl_page.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")

        self.entry_page = QLineEdit()
        self.entry_page.setPlaceholderText("输入页码 (如: 5)")
        self.entry_page.setFixedWidth(120)
        # 强制限制只能输入正整数
        self.entry_page.setValidator(QIntValidator(1, 99999))
        self.entry_page.setStyleSheet("""
            QLineEdit { background-color: rgba(0, 0, 0, 100); color: #00FFFF; border: 1px solid #555; border-radius: 5px; padding: 8px; font-family: Consolas; font-weight: bold;}
            QLineEdit:focus { border: 1px solid #00FFFF; }
        """)

        lbl_hint = QLabel("* 注：第一份新文件将包含至此页")
        lbl_hint.setStyleSheet("color: #888888; font-size: 12px;")

        page_layout.addWidget(self.lbl_page)
        page_layout.addWidget(self.entry_page)
        page_layout.addWidget(lbl_hint)
        page_layout.addStretch() # 将控件向左挤压
        layout.addLayout(page_layout)

        # 将按钮居中放置前加入间距
        layout.addSpacing(10)

        # 4. 核心执行按钮
        self.btn_run = QPushButton("⚡ 一键执行拆分")
        self.btn_run.setFixedSize(250, 45)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setStyleSheet("""
            QPushButton { background-color: transparent; color: #00FFFF; border: 1px solid #00FFFF; font-weight: bold; font-size: 15px; border-radius: 6px; }
            QPushButton:hover { background-color: rgba(0, 255, 255, 30); box-shadow: 0 0 10px #00FFFF; }
            QPushButton:disabled { color: #555; border: 1px solid #555; background-color: transparent; }
        """)
        self.btn_run.clicked.connect(self.split_pdf)
        layout.addWidget(self.btn_run, 0, Qt.AlignCenter)

        # 依赖检测拦截
        if not PYPDF_AVAILABLE:
            self.btn_run.setDisabled(True)
            self.btn_run.setText("🚫 缺少 pypdf 依赖库")

        # 底部弹簧，将上方组件顶在固定位置
        layout.addStretch()

    def select_file(self):
        """调起系统弹窗选择PDF"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要拆分的PDF文件",
            "",
            "PDF 格式文档 (*.pdf)"
        )
        if file_path:
            self.entry_file.setText(file_path)

    def split_pdf(self):
        """核心拆分逻辑"""
        input_pdf = self.entry_file.text().strip()
        split_page_str = self.entry_page.text().strip()

        # 1. 基础拦截校验
        if not input_pdf or not os.path.exists(input_pdf):
            QMessageBox.warning(self, "操作提示", "请先选择一个有效的 PDF 文件！")
            return

        if not split_page_str:
            QMessageBox.warning(self, "操作提示", "请在拆分节点处输入一个正整数页码！")
            return

        split_page = int(split_page_str)

        # 锁定按钮防连击
        self.btn_run.setText("⚙️ 引擎切割中...")
        self.btn_run.setDisabled(True)
        QApplication.processEvents()

        try:
            # 2. 核心拆分流程
            reader = PdfReader(input_pdf)
            total_pages = len(reader.pages)

            if split_page <= 0 or split_page >= total_pages:
                QMessageBox.critical(
                    self, 
                    "节点错误", 
                    f"拆分节点无效！\n当前 PDF 总页数为 {total_pages} 页，请输入 1 到 {total_pages - 1} 之间的数字。"
                )
                return

            writer_part1 = PdfWriter()
            writer_part2 = PdfWriter()

            # 按页码分配到两个不同的 Writer 中
            for i in range(total_pages):
                if i < split_page:
                    writer_part1.add_page(reader.pages[i])
                else:
                    writer_part2.add_page(reader.pages[i])

            # 3. 生成输出路径并保存
            base_dir = os.path.dirname(input_pdf)
            base_name = os.path.splitext(os.path.basename(input_pdf))[0]
            
            out_path1 = os.path.join(base_dir, f"{base_name}_第1至{split_page}页.pdf")
            out_path2 = os.path.join(base_dir, f"{base_name}_第{split_page+1}页至末尾.pdf")

            with open(out_path1, "wb") as f1:
                writer_part1.write(f1)
            with open(out_path2, "wb") as f2:
                writer_part2.write(f2)

            QMessageBox.information(
                self, 
                "拆分成功", 
                f"✅ 文件已成功断点拆分为双卷，并保存在原目录下：\n\n1. {os.path.basename(out_path1)}\n2. {os.path.basename(out_path2)}"
            )
            
            # 拆分完成后清空输入框，方便下一次操作
            self.entry_file.clear()
            self.entry_page.clear()

        except Exception as e:
            QMessageBox.critical(self, "程序异常", f"底层拆分过程中发生崩溃：\n{str(e)}")
            
        finally:
            self.btn_run.setText("⚡ 一键执行拆分")
            self.btn_run.setDisabled(False)


# =================================================================
# 独立调试机制
# =================================================================
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    # 动态定位图标路径
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    icon_path = os.path.join(base_dir, "imgs", "script.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = PluginWidget()
    window.setWindowTitle("PDF极速断点拆分引擎 - 独立调试模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(450, 300)
    window.show()
    sys.exit(app.exec())