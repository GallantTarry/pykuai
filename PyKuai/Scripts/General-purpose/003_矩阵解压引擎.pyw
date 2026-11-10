# -*- coding: utf-8 -*-
import os
import time
import zipfile
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication, QTextEdit)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QTextCursor, QFont, QFontDatabase

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
# 异步解压线程：防止解压大文件时主界面卡死 (新增自动化密码注入)
# =================================================================
class ExtractWorker(QThread):
    log_signal = Signal(str)  # 发送日志信号
    finished_signal = Signal(int, int)  # 发送完成信号 (成功数量, 失败数量)

    def __init__(self, folder_path, password=""):
        super().__init__()
        self.folder_path = folder_path
        self.password = password

    def run(self):
        success_count = 0
        fail_count = 0

        # 【核心升级】：使用 os.walk 深度遍历所有子文件夹
        archive_files = []
        for root_dir, _, files in os.walk(self.folder_path):
            for file in files:
                if file.lower().endswith(('.rar', '.zip')):
                    # 记录完整的绝对路径
                    archive_files.append(os.path.join(root_dir, file))

        if not archive_files:
            self.log_signal.emit("⚠️ 未在当前目录及任何子目录中找到 .rar 或 .zip 压缩包。")
            self.finished_signal.emit(0, 0)
            return

        self.log_signal.emit(
            f"🚀 雷达扫描完毕，共在各层级发现 {len(archive_files)} 个压缩包，开始执行解压矩阵...\n" + "-" * 40)

        for file_path in archive_files:
            file_name = os.path.basename(file_path)
            base_dir = os.path.dirname(file_path)
            rel_path = os.path.relpath(file_path, self.folder_path)
            folder_name = os.path.splitext(file_name)[0]
            target_dir = os.path.join(base_dir, folder_name)

            ext = file_name.lower().split('.')[-1]

            self.log_signal.emit(f"⏳ 正在使用 [{ext.upper()}] 引擎解压: {rel_path} ...")

            try:
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)

                # ==========================
                # 分支 1：处理 RAR 文件
                # ==========================
                if ext == 'rar':
                    if rarfile is None:
                        self.log_signal.emit(f"❌ 依赖缺失：缺少 rarfile 库，跳过 {rel_path}")
                        fail_count += 1
                        continue

                    with rarfile.RarFile(file_path, 'r') as rf:
                        if rf.needs_password():
                            if not self.password:
                                raise Exception("该压缩包已加密，但您未在面板提供解压密码！")
                            rf.extractall(target_dir, pwd=self.password)
                        else:
                            rf.extractall(target_dir)

                # ==========================
                # 分支 2：处理 ZIP 文件
                # ==========================
                elif ext == 'zip':
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        pwd_bytes = self.password.encode('utf-8') if self.password else None
                        # 【中文防乱码黑魔法】：遍历修复编码
                        for zip_info in zf.infolist():
                            try:
                                zip_info.filename = zip_info.filename.encode('cp437').decode('gbk')
                            except Exception:
                                pass

                            try:
                                zf.extract(zip_info, target_dir, pwd=pwd_bytes)
                            except RuntimeError as e:
                                err_msg = str(e).lower()
                                if 'password' in err_msg or 'encrypted' in err_msg or 'bad password' in err_msg:
                                    raise Exception("ZIP 压缩包解密失败，未提供密码或密码错误！")
                                else:
                                    raise

                self.log_signal.emit(f"✅ 解压成功 -> 归档至 {folder_name}/")
                success_count += 1

            except Exception as e:
                # 捕获因缺少 unrar.exe 导致的特殊错误
                if ext == 'rar' and rarfile is not None and isinstance(e, rarfile.RarCannotExec):
                    self.log_signal.emit(f"❌ 核心缺失: 系统未找到 unrar.exe！请检查 tools 文件夹。")
                else:
                    self.log_signal.emit(f"❌ 解压失败: {rel_path} | 错误详情: {e}")
                fail_count += 1

            time.sleep(0.1)  # 微小延迟，让UI动画更平滑

        self.log_signal.emit("-" * 40 + "\n🎉 深度批量解压行动执行完毕！")
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

        # 1. 标题 (移除硬编码字体)
        title_lbl = QLabel("RAR/ZIP 矩阵解压引擎")
        title_lbl.setStyleSheet("color: #FF9800; font-size: 22px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 2. 文件夹选择交互区
        folder_layout = QHBoxLayout()
        self.lbl_folder = QLabel("目标工作区:")
        self.lbl_folder.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_folder.setFixedWidth(90)

        self.entry_folder = QLineEdit()
        self.entry_folder.setPlaceholderText("请选择需要批量解压的最外层文件夹...")
        self.entry_folder.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
            }
            QLineEdit:focus { border: 1px solid #00FF00; }
            QLineEdit:disabled { color: #555; border: 1px solid #333; background-color: rgba(0, 0, 0, 50); }
        """)

        self.btn_browse = QPushButton("检索...")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.setStyleSheet("""
            QPushButton { background-color: #444; color: white; border-radius: 5px; padding: 8px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #666; }
            QPushButton:disabled { background-color: #333; color: #777; border: 1px solid #333; }
        """)
        self.btn_browse.clicked.connect(self.select_folder)

        folder_layout.addWidget(self.lbl_folder)
        folder_layout.addWidget(self.entry_folder)
        folder_layout.addWidget(self.btn_browse)
        layout.addLayout(folder_layout)

        # 3. 新增：全局密码输入区
        pwd_layout = QHBoxLayout()
        self.lbl_pwd = QLabel("万能解压码:")
        self.lbl_pwd.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_pwd.setFixedWidth(90)

        self.entry_pwd = QLineEdit()
        self.entry_pwd.setPlaceholderText("如有加密包，请在此输入密码 (无密码请留空)...")
        self.entry_pwd.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #FF9800;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
            }
            QLineEdit:focus { border: 1px solid #FF9800; }
            QLineEdit:disabled { color: #555; border: 1px solid #333; background-color: rgba(0, 0, 0, 50); }
        """)

        pwd_layout.addWidget(self.lbl_pwd)
        pwd_layout.addWidget(self.entry_pwd)
        pwd_layout.addSpacing(73)  # 占位，对齐上方浏览按钮的宽度
        layout.addLayout(pwd_layout)

        # 4. 实时终端日志框 (移除硬编码 Consolas)
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
        self.log_console.setHtml("<span style='color: #00FF00;'>等待初始化解压指令 (支持无限层级子目录穿透与智能解密)...</span><br>")
        layout.addWidget(self.log_console)

        # 5. 核心执行按钮
        self.btn_start = QPushButton("🚀 一键解压全境")
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
            QPushButton:hover { background-color: rgba(0, 255, 0, 30); }
            QPushButton:disabled { color: #555; border: 1px solid #333; background-color: transparent; }
        """)
        self.btn_start.clicked.connect(self.start_extraction)
        layout.addWidget(self.btn_start, 0, Qt.AlignCenter)

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "选择存放压缩包的最外层文件夹")
        if folder_path:
            self.entry_folder.setText(folder_path)
            self.append_log(f"> 目标战区已锁定: {folder_path}\n> 引擎将自动下潜搜索所有子目录。")

    def append_log(self, text):
        clean_html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        if "❌" in text or "失败" in text or "错误" in text or "缺失" in text:
            formatted = f"<span style='color: #FF5252;'>{clean_html}</span>"
        elif "⚠️" in text or "警告" in text:
            formatted = f"<span style='color: #FF9800;'>{clean_html}</span>"
        elif text.startswith("-") or text.startswith("="):
            formatted = f"<span style='color: #666666;'>{clean_html}</span>"
        elif "✅" in text or "🎉" in text:
            formatted = f"<span style='color: #00FF00; font-weight: bold;'>{clean_html}</span>"
        else:
            formatted = f"<span style='color: #00FF00;'>{clean_html}</span>"
        self.log_console.append(formatted)
        self.log_console.moveCursor(QTextCursor.End)

    def start_extraction(self):
        folder_path = self.entry_folder.text().strip()
        password = self.entry_pwd.text().strip()

        if not folder_path or not os.path.isdir(folder_path):
            QMessageBox.warning(self, "权限拒绝", "请先选择一个有效的目标工作区目录！")
            return

        self.btn_start.setDisabled(True)
        self.btn_browse.setDisabled(True)
        self.entry_folder.setDisabled(True)
        self.entry_pwd.setDisabled(True)
        self.btn_start.setText("⚙️ 雷达穿透运转中...")
        self.log_console.clear()

        # 将密码参数传递给核心工作线程
        self.worker = ExtractWorker(folder_path, password)
        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(self.on_extract_finished)
        self.worker.start()

    def on_extract_finished(self, success_count, fail_count):
        self.btn_start.setDisabled(False)
        self.btn_browse.setDisabled(False)
        self.entry_folder.setDisabled(False)
        self.entry_pwd.setDisabled(False)
        self.btn_start.setText("🚀 一键解压全境")

        if success_count > 0 or fail_count > 0:
            QMessageBox.information(self, "深度任务简报",
                                    f"解压穿透行动结束！\n\n✅ 成功解压: {success_count} 个\n❌ 失败跳过: {fail_count} 个")


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
    window.setWindowTitle("RAR/ZIP 矩阵解压引擎 (穿透版) - 独立沙盒模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(650, 450)
    window.show()
    sys.exit(app.exec())