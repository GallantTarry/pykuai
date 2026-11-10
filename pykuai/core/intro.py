# -*- coding: utf-8 -*-
"""
PyKuai Desktop Snake Slither-in Overlay
像素青蛇从 PowerShell 窗口外侧桌面上游走，爬向窗口左上角图标位置并激起绿光脉冲，
将 Windows PowerShell 标题与图标瞬间激活为 pykuai。
"""
import os
import sys
import math
import ctypes
from ctypes import wintypes

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QKeyEvent, QMouseEvent

from pykuai.core.ui import apply_terminal_identity


def find_terminal_window():
    """精确获取当前前台激活的终端窗口句柄 (Windows Terminal 或 Console)"""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # 1. 优先获取当前前台活跃窗口
    fg = user32.GetForegroundWindow()
    if fg and user32.IsWindowVisible(fg):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(fg, buf, 256)
        cname = buf.value
        if cname in ["CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass"]:
            return fg
        user32.GetWindowTextW(fg, buf, 256)
        title = buf.value.lower()
        if any(k in title for k in ["powershell", "cmd", "terminal", "pykuai"]):
            return fg

    # 2. 获取当前控制台窗口句柄
    c_hwnd = kernel32.GetConsoleWindow()
    if c_hwnd and user32.IsWindowVisible(c_hwnd):
        return c_hwnd

    # 3. 遍历查找可见的 Windows Terminal (CASCADIA_HOSTING_WINDOW_CLASS) 或 控制台
    candidates = []

    def enum_cb(h, _):
        if user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, buf, 256)
            if buf.value in ["CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass"]:
                candidates.append(h)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    if candidates:
        return candidates[0]

    return fg


def get_visual_window_rect(hwnd):
    """获取剔除 DWM 隐形阴影后的真实可视窗口边界 (支持 Win10/11)"""
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    rect = wintypes.RECT()
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect))
    if hr != 0 or (rect.right - rect.left < 50):
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect


class DesktopSnakeOverlay(QWidget):
    """跨越 Windows 桌面与终端边界、精准奔向左上角标签图标的像素小蛇动画"""
    def __init__(self, target_hwnd=None):
        super().__init__()
        self.target_hwnd = target_hwnd
        self.init_window()
        self.detect_terminal_rect()
        self.init_animation()

    def init_window(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 覆盖全屏幕桌面
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.screen_w = screen.width()
        self.screen_h = screen.height()

    def detect_terminal_rect(self):
        """探测当前 PowerShell / Windows Terminal 窗口与顶栏第一标签图标的真实坐标"""
        user32 = ctypes.windll.user32
        hwnd = self.target_hwnd or find_terminal_window()
        self.target_hwnd = hwnd

        is_maximized = bool(hwnd and user32.IsZoomed(hwnd))

        if hwnd:
            rect = get_visual_window_rect(hwnd)
            if is_maximized:
                # 窗口全屏最大化状态：标签栏顶贴屏幕最上方
                self.term_x = 0
                self.term_y = 0
                self.term_w = self.screen_w
                self.term_h = self.screen_h
                # 全屏时第一标签图标精确位置
                self.target_x = 22
                self.target_y = 16
            else:
                self.term_x = max(0, rect.left)
                self.term_y = max(0, rect.top)
                self.term_w = min(self.screen_w - self.term_x, rect.right - rect.left)
                self.term_h = min(self.screen_h - self.term_y, rect.bottom - rect.top)
                # 正常窗口时第一标签图标精确位置 (微调贴合 WT 与 conhost 标签页)
                self.target_x = self.term_x + 22
                self.target_y = self.term_y + 16
        else:
            self.term_w = min(1100, int(self.screen_w * 0.75))
            self.term_h = min(700, int(self.screen_h * 0.75))
            self.term_x = (self.screen_w - self.term_w) // 2
            self.term_y = (self.screen_h - self.term_h) // 2
            self.target_x = self.term_x + 22
            self.target_y = self.term_y + 16

        # 蛇的起点：严格设定在终端窗口外侧桌面上 (窗口左下方外侧)
        if self.term_x > 140:
            self.start_x = self.term_x - 110
            self.start_y = min(self.screen_h - 100, self.term_y + 200)
        else:
            self.start_x = max(20, self.target_x - 10)
            self.start_y = min(self.screen_h - 40, self.term_y + 360)

    def init_animation(self):
        self.frame = 0
        self.total_frames = 70  # 约 1.1 秒，轻快流畅
        self.snake_length = 18
        self.body_points = []

        # 左上角融合脉冲波参数
        self.pulse_active = False
        self.pulse_radius = 0
        self.pulse_max = 70

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(16)

    def update_animation(self):
        self.frame += 1
        progress = self.frame / self.total_frames

        # 贝塞尔平滑轨迹：桌面外部起点 -> 贴着窗口左缘向上游动 -> 钻入左上角图标区域
        t = min(1.0, progress * 1.25)
        u = 1.0 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t

        p0 = (self.start_x, self.start_y)
        p1 = (self.term_x - 30, self.term_y + 100)
        p2 = (self.term_x - 5, self.term_y + 35)
        p3 = (self.target_x, self.target_y)

        hx = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
        hy = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]

        # 正弦蛇行摆动
        wiggle = math.sin(self.frame * 0.5) * 6 * max(0.1, 1.0 - t * 0.8)
        angle = math.atan2(p3[1] - hy, p3[0] - hx) if t < 0.95 else 0
        perp_x = -math.sin(angle) * wiggle
        perp_y = math.cos(angle) * wiggle

        current_head = (hx + perp_x, hy + perp_y)
        self.body_points.insert(0, current_head)
        if len(self.body_points) > self.snake_length:
            self.body_points.pop()

        # 靠近左上角时，触发变身光芒并即刻注入 Windows 终端图标与标题
        if progress >= 0.7:
            if not self.pulse_active:
                self.pulse_active = True
                apply_terminal_identity("pykuai")

            self.pulse_radius += (self.pulse_max - self.pulse_radius) * 0.22

        if self.frame >= self.total_frames:
            self.timer.stop()
            self.close()

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)  # 保持硬核复古点阵像素

        # 1. 终端窗口左上角高亮虚线框 (标示小蛇奔赴的目标位置)
        pen_target = QPen(QColor(16, 185, 129, 90), 2, Qt.DashLine)
        painter.setPen(pen_target)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.term_x, self.term_y, min(240, self.term_w), 34, 6, 6)

        # 2. 钻入左上角激起的代码脉冲波
        if self.pulse_active:
            alpha = int(max(0, 240 * (1.0 - (self.pulse_radius / self.pulse_max))))
            if alpha > 0:
                pen_pulse = QPen(QColor(0, 255, 0, alpha), 3)
                painter.setPen(pen_pulse)
                painter.drawEllipse(QPointF(self.target_x, self.target_y), self.pulse_radius, self.pulse_radius)

                # 伴随光芒文字
                painter.setPen(QColor(255, 152, 0, alpha))
                painter.setFont(QFont("Consolas", 10, QFont.Bold))
                painter.drawText(int(self.target_x + 35), int(self.target_y + 5), "⚡ PYKUAI ⚡")

        # 3. 绘制像素蛇身
        if not self.body_points:
            return

        pixel_size = 14
        num_pts = len(self.body_points)
        for i in range(num_pts - 1, -1, -1):
            pt = self.body_points[i]
            ratio = 1.0 - (i / num_pts)
            cur_size = int(pixel_size * (0.6 + 0.4 * ratio))

            color = QColor(4, 120, 87) if i % 3 == 0 else QColor(16, 185, 129)
            px = int(pt[0] - cur_size // 2)
            py = int(pt[1] - cur_size // 2)
            painter.fillRect(px, py, cur_size, cur_size, color)

            # 像素边缘发光
            painter.setPen(QColor(57, 255, 20, 180))
            painter.drawRect(px, py, cur_size, cur_size)

        # 4. 绘制蛇头与粉舌
        head = self.body_points[0]
        hx, hy = head[0], head[1]
        head_size = 18

        h_px = int(hx - head_size // 2)
        h_py = int(hy - head_size // 2)
        painter.fillRect(h_px, h_py, head_size, head_size, QColor(0, 255, 0))
        painter.setPen(QColor(16, 185, 129))
        painter.drawRect(h_px, h_py, head_size, head_size)

        # 黑色像素眼
        painter.fillRect(int(hx - 4), int(hy - 5), 4, 4, QColor(0, 0, 0))
        painter.fillRect(int(hx + 2), int(hy - 5), 4, 4, QColor(0, 0, 0))

        # 俏皮粉舌 (向着目标吐信)
        if (self.frame // 3) % 2 == 0:
            tongue_color = QColor(255, 101, 132)  # #FF6584
            painter.fillRect(int(hx - 2), int(hy - head_size // 2 - 6), 4, 6, tongue_color)
            painter.fillRect(int(hx - 5), int(hy - head_size // 2 - 9), 3, 3, tongue_color)
            painter.fillRect(int(hx + 2), int(hy - head_size // 2 - 9), 3, 3, tongue_color)

    def keyPressEvent(self, event: QKeyEvent):
        self.timer.stop()
        self.close()

    def mousePressEvent(self, event: QMouseEvent):
        self.timer.stop()
        self.close()

    def closeEvent(self, event):
        self.timer.stop()
        apply_terminal_identity("pykuai")
        app = QApplication.instance()
        if app:
            app.quit()
        super().closeEvent(event)


def play_cinematic_intro() -> None:
    """启动像素小蛇自桌面游向 PowerShell 左上角标签图标的开机动画"""
    # 在初始化 Qt 前立即锁定终端窗口句柄
    target_hwnd = find_terminal_window()

    app = QApplication.instance()
    owns_app = False
    if not app:
        app = QApplication(sys.argv)
        owns_app = True

    try:
        overlay = DesktopSnakeOverlay(target_hwnd=target_hwnd)
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()

        if owns_app:
            app.exec()
    except Exception:
        pass
    finally:
        apply_terminal_identity("pykuai")
