# -*- coding: utf-8 -*-
"""
PyKuai Desktop Snake Slither-in Overlay
Animated pixel snake slithering from outside the terminal window onto the top-left
tab icon, pulsing with neon green energy and applying the PyKuai terminal identity.
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
    """Locate the active foreground terminal window handle (Windows Terminal or Console)."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # 1. Prefer the current foreground active window
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
        # Check top-level ancestor window
        GA_ROOT = 2
        root = user32.GetAncestor(fg, GA_ROOT)
        if root and user32.IsWindowVisible(root):
            user32.GetClassNameW(root, buf, 256)
            if buf.value in ["CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass"]:
                return root

    # 2. Fallback to current console window handle
    c_hwnd = kernel32.GetConsoleWindow()
    if c_hwnd and user32.IsWindowVisible(c_hwnd):
        return c_hwnd

    # 3. Enumerate visible Windows Terminal or Console windows
    candidates = []

    def enum_cb(h, _):
        if user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, buf, 256)
            if buf.value in ["CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass"]:
                if not user32.IsIconic(h):
                    candidates.append(h)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    if candidates:
        return candidates[0]

    return fg


def get_visual_window_rect(hwnd):
    """Get visual physical bounds excluding invisible DWM shadow borders (Win10/11)."""
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    rect = wintypes.RECT()
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect))
    if hr != 0 or (rect.right - rect.left < 50):
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect


class DesktopSnakeOverlay(QWidget):
    """Transparent desktop overlay animating the pixel snake toward the top-left tab icon."""
    def __init__(self, target_hwnd=None):
        super().__init__()
        self.target_hwnd = target_hwnd
        self.init_window()
        self.detect_terminal_rect()
        self.init_animation()

    def init_window(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Cover full virtual desktop across multi-monitor setups
        screen = QApplication.primaryScreen()
        v_geo = screen.virtualGeometry() if screen else QApplication.primaryScreen().geometry()
        self.setGeometry(v_geo)
        self.screen_w = v_geo.width()
        self.screen_h = v_geo.height()

    def detect_terminal_rect(self):
        """
        Detect PowerShell / Windows Terminal window rect and first-tab icon target,
        calibrated for Windows High-DPI scaling (100%, 125%, 150%, 200%).
        """
        user32 = ctypes.windll.user32
        hwnd = self.target_hwnd or find_terminal_window()
        self.target_hwnd = hwnd

        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0

        is_maximized = bool(hwnd and user32.IsZoomed(hwnd))

        if hwnd:
            rect = get_visual_window_rect(hwnd)
            phys_left = rect.left
            phys_top = rect.top
            phys_w = rect.right - rect.left
            phys_h = rect.bottom - rect.top

            if is_maximized:
                self.term_x = 0
                self.term_y = 0
                self.term_w = self.screen_w
                self.term_h = self.screen_h
                self.target_x = 20.0
                self.target_y = 16.0
            else:
                # Convert Win32 physical pixels into Qt logical pixels
                self.term_x = phys_left / dpr
                self.term_y = phys_top / dpr
                self.term_w = phys_w / dpr
                self.term_h = phys_h / dpr

                buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, buf, 256)
                if buf.value == "ConsoleWindowClass":
                    self.target_x = self.term_x + 16.0
                    self.target_y = self.term_y + 14.0
                else:
                    self.target_x = self.term_x + 20.0
                    self.target_y = self.term_y + 16.0
        else:
            self.term_w = min(1100, int(self.screen_w * 0.75))
            self.term_h = min(700, int(self.screen_h * 0.75))
            self.term_x = (self.screen_w - self.term_w) // 2
            self.term_y = (self.screen_h - self.term_h) // 2
            self.target_x = self.term_x + 20.0
            self.target_y = self.term_y + 16.0

        # Snake spawn point outside the lower-left edge of the terminal window
        if self.term_x > 120:
            self.start_x = self.term_x - 100
            self.start_y = min(self.screen_h - 100, self.term_y + 180)
        else:
            self.start_x = max(20, self.target_x - 10)
            self.start_y = min(self.screen_h - 40, self.term_y + 320)

    def init_animation(self):
        self.frame = 0
        self.total_frames = 65  # ~1.0 second fast animation
        self.snake_length = 18
        self.body_points = []

        self.pulse_active = False
        self.pulse_radius = 0
        self.pulse_max = 60

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(16)

    def update_animation(self):
        self.frame += 1
        progress = self.frame / self.total_frames

        # Smooth cubic Bezier path into the top-left tab icon
        t = min(1.0, progress * 1.25)
        u = 1.0 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t

        p0 = (self.start_x, self.start_y)
        p1 = (self.term_x - 25, self.term_y + 90)
        p2 = (self.term_x - 5, self.term_y + 30)
        p3 = (self.target_x, self.target_y)

        hx = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
        hy = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]

        # Sinusoidal slither wave
        wiggle = math.sin(self.frame * 0.5) * 5 * max(0.1, 1.0 - t * 0.8)
        angle = math.atan2(p3[1] - hy, p3[0] - hx) if t < 0.95 else 0
        perp_x = -math.sin(angle) * wiggle
        perp_y = math.cos(angle) * wiggle

        current_head = (hx + perp_x, hy + perp_y)
        self.body_points.insert(0, current_head)
        if len(self.body_points) > self.snake_length:
            self.body_points.pop()

        # Trigger glow pulse and apply terminal icon/title on arrival
        if progress >= 0.7:
            if not self.pulse_active:
                self.pulse_active = True
                apply_terminal_identity("pykuai")

            self.pulse_radius += (self.pulse_max - self.pulse_radius) * 0.25

        if self.frame >= self.total_frames:
            self.timer.stop()
            self.close()

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # 1. Impact pulse ring at top-left icon
        if self.pulse_active:
            alpha = int(max(0, 240 * (1.0 - (self.pulse_radius / self.pulse_max))))
            if alpha > 0:
                pen_pulse = QPen(QColor(0, 255, 0, alpha), 2)
                painter.setPen(pen_pulse)
                painter.drawEllipse(QPointF(self.target_x, self.target_y), self.pulse_radius, self.pulse_radius)

                painter.setPen(QColor(255, 152, 0, alpha))
                painter.setFont(QFont("Consolas", 10, QFont.Bold))
                painter.drawText(int(self.target_x + 30), int(self.target_y + 5), "⚡ PYKUAI ⚡")

        # 2. Pixel snake body
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

            painter.setPen(QColor(57, 255, 20, 180))
            painter.drawRect(px, py, cur_size, cur_size)

        # 3. Snake head & tongue
        head = self.body_points[0]
        hx, hy = head[0], head[1]
        head_size = 18

        h_px = int(hx - head_size // 2)
        h_py = int(hy - head_size // 2)
        painter.fillRect(h_px, h_py, head_size, head_size, QColor(0, 255, 0))
        painter.setPen(QColor(16, 185, 129))
        painter.drawRect(h_px, h_py, head_size, head_size)

        # Black pixel eyes
        painter.fillRect(int(hx - 4), int(hy - 5), 4, 4, QColor(0, 0, 0))
        painter.fillRect(int(hx + 2), int(hy - 5), 4, 4, QColor(0, 0, 0))

        # Pixel tongue
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
    """Launch the desktop pixel snake intro animation targeting the terminal tab icon."""
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
