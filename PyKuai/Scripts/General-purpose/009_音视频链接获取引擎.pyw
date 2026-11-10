# -*- coding: utf-8 -*-
import os
import subprocess
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication, QTextEdit, QComboBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QTextCursor, QFont, QFontDatabase


# =================================================================
# 异步下载线程：调用外部 yt-dlp.exe 和 ffmpeg.exe 防止主界面卡死
# =================================================================
class DownloadWorker(QThread):
    log_signal = Signal(str)  # 发送日志信号
    finished_signal = Signal(bool)  # 发送完成信号 (成功状态)

    def __init__(self, url, save_folder, format_index, scope_index):
        super().__init__()
        self.url = url
        self.save_folder = save_folder
        self.format_index = format_index  # 0: 视频+音频, 1: 纯音频
        self.scope_index = scope_index    # 0: 仅当前单集, 1: 整个列表(表单)

    def run(self):
        # 【极客改造】：指向上一级 tools 文件夹中的核心组件
        current_dir = os.path.dirname(os.path.abspath(__file__))
        tools_dir = os.path.abspath(os.path.join(current_dir, "../..", "tools"))
        ytdlp_path = os.path.join(tools_dir, "yt-dlp.exe")
        ffmpeg_path = os.path.join(tools_dir, "ffmpeg.exe")

        # 检查核心引擎是否存在
        if not os.path.exists(ytdlp_path):
            self.log_signal.emit(f"❌ 核心缺失: 未在 {tools_dir} 找到 yt-dlp.exe！")
            self.finished_signal.emit(False)
            return

        self.log_signal.emit(f"🚀 捕获雷达已启动，目标定位: {self.url}")
        self.log_signal.emit("-" * 40)

        # 构建 yt-dlp 执行指令
        cmd = [
            ytdlp_path,
            '--ffmpeg-location', ffmpeg_path,
            '--newline',  # 强制换行输出以便实时读取
            '-o', f'{self.save_folder}/%(title)s.%(ext)s'
        ]

        # 【新增功能】：判断是否下载表单(列表)
        if self.scope_index == 0:
            cmd.append('--no-playlist')
            self.log_signal.emit("⏳ 捕获范围: [仅当前资源]")
        else:
            cmd.append('--yes-playlist')
            self.log_signal.emit("⏳ 捕获范围: [整个列表/表单]")

        # 格式判断
        if self.format_index == 1:
            self.log_signal.emit("⏳ 执行 [纯音频提取] 协议，调用 ffmpeg 引擎进行 MP3 转换...")
            cmd.extend([
                '-f', 'bestaudio',
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', '0'
            ])
        else:
            self.log_signal.emit("⏳ 执行 [最高画质] 协议，自动合并最佳音视频流...")
            cmd.extend(['-f', 'bestvideo+bestaudio/best', '--merge-output-format', 'mp4'])

        cmd.append(self.url)

        try:
            # 启动子进程，隐藏控制台窗口 (Windows)
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo
                # 【乱码修复】：移除了 text=True 和强制 utf-8，改用底层字节流读取
            )

            # 实时读取终端输出流 (读取 bytes)
            for line_bytes in iter(process.stdout.readline, b''):
                try:
                    # 先尝试用 UTF-8 解码
                    clean_line = line_bytes.decode('utf-8').strip()
                except UnicodeDecodeError:
                    # 若失败，强制使用国标 GB18030 解码 (完美解决 Windows 下中文路径的  乱码问题)
                    clean_line = line_bytes.decode('gb18030', errors='replace').strip()

                if clean_line:
                    # 过滤一些无用的冗长信息，保持终端清爽
                    if "[download]" in clean_line or "[ExtractAudio]" in clean_line or "[Merger]" in clean_line:
                        self.log_signal.emit(f"> {clean_line}")

            process.wait()

            if process.returncode == 0:
                self.log_signal.emit("-" * 40 + "\n🎉 量子捕获行动执行完毕，数据已安全着陆！")
                self.finished_signal.emit(True)
            else:
                self.log_signal.emit("-" * 40 + f"\n❌ 捕获失败，引擎返回异常代码: {process.returncode}")
                self.finished_signal.emit(False)

        except Exception as e:
            self.log_signal.emit(f"❌ 进程崩溃 | 错误详情: {e}")
            self.finished_signal.emit(False)


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
        title_lbl = QLabel("音视频链接获取引擎")
        title_lbl.setStyleSheet("color: #FF9800; font-size: 22px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 2. 目标链接输入区
        url_layout = QHBoxLayout()
        self.lbl_url = QLabel("目标链接:")
        self.lbl_url.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_url.setFixedWidth(90)

        self.entry_url = QLineEdit()
        self.entry_url.setPlaceholderText("请输入需要捕获的视频网址 (如 YouTube, Bilibili, X 等)...")
        self.entry_url.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
            }
            QLineEdit:focus { border: 1px solid #00FF00; }
        """)

        url_layout.addWidget(self.lbl_url)
        url_layout.addWidget(self.entry_url)
        layout.addLayout(url_layout)

        # 3. 文件夹选择交互区
        folder_layout = QHBoxLayout()
        self.lbl_folder = QLabel("目标停泊区:")
        self.lbl_folder.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_folder.setFixedWidth(90)

        self.entry_folder = QLineEdit()
        self.entry_folder.setPlaceholderText("请选择下载文件存放的目录...")
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

        # 4. 格式选择区
        format_layout = QHBoxLayout()
        self.lbl_format = QLabel("捕获协议:")
        self.lbl_format.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_format.setFixedWidth(90)

        self.combo_format = QComboBox()
        self.combo_format.addItems(["🎬 完整视频 (最高画质+音频自动合并)", "🎵 纯音频 (调用 ffmpeg 剥离 MP3)"])
        self.combo_format.setStyleSheet("""
            QComboBox {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #222;
                color: #00FF00;
                selection-background-color: #444;
            }
        """)

        format_layout.addWidget(self.lbl_format)
        format_layout.addWidget(self.combo_format)
        format_layout.addSpacing(73)
        layout.addLayout(format_layout)

        # 5. 【新增】捕获范围选择区 (单集或表单)
        scope_layout = QHBoxLayout()
        self.lbl_scope = QLabel("捕获范围:")
        self.lbl_scope.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_scope.setFixedWidth(90)

        self.combo_scope = QComboBox()
        self.combo_scope.addItems(["📄 仅捕获当前资源 (单集)", "📑 捕获整个表单/列表 (批量)"])
        self.combo_scope.setStyleSheet("""
            QComboBox {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #222;
                color: #00FF00;
                selection-background-color: #444;
            }
        """)

        scope_layout.addWidget(self.lbl_scope)
        scope_layout.addWidget(self.combo_scope)
        scope_layout.addSpacing(73)
        layout.addLayout(scope_layout)

        # 6. 实时终端日志框
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
        self.log_console.setText("等待初始化捕获指令 (支持 yt-dlp 底层协议与 ffmpeg 音视频无损混流)...\n")
        layout.addWidget(self.log_console)

        # 7. 核心执行按钮
        self.btn_start = QPushButton("🚀 启动量子捕获")
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
            QPushButton:disabled { color: #555; border: 1px solid #555; background-color: transparent; }
        """)
        self.btn_start.clicked.connect(self.start_download)
        layout.addWidget(self.btn_start, 0, Qt.AlignCenter)

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "选择存放下载文件的目录")
        if folder_path:
            self.entry_folder.setText(folder_path)
            self.log_console.append(f"> 目标停泊区已锁定: {folder_path}")

    def append_log(self, text):
        self.log_console.append(text)
        self.log_console.moveCursor(QTextCursor.End)

    def start_download(self):
        url = self.entry_url.text().strip()
        folder_path = self.entry_folder.text().strip()
        format_index = self.combo_format.currentIndex()
        scope_index = self.combo_scope.currentIndex() # 获取单集或表单状态

        if not url:
            QMessageBox.warning(self, "协议拦截", "请先输入有效的目标链接！")
            return

        if not folder_path or not os.path.isdir(folder_path):
            QMessageBox.warning(self, "权限拒绝", "请先选择一个有效的本地停泊区目录！")
            return

        # 锁定 UI
        self.btn_start.setDisabled(True)
        self.btn_browse.setDisabled(True)
        self.entry_url.setDisabled(True)
        self.combo_format.setDisabled(True)
        self.combo_scope.setDisabled(True)
        self.btn_start.setText("⚙️ 数据流解析运转中...")
        self.log_console.clear()

        # 将参数传递给核心工作线程
        self.worker = DownloadWorker(url, folder_path, format_index, scope_index)
        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(self.on_download_finished)
        self.worker.start()

    def on_download_finished(self, is_success):
        # 释放 UI
        self.btn_start.setDisabled(False)
        self.btn_browse.setDisabled(False)
        self.entry_url.setDisabled(False)
        self.combo_format.setDisabled(False)
        self.combo_scope.setDisabled(False)
        self.btn_start.setText("🚀 启动量子捕获")

        if is_success:
            QMessageBox.information(self, "任务简报", "🎉 捕获行动圆满完成，文件已保存至目标停泊区。")
        else:
            QMessageBox.warning(self, "任务异常", "❌ 捕获过程中断，请检查控制台日志 (可能因网络代理或链接失效导致)。")


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
    window.setWindowTitle("网络资源捕获引擎 - 独立沙盒模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(650, 480)
    window.show()
    sys.exit(app.exec())