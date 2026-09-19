# -*- coding: utf-8 -*-
import os
import tempfile
import cv2
import numpy as np
import img2pdf
from PIL import Image
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication, QTextEdit)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QTextCursor, QFont, QFontDatabase


# =================================================================
# 异步转换线程：防止批量处理时主界面卡死，实时回传日志
# =================================================================
class ConvertWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(int, int)

    def __init__(self, selected_files, save_dir):
        super().__init__()
        self.selected_files = selected_files
        self.save_dir = save_dir

    def run(self):
        success_count = 0
        fail_count = 0

        self.log_signal.emit(
            f"🚀 引擎启动，共计挂载 {len(self.selected_files)} 张图像，开始执行纯净二值化扫描序列...\n" + "-" * 40)

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                for idx, img_path in enumerate(self.selected_files):
                    file_name = os.path.basename(img_path)
                    self.log_signal.emit(f"⏳ [{idx + 1}/{len(self.selected_files)}] 正在高斯重采样: {file_name} ...")

                    try:
                        # 避免中文路径报错，直接纯净读取
                        img_data = np.fromfile(img_path, dtype=np.uint8)
                        img = cv2.imdecode(img_data, cv2.IMREAD_COLOR)

                        if img is None:
                            self.log_signal.emit(f"❌ 图像解码失败跳过: {file_name}")
                            fail_count += 1
                            continue

                        # 核心：纯净高斯自适应二值化处理，完全保留原文件笔迹结构
                        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        binary = cv2.adaptiveThreshold(
                            gray, 255,
                            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                            cv2.THRESH_BINARY,
                            21, 15
                        )

                        base_name = os.path.splitext(file_name)[0]
                        pdf_path = os.path.join(self.save_dir, f"{base_name}_扫描件.pdf")
                        temp_img_path = os.path.join(temp_dir, f"{base_name}_temp.png")

                        # 将二值化后的图像阵列编码为纯图像字节流
                        cv2.imencode('.png', binary)[1].tofile(temp_img_path)

                        # 【核心修复】：使用 PIL 强行转存一次，洗掉可能被系统/Qt注入的渲染元数据
                        # 确保传递给 img2pdf 的是绝对纯净的光栅图像(Raster Image)
                        with Image.open(temp_img_path) as pure_img:
                            # img2pdf 只负责把图像原封不动塞进 PDF 容器，禁止任何默认文本布局
                            pdf_bytes = img2pdf.convert(pure_img.filename)

                        with open(pdf_path, "wb") as f:
                            f.write(pdf_bytes)

                        success_count += 1
                        self.log_signal.emit(f"✅ 生成成功 -> 独立导出至 {base_name}_扫描件.pdf")

                    except Exception as e:
                        self.log_signal.emit(f"❌ 转换异常: {file_name} | 报错: {str(e)}")
                        fail_count += 1

            self.log_signal.emit("-" * 40 + "\n🎉 纯净版扫描件转换矩阵执行完毕！")
            self.finished_signal.emit(success_count, fail_count)

        except Exception as e:
            self.log_signal.emit(f"❌ 引擎严重崩溃: {str(e)}")
            self.finished_signal.emit(success_count, fail_count)


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_files = []
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        # 1. 标题 (极客橙色)
        title_lbl = QLabel("图片转黑白扫描件引擎")
        title_lbl.setStyleSheet("color: #FF9800; font-size: 22px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 2. 载入图片交互区
        input_layout = QHBoxLayout()
        self.lbl_input = QLabel("源图矩阵:")
        self.lbl_input.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_input.setFixedWidth(90)

        self.entry_input = QLineEdit()
        self.entry_input.setReadOnly(True)
        self.entry_input.setPlaceholderText("请选择需要转换的一张或多张图片...")
        self.entry_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
            }
            QLineEdit:focus { border: 1px solid #00FF00; }
        """)

        self.btn_browse_in = QPushButton("载入...")
        self.btn_browse_in.setCursor(Qt.PointingHandCursor)
        self.btn_browse_in.setStyleSheet("""
            QPushButton { background-color: #444; color: white; border-radius: 5px; padding: 8px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #666; }
        """)
        self.btn_browse_in.clicked.connect(self.select_images)

        input_layout.addWidget(self.lbl_input)
        input_layout.addWidget(self.entry_input)
        input_layout.addWidget(self.btn_browse_in)
        layout.addLayout(input_layout)

        # 3. 输出目录选择区
        output_layout = QHBoxLayout()
        self.lbl_output = QLabel("导出工作区:")
        self.lbl_output.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_output.setFixedWidth(90)

        self.entry_output = QLineEdit()
        self.entry_output.setReadOnly(True)
        self.entry_output.setPlaceholderText("请指定生成的 PDF 存放的文件夹...")
        self.entry_output.setStyleSheet(self.entry_input.styleSheet())

        self.btn_browse_out = QPushButton("指定...")
        self.btn_browse_out.setCursor(Qt.PointingHandCursor)
        self.btn_browse_out.setStyleSheet(self.btn_browse_in.styleSheet())
        self.btn_browse_out.clicked.connect(self.select_output_dir)

        output_layout.addWidget(self.lbl_output)
        output_layout.addWidget(self.entry_output)
        output_layout.addWidget(self.btn_browse_out)
        layout.addLayout(output_layout)

        # 4. 实时终端日志框
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
        self.log_console.setText("等待初始化转换指令 (支持自适应阈值高斯纯净降噪)...\n")
        layout.addWidget(self.log_console)

        # 5. 核心执行按钮
        self.btn_start = QPushButton("🚀 一键生成纯净扫描件")
        self.btn_start.setFixedSize(220, 45)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                color: #00FF00; 
                border: 1px solid #00FF00;
                font-weight: bold; 
                font-size: 15px; 
                border-radius: 6px; 
            }
            QPushButton:hover { background-color: rgba(0, 255, 0, 30); box-shadow: 0 0 10px #00FF00; }
            QPushButton:disabled { color: #555; border: 1px solid #555; background-color: transparent; }
        """)
        self.btn_start.clicked.connect(self.start_conversion)
        layout.addWidget(self.btn_start, 0, Qt.AlignCenter)

    def select_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择源图矩阵",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if files:
            self.selected_files = files
            self.entry_input.setText(f"已装载 {len(files)} 张图像文件...")
            self.log_console.append(f"> 源图矩阵锁定，共计 {len(files)} 份样本。")

            # 自动匹配第一个文件所在的目录为默认导出目录
            if not self.entry_output.text():
                base_dir = os.path.dirname(files[0])
                self.entry_output.setText(base_dir)
                self.log_console.append(f"> 自动分配导出路径: {base_dir}")

            self.log_console.moveCursor(QTextCursor.End)

    def select_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择导出工作区")
        if dir_path:
            self.entry_output.setText(dir_path)
            self.log_console.append(f"> 导出路径重新定向至: {dir_path}")
            self.log_console.moveCursor(QTextCursor.End)

    def append_log(self, text):
        self.log_console.append(text)
        self.log_console.moveCursor(QTextCursor.End)

    def start_conversion(self):
        save_dir = self.entry_output.text().strip()

        if not self.selected_files:
            QMessageBox.warning(self, "依赖缺失", "请先装载需要转换的源图！")
            return
        if not save_dir or not os.path.isdir(save_dir):
            QMessageBox.warning(self, "路径错误", "请指定一个有效的导出工作区！")
            return

        self.btn_start.setDisabled(True)
        self.btn_browse_in.setDisabled(True)
        self.btn_browse_out.setDisabled(True)
        self.btn_start.setText("⚙️ 底层编码重构中...")
        self.log_console.clear()

        # 挂载后台工作线程
        self.worker = ConvertWorker(self.selected_files, save_dir)
        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(self.on_conversion_finished)
        self.worker.start()

    def on_conversion_finished(self, success_count, fail_count):
        self.btn_start.setDisabled(False)
        self.btn_browse_in.setDisabled(False)
        self.btn_browse_out.setDisabled(False)
        self.btn_start.setText("🚀 一键生成纯净扫描件")

        if success_count > 0 or fail_count > 0:
            QMessageBox.information(self, "生成报告",
                                    f"批量转换任务结束！\n\n✅ 成功生成 PDF: {success_count} 份\n❌ 处理失败: {fail_count} 份")


# =================================================================
# 独立调试机制：主程序挂载时会被无视
# =================================================================
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    current_dir = os.path.dirname(os.path.abspath(__file__))

    # 动态加载 ../../tools/zpix.ttf，保证单独运行测试时也是像素风
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
    window.setWindowTitle("图片转黑白扫描件引擎 - 独立沙盒模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(650, 450)
    window.show()
    sys.exit(app.exec())