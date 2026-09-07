# -*- coding: utf-8 -*-
import os
import sys
import time
import datetime
import ctypes
import cv2
import numpy as np
import keyboard

# ==========================================
# 核心黑魔法 0：彻底解决 Windows 缩放(DPI)导致的坐标偏移与截图不符
# 必须在初始化 QApplication 之前调用，抢夺物理像素的绝对控制权
# ==========================================
if sys.platform == 'win32':
    try:
        # Windows 8.1+ (强制按显示器物理像素映射)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # Windows Vista / 7 / 8
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLabel,
                               QFileDialog, QMessageBox, QApplication, QScrollArea, QFrame)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QRect, QPoint, QRectF
from PySide6.QtGui import QIcon, QPainter, QColor, QPen, QImage, QPixmap, QPainterPath

# ==========================================
# 动态解析全局路径
# ==========================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(CURRENT_DIR))
ICON_PATH = os.path.join(BASE_DIR, "imgs", "script.ico")


# ==========================================
# 模块一：全屏冻结与区域框选 (掏空透明版)
# ==========================================
class SelectionOverlay(QWidget):
    """全屏透明遮罩，用于确定长截图区域，选区内部完全透明"""
    rect_selected = Signal(QRect)
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setCursor(Qt.CrossCursor)

        self.screen_pix = QApplication.primaryScreen().grabWindow(0)
        self.start_pos = QPoint()
        self.end_pos = QPoint()
        self.is_drawing = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.screen_pix)

        path = QPainterPath()
        path.addRect(QRectF(self.rect()))

        if not self.start_pos.isNull() and not self.end_pos.isNull():
            selected_rect = QRect(self.start_pos, self.end_pos).normalized()
            path.addRect(QRectF(selected_rect))

            path.setFillRule(Qt.OddEvenFill)
            painter.setBrush(QColor(0, 0, 0, 150))
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)

            painter.setPen(QPen(QColor(0, 255, 0), 2, Qt.SolidLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(selected_rect)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(selected_rect.topLeft() + QPoint(5, -5),
                             f"锁定区域: {selected_rect.width()} x {selected_rect.height()} px")
        else:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.end_pos = self.start_pos
            self.is_drawing = True

    def mouseMoveEvent(self, event):
        if self.is_drawing:
            self.end_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_drawing:
            rect = QRect(self.start_pos, self.end_pos).normalized()
            if rect.width() > 100 and rect.height() > 100:
                self.rect_selected.emit(rect)
                self.close()
            else:
                self.start_pos = QPoint()
                self.end_pos = QPoint()
                self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()


# ==========================================
# 模块二：防止穿帮的外围提示虚框
# ==========================================
class BorderOverlay(QWidget):
    """滚动期间悬浮在屏幕上的纯绿色边框，鼠标事件穿透"""

    def __init__(self, target_rect):
        super().__init__()
        self.setWindowFlags(Qt.WindowTransparentForInput | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(QApplication.primaryScreen().geometry())
        self.target_rect = target_rect

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor(0, 255, 0, 200), 2, Qt.DashLine)
        painter.setPen(pen)

        adjusted_rect = self.target_rect.adjusted(-2, -2, 2, 2)
        painter.drawRect(adjusted_rect)

        painter.setPen(QColor(0, 255, 0))
        painter.drawText(adjusted_rect.bottomLeft() + QPoint(0, 25),
                         "↑ 锁定此区域：向下滚动鼠标 ( Enter 保存 | Esc 取消 )")


# ==========================================
# 模块三：带滚动条的实时预览窗口 (自带隐身魔法)
# ==========================================
class ThumbnailWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setFixedSize(300, 500)

        # 核心黑魔法：调用 Windows DWM API 排除自身不被截图
        if sys.platform == 'win32':
            try:
                hwnd = int(self.winId())
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
            except Exception as e:
                pass

        screen_geo = QApplication.primaryScreen().availableGeometry()
        self.move(screen_geo.width() - self.width() - 20, screen_geo.height() - self.height() - 20)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        frame = QFrame()
        frame.setStyleSheet("QFrame { background-color: #1E1E1E; border: 2px solid #00FFFF; }")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(5, 5, 5, 5)

        title = QLabel("实时长图生长预览")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #00FFFF; font-weight: bold; border: none; font-size: 14px;")
        frame_layout.addWidget(title)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #444; background: #000; }")

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.scroll_area.setWidget(self.image_label)
        frame_layout.addWidget(self.scroll_area)

        layout.addWidget(frame)

    def update_thumbnail(self, cv_img):
        cv_img = np.ascontiguousarray(cv_img)
        h, w, _ = cv_img.shape
        bytes_per_line = 3 * w
        q_img = QImage(cv_img.data, w, h, bytes_per_line, QImage.Format_BGR888)
        pixmap = QPixmap.fromImage(q_img)

        target_width = self.scroll_area.width() - 25
        scaled_pixmap = pixmap.scaledToWidth(target_width, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)

        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


# ==========================================
# 模块四：后台截取拼接线程 (高频采样抗丢帧版)
# ==========================================
class CaptureWorker(QThread):
    update_thumbnail = Signal(object)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, rect, save_dir):
        super().__init__()
        self.rect = rect
        self.save_dir = save_dir
        self.is_recording = True
        self.is_cancelled = False
        self.screen = QApplication.primaryScreen()

    def run(self):
        try:
            stitched_img = None
            last_valid_frame = None

            while self.is_recording:
                pixmap = self.screen.grabWindow(0, self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height())
                image = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)

                ptr = image.constBits()
                arr = np.array(ptr).reshape(image.height(), image.width(), 4)
                img_curr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

                if stitched_img is None:
                    stitched_img = img_curr
                    last_valid_frame = img_curr
                    self.update_thumbnail.emit(stitched_img)
                    continue

                h = img_curr.shape[0]

                # 【抗高速滚动黑魔法 1】：锚点极限下移，取 70%~90% 区间
                t_start = int(h * 0.70)
                t_end = int(h * 0.90)
                template = last_valid_frame[t_start:t_end, :]

                if np.mean(cv2.absdiff(img_curr, last_valid_frame)) > 1.0:
                    res = cv2.matchTemplate(img_curr, template, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)

                    # 【抗高速滚动黑魔法 2】：略微放宽置信度到 0.65，防止网页滚动太快导致的渲染撕裂/模糊
                    if max_val > 0.65:
                        overlap_y = max_loc[1]
                        shift = t_start - overlap_y
                        if shift > 5:
                            new_part = img_curr[h - shift: h, :]
                            stitched_img = np.vstack((stitched_img, new_part))
                            last_valid_frame = img_curr
                            self.update_thumbnail.emit(stitched_img)

                # 【抗高速滚动黑魔法 3】：将采样频率从 150ms 暴涨到 20ms（约50FPS）！
                time.sleep(0.02)

            if self.is_cancelled:
                self.error.emit("已通过 Esc 键取消长截图。")
            elif stitched_img is not None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(self.save_dir, f"PyKuai长截图_{timestamp}.png")
                cv2.imencode('.png', stitched_img)[1].tofile(save_path)
                self.finished.emit(save_path)

        except Exception as e:
            self.error.emit(f"底层错误: {str(e)}")

    def stop_and_save(self):
        self.is_recording = False

    def cancel_and_discard(self):
        self.is_cancelled = True
        self.is_recording = False


# ==========================================
# 模块五：主控面板与信号路由
# ==========================================
class HotkeySignal(QObject):
    triggered = Signal()
    enter_pressed = Signal()
    esc_pressed = Signal()


class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.save_dir = os.path.expanduser("~\\Desktop")
        self.is_listening = False

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.signal_bridge = HotkeySignal()
        self.signal_bridge.triggered.connect(self.start_selection_mode)
        self.signal_bridge.enter_pressed.connect(self.commit_capture)
        self.signal_bridge.esc_pressed.connect(self.cancel_capture)

        self.selection_overlay = None
        self.border_overlay = None
        self.thumbnail_win = None
        self.worker = None

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        lbl_title = QLabel("✂️ PyKuai 极客锁定长截图")
        lbl_title.setStyleSheet("color: #00FFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(lbl_title, 0, Qt.AlignCenter)

        lbl_desc = QLabel(
            "1. 开启下方监听 (需管理员权限)\n2. 网页按 [ Ctrl + Alt + R ] 呼出透视全屏冻结\n3. 拖拽鼠标绘制【锁定截取区域】(可按 Esc 退出)\n4. 向下滚动网页，右下角【实时生长预览】\n5. 按下 [ Enter ] 瞬间保存长图，或按 [ Esc ] 取消！")
        lbl_desc.setStyleSheet("color: #AAAAAA; font-size: 14px; line-height: 1.6;")
        lbl_desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_desc)

        self.btn_dir = QPushButton(f"📁 保存目录: {self.save_dir}")
        self.btn_dir.setCursor(Qt.PointingHandCursor)
        self.btn_dir.setStyleSheet(self._btn_style("#AAAAAA"))
        self.btn_dir.clicked.connect(self.select_dir)
        layout.addWidget(self.btn_dir)

        self.btn_toggle = QPushButton("🔴 开启快捷键监听 (Ctrl+Alt+R)")
        self.btn_toggle.setFixedHeight(50)
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_toggle.setStyleSheet(self._btn_style("#00FF00"))
        self.btn_toggle.clicked.connect(self.toggle_listening)
        layout.addWidget(self.btn_toggle)

        self.lbl_status = QLabel("就绪。请开启监听。")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #555555; font-weight: bold; font-size: 14px;")
        layout.addWidget(self.lbl_status)
        layout.addStretch()

    def _btn_style(self, color):
        return f"""
            QPushButton {{ 
                background-color: transparent; 
                color: {color}; border: 1px solid {color};
                font-weight: bold; font-size: 15px; 
                border-radius: 6px; padding: 10px;
            }}
            QPushButton:hover {{ background-color: rgba(255, 255, 255, 10); }}
        """

    def select_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录", self.save_dir)
        if d:
            self.save_dir = d
            self.btn_dir.setText(f"📁 保存目录: {self.save_dir}")

    def toggle_listening(self):
        if not self.is_listening:
            try:
                keyboard.add_hotkey('ctrl+alt+r', lambda: self.signal_bridge.triggered.emit())
                self.is_listening = True
                self.btn_toggle.setText("🟢 监听中... (等待 Ctrl+Alt+R 框选)")
                self.btn_toggle.setStyleSheet(self._btn_style("#FF4444"))
                self.lbl_status.setText("后台守护中。切出程序去截图吧。")
                self.lbl_status.setStyleSheet("color: #00FF00; font-weight: bold;")
            except Exception as e:
                QMessageBox.warning(self, "权限不足", f"绑定失败，请以管理员身份运行。\n{e}")
        else:
            keyboard.remove_all_hotkeys()
            self.is_listening = False
            self.btn_toggle.setText("🔴 开启快捷键监听 (Ctrl+Alt+R)")
            self.btn_toggle.setStyleSheet(self._btn_style("#00FF00"))
            self.lbl_status.setText("已停止监听。")
            self.lbl_status.setStyleSheet("color: #555555;")

    def start_selection_mode(self):
        if self.worker and self.worker.isRunning():
            return

        self.lbl_status.setText("请框选长截图区域 (按 Esc 退出)...")
        self.lbl_status.setStyleSheet("color: #FFFF00;")

        self.selection_overlay = SelectionOverlay()
        self.selection_overlay.rect_selected.connect(self.start_scrolling_mode)
        self.selection_overlay.cancelled.connect(lambda: self.on_capture_error("已在框选阶段取消。"))
        self.selection_overlay.show()

    def start_scrolling_mode(self, rect):
        self.border_overlay = BorderOverlay(rect)
        self.border_overlay.show()

        self.thumbnail_win = ThumbnailWindow()
        self.thumbnail_win.show()

        self.enter_hook = keyboard.on_press_key('enter', lambda e: self.signal_bridge.enter_pressed.emit())
        self.esc_hook = keyboard.on_press_key('esc', lambda e: self.signal_bridge.esc_pressed.emit())

        self.worker = CaptureWorker(rect, self.save_dir)
        self.worker.update_thumbnail.connect(self.thumbnail_win.update_thumbnail)
        self.worker.finished.connect(self.on_capture_finished)
        self.worker.error.connect(self.on_capture_error)
        self.worker.start()

        self.lbl_status.setText("🟢 正在录制！向下滚动，按 Enter 保存，按 Esc 丢弃。")
        self.lbl_status.setStyleSheet("color: #00FF00; font-weight: bold;")

    def _cleanup_hotkeys_and_ui(self):
        """统一清理录屏热键和所有悬浮窗"""
        for hook_name in ['enter_hook', 'esc_hook']:
            if hasattr(self, hook_name):
                try:
                    keyboard.unhook(getattr(self, hook_name))
                except:
                    pass
                delattr(self, hook_name)

        if self.border_overlay:
            self.border_overlay.close()
            self.border_overlay = None

        if self.thumbnail_win:
            self.thumbnail_win.close()
            self.thumbnail_win = None

    def commit_capture(self):
        self._cleanup_hotkeys_and_ui()
        if self.worker and self.worker.is_recording:
            self.worker.stop_and_save()
            self.lbl_status.setText("🧩 正在拼接并写入磁盘...")

    def cancel_capture(self):
        self._cleanup_hotkeys_and_ui()
        if self.worker and self.worker.is_recording:
            self.worker.cancel_and_discard()

    def on_capture_finished(self, path):
        self.lbl_status.setText(f"✅ 所见即所得！已保存至:\n{path}")
        self.lbl_status.setStyleSheet("color: #00FF00; font-weight: bold;")

    def on_capture_error(self, err):
        self.lbl_status.setText(f"🚫 {err}")
        self.lbl_status.setStyleSheet("color: #FFA500; font-weight: bold;")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PluginWidget()
    window.setWindowTitle("PyKuai 极客长截图")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 255);")
    window.resize(450, 450)
    window.show()
    sys.exit(app.exec())