# -*- coding: utf-8 -*-
import os
import time
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication, QTextEdit)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QIntValidator, QFont, QFontDatabase, QTextCursor

try:
    from pypdf import PdfReader, PdfWriter

    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


# =================================================================
# 异步拆分线程：防止处理巨型 PDF 时主界面卡死，并实时回传日志
# =================================================================
class SplitWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, input_pdf, split_page):
        super().__init__()
        self.input_pdf = input_pdf
        self.split_page = split_page

    def run(self):
        try:
            self.log_signal.emit(f"🚀 引擎已启动，目标靶机已锁定:\n    {self.input_pdf}")
            time.sleep(0.3)  # 微小延迟增强终端装载感

            self.log_signal.emit(f"⏳ 正在将 PDF 结构装载进内存进行解析...")
            reader = PdfReader(self.input_pdf)
            total_pages = len(reader.pages)

            self.log_signal.emit(f"[-] 解析完毕。当前 PDF 总页数: {total_pages} 页")

            if self.split_page <= 0 or self.split_page >= total_pages:
                self.log_signal.emit(f"❌ 警告：节点无效！拆分节点必须在 1 到 {total_pages - 1} 之间。")
                self.finished_signal.emit(False,
                                          f"拆分节点无效！\n当前 PDF 总页数为 {total_pages} 页，请输入 1 到 {total_pages - 1} 之间的数字。")
                return

            self.log_signal.emit(f"[*] 切割坐标已确认: 绝对节点在第 {self.split_page} 页\n" + "-" * 40)
            self.log_signal.emit(f"⏳ 正在执行分子重组切割序列...")

            writer_part1 = PdfWriter()
            writer_part2 = PdfWriter()

            # 按页码分配到两个不同的 Writer 中
            for i in range(total_pages):
                if i < self.split_page:
                    writer_part1.add_page(reader.pages[i])
                else:
                    writer_part2.add_page(reader.pages[i])

            # 生成输出路径并保存
            base_dir = os.path.dirname(self.input_pdf)
            base_name = os.path.splitext(os.path.basename(self.input_pdf))[0]

            out_path1 = os.path.join(base_dir, f"{base_name}_第1至{self.split_page}页.pdf")
            out_path2 = os.path.join(base_dir, f"{base_name}_第{self.split_page + 1}页至末尾.pdf")

            self.log_signal.emit(f"⏳ 正在执行磁盘 I/O 写入双卷实体...")

            with open(out_path1, "wb") as f1:
                writer_part1.write(f1)
            self.log_signal.emit(f"✅ 上卷已封存: {os.path.basename(out_path1)}")

            with open(out_path2, "wb") as f2:
                writer_part2.write(f2)
            self.log_signal.emit(f"✅ 下卷已封存: {os.path.basename(out_path2)}")

            self.log_signal.emit("-" * 40 + "\n🎉 极速断点拆分行动圆满结束！")

            msg = f"✅ 文件已成功断点拆分为双卷，并保存在原目录下：\n\n1. {os.path.basename(out_path1)}\n2. {os.path.basename(out_path2)}"
            self.finished_signal.emit(True, msg)

        except Exception as e:
            self.log_signal.emit(f"❌ 底层物理引擎崩溃: {str(e)}")
            self.finished_signal.emit(False, f"底层拆分过程中发生崩溃：\n{str(e)}")


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        # 初始化主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        # 1. 标题与说明区域 (统一极客橙主色调)
        title_lbl = QLabel("PDF 断点拆分引擎")
        title_lbl.setStyleSheet("color: #FF9800; font-size: 22px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("无损分割 PDF | 毫秒级断点切分 | 原地生成双卷")
        desc_lbl.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        desc_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_lbl)

        layout.addSpacing(10)

        # 2. 文件选择交互区
        file_layout = QHBoxLayout()
        self.lbl_file = QLabel("1. 目标靶机:")
        self.lbl_file.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_file.setFixedWidth(90)

        self.entry_file = QLineEdit()
        self.entry_file.setReadOnly(True)
        self.entry_file.setPlaceholderText("请锁定需要进行切割的 PDF 文件...")
        self.entry_file.setStyleSheet("""
            QLineEdit { background-color: rgba(0, 0, 0, 100); color: #00FF00; border: 1px solid #555; border-radius: 5px; padding: 8px; }
            QLineEdit:focus { border: 1px solid #00FF00; }
        """)

        self.btn_browse = QPushButton("雷达扫描...")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.setStyleSheet("""
            QPushButton { background-color: #444; color: white; border-radius: 5px; padding: 8px 15px; font-weight: bold; } 
            QPushButton:hover { background-color: #666; }
        """)
        self.btn_browse.clicked.connect(self.select_file)

        file_layout.addWidget(self.lbl_file)
        file_layout.addWidget(self.entry_file)
        file_layout.addWidget(self.btn_browse)
        layout.addLayout(file_layout)

        # 3. 拆分节点设置区
        page_layout = QHBoxLayout()
        self.lbl_page = QLabel("2. 切割坐标:")
        self.lbl_page.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_page.setFixedWidth(90)

        self.entry_page = QLineEdit()
        self.entry_page.setPlaceholderText("输入页码 (如: 5)")
        self.entry_page.setFixedWidth(120)
        # 强制限制只能输入正整数
        self.entry_page.setValidator(QIntValidator(1, 99999))
        self.entry_page.setStyleSheet("""
            QLineEdit { background-color: rgba(0, 0, 0, 100); color: #FF9800; border: 1px solid #555; border-radius: 5px; padding: 8px; font-weight: bold;}
            QLineEdit:focus { border: 1px solid #FF9800; }
        """)

        lbl_hint = QLabel("* 注：第一份新卷将绝对包含至此页")
        lbl_hint.setStyleSheet("color: #888888; font-size: 12px;")

        page_layout.addWidget(self.lbl_page)
        page_layout.addWidget(self.entry_page)
        page_layout.addWidget(lbl_hint)
        page_layout.addStretch()
        layout.addLayout(page_layout)

        # 4. 新增：透明实时终端日志框 (统一为终端绿代码流风格)
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
        self.log_console.setText("等待注入切割指令 (引擎处于休眠待命状态)...\n")
        layout.addWidget(self.log_console)

        # 5. 核心执行按钮 (统一为镂空霓虹绿特效)
        self.btn_run = QPushButton("🚀 执行断点切割")
        self.btn_run.setFixedSize(220, 45)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setStyleSheet("""
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
        self.btn_run.clicked.connect(self.start_split)
        layout.addWidget(self.btn_run, 0, Qt.AlignCenter)

        # 依赖检测拦截
        if not PYPDF_AVAILABLE:
            self.btn_run.setDisabled(True)
            self.btn_run.setText("🚫 缺少 pypdf 依赖库")

    def select_file(self):
        """调起系统弹窗选择PDF"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "请锁定目标靶机 (PDF文件)",
            "",
            "PDF 格式文档 (*.pdf)"
        )
        if file_path:
            self.entry_file.setText(file_path)
            self.log_console.append(f"> 物理拦截系统介入: 已捕获文件 {os.path.basename(file_path)}")
            self.log_console.moveCursor(QTextCursor.End)

    def append_log(self, text):
        self.log_console.append(text)
        self.log_console.moveCursor(QTextCursor.End)

    def start_split(self):
        """挂载异步拆分线程"""
        input_pdf = self.entry_file.text().strip()
        split_page_str = self.entry_page.text().strip()

        # 1. 基础拦截校验
        if not input_pdf or not os.path.exists(input_pdf):
            QMessageBox.warning(self, "操作异常", "指挥官，您还没有指定一个有效的 PDF 靶机！")
            return

        if not split_page_str:
            QMessageBox.warning(self, "操作异常", "必须输入切割的坐标轴节点（正整数页码）！")
            return

        split_page = int(split_page_str)

        # 锁定面板防误触
        self.btn_run.setText("⚙️ 引擎原子切分中...")
        self.btn_run.setDisabled(True)
        self.btn_browse.setDisabled(True)
        self.entry_page.setDisabled(True)
        self.log_console.clear()

        # 挂载后台工作线程
        self.worker = SplitWorker(input_pdf, split_page)
        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(self.on_split_finished)
        self.worker.start()

    def on_split_finished(self, success, msg):
        self.btn_run.setText("⚡ 执行断点切割")
        self.btn_run.setDisabled(False)
        self.btn_browse.setDisabled(False)
        self.entry_page.setDisabled(False)

        if success:
            QMessageBox.information(self, "执行简报", msg)
            self.entry_file.clear()
            self.entry_page.clear()
        else:
            QMessageBox.critical(self, "执行崩溃", msg)


# =================================================================
# 独立调试机制
# =================================================================
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    current_dir = os.path.dirname(os.path.abspath(__file__))

    # 动态加载 ../../tools/zpix.ttf，保证单独双击运行测试时也是像素风
    tools_dir = os.path.abspath(os.path.join(current_dir, "../..", "tools"))
    font_path = os.path.join(tools_dir, "zpix.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            app.setFont(QFont(font_family, 10))

    # 动态定位图标路径
    base_dir = os.path.dirname(os.path.dirname(current_dir))
    icon_path = os.path.join(base_dir, "imgs", "script.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = PluginWidget()
    window.setWindowTitle("PDF极速断点拆分引擎 - 独立沙盒模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    # 拉长窗口高度以容纳终端框
    window.resize(500, 450)
    window.show()
    sys.exit(app.exec())