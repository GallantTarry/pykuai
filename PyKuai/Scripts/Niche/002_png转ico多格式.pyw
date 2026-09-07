# -*- coding: utf-8 -*-
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication,
                               QCheckBox, QGridLayout, QFrame)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.file_path = ""
        self.default_sizes = [16, 32, 48, 64, 128, 256]
        self.checkboxes = {}
        self.init_ui()

    def init_ui(self):
        # 让插件自适应撑满主程序右侧区域
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(20)

        # 1. 标题与说明区域
        title_lbl = QLabel("PyKuai ICO 封装大师")
        title_lbl.setStyleSheet("color: #00FFFF; font-size: 22px; font-weight: bold; font-family: 'Microsoft YaHei';")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("无损转换 PNG 母图 | 动态装载多分辨率 | 生成标准 Windows 容器")
        desc_lbl.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        desc_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_lbl)

        layout.addSpacing(10)

        # 2. 文件选择交互区
        file_layout = QHBoxLayout()
        self.lbl_file = QLabel("1. 载入母图:")
        self.lbl_file.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")

        self.entry_file = QLineEdit()
        self.entry_file.setReadOnly(True)
        self.entry_file.setPlaceholderText("请选择需要转换的高清 PNG 格式图片...")
        self.entry_file.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
                font-family: Consolas;
            }
        """)

        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.setStyleSheet("""
            QPushButton { 
                background-color: #444; 
                color: white; 
                border-radius: 5px; 
                padding: 8px 15px; 
                font-weight: bold;
            }
            QPushButton:hover { background-color: #666; }
        """)
        self.btn_browse.clicked.connect(self.select_file)

        file_layout.addWidget(self.lbl_file)
        file_layout.addWidget(self.entry_file)
        file_layout.addWidget(self.btn_browse)
        layout.addLayout(file_layout)

        # 3. 分辨率选择区 (带边框的暗黑容器)
        size_frame = QFrame()
        size_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #444;
                border-radius: 8px;
                background-color: rgba(20, 20, 20, 150);
            }
        """)
        size_layout = QVBoxLayout(size_frame)
        size_layout.setContentsMargins(15, 15, 15, 15)

        lbl_size_title = QLabel("2. 勾选需要封装进 ICO 的分辨率矩阵:")
        lbl_size_title.setStyleSheet("color: #E0E0E0; font-size: 13px; border: none; background: transparent;")
        size_layout.addWidget(lbl_size_title)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(15)

        # 动态生成复选框
        row, col = 0, 0
        for size in self.default_sizes:
            chk = QCheckBox(f"{size} x {size}")
            chk.setChecked(True)  # 默认全部勾选
            chk.setCursor(Qt.PointingHandCursor)
            chk.setStyleSheet("""
                QCheckBox {
                    color: #00FF00;
                    font-size: 14px;
                    font-family: Consolas;
                    background: transparent;
                    border: none;
                }
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                    border: 1px solid #555;
                    border-radius: 3px;
                    background-color: #111;
                }
                QCheckBox::indicator:checked {
                    background-color: #00FF00;
                    border: 1px solid #00FF00;
                }
            """)
            self.checkboxes[size] = chk
            grid_layout.addWidget(chk, row, col)

            col += 1
            if col > 2:  # 每行放 3 个
                col = 0
                row += 1

        size_layout.addLayout(grid_layout)
        layout.addWidget(size_frame)

        # 弹簧将内容往中间挤
        layout.addStretch()

        # 4. 核心执行按钮
        self.btn_convert = QPushButton("⚡ 一键生成并导出 ICO")
        self.btn_convert.setFixedSize(280, 45)
        self.btn_convert.setCursor(Qt.PointingHandCursor)
        self.btn_convert.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                color: #00FFFF; 
                border: 1px solid #00FFFF;
                font-weight: bold; 
                font-size: 15px; 
                border-radius: 6px; 
            }
            QPushButton:hover { background-color: rgba(0, 255, 255, 30); box-shadow: 0 0 10px #00FFFF; }
            QPushButton:disabled { color: #555; border: 1px solid #555; background-color: transparent; }
        """)
        self.btn_convert.clicked.connect(self.generate_ico)

        # 将按钮居中放置
        layout.addWidget(self.btn_convert, 0, Qt.AlignCenter)

        if not PIL_AVAILABLE:
            self.btn_convert.setDisabled(True)
            self.btn_convert.setText("🚫 缺少 Pillow 依赖库")

    def select_file(self):
        """调起系统弹窗选择图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择高清 PNG 母图",
            "",
            "PNG 图片 (*.png);;所有文件 (*.*)"
        )
        if file_path:
            self.file_path = file_path
            self.entry_file.setText(file_path)

    def generate_ico(self):
        """核心封装逻辑"""
        if not PIL_AVAILABLE:
            QMessageBox.critical(self, "依赖缺失", "未检测到 Pillow 库，请检查打包环境！")
            return

        if not self.file_path:
            QMessageBox.warning(self, "操作提示", "请先选择一张 PNG 图片！")
            return

        # 收集勾选的尺寸
        selected_sizes = []
        for size, chk in self.checkboxes.items():
            if chk.isChecked():
                selected_sizes.append((size, size))

        if not selected_sizes:
            QMessageBox.warning(self, "操作提示", "请至少勾选一个分辨率规格！")
            return

        # 锁定按钮
        self.btn_convert.setText("⚙️ 引擎封装中...")
        self.btn_convert.setDisabled(True)
        QApplication.processEvents()

        try:
            # 设定默认导出名称与路径
            base_dir = os.path.dirname(self.file_path)
            base_name = os.path.splitext(os.path.basename(self.file_path))[0]
            default_save_path = os.path.join(base_dir, f"{base_name}.ico")

            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存多分辨率 ICO 文件",
                default_save_path,
                "ICO 图标文件 (*.ico)"
            )

            if not save_path:
                return  # 用户取消保存

            # 核心转换：利用 Pillow 读取图片并直接保存为多尺寸 ICO 容器
            img = Image.open(self.file_path).convert("RGBA")
            img.save(save_path, format="ICO", sizes=selected_sizes)

            QMessageBox.information(
                self,
                "封装成功",
                f"🎉 ICO 容器封装完成！\n\n已成功装入 {len(selected_sizes)} 种分辨率版本。\n文件已导出至:\n{save_path}"
            )

        except Exception as e:
            QMessageBox.critical(self, "发生异常", f"封装过程中发生错误:\n{str(e)}")

        finally:
            # 恢复按钮状态
            self.btn_convert.setText("⚡ 一键生成并导出 ICO")
            self.btn_convert.setDisabled(False)


# =================================================================
# 独立调试机制：被主程序 import 时会自动忽略这部分代码
# =================================================================
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    # 动态寻址加载图标
    current_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.abspath(os.path.join(current_dir, "../..", "imgs", "script.ico"))

    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = PluginWidget()
    window.setWindowTitle("PyKuai ICO 封装大师")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(500, 350)
    window.show()
    sys.exit(app.exec())