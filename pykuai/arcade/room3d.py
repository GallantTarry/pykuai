# -*- coding: utf-8 -*-
"""
PyKuai XP Playground — 3D Cutscene & Virtual Windows XP CRT (`pykuai.arcade.room3d`).

Pure pixel-canvas experience inside `xp` (minimalist, zero clutter):
  1. True 3D Perspective Cutscene (plays automatically every time `xp` runs):
     • Beat 1 (0.00s–1.35s): The bedroom door swings shut (`door_close` SFX). Inside a
       3D moonlit bedroom, a boy wearing a grey hoodie climbs stealthily out of his bed.
     • Beat 2 (1.35s–3.35s): The 3D camera tracks through the doorway into Father's room
       (`footsteps` SFX). Father is sleeping soundly in his bed (breathing chest + rising
       3D `Zzz` bubbles) while the grey-hoodie boy sneaks past toward the computer desk.
     • Beat 3 (3.35s–4.85s): The boy reaches Father's vintage beige CRT computer and hits
       the power switch (`pc_boot` SFX). The phosphor screen snaps on and the 3D camera
       zooms smoothly into the monitor glass.
  2. Windows XP Boot & "WELCOME" Splash (`xp_boot` mode):
     • Classic black Windows XP waving 4-color flag + chasing blue loader bars.
     • Transitions into the royal-blue Windows XP `WELCOME` splash screen accompanied by
       the synthesized E-flat major Windows XP Startup Chime (`xp_startup` SFX).
  3. Virtual Windows XP "Bliss" Desktop (`xp_desktop` & `xp_playing` modes):
     • Full-window simulated CRT Windows XP OS featuring sunlit green `Bliss` hills,
       cerulean sky, drifting cumulus clouds, glossy Luna blue taskbar, green `START`
       button with Start Menu popup, system tray live clock, and built-in `HEX 3D`.
"""
from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import ClassVar, Optional

from rich.text import Text

from pykuai.arcade import get_high_score, record_high_score
from pykuai.arcade.hex3d import (
    DEFAULT_PIX_H,
    DEFAULT_PIX_W,
    RGB,
    VOID_INT,
    VOID_RGB,
    _Hex3DEngine,
    _mix_int,
    _mix_rgb,
    _pack_quadrant_buffer,
    _pack_rgb,
    _scale_rgb,
)
from pykuai.core.audio import play_sfx, warmup_arcade_sfx

_HEX_SAVE_PATH = Path.home() / ".pykuai" / "hex3d_save.json"


def _save_hex_state(raw: bytes, summary: str) -> None:
    try:
        _HEX_SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "saved_at": time.strftime("%Y-%m-%d %H:%M"),
            "summary": summary,
            "data": base64.b64encode(raw).decode("ascii"),
        }
        tmp_fd, tmp_name = tempfile.mkstemp(dir=str(_HEX_SAVE_PATH.parent), prefix=".hex_", suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, indent=2))
                fh.flush()
            os.replace(tmp_name, _HEX_SAVE_PATH)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    except Exception:
        pass


def _load_hex_meta() -> tuple[Optional[bytes], str]:
    try:
        if not _HEX_SAVE_PATH.is_file():
            return None, ""
        payload = json.loads(_HEX_SAVE_PATH.read_text(encoding="utf-8"))
        b64 = payload.get("data", "")
        raw = base64.b64decode(b64) if b64 else None
        summary = str(payload.get("summary", "") or payload.get("saved_at", ""))
        return raw, summary
    except Exception:
        return None, ""


ROOM3D_HELP_TITLE = "XP Playground (xp) · 3D Cutscene & Windows XP CRT"
ROOM3D_HELP_TEXT = """\
[bold #00d2ff]3D Opening Cutscene[/]
  Every time [bold #00FF00]xp[/] opens, a 3D perspective cutscene plays automatically:
  1. The bedroom door swings shut; a boy wearing a grey hoodie climbs out of bed.
  2. He sneaks into his father's bedroom while his father is sleeping in bed (`Zzz`).
  3. He powers on Father's vintage CRT PC, and the camera zooms into Windows XP.
  • Press [bold]Space / Enter / Click[/] during the cutscene or boot splash to skip ahead.

[bold #00d2ff]Virtual Windows XP Desktop (`Bliss`)[/]
  • [bold #00FF00]Double-Click `HEX 3D` Icon[/] (or press [bold]Enter[/]) to launch the 3D game window.
  • [bold #FACC15]Click the Green `START` Button[/] (bottom-left) to open the XP Start Menu.
  • Every window features a top-right crimson [bold #FF5252]✕[/] close button.

[bold #00d2ff]Hex 3D Controls & Save State[/]
  • [bold #00FF00]D / Right[/]   Turn Clockwise (Broken Left D-Pad rule!).
  • [bold #38BDF8]W / Up[/]      Quick-step forward · [bold]Space / Enter[/] Start / Pause.
  • [bold #00FF00]F5 / F8[/]     Save / Load instant state for `HEX 3D`.
  • [bold #e5e7eb]R / P[/]       Restart or Pause in-game.
  • [bold #FF5252]✕ / Esc / Q[/] Close active game back to XP Desktop (auto-saves),
              or shut down Windows XP from the desktop to return to `pykuai ❯`."""

# Compact 3x5 pixel bitmap font for crisp typography inside the CRT framebuffer
_FONT_3X5: dict[str, tuple[int, int, int, int, int]] = {
    "A": (0b010, 0b101, 0b111, 0b101, 0b101),
    "B": (0b110, 0b101, 0b110, 0b101, 0b110),
    "C": (0b011, 0b100, 0b100, 0b100, 0b011),
    "D": (0b110, 0b101, 0b101, 0b101, 0b110),
    "E": (0b111, 0b100, 0b110, 0b100, 0b111),
    "F": (0b111, 0b100, 0b110, 0b100, 0b100),
    "G": (0b011, 0b100, 0b101, 0b101, 0b011),
    "H": (0b101, 0b101, 0b111, 0b101, 0b101),
    "I": (0b111, 0b010, 0b010, 0b010, 0b111),
    "J": (0b001, 0b001, 0b001, 0b101, 0b010),
    "K": (0b101, 0b101, 0b110, 0b101, 0b101),
    "L": (0b100, 0b100, 0b100, 0b100, 0b111),
    "M": (0b10001, 0b11011, 0b10101, 0b10001, 0b10001),
    "N": (0b101, 0b111, 0b111, 0b111, 0b101),
    "O": (0b010, 0b101, 0b101, 0b101, 0b010),
    "P": (0b110, 0b101, 0b110, 0b100, 0b100),
    "Q": (0b010, 0b101, 0b101, 0b011, 0b001),
    "R": (0b110, 0b101, 0b110, 0b101, 0b101),
    "S": (0b011, 0b100, 0b010, 0b001, 0b110),
    "T": (0b111, 0b010, 0b010, 0b010, 0b010),
    "U": (0b101, 0b101, 0b101, 0b101, 0b111),
    "V": (0b101, 0b101, 0b101, 0b010, 0b010),
    "W": (0b10001, 0b10001, 0b10101, 0b11011, 0b10001),
    "X": (0b101, 0b101, 0b010, 0b101, 0b101),
    "Y": (0b101, 0b101, 0b010, 0b010, 0b010),
    "Z": (0b111, 0b001, 0b010, 0b100, 0b111),
    "0": (0b111, 0b101, 0b101, 0b101, 0b111),
    "1": (0b010, 0b110, 0b010, 0b010, 0b111),
    "2": (0b111, 0b001, 0b111, 0b100, 0b111),
    "3": (0b111, 0b001, 0b011, 0b001, 0b111),
    "4": (0b101, 0b101, 0b111, 0b001, 0b001),
    "5": (0b111, 0b100, 0b111, 0b001, 0b111),
    "6": (0b111, 0b100, 0b111, 0b101, 0b111),
    "7": (0b111, 0b001, 0b010, 0b010, 0b010),
    "8": (0b111, 0b101, 0b111, 0b101, 0b111),
    "9": (0b111, 0b101, 0b111, 0b001, 0b111),
    ":": (0b000, 0b010, 0b000, 0b010, 0b000),
    ".": (0b000, 0b000, 0b000, 0b000, 0b010),
    "-": (0b000, 0b000, 0b111, 0b000, 0b000),
    "+": (0b000, 0b010, 0b111, 0b010, 0b000),
    "/": (0b001, 0b001, 0b010, 0b100, 0b100),
    "!": (0b010, 0b010, 0b010, 0b000, 0b010),
    " ": (0b000, 0b000, 0b000, 0b000, 0b000),
}


def _pixel_text_width(text: str, scale_x: int = 1) -> int:
    """Compute exact sub-pixel width of `_draw_pixel_text` accounting for 5px wide M/W glyphs."""
    total = 0
    for idx, ch in enumerate(text.upper()):
        gw = 5 if ch in ("M", "W") else 3
        total += gw * scale_x
        if idx + 1 < len(text):
            total += scale_x
    return total


def _draw_pixel_text(
    pbuf: list[int],
    width: int,
    height: int,
    x0: int,
    y0: int,
    text: str,
    fg_rgb: RGB,
    shadow_rgb: Optional[RGB] = None,
    scale_x: int = 1,
    scale_y: int = 1,
    zbuf: Optional[list[float]] = None,
    depth: float = 0.0,
) -> None:
    """Stamp crisp 3x5 (and 5x5 M/W) bitmap characters into the sub-pixel framebuffer."""
    fg_i = _pack_rgb(fg_rgb)
    sh_i = _pack_rgb(shadow_rgb) if shadow_rgb else None
    cur_x = x0
    for ch in text.upper():
        glyph = _FONT_3X5.get(ch, _FONT_3X5[" "])
        gw = 5 if ch in ("M", "W") else 3
        for ry in range(5):
            row_bits = glyph[ry]
            for rx in range(gw):
                if not ((row_bits >> (gw - 1 - rx)) & 1):
                    continue
                for sy in range(scale_y):
                    py = y0 + ry * scale_y + sy
                    if not (0 <= py < height):
                        continue
                    for sx in range(scale_x):
                        px = cur_x + rx * scale_x + sx
                        if not (0 <= px < width):
                            continue
                        idx = py * width + px
                        if zbuf is not None:
                            if depth < zbuf[idx]:
                                zbuf[idx] = depth
                                pbuf[idx] = fg_i
                        else:
                            pbuf[idx] = fg_i
                        if sh_i is not None and zbuf is None and px + 1 < width and py + 1 < height:
                            sh_idx = (py + 1) * width + (px + 1)
                            if pbuf[sh_idx] != fg_i:
                                pbuf[sh_idx] = sh_i
        cur_x += (gw + 1) * scale_x


class _True3DCutsceneEngine:
    """
    True 3D perspective cutscene renderer using Z-buffered 3D polygons & 3D spheres:
      • 0.00s–1.35s: Bedroom door swings shut (`door_close`), grey-hoodie boy climbs out of his 3D bed.
      • 1.35s–3.35s: 3D camera tracks across the partition doorway into Father's room
                     (`footsteps` SFX; Father breathing in bed with rising 3D `Zzz`).
      • 3.35s–4.85s: Boy turns on Father's 3D beige CRT computer (`pc_boot` SFX), the CRT
                     tube flashes on, and the camera zooms directly into the monitor glass.
    """

    TOTAL_DURATION = 4.85

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.t = 0.0
        self.done = False
        self._played_door = False
        self._played_steps_1 = False
        self._played_steps_2 = False
        self._played_boot = False

    def advance(self, dt: float) -> bool:
        if not self._played_door:
            self._played_door = True
            play_sfx("door_close")

        self.t += dt
        if self.t >= 1.35 and not self._played_steps_1:
            self._played_steps_1 = True
            play_sfx("footsteps")
        if self.t >= 2.30 and not self._played_steps_2:
            self._played_steps_2 = True
            play_sfx("footsteps")
        if self.t >= 3.35 and not self._played_boot:
            self._played_boot = True
            play_sfx("pc_boot")

        if self.t >= self.TOTAL_DURATION:
            self.done = True
            return True
        return False

    @property
    def status_text(self) -> str:
        if self.t < 0.70:
            return "Door clicks shut behind him... (Click or Space to skip)"
        if self.t < 1.35:
            return "Boy in a grey hoodie climbs quietly out of bed..."
        if self.t < 3.35:
            return "Tip-toeing into Father's bedroom while Father sleeps (Zzz)..."
        return "Powering on Father's vintage CRT computer..."

    def render_frame(self, width: int = DEFAULT_PIX_W, height: int = DEFAULT_PIX_H) -> Text:
        n_pix = width * height
        zbuf = [1e9] * n_pix
        pbuf = [VOID_INT] * n_pix

        # Smooth 3D camera choreography across Boy's Room (-4.0) -> Father Sleeping (+2.2) -> CRT Monitor (+6.05)
        if self.t < 1.30:
            u1 = min(1.0, self.t / 1.30)
            s1 = u1 * u1 * (3.0 - 2.0 * u1)
            cam_tx = -4.35 + s1 * 1.15
            cam_ty = 1.08
            cam_tz = 1.25
            cam_dist = 6.2 - s1 * 0.2
            pitch = 0.34
            yaw = 1.54
        elif self.t < 3.30:
            u2 = (self.t - 1.30) / 2.00
            s2 = u2 * u2 * (3.0 - 2.0 * u2)
            # Sweeps cleanly through the doorway past Father sleeping in bed (x = 2.3) to desk (x = 5.4)
            cam_tx = -3.20 + s2 * 8.65
            cam_ty = 1.12 + math.sin(s2 * math.pi) * 0.14
            cam_tz = 1.25 - math.sin(s2 * math.pi) * 0.12
            cam_dist = 6.0 - s2 * 0.55
            pitch = 0.34 - s2 * 0.08
            yaw = 1.54 - math.sin(s2 * math.pi) * 0.10
        else:
            # Zoom straight into the 3D CRT monitor screen glass at (6.05, 1.65, 1.18)
            u3 = min(1.0, (self.t - 3.30) / 1.55)
            ez = u3 * u3 * (3.0 - 2.0 * u3)
            cam_tx = 5.45 + ez * 0.60
            cam_ty = 1.12 + ez * 0.53
            cam_tz = 1.25 - ez * 0.07
            cam_dist = 5.45 * (1.0 - ez * 0.855)  # ends right at monitor glass (0.79 units)
            pitch = 0.26 * (1.0 - ez * 0.92)
            yaw = 1.54 + ez * (1.570796 - 1.54)

        fwd_x = math.cos(yaw)
        fwd_z = math.sin(yaw)
        # +X is right when yaw = +pi/2 (looking along +Z)
        right_x = fwd_z
        right_z = -fwd_x
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)

        cam_x = cam_tx - fwd_x * cam_dist * cos_p
        cam_y = cam_ty + cam_dist * sin_p
        cam_z = cam_tz - fwd_z * cam_dist * cos_p

        fov_y = height * 1.35
        fov_x = fov_y * 2.0
        cx = width * 0.5
        cy = height * 0.50

        def project(wx: float, wy: float, wz: float) -> Optional[tuple[float, float, float]]:
            vx = wx - cam_x
            vy = wy - cam_y
            vz = wz - cam_z
            cx_local = vx * right_x + vz * right_z
            horz_fwd = vx * fwd_x + vz * fwd_z
            cy_local = vy * cos_p + horz_fwd * sin_p
            cz_local = horz_fwd * cos_p - vy * sin_p
            if cz_local < 0.22:
                return None
            inv_z = 1.0 / cz_local
            return cx + cx_local * (fov_x * inv_z), cy - cy_local * (fov_y * inv_z), cz_local

        def raster_quad_3d(
            v0: tuple[float, float, float],
            v1: tuple[float, float, float],
            v2: tuple[float, float, float],
            v3: tuple[float, float, float],
            rgb: RGB,
            z_bias: float = 0.0,
            use_fog: bool = True,
        ) -> None:
            p0 = project(*v0)
            p1 = project(*v1)
            p2 = project(*v2)
            p3 = project(*v3)
            if not (p0 and p1 and p2 and p3):
                return
            x0p, y0p, z0p = p0
            x1p, y1p, z1p = p1
            x2p, y2p, z2p = p2
            x3p, y3p, z3p = p3
            min_x = max(0, int(min(x0p, x1p, x2p, x3p)))
            max_x = min(width - 1, int(max(x0p, x1p, x2p, x3p) + 0.99))
            min_y = max(0, int(min(y0p, y1p, y2p, y3p)))
            max_y = min(height - 1, int(max(y0p, y1p, y2p, y3p) + 0.99))
            if min_x > max_x or min_y > max_y:
                return

            avg_z = (z0p + z1p + z2p + z3p) * 0.25 + z_bias
            fog = max(0.0, min(0.42, (avg_z - 5.5) * 0.048)) if use_fog else 0.0
            c_packed = _pack_rgb(_mix_rgb(rgb, VOID_RGB, fog))

            area = (x1p - x0p) * (y2p - y0p) - (y1p - y0p) * (x2p - x0p)
            if abs(area) < 0.05:
                return
            s = 1.0 if area > 0 else -1.0

            # Unrolled 4-edge coefficients A*x + B*y + C >= -0.2 for fast inner loop
            a0 = -(y1p - y0p) * s
            b0 = (x1p - x0p) * s
            c0 = ((y1p - y0p) * x0p - (x1p - x0p) * y0p) * s + 0.2

            a1 = -(y2p - y1p) * s
            b1 = (x2p - x1p) * s
            c1 = ((y2p - y1p) * x1p - (x2p - x1p) * y1p) * s + 0.2

            a2 = -(y3p - y2p) * s
            b2 = (x3p - x2p) * s
            c2 = ((y3p - y2p) * x2p - (x3p - x2p) * y2p) * s + 0.2

            a3 = -(y0p - y3p) * s
            b3 = (x0p - x3p) * s
            c3 = ((y0p - y3p) * x3p - (x0p - x3p) * y3p) * s + 0.2

            sx0 = min_x + 0.5
            for py in range(min_y, max_y + 1):
                pyc = py + 0.5
                row = py * width
                e0 = a0 * sx0 + b0 * pyc + c0
                e1 = a1 * sx0 + b1 * pyc + c1
                e2 = a2 * sx0 + b2 * pyc + c2
                e3 = a3 * sx0 + b3 * pyc + c3
                for px in range(min_x, max_x + 1):
                    if e0 >= 0.0 and e1 >= 0.0 and e2 >= 0.0 and e3 >= 0.0:
                        idx = row + px
                        if avg_z < zbuf[idx]:
                            zbuf[idx] = avg_z
                            pbuf[idx] = c_packed
                    e0 += a0
                    e1 += a1
                    e2 += a2
                    e3 += a3

        def draw_box_3d(
            x0: float,
            y0: float,
            z0: float,
            x1: float,
            y1: float,
            z1: float,
            top_rgb: RGB,
            front_rgb: RGB,
            side_rgb: RGB,
            z_bias: float = 0.0,
        ) -> None:
            raster_quad_3d((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), front_rgb, z_bias)
            raster_quad_3d((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1), top_rgb, z_bias)
            raster_quad_3d((x0, y0, z1), (x0, y0, z0), (x0, y1, z0), (x0, y1, z1), side_rgb, z_bias)
            raster_quad_3d((x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0), side_rgb, z_bias)

        def stamp_sphere_3d(
            wx: float,
            wy: float,
            wz: float,
            r_x: float,
            r_y: float,
            core_rgb: RGB,
            rim_rgb: RGB,
            z_bias: float = -0.10,
        ) -> None:
            proj = project(wx, wy, wz)
            if proj is None:
                return
            sx, sy, cz = proj
            rx_px = max(1.0, r_x * (fov_x / cz))
            ry_px = max(0.8, r_y * (fov_y / cz))
            x0 = max(0, int(sx - rx_px))
            x1 = min(width - 1, int(sx + rx_px))
            y0 = max(0, int(sy - ry_px))
            y1 = min(height - 1, int(sy + ry_px))
            depth = cz + z_bias
            c_core = _pack_rgb(core_rgb)
            c_rim = _pack_rgb(rim_rgb)
            inv_rx = 1.0 / rx_px
            inv_ry = 1.0 / ry_px
            for py in range(y0, y1 + 1):
                ny = (py + 0.5 - sy) * inv_ry
                ny2 = ny * ny
                row = py * width
                for px in range(x0, x1 + 1):
                    nx = (px + 0.5 - sx) * inv_rx
                    if nx * nx + ny2 <= 1.0:
                        idx = row + px
                        if depth < zbuf[idx]:
                            zbuf[idx] = depth
                            # Top-left directional rim shading (no center dot artifact)
                            pbuf[idx] = c_rim if (nx + ny < -0.52) else c_core

        pc_on = self.t >= 3.35
        door_open = max(0.0, 1.0 - (self.t / 0.56)) * 0.95

        # ── 1. 3D Hardwood & Tile Floors + Moonlit & CRT Dynamic Lighting + Night Walls ──
        for tx in range(-10, 11):
            for tz in range(-2, 4):
                is_alt = (tx + tz) % 2 == 0
                if tx < 0:
                    flr_c = (28, 39, 62) if is_alt else (22, 31, 50)
                    # Cool silvery moonlight cast from Boy's bedroom window onto floor
                    if -5 <= tx <= -2 and 0 <= tz <= 2:
                        moon_k = max(0.0, 1.0 - abs((tx + 3.5) - (2.0 - tz) * 0.45) * 0.48)
                        flr_c = _mix_rgb(flr_c, (88, 124, 186), moon_k * 0.44)
                    # Warm hallway light wedge near door while door closes
                    if door_open > 0.04 and tx in (-6, -5) and 1 <= tz <= 2:
                        flr_c = _mix_rgb(flr_c, (214, 166, 62), (door_open / 0.95) * 0.48)
                else:
                    flr_c = (58, 36, 26) if is_alt else (48, 30, 22)
                    # Soft blue CRT bounce glow on hardwood near Father's computer desk
                    if pc_on and 4 <= tx <= 7 and 0 <= tz <= 1:
                        flr_c = _mix_rgb(flr_c, (48, 132, 198), 0.24)
                raster_quad_3d(
                    (float(tx), 0.0, float(tz)),
                    (float(tx + 1), 0.0, float(tz)),
                    (float(tx + 1), 0.0, float(tz + 1)),
                    (float(tx), 0.0, float(tz + 1)),
                    flr_c,
                    z_bias=0.25,
                )

        # Back wall segmented across [-10..11] with moonlight & CRT bounce shading
        for wx_i in range(-10, 11):
            wall_c = (18, 28, 50) if wx_i < 0 else (26, 32, 50)
            if -5 <= wx_i <= -2:
                wall_c = _mix_rgb(wall_c, (42, 64, 108), 0.28)
            elif pc_on and 5 <= wx_i <= 7:
                wall_c = _mix_rgb(wall_c, (40, 96, 152), 0.30)
            raster_quad_3d(
                (float(wx_i), 0.0, 3.0),
                (float(wx_i + 1), 0.0, 3.0),
                (float(wx_i + 1), 3.6, 3.0),
                (float(wx_i), 3.6, 3.0),
                wall_c,
                z_bias=0.35,
            )
            raster_quad_3d(
                (float(wx_i), 0.0, 2.97),
                (float(wx_i + 1), 0.0, 2.97),
                (float(wx_i + 1), 0.18, 2.97),
                (float(wx_i), 0.18, 2.97),
                (68, 82, 102) if wx_i < 0 else (76, 54, 42),
                z_bias=0.30,
            )

        def cast_floor_shadow(sx0: float, sz0: float, sx1: float, sz1: float, left_room: bool) -> None:
            sh_c = (9, 13, 24) if left_room else (20, 12, 9)
            raster_quad_3d(
                (sx0, 0.008, sz0), (sx1, 0.008, sz0), (sx1, 0.008, sz1), (sx0, 0.008, sz1),
                sh_c, z_bias=0.17,
            )

        # 3D Partition Wall & Walnut-Trimmed Doorway Arch between Boy's Room and Father's Room (x = 0.0)
        draw_box_3d(-0.18, 0.0, 1.45, 0.18, 3.4, 3.0, (71, 85, 105), (51, 65, 85), (30, 41, 59))
        draw_box_3d(-0.18, 2.25, -0.6, 0.18, 3.4, 1.45, (71, 85, 105), (51, 65, 85), (30, 41, 59))
        draw_box_3d(-0.22, 0.0, 1.37, 0.22, 2.28, 1.47, (124, 72, 42), (102, 58, 34), (74, 42, 24))
        draw_box_3d(-0.22, 2.18, -0.58, 0.22, 2.30, 1.47, (124, 72, 42), (102, 58, 34), (74, 42, 24))

        # ── 2. Boy's Bedroom: Closing 3D Door, Moonlit Window, Nightstand & Rug ──
        dx_hinge = -6.15
        dx_edge = dx_hinge + math.cos(door_open) * 1.10
        dz_edge = 2.95 - math.sin(door_open) * 1.10
        draw_box_3d(-6.22, 0.0, 2.88, -6.14, 2.42, 2.99, (112, 64, 36), (94, 52, 28), (72, 40, 22))
        draw_box_3d(-5.06, 0.0, 2.88, -4.98, 2.42, 2.99, (112, 64, 36), (94, 52, 28), (72, 40, 22))
        if door_open > 0.03:
            raster_quad_3d((-6.15, 0.0, 2.98), (-5.05, 0.0, 2.98), (-5.05, 2.35, 2.98), (-6.15, 2.35, 2.98), (250, 204, 21), z_bias=0.22)
            beam_w = 1.05 * (door_open / 0.95)
            raster_quad_3d((-6.15, 0.012, 2.92), (-6.15 + beam_w, 0.012, 2.92), (-5.75 + beam_w * 0.85, 0.012, 1.45), (-6.15, 0.012, 1.45), (180, 142, 46), z_bias=0.14)
        raster_quad_3d((dx_hinge, 0.0, 2.95), (dx_edge, 0.0, dz_edge), (dx_edge, 2.35, dz_edge), (dx_hinge, 2.35, 2.95), (138, 76, 42), z_bias=-0.04)
        knob_x = dx_hinge + math.cos(door_open) * 0.90
        knob_z = 2.93 - math.sin(door_open) * 0.90
        stamp_sphere_3d(knob_x, 1.05, knob_z, 0.07, 0.07, (250, 204, 21), (255, 255, 255))

        # Moonlit Window + Outer Wood Frame + Window Mullions + Glowing Moon + Stars
        raster_quad_3d((-4.60, 1.38, 2.95), (-2.40, 1.38, 2.95), (-2.40, 2.82, 2.95), (-4.60, 2.82, 2.95), (96, 112, 138), z_bias=0.19)
        raster_quad_3d((-4.50, 1.45, 2.94), (-2.50, 1.45, 2.94), (-2.50, 2.75, 2.94), (-4.50, 2.75, 2.94), (10, 24, 58), z_bias=0.15)
        stamp_sphere_3d(-3.10, 2.32, 2.90, 0.22, 0.22, (254, 240, 138), (255, 255, 240))
        stamp_sphere_3d(-4.15, 2.48, 2.91, 0.03, 0.03, (226, 232, 240), (255, 255, 255))
        stamp_sphere_3d(-3.72, 1.88, 2.91, 0.03, 0.03, (226, 232, 240), (255, 255, 255))
        stamp_sphere_3d(-2.72, 1.72, 2.91, 0.03, 0.03, (186, 230, 253), (255, 255, 255))
        raster_quad_3d((-3.53, 1.45, 2.91), (-3.47, 1.45, 2.91), (-3.47, 2.75, 2.91), (-3.53, 2.75, 2.91), (96, 112, 138), z_bias=0.11)
        raster_quad_3d((-4.50, 2.07, 2.91), (-2.50, 2.07, 2.91), (-2.50, 2.13, 2.91), (-4.50, 2.13, 2.91), (96, 112, 138), z_bias=0.11)
        # Soft moonlight beam cast onto floor across Boy's rug & doorway path
        raster_quad_3d((-4.45, 0.011, 2.86), (-2.55, 0.011, 2.86), (-2.10, 0.011, 0.55), (-4.20, 0.011, 0.55), (56, 86, 138), z_bias=0.15)

        # Boy's Bedside Rug, Nightstand + Table Lamp, Cast Floor Shadows, and 3D Bed
        raster_quad_3d((-5.20, 0.006, 0.12), (-2.55, 0.006, 0.12), (-2.55, 0.006, 0.88), (-5.20, 0.006, 0.88), (30, 64, 96), z_bias=0.18)
        raster_quad_3d((-5.08, 0.009, 0.20), (-2.67, 0.009, 0.20), (-2.67, 0.009, 0.80), (-5.08, 0.009, 0.80), (42, 82, 118), z_bias=0.16)
        cast_floor_shadow(-5.25, 0.86, -2.68, 2.74, left_room=True)
        cast_floor_shadow(-5.90, 1.88, -5.22, 2.60, left_room=True)

        draw_box_3d(-5.85, 0.0, 1.92, -5.28, 0.56, 2.55, (132, 76, 46), (104, 58, 34), (78, 44, 26))
        draw_box_3d(-5.64, 0.56, 2.16, -5.48, 0.72, 2.32, (148, 163, 184), (100, 116, 139), (71, 85, 105))
        draw_box_3d(-5.74, 0.72, 2.06, -5.38, 0.96, 2.42, (203, 213, 225), (148, 163, 184), (100, 116, 139))

        draw_box_3d(-5.10, 0.0, 0.90, -2.80, 0.56, 2.70, (241, 245, 249), (120, 66, 38), (92, 52, 30))
        draw_box_3d(-5.10, 0.56, 2.38, -2.80, 1.32, 2.70, (146, 84, 52), (120, 66, 38), (92, 52, 30))
        draw_box_3d(-5.00, 0.57, 0.94, -2.90, 0.72, 1.98, (59, 130, 246), (37, 99, 235), (29, 78, 216))

        # ── 3. Father's Room: Nightstand + Glowing LED Alarm Clock + Wall Frame + Sleeping Father ──
        cast_floor_shadow(0.24, 1.88, 0.88, 2.72, left_room=False)
        cast_floor_shadow(0.88, 1.28, 3.96, 2.90, left_room=False)
        draw_box_3d(0.28, 0.0, 1.94, 0.84, 0.62, 2.66, (112, 60, 38), (90, 48, 30), (68, 36, 22))
        draw_box_3d(0.40, 0.62, 2.10, 0.72, 0.78, 2.34, (30, 41, 59), (15, 23, 42), (15, 23, 42))
        raster_quad_3d((0.44, 0.66, 2.09), (0.68, 0.66, 2.09), (0.68, 0.74, 2.09), (0.44, 0.74, 2.09), (239, 68, 68), z_bias=-0.04, use_fog=False)

        # Wall Frame above Father's Bed
        raster_quad_3d((1.82, 1.88, 2.95), (2.98, 1.88, 2.95), (2.98, 2.60, 2.95), (1.82, 2.60, 2.95), (120, 68, 40), z_bias=0.19)
        raster_quad_3d((1.92, 1.96, 2.93), (2.88, 1.96, 2.93), (2.88, 2.52, 2.93), (1.92, 2.52, 2.93), (52, 82, 118), z_bias=0.15)
        raster_quad_3d((1.92, 1.96, 2.92), (2.88, 1.96, 2.92), (2.50, 2.24, 2.92), (1.92, 2.12, 2.92), (42, 92, 74), z_bias=0.12)

        draw_box_3d(0.95, 0.0, 1.35, 3.85, 0.64, 2.85, (241, 245, 249), (92, 48, 32), (68, 36, 24))
        draw_box_3d(0.95, 0.64, 2.52, 3.85, 1.62, 2.85, (115, 60, 40), (92, 48, 32), (68, 36, 24))
        draw_box_3d(1.18, 0.65, 2.12, 2.20, 0.84, 2.50, (248, 250, 252), (226, 232, 240), (148, 163, 184))

        breath = 0.07 * math.sin(self.t * 2.8)
        draw_box_3d(1.12, 0.65, 1.42, 3.68, 1.04 + breath, 2.18, (153, 27, 27), (127, 29, 29), (88, 20, 20))
        stamp_sphere_3d(1.68, 0.98, 2.28, 0.30, 0.26, (234, 170, 108), (253, 198, 138))
        stamp_sphere_3d(1.68, 1.12, 2.34, 0.31, 0.20, (55, 48, 46), (82, 72, 68))

        for z_i, ch in enumerate(("Z", "Z", "Z")):
            z_cycle = (self.t * 0.72 + z_i * 0.33) % 1.0
            zx = 1.75 + z_cycle * 0.78 + math.sin(self.t * 2.6 + z_i) * 0.08
            zy = 1.42 + z_cycle * 1.18
            proj_z = project(zx, zy, 2.20)
            if proj_z is not None:
                sx_z, sy_z, cz_z = proj_z
                fade = 1.0 - max(0.0, (z_cycle - 0.65) / 0.35)
                z_col = _scale_rgb((186, 230, 253), 0.60 + 0.40 * fade)
                _draw_pixel_text(
                    pbuf,
                    width,
                    height,
                    int(sx_z) - 2,
                    int(sy_z) - 2,
                    ch,
                    fg_rgb=z_col,
                    scale_x=2,
                    scale_y=1,
                    zbuf=zbuf,
                    depth=cz_z - 0.15,
                )

        # ── 4. Father's 3D Computer Desk, Study Chair & Vintage Beige CRT PC ──
        cast_floor_shadow(4.78, 1.02, 7.62, 2.58, left_room=False)
        draw_box_3d(6.02, 0.0, 0.36, 6.48, 0.44, 0.80, (76, 48, 34), (62, 38, 28), (48, 30, 22))
        draw_box_3d(6.04, 0.44, 0.36, 6.46, 0.82, 0.46, (88, 56, 40), (72, 46, 32), (56, 36, 24))

        desk_top_c: RGB = (166, 108, 72) if not pc_on else _mix_rgb((146, 84, 52), (96, 172, 228), 0.28)
        draw_box_3d(4.75, 0.96, 1.05, 7.55, 1.12, 2.55, desk_top_c, (110, 62, 38), (82, 46, 28))
        draw_box_3d(4.85, 0.0, 1.10, 5.15, 0.96, 2.45, (82, 46, 28), (68, 38, 24), (54, 30, 18))
        draw_box_3d(7.15, 0.0, 1.10, 7.45, 0.96, 2.45, (82, 46, 28), (68, 38, 24), (54, 30, 18))

        # Desk Notebooks & Vintage Beige Speaker on Left of Monitor
        draw_box_3d(4.86, 1.12, 1.32, 5.26, 1.24, 1.64, (16, 185, 129), (16, 185, 129), (6, 95, 70))
        draw_box_3d(4.88, 1.24, 1.34, 5.24, 1.35, 1.62, (79, 70, 229), (79, 70, 229), (49, 46, 129))
        draw_box_3d(4.90, 1.35, 1.36, 5.22, 1.44, 1.60, (245, 158, 11), (217, 119, 6), (146, 64, 14))
        draw_box_3d(4.86, 1.12, 1.88, 5.18, 1.72, 2.26, (218, 212, 196), (186, 180, 164), (142, 136, 122))

        # Beige PC Tower + Green/Standby LED
        draw_box_3d(6.88, 1.12, 1.25, 7.42, 2.08, 2.22, (238, 232, 214), (218, 210, 190), (166, 158, 140))
        led_c: RGB = (0, 255, 102) if pc_on else (245, 158, 11)
        stamp_sphere_3d(7.14, 1.72, 1.21, 0.08, 0.08, led_c, (255, 255, 255))

        # Vintage Beige CRT Monitor + Keyboard + Mousepad & Ball Mouse
        crt_front: RGB = (232, 226, 208) if not pc_on else (240, 244, 248)
        draw_box_3d(5.28, 1.16, 1.20, 6.82, 2.14, 2.25, (242, 236, 220), crt_front, (168, 160, 142))
        draw_box_3d(5.48, 1.12, 0.90, 6.44, 1.17, 1.12, (241, 245, 249), (203, 213, 225), (148, 163, 184))
        raster_quad_3d((6.50, 1.125, 0.88), (6.80, 1.125, 0.88), (6.80, 1.125, 1.14), (6.50, 1.125, 1.14), (30, 58, 138), z_bias=-0.02)
        draw_box_3d(6.58, 1.13, 0.95, 6.72, 1.18, 1.09, (241, 245, 249), (203, 213, 225), (148, 163, 184))

        if not pc_on:
            raster_quad_3d(
                (5.42, 1.26, 1.18), (6.68, 1.26, 1.18), (6.68, 2.04, 1.18), (5.42, 2.04, 1.18),
                (10, 16, 28), z_bias=-0.06, use_fog=False,
            )
        else:
            # Cyan CRT screen-light spill across desktop front edge
            raster_quad_3d(
                (5.32, 1.126, 0.92), (6.78, 1.126, 0.92), (6.68, 1.126, 1.20), (5.42, 1.126, 1.20),
                (112, 192, 246), z_bias=-0.03, use_fog=False,
            )
            boot_dt = self.t - 3.35
            if boot_dt < 0.25:
                raster_quad_3d(
                    (5.42, 1.26, 1.18), (6.68, 1.26, 1.18), (6.68, 2.04, 1.18), (5.42, 2.04, 1.18),
                    (12, 18, 32), z_bias=-0.06, use_fog=False,
                )
                raster_quad_3d(
                    (5.44, 1.60, 1.17), (6.66, 1.60, 1.17), (6.66, 1.72, 1.17), (5.44, 1.72, 1.17),
                    (224, 242, 254), z_bias=-0.09, use_fog=False,
                )
            else:
                raster_quad_3d(
                    (5.42, 1.26, 1.18), (6.68, 1.26, 1.18), (6.68, 2.04, 1.18), (5.42, 2.04, 1.18),
                    (6, 10, 20), z_bias=-0.06, use_fog=False,
                )
                raster_quad_3d((5.92, 1.68, 1.17), (6.04, 1.68, 1.17), (6.04, 1.78, 1.17), (5.92, 1.78, 1.17), (242, 80, 34), z_bias=-0.09, use_fog=False)
                raster_quad_3d((6.06, 1.68, 1.17), (6.18, 1.68, 1.17), (6.18, 1.78, 1.17), (6.06, 1.78, 1.17), (127, 186, 0), z_bias=-0.09, use_fog=False)
                raster_quad_3d((5.92, 1.55, 1.17), (6.04, 1.55, 1.17), (6.04, 1.65, 1.17), (5.92, 1.65, 1.17), (0, 164, 239), z_bias=-0.09, use_fog=False)
                raster_quad_3d((6.06, 1.55, 1.17), (6.18, 1.55, 1.17), (6.18, 1.65, 1.17), (6.06, 1.65, 1.17), (255, 185, 0), z_bias=-0.09, use_fog=False)
                raster_quad_3d((5.85, 1.38, 1.17), (6.25, 1.38, 1.17), (6.25, 1.44, 1.17), (5.85, 1.44, 1.17), (56, 189, 248), z_bias=-0.09, use_fog=False)

        # ── 5. The 3D Little Boy Wearing the Grey Hoodie (sneaks in foreground z ~ 0.15) ──
        hoodie_main: RGB = (166, 174, 186) if not pc_on else (178, 198, 224)
        hoodie_hood: RGB = (116, 124, 138) if not pc_on else (130, 152, 182)
        hoodie_rim: RGB = (232, 238, 248) if not pc_on else (186, 230, 253)

        if self.t < 0.65:
            rise = max(0.0, (self.t - 0.30) / 0.35)
            bx, by, bz = -4.15, 0.85 + rise * 0.25, 2.05
            stamp_sphere_3d(bx, by, bz, 0.34, 0.28, hoodie_hood, hoodie_rim)
            stamp_sphere_3d(bx + 0.16, by + 0.05, bz - 0.12, 0.26, 0.24, (253, 186, 116), (255, 220, 175))
        else:
            if self.t < 1.35:
                uc = (self.t - 0.65) / 0.70
                bx = -4.0 + uc * 1.4
                bz = 1.75 - uc * 1.55
                by = (1.0 - uc) * 0.45
                stride = math.sin(self.t * 16.0) * 0.16
            elif self.t < 3.30:
                ur = (self.t - 1.35) / 1.95
                bx = -2.6 + ur * 8.15
                bz = 0.20 + ur * 0.32
                stride = math.sin(self.t * 20.0) * 0.24
                by = abs(math.sin(self.t * 20.0)) * 0.10
            else:
                bx = 5.55
                bz = 0.52
                by = 0.0
                stride = 0.0

            if self.t < 4.15:
                # Cast soft ground shadow directly beneath Boy's feet
                cast_floor_shadow(bx - 0.36, bz - 0.28, bx + 0.36, bz + 0.28, left_room=(bx < 0.0))
                stamp_sphere_3d(bx - stride, by + 0.26, bz, 0.16, 0.26, (30, 58, 138), (59, 130, 246))
                stamp_sphere_3d(bx + stride, by + 0.26, bz - 0.06, 0.16, 0.26, (23, 37, 84), (37, 99, 235))
                stamp_sphere_3d(bx - stride * 0.9, 0.07, bz - 0.02, 0.18, 0.08, (226, 232, 240), (255, 255, 255))
                stamp_sphere_3d(bx + stride * 0.9, 0.07, bz - 0.08, 0.18, 0.08, (203, 213, 225), (241, 245, 249))
                stamp_sphere_3d(bx, by + 0.72, bz, 0.34, 0.38, hoodie_main, hoodie_rim)
                stamp_sphere_3d(bx - 0.14, by + 1.15, bz + 0.05, 0.33, 0.31, hoodie_hood, hoodie_rim)
                stamp_sphere_3d(bx + 0.08, by + 1.16, bz - 0.04, 0.25, 0.25, (253, 186, 116), (255, 224, 180))
                stamp_sphere_3d(bx + 0.06, by + 1.30, bz - 0.02, 0.26, 0.14, (30, 27, 36), (63, 63, 70))

                if self.t >= 3.25:
                    reach = math.sin(min(1.0, (self.t - 3.25) / 0.50) * math.pi)
                    ax = bx + 0.38 + reach * 0.95
                    ay = by + 0.85 + reach * 0.68
                    az = bz + reach * 0.58
                    stamp_sphere_3d((bx + ax) * 0.5, (by + 0.82 + ay) * 0.5, (bz + az) * 0.5, 0.18, 0.14, hoodie_main, hoodie_rim)
                    stamp_sphere_3d(ax, ay, az, 0.13, 0.13, (253, 186, 116), (255, 255, 255))
                else:
                    stamp_sphere_3d(bx + stride * 0.8, by + 0.72, bz - 0.14, 0.16, 0.16, hoodie_hood, hoodie_rim)

        return _pack_quadrant_buffer(pbuf, width, height)


class _WinXPDesktopEngine:
    """
    Renders the simulated Vintage CRT Windows XP OS inside the 2x2 Quadrant sub-pixel canvas:
      1. Windows XP Black Waving Flag Boot & Chasing Progress Bars (`boot_t < 1.05`)
      2. Windows XP Royal Blue `WELCOME` Splash Screen + Startup Chime (`1.05 <= boot_t < 2.85`)
      3. Windows XP `Bliss` Wallpaper Desktop (Cerulean Sky + Shaded Clouds
         + Sunlit Rolling Green Hills + Glossy Luna Blue Taskbar + Green `START` Button
         + Live Tray Speaker & Clock + `HEX 3D` Application Icon).
    """

    BOOT_DURATION = 2.85
    WELCOME_START = 1.05
    TASKBAR_H = 8

    def __init__(self) -> None:
        self.boot_t = 0.0
        self.elapsed = 0.0
        self._played_welcome_chime = False
        self.start_menu_open = False
        self.balloon_text = ""
        self.balloon_timer = 0.0

        self._welcome_bg_key: tuple[int, int] = (-1, -1)
        self._welcome_bg: list[int] = []
        self._bliss_bg_key: tuple[int, int] = (-1, -1)
        self._bliss_bg: list[int] = []

    def reset_boot(self) -> None:
        self.boot_t = 0.0
        self._played_welcome_chime = False
        self.start_menu_open = False

    def show_balloon(self, message: str, duration: float = 4.5) -> None:
        self.balloon_text = message
        self.balloon_timer = duration

    def advance_boot(self, dt: float) -> bool:
        self.boot_t += dt
        self.elapsed += dt
        if self.boot_t >= self.WELCOME_START and not self._played_welcome_chime:
            self._played_welcome_chime = True
            play_sfx("xp_startup")
        return self.boot_t >= self.BOOT_DURATION

    def advance_desktop(self, dt: float) -> None:
        self.elapsed += dt
        if self.balloon_timer > 0.0:
            self.balloon_timer = max(0.0, self.balloon_timer - dt)

    def _get_welcome_backdrop(self, width: int, height: int) -> list[int]:
        if self._welcome_bg_key == (width, height) and self._welcome_bg:
            return self._welcome_bg.copy()

        bg = [VOID_INT] * (width * height)
        top_bar_h = max(4, int(height * 0.16))
        bot_bar_h = max(4, int(height * 0.16))
        div_x = int(width * 0.34)
        body_mid_y = (top_bar_h + height - bot_bar_h) * 0.5
        body_half_h = max(1.0, (height - top_bar_h - bot_bar_h) * 0.5)

        for y in range(height):
            row = y * width
            if y < top_bar_h or y >= height - bot_bar_h:
                c = _pack_rgb((0, 48, 156))
                for x in range(width):
                    bg[row + x] = c
            elif y == top_bar_h:
                for x in range(width):
                    t_x = max(0.0, 1.0 - abs(x - width * 0.35) / max(1.0, width * 0.65))
                    bg[row + x] = _pack_rgb(_mix_rgb((0, 48, 156), (251, 146, 60), t_x))
            elif y == height - bot_bar_h - 1:
                for x in range(width):
                    t_x = max(0.0, 1.0 - abs(x - width * 0.50) / max(1.0, width * 0.60))
                    bg[row + x] = _pack_rgb(_mix_rgb((0, 48, 156), (96, 185, 252), t_x))
            else:
                ny = (y - top_bar_h) / max(1, height - top_bar_h - bot_bar_h)
                div_fade = max(0.0, 1.0 - abs(y - body_mid_y) / body_half_h)
                for x in range(width):
                    nx = x / max(1, width)
                    glow = math.exp(-((nx - 0.28) ** 2 + (ny - 0.34) ** 2) * 4.2)
                    col = _mix_rgb((90, 126, 220), (168, 202, 254), glow * 0.78)
                    if width >= 132 and x == div_x:
                        col = _mix_rgb(col, (226, 240, 255), div_fade * 0.65)
                    bg[row + x] = _pack_rgb(col)

        self._welcome_bg_key = (width, height)
        self._welcome_bg = bg
        return bg.copy()

    def _get_bliss_backdrop(self, width: int, desk_h: int) -> list[int]:
        if self._bliss_bg_key == (width, desk_h) and self._bliss_bg:
            return self._bliss_bg.copy()

        bg = [VOID_INT] * (width * desk_h)
        for y in range(desk_h):
            row = y * width
            ny = y / max(1.0, desk_h - 1)
            for x in range(width):
                nx = x / max(1.0, width - 1)
                bg_hill = 0.50 + 0.08 * math.sin(nx * 4.5 + 0.6)
                fg_hill = 0.72 - 0.25 * math.sin(nx * 3.1 - 0.15) - 0.08 * nx

                if ny >= fg_hill:
                    depth_g = min(1.0, (ny - fg_hill) / 0.42)
                    sun_ridge = 0.64 + 0.36 * math.sin(nx * 4.8 + ny * 2.4)
                    grass = _mix_rgb((134, 218, 56), (40, 122, 20), depth_g * 0.76)
                    grass = _scale_rgb(grass, 0.90 + 0.16 * sun_ridge)
                    rgb = grass
                elif ny >= bg_hill:
                    depth_g = min(1.0, (ny - bg_hill) / 0.35)
                    rgb = _mix_rgb((78, 164, 34), (30, 98, 16), depth_g * 0.70)
                else:
                    sky_t = min(1.0, ny / 0.62)
                    rgb = _mix_rgb((20, 92, 210), (150, 206, 254), sky_t)
                if x == 0 or x == width - 1 or y == 0:
                    rgb = _mix_rgb(rgb, (12, 24, 48), 0.26)
                bg[row + x] = _pack_rgb(rgb)

        self._bliss_bg_key = (width, desk_h)
        self._bliss_bg = bg
        return bg.copy()

    def _draw_waving_xp_flag(
        self,
        pbuf: list[int],
        width: int,
        height: int,
        fx: int,
        fy: int,
        pane_w: int,
        pane_h: int,
        gap: int,
        phase: float,
    ) -> None:
        # Solid pure-color 4 panes stepped in 2px wave slices for crisp 2x2 Quadrant edges
        panes = (
            (0, 0, (242, 80, 34)),   # Red TL
            (1, 0, (127, 186, 0)),   # Green TR
            (0, 1, (0, 164, 239)),   # Blue BL
            (1, 1, (255, 185, 0)),   # Yellow BR
        )
        for col_i, row_i, body_rgb in panes:
            x0 = fx + col_i * (pane_w + gap)
            y0 = fy + row_i * (pane_h + 2)
            c_body = _pack_rgb(body_rgb)
            for dx in range(pane_w):
                wave = round(math.sin((col_i * pane_w + dx) * 0.24 + phase) * 0.85)
                px = x0 + dx - row_i
                if not (0 <= px < width):
                    continue
                for dy in range(pane_h):
                    py = y0 + dy + wave
                    if 0 <= py < height:
                        pbuf[py * width + px] = c_body

    def render_boot_frame(self, width: int = DEFAULT_PIX_W, height: int = DEFAULT_PIX_H) -> Text:
        cx = (width // 2) & ~1
        cy = (height // 2) & ~1

        if self.boot_t < self.WELCOME_START:
            # ── Phase A: Classic Black Windows XP Boot Screen + Waving Flag + Chasing Bars ──
            pbuf = [VOID_INT] * (width * height)

            def fill_box(x0: int, y0: int, x1: int, y1: int, rgb: RGB) -> None:
                col = _pack_rgb(rgb)
                for y in range(max(0, y0), min(height, y1)):
                    row = y * width
                    for x in range(max(0, x0), min(width, x1)):
                        pbuf[row + x] = col

            self._draw_waving_xp_flag(
                pbuf, width, height, cx - 12, cy - 16, pane_w=12, pane_h=4, gap=2, phase=self.boot_t * 5.0
            )

            ms_txt = "MICROSOFT"
            ms_w = _pixel_text_width(ms_txt, 1)
            _draw_pixel_text(pbuf, width, height, (cx - ms_w // 2) & ~1, cy - 4, ms_txt, (168, 184, 204))

            title = "WINDOWS XP"
            sx_t = 2 if width >= 110 else 1
            tw = _pixel_text_width(title, sx_t)
            _draw_pixel_text(
                pbuf,
                width,
                height,
                (cx - tw // 2) & ~1,
                cy + 4,
                title,
                (248, 250, 252),
                scale_x=sx_t,
                scale_y=1,
            )

            bar_w = min(56, max(32, width // 3)) & ~1
            bx0 = (cx - bar_w // 2) & ~1
            by0 = min(height - 6, cy + 12) & ~1
            fill_box(bx0 - 2, by0 - 1, bx0 + bar_w + 2, by0 + 4, (100, 116, 139))
            fill_box(bx0, by0, bx0 + bar_w, by0 + 3, (8, 12, 20))
            cycle_u = (self.boot_t / self.WELCOME_START) * 1.45
            scroll_pos = int((cycle_u % 1.0) * (bar_w + 18)) - 14
            for b_i in range(3):
                px = bx0 + scroll_pos + b_i * 6
                cx0 = max(bx0, px)
                cx1 = min(bx0 + bar_w, px + 4)
                if cx0 < cx1:
                    col = (125, 211, 252) if b_i == 1 else (56, 189, 248)
                    fill_box(cx0, by0, cx1, by0 + 3, col)

            return _pack_quadrant_buffer(pbuf, width, height)

        # ── Phase B: Classic Windows XP Royal-Blue "WELCOME" Splash ──
        pbuf = self._get_welcome_backdrop(width, height)
        text = "WELCOME"
        if width >= 132:
            div_x = int(width * 0.34) & ~1
            self._draw_waving_xp_flag(
                pbuf, width, height, div_x - 24, cy - 8, pane_w=8, pane_h=4, gap=2, phase=self.boot_t * 2.8
            )
            _draw_pixel_text(pbuf, width, height, div_x - 30, cy + 4, "WIN XP", (241, 245, 249))
            sx_w = 3
            sy_w = 2 if height >= 36 else 1
            tw_px = _pixel_text_width(text, sx_w)
            th_px = 5 * sy_w
            rx = (div_x + (width - div_x - tw_px) // 2) & ~1
            _draw_pixel_text(
                pbuf, width, height, rx, (cy - th_px // 2) & ~1, text, fg_rgb=(255, 255, 255),
                scale_x=sx_w, scale_y=sy_w,
            )
        else:
            sx_w = 2
            sy_w = 2 if height >= 36 else 1
            tw_px = _pixel_text_width(text, sx_w)
            th_px = 5 * sy_w
            _draw_pixel_text(
                pbuf, width, height, (cx - tw_px // 2) & ~1, (cy - th_px // 2) & ~1, text, fg_rgb=(255, 255, 255),
                scale_x=sx_w, scale_y=sy_w,
            )
        return _pack_quadrant_buffer(pbuf, width, height)

    @staticmethod
    def get_icon_boxes(width: int, height: int, count: int = 1) -> list[tuple[int, int, int, int]]:
        """Return even-aligned sub-pixel bounding boxes `(x0, y0, x1, y1)` for Windows XP desktop icons."""
        boxes: list[tuple[int, int, int, int]] = []
        desk_h = max(16, height - _WinXPDesktopEngine.TASKBAR_H)
        row_step = 16
        col_step = 30
        max_rows = max(2, (desk_h - 2) // row_step)
        for idx in range(count):
            col = idx // max_rows
            row = idx % max_rows
            ix0 = 6 + col * col_step
            iy0 = 2 + row * row_step
            if ix0 + 24 <= width - 2 and iy0 + 14 <= desk_h:
                boxes.append((ix0, iy0, ix0 + 24, iy0 + 14))
        return boxes

    @staticmethod
    def start_menu_rect(width: int, height: int) -> tuple[int, int, int, int]:
        tb_y0 = height - _WinXPDesktopEngine.TASKBAR_H
        sm_w = min(64, max(48, width // 4)) & ~1
        sm_h = min(22, max(18, tb_y0)) & ~1
        sm_y0 = max(0, tb_y0 - sm_h) & ~1
        return 0, sm_y0, sm_w, tb_y0

    @staticmethod
    def start_menu_close_rect(width: int, height: int) -> tuple[int, int, int, int]:
        _, sm_y0, sm_x1, _ = _WinXPDesktopEngine.start_menu_rect(width, height)
        return sm_x1 - 8, sm_y0 + 1, sm_x1 - 1, sm_y0 + 7

    @staticmethod
    def start_menu_off_rect(width: int, height: int) -> tuple[int, int, int, int]:
        sm_x0, sm_y0, sm_x1, sm_y1 = _WinXPDesktopEngine.start_menu_rect(width, height)
        y0 = min(sm_y1 - 8, sm_y0 + 10)
        y1 = max(y0 + 6, sm_y1 - 2)
        return sm_x0 + 6, y0, sm_x1 - 6, y1

    def render_desktop(
        self,
        width: int,
        height: int,
        icon_selected: bool = True,
        has_save: bool = False,
    ) -> Text:
        """
        Render the Windows XP `Bliss` Wallpaper Desktop + Luna Taskbar + Green `START` Button
        + Live System Tray + built-in `HEX 3D` Software Icon.
        """
        tb_h = self.TASKBAR_H
        desk_h = max(10, height - tb_h)
        tb_y0 = height - tb_h

        # ── 1. Cached Bliss Rolling Hills & Sky + Sunlit/Shadowed Multi-Lobe Cumulus Clouds ──
        pbuf = self._get_bliss_backdrop(width, desk_h) + [VOID_INT] * (width * tb_h)

        cloud_shift = self.elapsed * 0.55
        clouds = (
            (width * 0.28, desk_h * 0.18, 12.0, 2.4),
            (width * 0.60, desk_h * 0.13, 15.0, 2.8),
            (width * 0.85, desk_h * 0.21, 11.0, 2.2),
        )
        white_i = _pack_rgb((252, 254, 255))
        shadow_c_i = _pack_rgb((202, 224, 248))
        for c_x, c_y, c_rx, c_ry in clouds:
            scx = (c_x + cloud_shift) % width
            for lobe_dx, lobe_dy, lobe_mul in ((0.0, 0.0, 1.0), (-c_rx * 0.45, c_ry * 0.25, 0.72), (c_rx * 0.48, c_ry * 0.30, 0.68)):
                lx = scx + lobe_dx
                ly = c_y + lobe_dy
                rx_l = c_rx * lobe_mul
                ry_l = c_ry * lobe_mul
                for y in range(max(0, int(ly - ry_l)), min(desk_h, int(ly + ry_l + 1))):
                    ny = (y - ly) / max(0.5, ry_l)
                    ny2 = ny * ny
                    row = y * width
                    lobe_tint = shadow_c_i if ny > 0.35 else white_i
                    for x in range(max(0, int(lx - rx_l)), min(width, int(lx + rx_l + 1))):
                        nx = (x - lx) / max(0.5, rx_l)
                        d2 = nx * nx + ny2
                        if d2 <= 1.0:
                            pbuf[row + x] = _mix_int(pbuf[row + x], lobe_tint, 0.82 * (1.0 - d2 * 0.32))

        def fill_rect(x0: int, y0: int, x1: int, y1: int, rgb: RGB, border_rgb: Optional[RGB] = None) -> None:
            c_f = _pack_rgb(rgb)
            c_b = _pack_rgb(border_rgb) if border_rgb else c_f
            for y in range(max(0, y0), min(height, y1)):
                row = y * width
                tb = border_rgb is not None and (y == y0 or y == y1 - 1)
                for x in range(max(0, x0), min(width, x1)):
                    if tb or (border_rgb is not None and (x == x0 or x == x1 - 1)):
                        pbuf[row + x] = c_b
                    else:
                        pbuf[row + x] = c_f

        def set_px(px: int, py: int, rgb: RGB) -> None:
            if 0 <= px < width and 0 <= py < height:
                pbuf[py * width + px] = _pack_rgb(rgb)

        # ── 2. Desktop Icon: Built-in `HEX 3D` Game Software ──
        boxes = self.get_icon_boxes(width, height, 1)
        for ix0, iy0, ix1, iy1 in boxes:
            if icon_selected:
                sel_col = _pack_rgb((28, 84, 198))
                for y in range(max(0, iy0), min(desk_h, iy0 + 8)):
                    row = y * width
                    for x in range(max(0, ix0), min(width, ix1)):
                        pbuf[row + x] = _mix_int(pbuf[row + x], sel_col, 0.56)

            cx0, cy0, cx1, cy1 = ix0 + 4, iy0, ix1 - 4, iy0 + 8
            # Mini XP CRT monitor icon with glowing 3D cyber-emerald core
            fill_rect(cx0, cy0, cx1, cy1, (10, 26, 46), border_rgb=(203, 213, 225))
            fill_rect(cx0 + 2, cy0 + 1, cx1 - 2, cy0 + 3, (28, 84, 198))
            fill_rect(cx0 + 3, cy0 + 3, cx0 + 11, cy0 + 7, (16, 185, 129))
            fill_rect(cx0 + 5, cy0 + 3, cx0 + 9, cy0 + 5, (0, 255, 102))
            fill_rect(cx1 - 4, cy0 + 4, cx1 - 2, cy0 + 6, (56, 189, 248))
            if has_save:
                fill_rect(cx1 - 2, cy0, cx1, cy0 + 2, (0, 255, 102))

            lbl_bg: RGB = (28, 84, 198) if icon_selected else (18, 36, 72)
            fill_rect(ix0, iy0 + 8, ix1, iy0 + 14, lbl_bg)
            code_txt = "HEX 3D"
            tw_px = _pixel_text_width(code_txt, 1)
            lbl_x = max(ix0, (ix0 + ix1 - tw_px) // 2)
            _draw_pixel_text(
                pbuf,
                width,
                height,
                lbl_x,
                iy0 + 8,
                code_txt,
                fg_rgb=(255, 255, 255),
            )

        # ── 3. Windows XP Luna Glossy Taskbar (`TASKBAR_H = 8` even), Rounded `START`, System Tray ──
        for y in range(tb_y0, height):
            row = y * width
            if y == tb_y0:
                tb_rgb = (104, 168, 255)
            elif y == tb_y0 + 1:
                tb_rgb = (56, 118, 236)
            elif y == height - 1:
                tb_rgb = (22, 62, 162)
            else:
                tb_rgb = (36, 93, 219)
            c_tb = _pack_rgb(tb_rgb)
            for x in range(width):
                pbuf[row + x] = c_tb

        start_w = 32
        st_hi = self.start_menu_open
        for y in range(tb_y0, height):
            row = y * width
            if y <= tb_y0 + 1:
                g_rgb = (134, 228, 98) if not st_hi else (164, 244, 126)
            elif y == height - 1:
                g_rgb = (32, 112, 22)
            else:
                g_rgb = (82, 198, 58) if st_hi else (58, 168, 38)
            c_g = _pack_rgb(g_rgb)
            x_lim = start_w - 2 if y in (tb_y0, height - 1) else start_w
            for x in range(x_lim):
                pbuf[row + x] = c_g
        # 2x2 Quadrant-aligned 4-color XP flag inside green `START` button
        fy = tb_y0 + 2
        fill_rect(2, fy, 4, fy + 2, (242, 80, 34))
        fill_rect(4, fy, 6, fy + 2, (127, 186, 0))
        fill_rect(2, fy + 2, 4, fy + 4, (0, 164, 239))
        fill_rect(4, fy + 2, 6, fy + 4, (255, 185, 0))
        _draw_pixel_text(pbuf, width, height, 8, tb_y0 + 2, "START", fg_rgb=(255, 255, 255))

        tray_w = 34 if width >= 92 else 26
        tray_x0 = width - tray_w
        for y in range(tb_y0, height):
            row = y * width
            tr_rgb = (64, 184, 250) if y <= tb_y0 + 1 else ((18, 140, 228) if y < height - 1 else (14, 108, 192))
            c_tr = _pack_rgb(tr_rgb)
            for x in range(tray_x0, width):
                pbuf[row + x] = c_tr
        if width >= 92:
            sx_tr = tray_x0 + 2
            sy_tr = tb_y0 + 2
            fill_rect(sx_tr, sy_tr + 2, sx_tr + 2, sy_tr + 4, (226, 232, 240))
            fill_rect(sx_tr + 2, sy_tr + 1, sx_tr + 4, sy_tr + 5, (255, 255, 255))
            fill_rect(sx_tr + 5, sy_tr + 2, sx_tr + 6, sy_tr + 4, (186, 230, 253))
            clock_x = tray_x0 + 10
        else:
            clock_x = tray_x0 + 4
        clock_txt = time.strftime("%H:%M")
        _draw_pixel_text(pbuf, width, height, clock_x, tb_y0 + 2, clock_txt, fg_rgb=(255, 255, 255))

        # ── 4. Optional Windows XP Balloon Tip above System Tray (EVEN aligned) ──
        if self.balloon_timer > 0.0 and self.balloon_text:
            msg = self.balloon_text[:16].upper()
            bw = (max(40, _pixel_text_width(msg, 1) + 8)) & ~1
            bx0 = max(4, width - bw - 4) & ~1
            by0 = max(2, tb_y0 - 12) & ~1
            fill_rect(bx0 - 2, by0 - 1, bx0 + bw + 2, by0 + 9, (30, 41, 59))
            fill_rect(bx0, by0, bx0 + bw, by0 + 8, (254, 252, 232))
            _draw_pixel_text(pbuf, width, height, bx0 + 4, by0 + 2, msg, fg_rgb=(15, 23, 42))

        # ── 5. Minimal Windows XP Start Menu Popup (`[X]` Close + Shutdown `OFF` Only) ──
        if self.start_menu_open:
            sm_x0, sm_y0, sm_x1, sm_y1 = self.start_menu_rect(width, height)
            hdr_h = 8
            fill_rect(sm_x0, sm_y0, sm_x1, sm_y0 + hdr_h, (28, 84, 198))
            cx0, cy0, cx1, cy1 = self.start_menu_close_rect(width, height)
            fill_rect(cx0, cy0, cx1, cy1, (220, 38, 38), border_rgb=(254, 202, 202))
            _draw_pixel_text(pbuf, width, height, cx0 + 2, cy0 + 1, "X", (255, 255, 255))

            fill_rect(sm_x0, sm_y0 + hdr_h, sm_x1, sm_y1, (240, 245, 252))
            ox0, oy0, ox1, oy1 = self.start_menu_off_rect(width, height)
            fill_rect(ox0, oy0, ox1, oy1, (220, 38, 38), border_rgb=(254, 202, 202))
            off_w = _pixel_text_width("OFF", 1)
            badge_w = off_w + 8
            bx = max(ox0 + 2, (ox0 + ox1 - badge_w) // 2) & ~1
            by = max(oy0 + 1, (oy0 + oy1 - 5) // 2) & ~1
            fill_rect(bx, by + 1, bx + 4, by + 4, (255, 255, 255))
            _draw_pixel_text(pbuf, width, height, bx + 7, by, "OFF", (255, 255, 255))

            # Crisp 1px Luna border enclosing Start Menu popup against Bliss sky
            fill_rect(sm_x1 - 1, sm_y0, sm_x1, sm_y1, (18, 62, 162))
            fill_rect(sm_x0, sm_y0, sm_x1, sm_y0 + 1, (96, 165, 250))
            fill_rect(sm_x0, sm_y0, sm_x0 + 1, sm_y1, (96, 165, 250))

        return _pack_quadrant_buffer(pbuf, width, height)


def build_arcade_room_app(auto_boot_hex: bool = False, skip_cutscene: bool = False):
    """
    Build the pure-pixel Virtual CRT XP Playground App (`xp`):
      • Full-window minimalist CRT presentation with close `[✕]` buttons on every window.
      • Plays the 3D sneak-in cutscene -> Windows XP Boot & `WELCOME` splash -> Windows XP
        `Bliss` Desktop (`HEX 3D` double-click launch & instant Save/Load state).
    """
    from textual import events, on
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Center, Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, Static

    from pykuai.core.tui import (
        CYBER_TUI_CSS,
        HelpModalScreen,
        PyKuaiStudioApp,
    )

    class _CrtCanvas(Static):
        """Pure pixel-buffer viewport with Textual text selection disabled to prevent blue stripe artifacts."""

        ALLOW_SELECT: ClassVar[bool] = False
        can_focus = False

    xp_css = CYBER_TUI_CSS + """
    Screen {
        align: center middle;
        background: #04060b;
        padding: 0;
    }

    #crt-shell {
        width: 100%;
        height: 100%;
        align: center middle;
        background: #04060b;
        padding: 0;
    }

    #btn-game-close {
        width: 5;
        min-width: 5;
        max-width: 5;
        height: 1;
        min-height: 1;
        border: none;
        padding: 0;
        margin: 0;
        background: #dc2626;
        color: #ffffff;
        text-style: bold;
        content-align: center middle;
    }

    #btn-game-close:hover {
        background: #ef4444;
        color: #ffffff;
    }

    #viewport-wrap {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #crt-frame {
        width: auto;
        height: auto;
        align: center middle;
        padding: 0;
    }

    #xp-game-bar {
        display: none;
        height: 1;
        background: #1c54c6;
        padding: 0;
    }

    #xp-game-title {
        width: 1fr;
        height: 1;
        background: #1c54c6;
        color: #ffffff;
        text-style: bold;
        padding: 0 1;
    }

    #crt-viewport {
        border: heavy #334155;
        background: #070910;
        padding: 0;
        content-align: center middle;
    }

    #crt-viewport.-xp-desktop {
        border: heavy #d6d3c9;
    }

    #crt-viewport.-fault {
        border: heavy #FF5252;
    }
    """

    class ArcadeWinXPApp(PyKuaiStudioApp):
        ALLOW_SELECT: ClassVar[bool] = False
        CSS = xp_css
        HELP_TITLE = ROOM3D_HELP_TITLE
        HELP_TEXT = ROOM3D_HELP_TEXT
        BINDINGS = [
            *PyKuaiStudioApp.BINDINGS,
            Binding("question_mark", "show_help", "Help", show=False),
            Binding("enter", "primary_action", "Launch/Start", show=False),
            Binding("space", "space_action", "Skip/Pause", show=False),
            Binding("right", "key_right", "Right", show=False),
            Binding("d", "key_right", "Right", show=False),
            Binding("D", "key_right", "Right", show=False),
            Binding("left", "key_left", "Left", show=False),
            Binding("a", "key_left", "Left", show=False),
            Binding("A", "key_left", "Left", show=False),
            Binding("up", "key_up", "Up", show=False),
            Binding("w", "key_up", "Up", show=False),
            Binding("W", "key_up", "Up", show=False),
            Binding("f5", "save_game_state", "Save State", show=False),
            Binding("f8", "load_game_state", "Load State", show=False),
            Binding("r", "restart_game", "Restart", show=False),
            Binding("R", "restart_game", "Restart", show=False),
            Binding("p", "pause_game", "Pause", show=False),
            Binding("P", "pause_game", "Pause", show=False),
            Binding("q", "back_or_exit", "Exit", show=False),
            Binding("Q", "back_or_exit", "Exit", show=False),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.icon_selected = True
            self.cutscene = _True3DCutsceneEngine()
            self.xp = _WinXPDesktopEngine()
            # Modes: "cutscene" -> "xp_boot" -> "xp_desktop" -> "xp_playing"
            self.mode = "xp_desktop" if skip_cutscene else "cutscene"
            self.hex_engine: Optional[_Hex3DEngine] = None
            self.pending_auto_boot = bool(auto_boot_hex)
            self._desk_idle_accum = 0.0
            self._last_tick = time.perf_counter()
            self._last_click_ts = 0.0
            self.pix_w = DEFAULT_PIX_W
            self.pix_h = DEFAULT_PIX_H

        def _recompute_viewport(self) -> None:
            tw = max(48, self.size.width)
            th = max(18, self.size.height)

            view_cols = min(220, max(40, tw - 4))
            if view_cols % 2 == 1:
                view_cols -= 1
            view_rows = min(74, max(12, th - 3))
            self.pix_w = view_cols * 2
            self.pix_h = view_rows * 2

            vp = self.query_one("#crt-viewport", _CrtCanvas)
            vp.styles.width = view_cols + 2
            vp.styles.height = view_rows + 2
            gbar = self.query_one("#xp-game-bar", Horizontal)
            gbar.styles.width = view_cols + 2

        def compose(self) -> ComposeResult:
            with Vertical(id="crt-shell"):
                with Center(id="viewport-wrap"):
                    with Vertical(id="crt-frame"):
                        with Horizontal(id="xp-game-bar"):
                            yield Static("", id="xp-game-title")
                            btn_game = Button("✕", id="btn-game-close")
                            btn_game.can_focus = False
                            yield btn_game
                        yield _CrtCanvas("", id="crt-viewport")

        def on_mount(self) -> None:
            warmup_arcade_sfx()
            self._recompute_viewport()
            if self.mode == "cutscene":
                self.cutscene.reset()
            elif self.pending_auto_boot:
                self.pending_auto_boot = False
                self._boot_hex3d()
            self._sync_view()
            self._last_tick = time.perf_counter()
            self.set_interval(1.0 / 30.0, self._on_tick)

        def on_resize(self, event: events.Resize) -> None:
            self._recompute_viewport()
            self._sync_view()

        def _screen_to_subpixel(self, screen_x: int, screen_y: int) -> Optional[tuple[int, int]]:
            vp = self.query_one("#crt-viewport", _CrtCanvas)
            creg = vp.content_region
            if not creg.contains(screen_x, screen_y):
                return None
            cx_cell = screen_x - creg.x
            cy_cell = screen_y - creg.y
            if cx_cell < 0 or cy_cell < 0 or cx_cell >= self.pix_w // 2 or cy_cell >= self.pix_h // 2:
                return None
            return cx_cell * 2 + 1, cy_cell * 2 + 1

        @on(Button.Pressed, "#btn-game-close")
        def _on_game_close_pressed(self) -> None:
            if self.mode == "xp_playing":
                self._close_game_to_xp_desktop()

        def on_mouse_down(self, event: events.MouseDown) -> None:
            if isinstance(self.screen, ModalScreen):
                return
            if self.screen.selections:
                self.screen.clear_selection()
            pt = self._screen_to_subpixel(event.screen_x, event.screen_y)
            if pt is None:
                return
            px, py = pt

            if self.mode == "cutscene":
                play_sfx("enter")
                self._enter_xp_boot()
                return

            if self.mode == "xp_boot":
                play_sfx("enter")
                self._enter_xp_desktop()
                return

            if self.mode == "xp_desktop":
                tb_y0 = self.pix_h - self.xp.TASKBAR_H
                if py >= tb_y0 and px <= 31:
                    play_sfx("click")
                    self.xp.start_menu_open = not self.xp.start_menu_open
                    self._last_click_ts = 0.0
                    self._sync_view()
                    return

                if self.xp.start_menu_open:
                    sm_x0, sm_y0, sm_x1, sm_y1 = self.xp.start_menu_rect(self.pix_w, self.pix_h)
                    if sm_x0 <= px <= sm_x1 and sm_y0 <= py < sm_y1:
                        cx0, cy0, cx1, cy1 = self.xp.start_menu_close_rect(self.pix_w, self.pix_h)
                        if cx0 - 1 <= px <= cx1 + 1 and cy0 - 1 <= py <= cy1 + 1:
                            self.xp.start_menu_open = False
                            play_sfx("click")
                            self._sync_view()
                            return
                        ox0, oy0, ox1, oy1 = self.xp.start_menu_off_rect(self.pix_w, self.pix_h)
                        if ox0 <= px <= ox1 and oy0 <= py <= oy1:
                            play_sfx("click")
                            self.exit(0)
                            return
                        return
                    self.xp.start_menu_open = False

                boxes = self.xp.get_icon_boxes(self.pix_w, self.pix_h, 1)
                now = time.perf_counter()
                for ix0, iy0, ix1, iy1 in boxes:
                    if ix0 - 2 <= px <= ix1 + 2 and iy0 - 1 <= py <= iy1 + 1:
                        is_dbl = self.icon_selected and (now - self._last_click_ts) <= 0.70
                        self.icon_selected = True
                        if is_dbl:
                            self._last_click_ts = 0.0
                            self._boot_hex3d()
                        else:
                            self._last_click_ts = now
                            play_sfx("click")
                            self._sync_view()
                        return

                self._last_click_ts = 0.0
                self._sync_view()

        def _enter_xp_boot(self) -> None:
            self.cutscene.done = True
            if self.pending_auto_boot:
                self.pending_auto_boot = False
                self._boot_hex3d()
                return
            self.mode = "xp_boot"
            self.xp.reset_boot()
            self._sync_view()

        def _enter_xp_desktop(self) -> None:
            if self.pending_auto_boot:
                self.pending_auto_boot = False
                self._boot_hex3d()
                return
            self.mode = "xp_desktop"
            self._sync_view()

        def _boot_hex3d(self, load_saved: bool = False) -> None:
            self.hex_engine = _Hex3DEngine()
            if load_saved:
                raw, _ = _load_hex_meta()
                if raw:
                    self.hex_engine.deserialize_state(raw)
            play_sfx("enter")
            self.mode = "xp_playing"
            self._sync_view()

        def _persist_hex_state(self) -> None:
            if self.hex_engine is None:
                return
            score = self.hex_engine.score
            record_high_score("hex", score)
            _save_hex_state(
                self.hex_engine.serialize_state(),
                summary=f"Stage {self.hex_engine.stage_idx + 1} · Score {score}",
            )

        def _close_game_to_xp_desktop(self) -> None:
            self._persist_hex_state()
            self.hex_engine = None
            self.mode = "xp_desktop"
            play_sfx("click")
            self.xp.show_balloon("HEX 3D SAVED", duration=3.2)
            self._sync_view()

        def _on_tick(self) -> None:
            now = time.perf_counter()
            dt = min(0.08, max(0.005, now - self._last_tick))
            self._last_tick = now

            if isinstance(self.screen, ModalScreen):
                return

            if self.mode == "cutscene":
                if self.cutscene.advance(dt):
                    self._enter_xp_boot()
                    return
                self._sync_view()
                return

            if self.mode == "xp_boot":
                if self.xp.advance_boot(dt):
                    self._enter_xp_desktop()
                    return
                self._sync_view()
                return

            if self.mode == "xp_desktop":
                self.xp.advance_desktop(dt)
                self._desk_idle_accum += dt
                if self._desk_idle_accum >= 0.14:
                    self._desk_idle_accum = 0.0
                    self._sync_view()
                return

            if self.hex_engine is not None:
                ev = self.hex_engine.advance_frame(dt)
                if ev == "orb":
                    play_sfx("key")
                elif ev == "stage":
                    play_sfx("enter")
                elif ev == "rim":
                    play_sfx("paste")
                elif ev in ("gameover", "victory"):
                    play_sfx("snake" if ev == "victory" else "paste")

            self._sync_view()

        def _sync_view(self) -> None:
            self._desk_idle_accum = 0.0
            vp = self.query_one("#crt-viewport", _CrtCanvas)
            gbar = self.query_one("#xp-game-bar", Horizontal)
            gtitle = self.query_one("#xp-game-title", Static)

            if self.mode == "cutscene":
                gbar.display = False
                vp.set_class(False, "-xp-desktop")
                vp.set_class(False, "-fault")
                vp.update(self.cutscene.render_frame(self.pix_w, self.pix_h))
                return

            if self.mode == "xp_boot":
                gbar.display = False
                vp.set_class(True, "-xp-desktop")
                vp.set_class(False, "-fault")
                vp.update(self.xp.render_boot_frame(self.pix_w, self.pix_h))
                return

            if self.mode == "xp_desktop":
                gbar.display = False
                vp.set_class(True, "-xp-desktop")
                vp.set_class(False, "-fault")
                has_save = _HEX_SAVE_PATH.is_file()
                vp.update(self.xp.render_desktop(self.pix_w, self.pix_h, icon_selected=self.icon_selected, has_save=has_save))
                return

            # In-CRT Active Gameplay (`xp_playing`)
            assert self.hex_engine is not None
            e = self.hex_engine
            from pykuai.arcade.hex3d import STAGES

            gbar.display = True
            vp.set_class(True, "-xp-desktop")
            stage_name = str(STAGES[e.stage_idx]["name"])
            gtitle.update(
                f" HEX 3D · {stage_name} ({e.stage_orbs}/{e.stage_goal}) · SCORE {e.score} · BEST {e.best_score}"
            )
            vp.update(e.render_frame(self.pix_w, self.pix_h))
            vp.set_class(e.left_fault_ticks > 0 or e.phase == "gameover", "-fault")

        # ── Keyboard Actions ──

        def action_primary_action(self) -> None:
            if isinstance(self.screen, ModalScreen):
                return
            if self.mode == "cutscene":
                play_sfx("enter")
                self._enter_xp_boot()
            elif self.mode == "xp_boot":
                play_sfx("enter")
                self._enter_xp_desktop()
            elif self.mode == "xp_desktop":
                self._boot_hex3d()
            elif self.mode == "xp_playing" and self.hex_engine is not None:
                self.hex_engine.start_if_intro()
                play_sfx("enter")
                self._sync_view()

        def action_space_action(self) -> None:
            if isinstance(self.screen, ModalScreen):
                return
            if self.mode == "cutscene":
                play_sfx("enter")
                self._enter_xp_boot()
                return
            if self.mode == "xp_boot":
                play_sfx("enter")
                self._enter_xp_desktop()
                return
            if self.mode == "xp_desktop":
                self._boot_hex3d()
                return
            if self.hex_engine is not None:
                if self.hex_engine.phase == "intro":
                    self.hex_engine.start_if_intro()
                    play_sfx("enter")
                elif self.hex_engine.phase == "playing":
                    self.hex_engine.phase = "paused"
                    self.hex_engine.status_line = "PAUSED · Space to resume · F5 to save · Esc to desktop"
                    play_sfx("click")
                elif self.hex_engine.phase == "paused":
                    self.hex_engine.phase = "playing"
                    play_sfx("click")
            self._sync_view()

        def action_key_right(self) -> None:
            if isinstance(self.screen, ModalScreen) or self.mode != "xp_playing" or self.hex_engine is None:
                return
            fb = self.hex_engine.input_turn_right()
            play_sfx("enter" if fb == "start" else "click")
            self._sync_view()

        def action_key_left(self) -> None:
            if isinstance(self.screen, ModalScreen) or self.mode != "xp_playing" or self.hex_engine is None:
                return
            self.hex_engine.input_turn_left_fault()
            play_sfx("paste")
            self._sync_view()

        def action_key_up(self) -> None:
            if isinstance(self.screen, ModalScreen) or self.mode != "xp_playing" or self.hex_engine is None:
                return
            ev = self.hex_engine.input_quick_step()
            if ev == "orb":
                play_sfx("key")
            elif ev == "stage":
                play_sfx("enter")
            self._sync_view()

        def action_save_game_state(self) -> None:
            if isinstance(self.screen, ModalScreen) or self.mode != "xp_playing" or self.hex_engine is None:
                return
            self._persist_hex_state()
            self.hex_engine.status_line = f"Saved HEX 3D · Stage {self.hex_engine.stage_idx + 1} · Score {self.hex_engine.score}"
            play_sfx("enter")
            self._sync_view()

        def action_load_game_state(self) -> None:
            if isinstance(self.screen, ModalScreen):
                return
            raw, summary = _load_hex_meta()
            if not raw:
                play_sfx("paste")
                if self.mode == "xp_desktop":
                    self.xp.show_balloon("NO SAVED RUN", duration=2.4)
                elif self.hex_engine is not None:
                    self.hex_engine.status_line = "No saved HEX 3D state yet. Press F5 first."
                self._sync_view()
                return

            if self.mode != "xp_playing":
                self._boot_hex3d(load_saved=True)
                return

            assert self.hex_engine is not None
            ok = self.hex_engine.deserialize_state(raw)
            if ok and summary:
                self.hex_engine.status_line = f"Loaded HEX 3D ({summary}) · Space / D to resume"
            play_sfx("enter" if ok else "paste")
            self._sync_view()

        def action_restart_game(self) -> None:
            if isinstance(self.screen, ModalScreen) or self.mode != "xp_playing" or self.hex_engine is None:
                return
            play_sfx("snake")
            record_high_score("hex", self.hex_engine.score)
            self.hex_engine.reset(show_intro=False)
            self._sync_view()

        def action_pause_game(self) -> None:
            if isinstance(self.screen, ModalScreen):
                return
            if self.mode == "xp_playing":
                self.action_space_action()

        def action_back_or_exit(self) -> None:
            if isinstance(self.screen, HelpModalScreen):
                self.screen.action_dismiss_help()
                return
            if self.mode == "xp_playing":
                self._close_game_to_xp_desktop()
                return
            play_sfx("click")
            self.hex_engine = None
            self.exit(0)

        def action_cancel(self) -> None:
            self.action_back_or_exit()

    return ArcadeWinXPApp()
