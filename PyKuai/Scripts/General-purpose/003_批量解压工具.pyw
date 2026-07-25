# -*- coding: utf-8 -*-
import os
import time
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication, QTextEdit)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QTextCursor

try:
    import rarfile

    # 【极客改造】：指向上一级 tools 文件夹中的 unrar.exe
    current_dir = os.path.dirname(os.path.abspath(__file__))
    unrar_path = os.path.abspath(os.path.join(current_dir, "../..", "tools", "unrar.exe"))

    # 兼容可能的命名大小写 (UnRAR.exe)
    if not os.path.exists(unrar_path):
        unrar_path_alt = os.path.abspath(os.path.join(current_dir, "../..", "tools", "UnRAR.exe"))
        if os.path.exists(unrar_path_alt):
            unrar_path = unrar_path_alt

    if os.path.exists(unrar_path):
        rarfile.UNRAR_TOOL = unrar_path
except ImportError:
    rarfile = None


# =================================================================
# 异步解压线程：防止解压大文件时主界面卡死
# =================================================================
class ExtractWorker(QThread):
    log_signal = Signal(str)  # 发送日志信号
    finished_signal = Signal(int, int)  # 发送完成信号 (成功数量, 失败数量)

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        if rarfile is None:
            self.log_signal.emit("❌ 致命错误：缺少 rarfile 依赖库！\n请在终端(cmd/powershell)中执行: pip install rarfile")
            self.finished_signal.emit(0, 0)
            return

        success_count = 0
        fail_count = 0

        # 获取目录下所有的 .rar 文件
        rar_files = [f for f in os.listdir(self.folder_path) if f.lower().endswith('.rar')]

        if not rar_files:
            self.log_signal.emit("⚠️ 未在当前目录下找到任何 .rar 文件。")
            self.finished_signal.emit(0, 0)
            return

        self.log_signal.emit(f"🚀 扫描完毕，共发现 {len(rar_files)} 个 RAR 压缩包，开始执行解压矩阵...\n" + "-" * 40)

        for file in rar_files:
            file_path = os.path.join(self.folder_path, file)
            # 以压缩包名作为新文件夹的名称 (去掉 .rar 后缀)
            folder_name = os.path.splitext(file)[0]
            target_dir = os.path.join(self.folder_path, folder_name)

            self.log_signal.emit(f"⏳ 正在解压: {file} ...")

            try:
                # 创建对应的专属目录
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)

                # 执行解压逻辑
                with rarfile.RarFile(file_path, 'r') as rf:
                    rf.extractall(target_dir)

                self.log_signal.emit(f"✅ 解压成功 -> {folder_name}/")
                success_count += 1

            except rarfile.RarCannotExec:
                self.log_signal.emit(f"❌ 核心缺失: 系统未找到 unrar.exe！请检查 tools 文件夹下是否存在核心文件。")
                fail_count += 1
                break  # 缺少核心程序，直接中断后续循环
            except Exception as e:
                self.log_signal.emit(f"❌ 解压失败: {file} | 错误详情: {e}")
                fail_count += 1

            time.sleep(0.1)  # 微小延迟，让UI动画更平滑

        self.log_signal.emit("-" * 40 + "\n🎉 批量解压任务队列执行完毕！")
        self.finished_signal.emit(success_count, fail_count)


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        # 1. 标题
        title_lbl = QLabel("RAR 矩阵解压引擎")
        title_lbl.setStyleSheet("color: #00FFFF; font-size: 22px; font-weight: bold; font-family: 'Microsoft YaHei';")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 2. 文件夹选择交互区
        folder_layout = QHBoxLayout()
        self.lbl_folder = QLabel("目标工作区:")
        self.lbl_folder.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")

        self.entry_folder = QLineEdit()
        self.entry_folder.setPlaceholderText("请选择需要批量解压的 RAR 所在文件夹...")
        self.entry_folder.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
                font-family: Consolas;
            }
            QLineEdit:focus { border: 1px solid #00FF00; }
        """)

        self.btn_browse = QPushButton("检索...")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.setStyleSheet("""
            QPushButton { background-color: #444; color: white; border-radius: 5px; padding: 8px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #666; }
        """)
        self.btn_browse.clicked.connect(self.select_folder)

        folder_layout.addWidget(self.lbl_folder)
        folder_layout.addWidget(self.entry_folder)
        folder_layout.addWidget(self.btn_browse)
        layout.addLayout(folder_layout)

        # 3. 实时终端日志框
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("""
            QTextEdit {
                background-color: rgba(10, 10, 10, 200);
                color: #00FF00;
                border: 1px solid #333;
                border-radius: 5px;
                padding: 10px;
                font-family: Consolas;
                font-size: 13px;
            }
        """)
        self.log_console.setText("等待初始化解压指令...\n")
        layout.addWidget(self.log_console)

        # 4. 核心执行按钮
        self.btn_start = QPushButton("⚡ 一键解压全境")
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
        self.btn_start.clicked.connect(self.start_extraction)
        layout.addWidget(self.btn_start, 0, Qt.AlignCenter)

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "选择存放 RAR 的文件夹")
        if folder_path:
            self.entry_folder.setText(folder_path)
            self.log_console.append(f"> 目标路径已锁定: {folder_path}")

    def append_log(self, text):
        self.log_console.append(text)
        self.log_console.moveCursor(QTextCursor.End)

    def start_extraction(self):
        folder_path = self.entry_folder.text().strip()
        if not folder_path or not os.path.isdir(folder_path):
            QMessageBox.warning(self, "权限拒绝", "请先选择一个有效的目标工作区目录！")
            return

        self.btn_start.setDisabled(True)
        self.btn_browse.setDisabled(True)
        self.btn_start.setText("⚙️ 引擎运转中...")
        self.log_console.clear()

        self.worker = ExtractWorker(folder_path)
        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(self.on_extract_finished)
        self.worker.start()

    def on_extract_finished(self, success_count, fail_count):
        self.btn_start.setDisabled(False)
        self.btn_browse.setDisabled(False)
        self.btn_start.setText("⚡ 一键解压全境")

        if success_count > 0 or fail_count > 0:
            QMessageBox.information(self, "任务简报",
                                    f"解压行动结束！\n\n✅ 成功解压: {success_count} 个\n❌ 失败跳过: {fail_count} 个")


# =================================================================
# 独立调试机制：主程序挂载时会被无视
# =================================================================
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.abspath(os.path.join(current_dir, "../..", "imgs", "script.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = PluginWidget()
    window.setWindowTitle("RAR 矩阵解压引擎 - 独立沙盒模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(650, 450)
    window.show()
    sys.exit(app.exec())