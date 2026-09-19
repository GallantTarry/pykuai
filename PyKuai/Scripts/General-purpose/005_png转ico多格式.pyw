# -*- coding: utf-8 -*-
import os
import time
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication,
                               QCheckBox, QGridLayout, QFrame, QTextEdit)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QFont, QFontDatabase, QTextCursor

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# =================================================================
# 异步封装线程：输出极客日志并防止主界面阻塞
# =================================================================
class IcoWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, file_path, save_path, selected_sizes):
        super().__init__()
        self.file_path = file_path
        self.save_path = save_path
        self.selected_sizes = selected_sizes

    def run(self):
        try:
            self.log_signal.emit(f"🚀 引擎启动，挂载高精母图:\n    {self.file_path}")
            time.sleep(0.2)  # 微小延迟增强终端装载感

            self.log_signal.emit(f"[*] 正在解析并重采样 {len(self.selected_sizes)} 种分辨率矩阵...")

            # 核心转换：利用 Pillow 读取图片并直接保存为多尺寸 ICO 容器
            img = Image.open(self.file_path).convert("RGBA")
            img.save(self.save_path, format="ICO", sizes=self.selected_sizes)

            self.log_signal.emit(f"✅ 物理封装成功！容器已导出至:\n    {self.save_path}")
            self.log_signal.emit("-" * 40 + "\n🎉 ICO 矩阵封装执行完毕！")

            self.finished_signal.emit(True,
                                      f"🎉 ICO 容器封装完成！\n\n已成功装入 {len(self.selected_sizes)} 种分辨率版本。")

        except Exception as e:
            self.log_signal.emit(f"❌ 封装异常: {str(e)}")
            self.finished_signal.emit(False, str(e))


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.file_path = ""
        self.default_sizes = [16, 32, 48, 64, 128, 256]
        self.checkboxes = {}
        self.worker = None
        self.init_ui()

    def init_ui(self):
        # 让插件自适应撑满主程序右侧区域
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        # 1. 标题与说明区域 (统一为极客橙 #FF9800)
        title_lbl = QLabel("PyKuai ICO 封装大师")
        title_lbl.setStyleSheet("color: #FF9800; font-size: 22px; font-weight: bold;")
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
        self.lbl_file.setFixedWidth(90)

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
            }
            QLineEdit:focus { border: 1px solid #00FF00; }
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

        # 动态生成复选框 (剔除硬编码字体)
        row, col = 0, 0
        for size in self.default_sizes:
            chk = QCheckBox(f"{size} x {size}")
            chk.setChecked(True)  # 默认全部勾选
            chk.setCursor(Qt.PointingHandCursor)
            chk.setStyleSheet("""
                QCheckBox {
                    color: #00FF00;
                    font-size: 14px;
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

        # 4. 实时终端日志框 (统一终端绿代码流风格)
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
        self.log_console.setText("等待初始化封装指令 (支持多图层无损组合)...\n")
        layout.addWidget(self.log_console)

        # 5. 核心执行按钮 (统一镂空霓虹绿特效)
        self.btn_convert = QPushButton("🚀 一键封装并导出")
        self.btn_convert.setFixedSize(280, 45)
        self.btn_convert.setCursor(Qt.PointingHandCursor)
        self.btn_convert.setStyleSheet("""
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
            self.log_console.append(f"\n>_ 已锁定母图: {file_path}")
            self.log_console.moveCursor(QTextCursor.End)

    def append_log(self, text):
        self.log_console.append(text)
        self.log_console.moveCursor(QTextCursor.End)

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

            # 锁定按钮面板
            self.btn_convert.setText("⚙️ 引擎重载与封装中...")
            self.btn_convert.setDisabled(True)
            self.btn_browse.setDisabled(True)
            self.log_console.clear()

            # 挂载异步线程
            self.worker = IcoWorker(self.file_path, save_path, selected_sizes)
            self.worker.log_signal.connect(self.append_log)
            self.worker.finished_signal.connect(self.on_generate_finished)
            self.worker.start()

        except Exception as e:
            QMessageBox.critical(self, "发生异常", f"预处理过程中发生错误:\n{str(e)}")
            self.btn_convert.setText("🚀 一键封装并导出")
            self.btn_convert.setDisabled(False)
            self.btn_browse.setDisabled(False)

    def on_generate_finished(self, success, msg):
        self.btn_convert.setText("🚀 一键封装并导出")
        self.btn_convert.setDisabled(False)
        self.btn_browse.setDisabled(False)

        if success:
            QMessageBox.information(self, "封装成功", msg)
        else:
            QMessageBox.critical(self, "发生异常", f"封装过程中发生错误:\n{msg}")


# =================================================================
# 独立调试机制：被主程序 import 时会自动忽略这部分代码
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
    window.setWindowTitle("PyKuai ICO 封装大师 - 独立沙盒模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    # 拉高窗口以容纳新增的终端日志框
    window.resize(500, 500)
    window.show()
    sys.exit(app.exec())