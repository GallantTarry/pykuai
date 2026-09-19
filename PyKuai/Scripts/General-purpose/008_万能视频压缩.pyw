# -*- coding: utf-8 -*-
import os
import sys
import json
import re
import subprocess
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication, QTextEdit, QProgressBar)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPainter, QColor, QPainterPath, QPen, QFont, QFontDatabase, QTextCursor

# =================================================================
# 引擎路径解析 (适配 PyKuai 项目结构：Scripts/分类/本脚本 -> ../../tools)
# =================================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    # 假设本脚本位于 Scripts/某文件夹/ 目录下，向上两级即为根目录
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

TOOLS_DIR = os.path.join(BASE_DIR, "tools")
FFMPEG_PATH = os.path.join(TOOLS_DIR, "ffmpeg.exe")
FFPROBE_PATH = os.path.join(TOOLS_DIR, "ffprobe.exe")


# =================================================================
# 自定义胶囊圆角进度条：利用 QPainterPath 绝对裁切，告别直角矩形
# =================================================================
class CapsuleProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)
        self.setTextVisible(False)  # 禁用系统文字，改由底层抗锯齿手绘
        self.chunk_color = QColor("#00FF00")  # 默认高亮绿

    def set_chunk_color(self, hex_color):
        self.chunk_color = QColor(hex_color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)  # 开启全局抗锯齿

        rect = self.rect()
        radius = rect.height() / 2  # 完美半圆胶囊弧度

        # 1. 绘制背景圆角胶囊底框
        painter.setPen(QPen(QColor("#444"), 1))
        painter.setBrush(QColor(0, 0, 0, 100))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)

        # 2. 绘制内部填充（利用路径遮罩强行圆角，彻底解决矩形溢出）
        val = self.value()
        min_val = self.minimum()
        max_val = self.maximum() or 100

        if max_val > min_val and val > min_val:
            ratio = min(1.0, max(0.0, (val - min_val) / (max_val - min_val)))
            progress_width = rect.width() * ratio

            clip_path = QPainterPath()
            clip_path.addRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)
            painter.setClipPath(clip_path)

            painter.setPen(Qt.NoPen)
            painter.setBrush(self.chunk_color)
            painter.drawRect(rect.x(), rect.y(), int(progress_width), rect.height())

        # 3. 居中绘制百分比文字（强制继承全局 zpix 像素字体）
        painter.setClipping(False)
        painter.setPen(QColor("#FFFFFF"))
        font = self.font()
        font.setBold(True)
        painter.setFont(font)
        percent_text = f"{int((val - min_val) / (max_val - min_val) * 100)}%" if max_val > min_val else f"{val}%"
        painter.drawText(rect, Qt.AlignCenter, percent_text)


# =================================================================
# 后台异步压缩线程：解析时长、计算码率、实时截获 FFmpeg 进度
# =================================================================
class VideoCompressWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal(bool, str)

    def __init__(self, input_file, output_file, target_size_mb):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.target_size_mb = float(target_size_mb)

    def run(self):
        try:
            if not os.path.exists(FFMPEG_PATH) or not os.path.exists(FFPROBE_PATH):
                self.finished_signal.emit(False, "找不到引擎文件！请确保 tools 目录下有 ffmpeg.exe 和 ffprobe.exe")
                return

            self.log_signal.emit(f"[*] 正在分析视频流信息:\n    {self.input_file}")

            # 1. 获取视频时长
            duration = self.get_video_duration(self.input_file)
            if not duration:
                self.finished_signal.emit(False, "无法读取视频时长，可能是视频文件已损坏。")
                return

            # 2. 码率计算
            audio_bitrate_kbps = 128
            target_total_bitrate_kbps = (self.target_size_mb * 8192) / duration
            target_video_bitrate_kbps = target_total_bitrate_kbps - audio_bitrate_kbps

            if target_video_bitrate_kbps <= 50:
                self.finished_signal.emit(False, "目标体积过小，无法为该时长的视频分配足够码率！请调大目标 MB。")
                return

            video_bitrate_str = f"{int(target_video_bitrate_kbps)}k"
            self.log_signal.emit(f"[-] 视频时长: {duration:.2f} 秒")
            self.log_signal.emit(f"[-] 目标总码率: {int(target_total_bitrate_kbps)} kbps")
            self.log_signal.emit(f"[-] 分配视频码率: {video_bitrate_str} (音频固定 128k)")
            self.log_signal.emit("[*] 正在执行重编码，请关注下方进度条...")

            # 3. 组装 FFmpeg 命令 (单步压制)
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", self.input_file,
                "-c:v", "libx264",
                "-b:v", video_bitrate_str,
                "-c:a", "aac",
                "-b:a", f"{audio_bitrate_kbps}k",
                self.output_file
            ]

            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='ignore',
                startupinfo=startupinfo
            )

            # 4. 实时解析进度输出
            time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2}\.\d+)")
            for line in process.stdout:
                match = time_regex.search(line)
                if match:
                    h, m, s = match.groups()
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)
                    progress = int((current_time / duration) * 100)
                    self.progress_signal.emit(min(progress, 99))

            process.wait()

            if process.returncode == 0:
                self.progress_signal.emit(100)
                original_size = os.path.getsize(self.input_file) / (1024 * 1024)
                compressed_size = os.path.getsize(self.output_file) / (1024 * 1024)
                ratio = (compressed_size / original_size) * 100

                msg = (f"✅ 视频压缩圆满完成！\n\n"
                       f"原体积: {original_size:.2f} MB\n"
                       f"新体积: {compressed_size:.2f} MB\n"
                       f"体积占比: {ratio:.1f}%")
                self.log_signal.emit(f"[*] 写入完成！新体积: {compressed_size:.2f} MB ({ratio:.1f}%)")
                self.finished_signal.emit(True, msg)
            else:
                self.finished_signal.emit(False, "FFmpeg 引擎执行中断或报错，请检查源文件格式。")

        except Exception as e:
            self.finished_signal.emit(False, f"压缩核心崩溃！\n报错详情: {str(e)}")

    def get_video_duration(self, file_path):
        try:
            cmd = [
                FFPROBE_PATH, "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", file_path
            ]
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore',
                startupinfo=startupinfo
            )
            if not result.stdout:
                return None
            info = json.loads(result.stdout)
            return float(info['format']['duration'])
        except Exception:
            return None


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget，适配 PyKuai
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        # 1. 标题 (统一为极客橙色)
        title_lbl = QLabel("万能视频压缩引擎")
        title_lbl.setStyleSheet("color: #FF9800; font-size: 22px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 2. 输入文件选择区
        input_layout = QHBoxLayout()
        self.lbl_input = QLabel("待压缩视频:")
        self.lbl_input.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_input.setFixedWidth(100)

        self.entry_input = QLineEdit()
        self.entry_input.setReadOnly(True)
        self.entry_input.setPlaceholderText("请选择需要瘦身的视频文件 (.mp4 .mkv .avi)...")
        self.entry_input.setStyleSheet(self.get_line_edit_style())

        self.btn_input = QPushButton("浏览...")
        self.btn_input.setCursor(Qt.PointingHandCursor)
        self.style_browse_btn(self.btn_input)
        self.btn_input.clicked.connect(self.select_input_file)

        input_layout.addWidget(self.lbl_input)
        input_layout.addWidget(self.entry_input)
        input_layout.addWidget(self.btn_input)
        layout.addLayout(input_layout)

        # 3. 输出文件路径选择区
        output_layout = QHBoxLayout()
        self.lbl_output = QLabel("导出至:")
        self.lbl_output.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_output.setFixedWidth(100)

        self.entry_output = QLineEdit()
        self.entry_output.setReadOnly(True)
        self.entry_output.setPlaceholderText("请指定压缩后视频的保存位置...")
        self.entry_output.setStyleSheet(self.get_line_edit_style())

        self.btn_output = QPushButton("另存为...")
        self.btn_output.setCursor(Qt.PointingHandCursor)
        self.style_browse_btn(self.btn_output)
        self.btn_output.clicked.connect(self.select_output_file)

        output_layout.addWidget(self.lbl_output)
        output_layout.addWidget(self.entry_output)
        output_layout.addWidget(self.btn_output)
        layout.addLayout(output_layout)

        # 4. 控制面板区 (目标大小设置)
        controls_layout = QHBoxLayout()
        self.lbl_size = QLabel("压缩目标大小 (MB):")
        self.lbl_size.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_size.setFixedWidth(140)

        self.entry_size = QLineEdit()
        self.entry_size.setText("100")
        self.entry_size.setPlaceholderText("输入期望的 MB 值，例如 50")
        self.entry_size.setStyleSheet(self.get_line_edit_style())
        self.entry_size.setFixedWidth(150)

        controls_layout.addWidget(self.lbl_size)
        controls_layout.addWidget(self.entry_size)
        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # 5. 透明实时日志区
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("""
            QTextEdit {
                background-color: rgba(10, 10, 10, 200);
                color: #00FF00;
                border: 1px solid #333;
                border-radius: 5px;
                padding: 10px;
                font-size: 13px;
            }
        """)
        self.log_area.append(
            ">_ 视频压缩核心 (FFmpeg) 已就绪...\n"
            ">_ 特性支持：\n"
            f"  [依赖引擎]: {FFMPEG_PATH}\n"
            "  1. 自动根据目标体积计算最佳视频码率。\n"
            "  2. 基于 libx264 编码，兼顾高画质与高压率。\n"
            "  3. 实时抗锯齿胶囊进度反馈。")
        layout.addWidget(self.log_area)

        # 6. 原生抗锯齿胶囊圆角进度条
        self.progress_bar = CapsuleProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 7. 核心执行按钮 (统一为镂空霓虹绿特效)
        self.btn_start = QPushButton("🚀 一键极限压缩")
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
        self.btn_start.clicked.connect(self.start_compress)

        layout.addWidget(self.btn_start, 0, Qt.AlignCenter)

    def get_line_edit_style(self):
        return """
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
            }
            QLineEdit:focus { border: 1px solid #00FF00; }
        """

    def style_browse_btn(self, btn):
        btn.setStyleSheet("""
            QPushButton { 
                background-color: #444; 
                color: white; 
                border-radius: 5px; 
                padding: 8px 15px; 
                font-weight: bold;
            }
            QPushButton:hover { background-color: #666; }
            QPushButton:disabled { background-color: #333; color: #777; }
        """)

    def select_input_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择待压缩的视频", "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.flv);;All Files (*)"
        )
        if file_path:
            self.entry_input.setText(file_path)
            self.log_area.append(f"\n>_ 锁定源视频: {file_path}")
            self.log_area.moveCursor(QTextCursor.End)

            if not self.entry_output.text():
                file_dir = os.path.dirname(file_path)
                file_name, _ = os.path.splitext(os.path.basename(file_path))
                default_out = os.path.join(file_dir, f"{file_name}_min.mp4")
                self.entry_output.setText(default_out)
                self.log_area.append(f">_ 自动配置默认输出路径: {default_out}")
                self.log_area.moveCursor(QTextCursor.End)

    def select_output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存压缩后的视频",
            self.entry_output.text() or "压缩后视频.mp4",
            "MP4 Video (*.mp4);;All Files (*)"
        )
        if file_path:
            self.entry_output.setText(file_path)
            self.log_area.append(f">_ 锁定目标输出路径: {file_path}")
            self.log_area.moveCursor(QTextCursor.End)

    def start_compress(self):
        input_file = self.entry_input.text().strip()
        output_file = self.entry_output.text().strip()
        target_size = self.entry_size.text().strip()

        if not input_file or not os.path.exists(input_file):
            QMessageBox.warning(self, "操作提示", "请先选择真实存在的源视频文件！")
            return
        if not output_file:
            QMessageBox.warning(self, "操作提示", "请指定输出文件的保存路径！")
            return
        try:
            target_mb = float(target_size)
            if target_mb <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "操作提示", "目标大小必须是大于 0 的有效数字！")
            return

        self.btn_start.setText("⏳ 正在跨维压缩中...")
        self.btn_start.setDisabled(True)
        self.btn_input.setDisabled(True)
        self.btn_output.setDisabled(True)
        self.entry_size.setDisabled(True)

        self.progress_bar.setValue(0)
        self.progress_bar.set_chunk_color("#FF4500")  # 运行时切为警示橙红

        self.log_area.append("\n==============================================")
        self.log_area.append(f">_ 引擎启动，目标体积 {target_mb}MB，开始转码...")
        self.log_area.moveCursor(QTextCursor.End)

        self.worker = VideoCompressWorker(input_file, output_file, target_mb)
        self.worker.log_signal.connect(self.update_log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.compress_finished)
        self.worker.start()

    def update_log(self, msg):
        self.log_area.append(msg)
        self.log_area.moveCursor(QTextCursor.End)

    def update_progress(self, percent):
        self.progress_bar.setValue(percent)

    def compress_finished(self, success, msg):
        self.btn_start.setText("🚀 一键极限压缩")
        self.btn_start.setDisabled(False)
        self.btn_input.setDisabled(False)
        self.btn_output.setDisabled(False)
        self.entry_size.setDisabled(False)

        self.progress_bar.set_chunk_color("#00FF00")  # 完成后恢复科技绿

        self.log_area.append(msg)
        self.log_area.append("==============================================\n")
        self.log_area.moveCursor(QTextCursor.End)

        if success:
            QMessageBox.information(self, "压缩成功", msg)
        else:
            QMessageBox.critical(self, "运行异常", msg)


# =================================================================
# 独立调试机制
# =================================================================
if __name__ == "__main__":
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
    window.setWindowTitle("万能视频压缩引擎 - 独立沙盒模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(650, 500)
    window.show()
    sys.exit(app.exec())