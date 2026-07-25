# -*- coding: utf-8 -*-
import os
import tempfile
import cv2
import numpy as np
import img2pdf
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLabel,
                               QFileDialog, QMessageBox, QApplication)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon


class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_files = []

        # 动态定位图标路径：当前文件所在目录向外跳两层到根目录，再进入 imgs 文件夹
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        icon_path = os.path.join(base_dir, "imgs", "script.ico")
        self.setWindowIcon(QIcon(icon_path))

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        self.lbl_status = QLabel("尚未选择图片 (支持多选)")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #AAAAAA; font-size: 14px; font-weight: bold;")
        layout.addWidget(self.lbl_status)

        self.btn_select = QPushButton("📂 1. 选择待转换的图片")
        self.btn_select.setFixedSize(250, 45)
        self.btn_select.setCursor(Qt.PointingHandCursor)
        self.btn_select.setStyleSheet(self._btn_style())
        self.btn_select.clicked.connect(self.select_images)
        layout.addWidget(self.btn_select, 0, Qt.AlignCenter)

        self.btn_convert = QPushButton("🖨️ 2. 独立导出黑白扫描件 PDF")
        self.btn_convert.setFixedSize(250, 45)
        self.btn_convert.setCursor(Qt.PointingHandCursor)
        self.btn_convert.setStyleSheet(self._btn_style())
        self.btn_convert.clicked.connect(self.process_and_convert)
        self.btn_convert.setEnabled(False)
        layout.addWidget(self.btn_convert, 0, Qt.AlignCenter)

    def _btn_style(self):
        return """
            QPushButton { 
                background-color: transparent; 
                color: #00FFFF; 
                border: 1px solid #00FFFF;
                font-weight: bold; 
                font-size: 15px; 
                border-radius: 6px; 
            }
            QPushButton:hover { background-color: rgba(0, 255, 255, 30); }
            QPushButton:disabled { color: #555555; border: 1px solid #555555; }
        """

    def select_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if files:
            self.selected_files = files
            self.lbl_status.setText(f"已选择 {len(files)} 张图片，等待转换...")
            self.lbl_status.setStyleSheet("color: #00FF00; font-size: 14px; font-weight: bold;")
            self.btn_convert.setEnabled(True)

    def process_and_convert(self):
        if not self.selected_files:
            return

        # 变更为选择输出文件夹
        save_dir = QFileDialog.getExistingDirectory(self, "选择保存 PDF 扫描件的文件夹")
        if not save_dir:
            return

        self.lbl_status.setText("正在逐个生成独立 PDF，请稍候...")
        QApplication.processEvents()

        success_count = 0
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                for img_path in self.selected_files:
                    # 避免中文路径报错
                    img_data = np.fromfile(img_path, dtype=np.uint8)
                    img = cv2.imdecode(img_data, cv2.IMREAD_COLOR)

                    if img is None:
                        continue

                    # 二值化处理
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    binary = cv2.adaptiveThreshold(
                        gray, 255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY,
                        21, 15
                    )

                    # 提取原文件名，生成对应的独立 PDF 路径
                    base_name = os.path.splitext(os.path.basename(img_path))[0]
                    pdf_path = os.path.join(save_dir, f"{base_name}_扫描件.pdf")
                    temp_img_path = os.path.join(temp_dir, f"{base_name}_temp.png")

                    # 保存单张临时黑白图并独立转换为 PDF
                    cv2.imencode('.png', binary)[1].tofile(temp_img_path)
                    with open(pdf_path, "wb") as f:
                        f.write(img2pdf.convert(temp_img_path))

                    success_count += 1

            QMessageBox.information(self, "转换成功", f"成功生成 {success_count} 个独立 PDF！\n已保存至：\n{save_dir}")
            self.lbl_status.setText("转换完成！可继续选择新图片。")

        except Exception as e:
            QMessageBox.critical(self, "发生错误", f"转换过程中出现异常：\n{str(e)}")
            self.lbl_status.setText("转换失败。")


# =================================================================
# 独立调试机制
# =================================================================
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    # 全局设置调试窗口图标
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    app.setWindowIcon(QIcon(os.path.join(base_dir, "imgs", "script.ico")))

    window = PluginWidget()
    window.setWindowTitle("图片转扫描件 - 独立调试模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(350, 200)
    window.show()
    sys.exit(app.exec())