# -*- coding: utf-8 -*-
import os
from PIL import Image
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication, QTextEdit, QSlider)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QFont, QFontDatabase, QTextCursor


# =================================================================
# 后台异步压缩线程：处理图像缩放、格式转换与画质压缩
# =================================================================
class CompressWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, input_file, output_file, scale_ratio, quality):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.scale_ratio = scale_ratio / 100.0  # 转换为 0.1 到 1.0 之间的小数
        self.quality = quality

    def format_size(self, size):
        if size > 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        return f"{size / 1024:.2f} KB"

    def run(self):
        try:
            self.log_signal.emit(f"[*] 正在读取源图片:\n    {self.input_file}")

            # 突破大图限制
            Image.MAX_IMAGE_PIXELS = None

            original_size = os.path.getsize(self.input_file)
            self.log_signal.emit(f"[-] 原始文件体积: {self.format_size(original_size)}")

            with Image.open(self.input_file) as img:
                out_ext = os.path.splitext(self.output_file)[1].lower()

                # 处理格式兼容性：如果要保存为不支持透明度的格式（如JPG），则将RGBA/P通道转换为RGB
                if out_ext in ['.jpg', '.jpeg'] and img.mode in ('RGBA', 'P', 'LA'):
                    self.log_signal.emit("[-] 目标格式不支持透明通道，正在自动转换为 RGB 模式...")
                    # 创建一个白色背景，防止透明部分变黑
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == 'RGBA':
                        bg.paste(img, mask=img.split()[3])
                    else:
                        bg.paste(img)
                    img = bg

                # 尺寸缩放处理
                if self.scale_ratio < 1.0:
                    new_width = max(1, int(img.width * self.scale_ratio))
                    new_height = max(1, int(img.height * self.scale_ratio))
                    self.log_signal.emit(
                        f"[*] 正在重采样缩放尺寸: {img.width}x{img.height} -> {new_width}x{new_height}")
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    self.log_signal.emit(f"[-] 保持原始分辨率: {img.width}x{img.height}")

                # 执行保存与画质压缩
                self.log_signal.emit(f"[*] 正在执行编码压缩 (设定画质: {self.quality}%)...")
                save_kwargs = {}

                # 仅对支持的格式应用 quality 参数
                if out_ext in ['.jpg', '.jpeg', '.webp']:
                    save_kwargs['quality'] = self.quality
                    save_kwargs['optimize'] = True
                elif out_ext in ['.png']:
                    save_kwargs['optimize'] = True
                    self.log_signal.emit("[-] 提示: PNG是无损格式，画质参数将被忽略，仅执行结构优化。")

                img.save(self.output_file, **save_kwargs)

            compressed_size = os.path.getsize(self.output_file)
            ratio = compressed_size / original_size * 100

            msg = (f"✅ 图像压缩圆满完成！\n\n"
                   f"原体积: {self.format_size(original_size)}\n"
                   f"新体积: {self.format_size(compressed_size)}\n"
                   f"体积占比: {ratio:.1f}%")

            self.log_signal.emit(f"[*] 写入完成！新体积: {self.format_size(compressed_size)} ({ratio:.1f}%)")
            self.finished_signal.emit(True, msg)

        except Exception as e:
            self.finished_signal.emit(False, f"压缩失败！\n报错详情: {str(e)}")


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

        # 1. 标题 (统一为极客橙 #FF9800)
        title_lbl = QLabel("万能图片压缩引擎")
        title_lbl.setStyleSheet("color: #FF9800; font-size: 22px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 2. 输入文件选择区
        input_layout = QHBoxLayout()
        self.lbl_input = QLabel("待压缩图片:")
        self.lbl_input.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_input.setFixedWidth(100)

        self.entry_input = QLineEdit()
        self.entry_input.setReadOnly(True)
        self.entry_input.setPlaceholderText("请选择需要瘦身的图片 (支持多格式)...")
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
        self.entry_output.setPlaceholderText("请指定压缩后图片的保存位置...")
        self.entry_output.setStyleSheet(self.entry_input.styleSheet())

        self.btn_output = QPushButton("另存为...")
        self.btn_output.setCursor(Qt.PointingHandCursor)
        self.style_browse_btn(self.btn_output)
        self.btn_output.clicked.connect(self.select_output_file)

        output_layout.addWidget(self.lbl_output)
        output_layout.addWidget(self.entry_output)
        output_layout.addWidget(self.btn_output)
        layout.addLayout(output_layout)

        # 4. 控制面板区 (缩放与画质)
        controls_layout = QHBoxLayout()

        # 尺寸缩放滑块
        scale_layout = QVBoxLayout()
        self.lbl_scale = QLabel("尺寸缩放: 100%")
        self.lbl_scale.setStyleSheet("color: #E0E0E0; font-size: 13px; font-weight: bold;")
        self.slider_scale = QSlider(Qt.Horizontal)
        self.slider_scale.setRange(10, 100)
        self.slider_scale.setValue(100)
        self.style_slider(self.slider_scale)
        self.slider_scale.valueChanged.connect(lambda v: self.lbl_scale.setText(f"尺寸缩放: {v}%"))
        scale_layout.addWidget(self.lbl_scale)
        scale_layout.addWidget(self.slider_scale)

        # 导出画质滑块
        quality_layout = QVBoxLayout()
        self.lbl_quality = QLabel("导出画质: 80%")
        self.lbl_quality.setStyleSheet("color: #E0E0E0; font-size: 13px; font-weight: bold;")
        self.slider_quality = QSlider(Qt.Horizontal)
        self.slider_quality.setRange(1, 100)
        self.slider_quality.setValue(80)
        self.style_slider(self.slider_quality)
        self.slider_quality.valueChanged.connect(lambda v: self.lbl_quality.setText(f"导出画质: {v}%"))
        quality_layout.addWidget(self.lbl_quality)
        quality_layout.addWidget(self.slider_quality)

        controls_layout.addLayout(scale_layout)
        controls_layout.addSpacing(30)
        controls_layout.addLayout(quality_layout)
        layout.addLayout(controls_layout)

        # 5. 透明实时日志区 (统一终端绿)
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
            ">_ 万能图片压缩引擎已就绪...\n"
            ">_ 特性支持：\n"
            "  1. 支持 JPG, PNG, WEBP, BMP 等绝大多数主流格式。\n"
            "  2. 可自由调节分辨率比例（物理降维）。\n"
            "  3. 可自由指定导出画质（编码降维）。\n"
            "  4. 自动处理透明图层转 JPG 时的通道冲突问题。")
        layout.addWidget(self.log_area)

        # 6. 核心执行按钮 (统一镂空霓虹绿发光)
        self.btn_start = QPushButton("🚀 开始极限压缩")
        self.btn_start.setFixedSize(260, 45)
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
        self.btn_start.clicked.connect(self.start_compress)

        layout.addWidget(self.btn_start, 0, Qt.AlignCenter)

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

    def style_slider(self, slider):
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #555;
                height: 6px;
                background: rgba(0,0,0,100);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #00FF00;
                border: 1px solid #222;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
        """)

    def select_input_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择待压缩的图片", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tiff);;All Files (*)"
        )
        if file_path:
            self.entry_input.setText(file_path)
            self.log_area.append(f"\n>_ 锁定源图片: {file_path}")
            self.log_area.moveCursor(QTextCursor.End)

            if not self.entry_output.text():
                # 自动生成默认的输出路径
                file_dir = os.path.dirname(file_path)
                file_name, file_ext = os.path.splitext(os.path.basename(file_path))
                default_out = os.path.join(file_dir, f"{file_name}_min{file_ext}")
                self.entry_output.setText(default_out)
                self.log_area.append(f">_ 自动配置默认输出路径: {default_out}")
                self.log_area.moveCursor(QTextCursor.End)

    def select_output_file(self):
        source_path = self.entry_input.text()
        default_ext = ".jpg"
        if source_path:
            default_ext = os.path.splitext(source_path)[1]

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存压缩后的图片",
            self.entry_output.text() or f"压缩后图片{default_ext}",
            "Images (*.jpg *.jpeg *.png *.webp *.bmp);;All Files (*)"
        )
        if file_path:
            self.entry_output.setText(file_path)
            self.log_area.append(f">_ 锁定目标输出路径: {file_path}")
            self.log_area.moveCursor(QTextCursor.End)

    def start_compress(self):
        input_file = self.entry_input.text().strip()
        output_file = self.entry_output.text().strip()

        if not input_file or not os.path.exists(input_file):
            QMessageBox.warning(self, "操作提示", "请先选择真实存在的源图片文件！")
            return
        if not output_file:
            QMessageBox.warning(self, "操作提示", "请指定输出文件的保存路径！")
            return

        self.btn_start.setText("⏳ 正在全力压缩中...")
        self.btn_start.setDisabled(True)
        self.btn_input.setDisabled(True)
        self.btn_output.setDisabled(True)

        # 禁用滑块防止运行中修改
        self.slider_scale.setDisabled(True)
        self.slider_quality.setDisabled(True)

        self.log_area.append("\n==============================================")
        self.log_area.append(">_ 引擎启动，开始执行降维序列...")
        self.log_area.moveCursor(QTextCursor.End)

        scale_val = self.slider_scale.value()
        quality_val = self.slider_quality.value()

        self.worker = CompressWorker(input_file, output_file, scale_val, quality_val)
        self.worker.log_signal.connect(self.update_log)
        self.worker.finished_signal.connect(self.compress_finished)
        self.worker.start()

    def update_log(self, msg):
        self.log_area.append(msg)
        self.log_area.moveCursor(QTextCursor.End)

    def compress_finished(self, success, msg):
        self.btn_start.setText("🚀 开始极限压缩")
        self.btn_start.setDisabled(False)
        self.btn_input.setDisabled(False)
        self.btn_output.setDisabled(False)
        self.slider_scale.setDisabled(False)
        self.slider_quality.setDisabled(False)

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

    icon_path = os.path.abspath(os.path.join(current_dir, "../..", "imgs", "script.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = PluginWidget()
    window.setWindowTitle("万能图片压缩 - 独立调试模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(650, 480)
    window.show()
    sys.exit(app.exec())