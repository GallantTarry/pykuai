# -*- coding: utf-8 -*-
"""
PyKuai: Hex 3D (`hex`)
Compact Multicolored 3D Honeycomb Snake — Forced Right-Only Edition.

Backstory:
  When TuKuai was young, his older brother gave him a Nokia phone whose center square D-pad
  had a broken LEFT switch — it could only click RIGHT. TuKuai beat the entire game anyway.
"""
from __future__ import annotations

from collections import deque
import math
import random
from typing import Optional

from rich.console import Console
from rich.text import Text

from pykuai.arcade import ArcadeGame, get_high_score, record_high_score
from pykuai.core.audio import play_sfx
from pykuai.core.ui import print_error

CubeCoord = tuple[int, int, int]
RGB = tuple[int, int, int]

DEFAULT_PIX_W = 58
DEFAULT_PIX_H = 26  # 13 half-block terminal rows inside compact 78x24 studio card
VOID_RGB: RGB = (7, 9, 16)
VOID_HEX = "#070910"

# Clockwise cube directions matching (+wx, +wz) right-handed top-down orientation
HEX_DIRS: tuple[CubeCoord, ...] = (
    (1, 0, -1),
    (0, 1, -1),
    (-1, 1, 0),
    (-1, 0, 1),
    (0, -1, 1),
    (1, -1, 0),
)

# Multicolored 6-hue jewel mosaic palette (no green so the green spotted snake pops clearly!)
MOSAIC_TILES: tuple[tuple[RGB, RGB, RGB], ...] = (
    ((16, 108, 138), (56, 224, 248), (10, 62, 84)),    # Electric Cyan
    ((62, 54, 186), (138, 150, 255), (36, 30, 118)),   # Royal Indigo
    ((124, 38, 198), (206, 146, 255), (72, 22, 120)),  # Amethyst Violet
    ((182, 28, 96), (250, 124, 190), (108, 16, 58)),   # Neon Rose
    ((176, 84, 16), (255, 198, 56), (104, 48, 10)),    # Amber Gold
    ((28, 82, 206), (104, 174, 255), (16, 48, 126)),   # Cobalt Blue
)

STAGES: tuple[dict[str, object], ...] = (
    {"name": "SECTOR 1", "radius": 4, "goal": 6, "step_sec": 0.34, "palette_shift": 0},
    {"name": "SECTOR 2", "radius": 4, "goal": 8, "step_sec": 0.30, "palette_shift": 2},
    {"name": "SECTOR 3", "radius": 5, "goal": 10, "step_sec": 0.27, "palette_shift": 4},
)

HEX3D_HELP = """\
[bold #22d3ee]PyKuai: Hex 3D (hex) · Broken-Left Legend[/]
  [italic #a5f3fc]When TuKuai was young, his older brother gave him a Nokia phone.[/]
  [italic #a5f3fc]Its square center D-pad was broken on the LEFT — it could only click RIGHT.[/]
  [italic #a5f3fc]Spinning right on the spot, TuKuai conquered the entire 3D hex arena anyway.[/]

[bold #22d3ee]How Right-Only Steering Works[/]
  • [bold #00FF00]→ / D (Tap 1–4x)[/] Pivots your aim reticle clockwise [bold]instantly[/] on the current hex!
    Tap 1x = +60 deg Right | Tap 2x = +120 deg | Tap 4x = Left (-60 deg)!
  • [bold #FF5252]← / A Locked[/]    Left D-pad is broken and triggers a hardware fault warning.
  • Outer rim safely deflects clockwise (-5 pts); biting your tail ends the run.

[bold #22d3ee]Controls[/]
  • [bold #e5e7eb]→ / D[/]         Instant clockwise pivot (+60 deg)
  • [bold #e5e7eb]Space / P[/]     Start or Pause
  • [bold #e5e7eb]R[/]             Restart
  • [bold #e5e7eb]Esc / Q[/]       Save & Exit"""


_HEX_STR_CACHE: dict[int, str] = {}


def _rgb_to_hex(rgb: RGB) -> str:
    key = (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]
    cached = _HEX_STR_CACHE.get(key)
    if cached is None:
        cached = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        if len(_HEX_STR_CACHE) < 4096:
            _HEX_STR_CACHE[key] = cached
    return cached


def _mix_rgb(a: RGB, b: RGB, t: float) -> RGB:
    if t <= 0.0:
        return a
    if t >= 1.0:
        return b
    inv = 1.0 - t
    return (
        int(a[0] * inv + b[0] * t),
        int(a[1] * inv + b[1] * t),
        int(a[2] * inv + b[2] * t),
    )


def _scale_rgb(c: RGB, k: float) -> RGB:
    return (
        max(0, min(255, int(c[0] * k))),
        max(0, min(255, int(c[1] * k))),
        max(0, min(255, int(c[2] * k))),
    )


def _cube_dist(a: CubeCoord, b: CubeCoord) -> int:
    return (abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])) // 2


def _cube_to_world_xz(c: CubeCoord, hex_size: float = 1.0) -> tuple[float, float]:
    q, r, _ = c
    return hex_size * math.sqrt(3.0) * (q + r * 0.5), hex_size * 1.5 * r


def _build_stage_heights(stage_idx: int, radius: int) -> dict[CubeCoord, float]:
    heights: dict[CubeCoord, float] = {}
    for q in range(-radius, radius + 1):
        for r in range(-radius, radius + 1):
            s = -q - r
            if max(abs(q), abs(r), abs(s)) > radius:
                continue
            wx, wz = _cube_to_world_xz((q, r, s))
            dist = _cube_dist((q, r, s), (0, 0, 0))
            if stage_idx == 0:
                ang = math.atan2(wz, wx)
                h = 0.22 + 0.48 * (1.0 - dist / max(1, radius)) + 0.28 * math.sin(ang + dist * 0.55)
            elif stage_idx == 1:
                hill_a = 1.25 * math.exp(-((wx + 2.2) ** 2 + (wz - 1.1) ** 2) / 4.6)
                hill_b = 1.25 * math.exp(-((wx - 2.2) ** 2 + (wz + 1.1) ** 2) / 4.6)
                h = 0.10 + hill_a + hill_b
            else:
                ring_peak = 1.05 * math.exp(-((dist - 3.0) ** 2) / 1.8)
                center_spire = 1.25 if dist <= 1 else 0.0
                wave = 0.22 * math.cos(wx * 0.7) * math.sin(wz * 0.7)
                h = 0.12 + ring_peak + center_spire + wave
            heights[(q, r, s)] = round(h, 3)
    return heights


class _Hex3DEngine:
    """Deterministic cube-grid 3D snake with instant pivot, mosaic tiles & green spotted snake."""

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self.rng = rng or random.Random()
        self.best_score = get_high_score("hex")
        self.reset(show_intro=True)

    def reset(self, show_intro: bool = False) -> None:
        self.best_score = max(getattr(self, "best_score", 0), get_high_score("hex"))
        self.stage_idx = 0
        self.score = 0
        self.total_orbs = 0
        self.phase = "intro" if show_intro else "playing"  # intro | playing | paused | gameover | victory
        self.new_record = False
        self.left_fault_ticks = 0
        self.right_flash_ticks = 0
        self.elapsed = 0.0
        self.step_accum = 0.0
        self.status_line = (
            "Left D-Pad broken! Tap D / -> or Space to start."
            if show_intro
            else "Tap D / -> to spin aim right (+60 deg) toward star!"
        )
        self._load_stage(0)

    def _load_stage(self, idx: int) -> None:
        self.stage_idx = idx
        spec = STAGES[idx]
        self.radius = int(spec["radius"])
        self.stage_goal = int(spec["goal"])
        self.step_interval = float(spec["step_sec"])
        palette_shift = int(spec["palette_shift"])
        self.stage_orbs = 0
        self.heights = _build_stage_heights(idx, self.radius)
        self.valid_cells = set(self.heights.keys())

        corner_angles = [math.radians(60 * i + 30) for i in range(6)]
        r_outer = 0.87
        r_inner = 0.73
        floor_y = -0.65

        # (cell, h, outer_verts, inner_verts, fill_rgb, rim_rgb)
        self._mesh_tiles: list[tuple[CubeCoord, float, list[tuple[float, float, float]], list[tuple[float, float, float]], RGB, RGB]] = []
        self._mesh_cliffs: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], tuple[float, float, float], float, float, RGB]] = []

        cell_centers = {c: _cube_to_world_xz(c) for c in self.valid_cells}
        for cell, h in self.heights.items():
            wx, wz = cell_centers[cell]
            q, r, _ = cell
            # Proper mosaic coloring: neighbors never share the same base jewel color
            color_idx = (q * 2 + r * 3 + palette_shift) % len(MOSAIC_TILES)
            fill_base, rim_base, cliff_base = MOSAIC_TILES[color_idx]

            outer_verts = [(wx + r_outer * math.cos(a), h, wz + r_outer * math.sin(a)) for a in corner_angles]
            inner_verts = [(wx + r_inner * math.cos(a), h + 0.015, wz + r_inner * math.sin(a)) for a in corner_angles]
            elev_mul = max(0.80, min(1.30, 0.86 + h * 0.30))
            tile_col = _scale_rgb(fill_base, elev_mul)
            rim_col = _scale_rgb(rim_base, min(1.15, elev_mul))
            self._mesh_tiles.append((cell, h, outer_verts, inner_verts, tile_col, rim_col))

            for i in range(6):
                a_pt = outer_verts[i]
                b_pt = outer_verts[(i + 1) % 6]
                mx = (a_pt[0] + b_pt[0]) * 0.5 - wx
                mz = (a_pt[2] + b_pt[2]) * 0.5 - wz
                n_len = math.hypot(mx, mz) or 1.0
                nx, nz = mx / n_len, mz / n_len
                px_out = wx + nx * 1.73
                pz_out = wz + nz * 1.73
                drop_y = floor_y
                is_exterior = True
                for nc, (nwx, nwz) in cell_centers.items():
                    if nc != cell and (nwx - px_out) ** 2 + (nwz - pz_out) ** 2 < 0.6:
                        is_exterior = False
                        drop_y = self.heights[nc] if h > self.heights[nc] + 0.14 else h
                        break
                if is_exterior or drop_y < h - 0.12:
                    bot_a = (a_pt[0], drop_y, a_pt[2])
                    bot_b = (b_pt[0], drop_y, b_pt[2])
                    self._mesh_cliffs.append((a_pt, b_pt, bot_b, bot_a, nx, nz, _scale_rgb(cliff_base, 0.82 + (i % 2) * 0.22)))

        start_body: list[CubeCoord] = [(0, 0, 0), (-1, 0, 1), (-1, 1, 0), (0, 1, -1)]
        self.snake: deque[CubeCoord] = deque(start_body)
        self.prev_snake: list[CubeCoord] = list(start_body)
        self.dir_idx = 0
        self.step_accum = 0.0

        hx, hz = _cube_to_world_xz(self.snake[0])
        self.cam_yaw = 0.0
        self.cam_target_x = hx
        self.cam_target_y = self.heights[self.snake[0]]
        self.cam_target_z = hz
        self.orb: CubeCoord = (2, 0, -2)
        self._spawn_orb()

    def _neck_dir(self) -> Optional[int]:
        if len(self.snake) < 2:
            return None
        hq, hr, hs = self.snake[0]
        nq, nr, ns = self.snake[1]
        diff = (nq - hq, nr - hr, ns - hs)
        for i, d in enumerate(HEX_DIRS):
            if d == diff:
                return i
        return None

    def _next_cell(self, d_idx: Optional[int] = None) -> CubeCoord:
        idx = self.dir_idx if d_idx is None else d_idx
        hq, hr, hs = self.snake[0]
        dq, dr, ds = HEX_DIRS[idx]
        return (hq + dq, hr + dr, hs + ds)

    def _spawn_orb(self) -> None:
        snake_set = set(self.snake)
        head = self.snake[0]
        candidates = [c for c in self.valid_cells if c not in snake_set and _cube_dist(c, head) >= 2]
        if not candidates:
            candidates = [c for c in self.valid_cells if c not in snake_set]
        if candidates:
            self.orb = self.rng.choice(sorted(candidates))

    def start_if_intro(self) -> None:
        if self.phase == "intro":
            self.phase = "playing"
            self.status_line = "Right-Only Active! Tap D / -> to pivot right."

    def input_turn_right(self) -> str:
        """Instant clockwise +60 deg heading pivot (skipping backward neck direction)."""
        if self.phase == "intro":
            self.start_if_intro()
            self.right_flash_ticks = 6
            return "start"
        if self.phase != "playing":
            return "ignored"

        neck = self._neck_dir()
        cand = (self.dir_idx + 1) % 6
        if neck is not None and cand == neck:
            cand = (cand + 1) % 6
        self.dir_idx = cand
        self.right_flash_ticks = 6
        return "turn_right"

    def input_turn_left_fault(self) -> str:
        self.left_fault_ticks = 14
        self.status_line = "LEFT KEY BROKEN! Tap D / -> clockwise (4x = Left)."
        return "fault_left"

    def _finish_run(self, won: bool, reason: str) -> str:
        self.phase = "victory" if won else "gameover"
        if won:
            self.score += 150
        self.best_score, self.new_record = record_high_score("hex", self.score)
        star = " * NEW RECORD!" if self.new_record else ""
        self.status_line = f"{reason} Score: {self.score}{star}"
        return self.phase

    def _logic_step(self) -> Optional[str]:
        self.prev_snake = list(self.snake)
        nxt = self._next_cell()
        event: Optional[str] = None

        if nxt not in self.valid_cells:
            hq, hr, hs = self.snake[0]
            neck = self._neck_dir()
            for offset in (1, 2, 3, 4, 5):
                slide_dir = (self.dir_idx + offset) % 6
                if neck is not None and slide_dir == neck:
                    continue
                sdq, sdr, sds = HEX_DIRS[slide_dir]
                slide_nxt = (hq + sdq, hr + sdr, hs + sds)
                if slide_nxt in self.valid_cells:
                    self.dir_idx = slide_dir
                    nxt = slide_nxt
                    break
            self.score = max(0, self.score - 5)
            self.status_line = "Rim slide (-5 pts) — pivot right earlier!"
            event = "rim"

        ate_orb = nxt == self.orb
        body_check = set(self.snake) if ate_orb else set(list(self.snake)[:-1])
        if nxt in body_check:
            return self._finish_run(False, "CRASHED INTO TAIL!")

        self.snake.appendleft(nxt)
        if not ate_orb:
            self.snake.pop()
        else:
            self.prev_snake.append(self.prev_snake[-1])
            self.total_orbs += 1
            self.stage_orbs += 1
            self.score += 25
            if self.score > self.best_score:
                self.best_score = self.score

            if self.stage_orbs >= self.stage_goal:
                if self.stage_idx + 1 < len(STAGES):
                    nxt_stage = self.stage_idx + 1
                    st_name = str(STAGES[nxt_stage]["name"])
                    self.score += 60
                    self._load_stage(nxt_stage)
                    self.status_line = f"SECTOR CLEAR! Welcome to {st_name} (+60)"
                    return "stage"
                return self._finish_run(True, "BROKEN-LEFT VICTORY!")

            self._spawn_orb()
            self.status_line = f"Beacon +25 ({self.stage_orbs}/{self.stage_goal}) · Tap D / ->"
            event = "orb"

        return event

    def advance_frame(self, dt: float) -> Optional[str]:
        self.elapsed += dt
        if self.left_fault_ticks > 0:
            self.left_fault_ticks -= 1
        if self.right_flash_ticks > 0:
            self.right_flash_ticks -= 1

        event: Optional[str] = None
        if self.phase == "intro":
            self.cam_yaw = (self.cam_yaw + dt * 0.48) % (2.0 * math.pi)
        elif self.phase == "playing":
            self.step_accum += dt
            while self.step_accum >= self.step_interval:
                self.step_accum -= self.step_interval
                step_ev = self._logic_step()
                if step_ev is not None:
                    event = step_ev
                if self.phase != "playing":
                    break

            target_yaw = self.dir_idx * (math.pi / 3.0)
            yaw_diff = (target_yaw - self.cam_yaw + math.pi) % (2.0 * math.pi) - math.pi
            self.cam_yaw = (self.cam_yaw + yaw_diff * min(1.0, dt * 6.5)) % (2.0 * math.pi)

            t = min(1.0, self.step_accum / max(0.01, self.step_interval))
            hx1, hz1 = _cube_to_world_xz(self.snake[0])
            hy1 = self.heights[self.snake[0]]
            hx0, hz0 = _cube_to_world_xz(self.prev_snake[0])
            hy0 = self.heights[self.prev_snake[0]]
            tx = hx0 + (hx1 - hx0) * t
            ty = hy0 + (hy1 - hy0) * t
            tz = hz0 + (hz1 - hz0) * t
            self.cam_target_x += (tx - self.cam_target_x) * min(1.0, dt * 10.0)
            self.cam_target_y += (ty - self.cam_target_y) * min(1.0, dt * 8.0)
            self.cam_target_z += (tz - self.cam_target_z) * min(1.0, dt * 10.0)
        elif self.phase == "victory":
            self.cam_yaw = (self.cam_yaw + dt * 0.65) % (2.0 * math.pi)

        return event

    def render_frame(self, width: int = DEFAULT_PIX_W, height: int = DEFAULT_PIX_H) -> Text:
        """Render fine-grained multicolored 3D hex mosaic with a little green spotted snake."""
        n_pix = width * height
        zbuf = [1e9] * n_pix
        pbuf: list[RGB] = [VOID_RGB] * n_pix

        fwd_x = math.cos(self.cam_yaw)
        fwd_z = math.sin(self.cam_yaw)
        right_x = -fwd_z
        right_z = fwd_x

        pitch = 0.60  # Crisp ~34 deg fine-scale panoramic vantage
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)

        if self.phase == "intro":
            cam_dist = 9.4
            cam_x = -fwd_x * cam_dist
            cam_y = cam_dist * math.tan(pitch) * 0.96
            cam_z = -fwd_z * cam_dist
        else:
            cam_dist = 7.7
            la_x = self.cam_target_x + fwd_x * 1.10
            la_y = self.cam_target_y + 0.12
            la_z = self.cam_target_z + fwd_z * 1.10
            cam_x = la_x - fwd_x * cam_dist
            cam_y = la_y + cam_dist * math.tan(pitch) * 0.96
            cam_z = la_z - fwd_z * cam_dist

        fov = width * 0.64  # Fine-grained proportional tiles inside compact card
        cx = width * 0.5
        cy = height * 0.52

        def project(wx: float, wy: float, wz: float) -> Optional[tuple[float, float, float]]:
            vx = wx - cam_x
            vy = wy - cam_y
            vz = wz - cam_z
            cx_local = vx * right_x + vz * right_z
            horz_fwd = vx * fwd_x + vz * fwd_z
            cy_local = vy * cos_p + horz_fwd * sin_p
            cz_local = -vy * sin_p + horz_fwd * cos_p
            if cz_local < 1.35:
                return None
            inv_z = fov / cz_local
            return cx + cx_local * inv_z, cy - cy_local * inv_z, cz_local

        def raster_tri(
            p0: tuple[float, float, float],
            p1: tuple[float, float, float],
            p2: tuple[float, float, float],
            base_rgb: RGB,
            z_bias: float = 0.0,
        ) -> None:
            x0, y0, z0 = p0
            x1, y1, z1 = p1
            x2, y2, z2 = p2
            area = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
            if abs(area) < 0.05:
                return
            min_x = max(0, int(min(x0, x1, x2)))
            max_x = min(width - 1, int(max(x0, x1, x2)))
            min_y = max(0, int(min(y0, y1, y2)))
            max_y = min(height - 1, int(max(y0, y1, y2)))
            if min_x > max_x or min_y > max_y:
                return

            inv_abs = 1.0 / abs(area)
            sign = 1.0 if area > 0.0 else -1.0
            for py in range(min_y, max_y + 1):
                py_c = py + 0.5
                row_off = py * width
                for px in range(min_x, max_x + 1):
                    px_c = px + 0.5
                    w0 = ((x1 - px_c) * (y2 - py_c) - (y1 - py_c) * (x2 - px_c)) * sign
                    if w0 < -0.04:
                        continue
                    w1 = ((x2 - px_c) * (y0 - py_c) - (y2 - py_c) * (x0 - px_c)) * sign
                    if w1 < -0.04:
                        continue
                    w2 = ((x0 - px_c) * (y1 - py_c) - (y0 - py_c) * (x1 - px_c)) * sign
                    if w2 < -0.04:
                        continue
                    depth = (w0 * z0 + w1 * z1 + w2 * z2) * inv_abs + z_bias
                    idx = row_off + px
                    if depth < zbuf[idx]:
                        zbuf[idx] = depth
                        fog = max(0.0, min(0.54, (depth - 5.6) / 17.5))
                        pbuf[idx] = _mix_rgb(base_rgb, VOID_RGB, fog)

        head_cell = self.snake[0]
        aim_cell = self._next_cell()
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 6.0)

        # 1. Cliffs (back-face culled)
        for pa_t, pb_t, pb_b, pa_b, nx, nz, c_col in self._mesh_cliffs:
            if (pa_t[0] - cam_x) * nx + (pa_t[2] - cam_z) * nz >= 0.12:
                continue
            p0 = project(*pa_t)
            p1 = project(*pb_t)
            p2 = project(*pb_b)
            p3 = project(*pa_b)
            if p0 and p1 and p2 and p3:
                raster_tri(p0, p1, p2, c_col, z_bias=0.05)
                raster_tri(p0, p2, p3, c_col, z_bias=0.05)

        # 2. Multicolored 3D Honeycomb Plateaus
        for cell, h, outer_verts, inner_verts, tile_col, rim_col in self._mesh_tiles:
            p_out = [project(*v) for v in outer_verts]
            p_in = [project(*v) for v in inner_verts]
            if not (all(pt is not None for pt in p_out) and all(pt is not None for pt in p_in)):
                continue
            po = [pt for pt in p_out if pt is not None]
            pi = [pt for pt in p_in if pt is not None]

            if cell == self.orb:
                bezel_rgb = (255, 245, 130)
                plate_rgb = _mix_rgb(tile_col, (255, 225, 80), 0.35 + 0.35 * pulse)
            elif cell == aim_cell and self.phase == "playing":
                bezel_rgb = (240, 253, 244)
                plate_rgb = _scale_rgb(tile_col, 1.25)
            elif cell == head_cell:
                bezel_rgb = (220, 255, 230)
                plate_rgb = _scale_rgb(tile_col, 1.18)
            else:
                bezel_rgb = rim_col
                plate_rgb = tile_col

            for ti in range(1, 5):
                raster_tri(po[0], po[ti], po[ti + 1], bezel_rgb, z_bias=0.02)
                raster_tri(pi[0], pi[ti], pi[ti + 1], plate_rgb, z_bias=0.0)

        def stamp_disk(
            wx: float,
            wy: float,
            wz: float,
            radius_world: float,
            core_rgb: RGB,
            spot_rgb: RGB,
            z_bias: float = -0.34,
            flat_shadow: bool = False,
            spot_center: bool = False,
        ) -> None:
            proj = project(wx, wy, wz)
            if proj is None:
                return
            sx, sy, cz = proj
            r_px = max(0.95, radius_world * (fov / cz))
            ry_px = r_px * (0.55 if flat_shadow else 1.0)
            r2 = r_px * r_px
            x0 = max(0, int(sx - r_px))
            x1 = min(width - 1, int(sx + r_px))
            y0 = max(0, int(sy - ry_px))
            y1 = min(height - 1, int(sy + ry_px))
            depth = cz + z_bias
            fog = 0.0 if flat_shadow else max(0.0, min(0.35, (depth - 5.2) / 20.0))
            c_main = core_rgb if flat_shadow else _mix_rgb(core_rgb, VOID_RGB, fog)
            c_spot = spot_rgb if flat_shadow else _mix_rgb(spot_rgb, VOID_RGB, fog * 0.6)
            ry_ratio = (r_px / ry_px) ** 2 if flat_shadow else 1.0
            for py in range(y0, y1 + 1):
                dy = (py + 0.5) - sy
                dy2 = dy * dy * ry_ratio
                row_off = py * width
                for px in range(x0, x1 + 1):
                    dx = (px + 0.5) - sx
                    d2 = dx * dx + dy2
                    if d2 <= r2 and depth < zbuf[row_off + px]:
                        idx = row_off + px
                        zbuf[idx] = depth
                        if flat_shadow:
                            pbuf[idx] = c_main
                        elif spot_center:
                            pbuf[idx] = c_spot if d2 <= r2 * 0.34 else c_main
                        else:
                            pbuf[idx] = c_spot if (dx < -r_px * 0.14 and dy < -r_px * 0.14) or d2 < r2 * 0.22 else c_main

        # 3. Delicate Crisp Beacon Crystal + Subtle Sky Beam
        ox, oz = _cube_to_world_xz(self.orb)
        oh = self.heights[self.orb]
        oy = oh + 0.44 + 0.14 * math.sin(self.elapsed * 5.0)
        stamp_disk(ox, oh + 0.03, oz, 0.28, (6, 8, 16), (6, 8, 16), z_bias=-0.05, flat_shadow=True)
        for step_h in (0.85, 1.18, 1.50):
            stamp_disk(ox, oh + step_h, oz, 0.08, (254, 240, 138), (255, 255, 240), z_bias=-0.22)
        stamp_disk(ox, oy, oz, 0.28, (250, 204, 21), (255, 255, 235), z_bias=-0.38)

        # 4. Little Green Spotted Snake (`pykuai`) gliding across multicolored tiles
        t = min(1.0, self.step_accum / max(0.01, self.step_interval)) if self.phase == "playing" else 1.0
        seg_pos: list[tuple[float, float, float, float]] = []
        seg_count = len(self.snake)
        for idx in range(seg_count):
            c1 = self.snake[idx]
            c0 = self.prev_snake[idx] if idx < len(self.prev_snake) else c1
            x0, z0 = _cube_to_world_xz(c0)
            y0 = self.heights.get(c0, 0.2)
            x1, z1 = _cube_to_world_xz(c1)
            y1 = self.heights.get(c1, 0.2)
            wx = x0 + (x1 - x0) * t
            wz = z0 + (z1 - z0) * t
            ground_y = y0 + (y1 - y0) * t
            seg_pos.append((wx, ground_y + 0.34, wz, ground_y))

        for idx in range(seg_count - 1, -1, -1):
            wx, wy, wz, gy = seg_pos[idx]
            ratio = idx / max(1, seg_count - 1)
            stamp_disk(wx, gy + 0.03, wz, 0.28, (4, 6, 12), (4, 6, 12), z_bias=-0.06, flat_shadow=True)

            if self.phase == "gameover":
                body_rgb = (239, 68, 68) if idx == 0 else (153, 27, 27)
                spot_rgb = (254, 202, 202)
                rad = 0.34 if idx == 0 else 0.26
            elif idx == 0:
                # Bright emerald head with crisp lighter crown
                body_rgb = (22, 196, 86) if self.right_flash_ticks == 0 else (74, 222, 128)
                spot_rgb = (187, 247, 208)
                rad = 0.35
            else:
                # Green body with alternating bright lime-gold and dark-forest dorsal spots!
                base_g = int(205 - 45 * ratio)
                body_rgb = (16, base_g, 64)
                spot_rgb = (217, 249, 157) if idx % 2 == 1 else (6, 78, 42)
                rad = 0.30 - 0.07 * ratio

            if idx < seg_count - 1:
                nx_w, ny_w, nz_w, _ = seg_pos[idx + 1]
                # Connecting bridge in matching green
                stamp_disk(
                    (wx + nx_w) * 0.5,
                    (wy + ny_w) * 0.5,
                    (wz + nz_w) * 0.5,
                    max(0.18, rad * 0.82),
                    (16, 175, 58) if self.phase != "gameover" else (153, 27, 27),
                    (74, 222, 128),
                    z_bias=-0.28,
                )

            stamp_disk(
                wx,
                wy,
                wz,
                rad,
                body_rgb,
                spot_rgb,
                z_bias=-0.36,
                spot_center=(idx > 0 and self.phase != "gameover"),
            )

        # Tiny twin dark eyes on green snake head facing `dir_idx`
        hx_w, hy_w, hz_w, _ = seg_pos[0]
        head_ang = self.dir_idx * (math.pi / 3.0)
        fx, fz = math.cos(head_ang), math.sin(head_ang)
        rx, rz = -fz, fx
        eye_rgb = (10, 35, 18) if self.right_flash_ticks == 0 else (255, 255, 255)
        for side in (-0.15, 0.15):
            stamp_disk(
                hx_w + fx * 0.24 + rx * side,
                hy_w + 0.10,
                hz_w + fz * 0.24 + rz * side,
                0.08,
                eye_rgb,
                eye_rgb,
                z_bias=-0.46,
            )

        # 5. Pack Half-Block Frame
        out = Text()
        rows_out = height // 2
        for pair_idx in range(rows_out):
            top_off = (pair_idx * 2) * width
            bot_off = top_off + width
            run_chars: list[str] = []
            run_style: Optional[str] = None

            def flush_run() -> None:
                if run_chars:
                    out.append("".join(run_chars), style=run_style or "")
                    run_chars.clear()

            for x in range(width):
                trgb = pbuf[top_off + x]
                brgb = pbuf[bot_off + x]
                if trgb == VOID_RGB and brgb == VOID_RGB:
                    ch, style = " ", f"on {VOID_HEX}"
                elif trgb == brgb:
                    tc = _rgb_to_hex(trgb)
                    ch, style = "█", f"{tc} on {VOID_HEX}"
                elif brgb == VOID_RGB:
                    tc = _rgb_to_hex(trgb)
                    ch, style = "▀", f"{tc} on {VOID_HEX}"
                elif trgb == VOID_RGB:
                    bc = _rgb_to_hex(brgb)
                    ch, style = "▄", f"{bc} on {VOID_HEX}"
                else:
                    tc = _rgb_to_hex(trgb)
                    bc = _rgb_to_hex(brgb)
                    ch, style = "▀", f"{tc} on {bc}"

                if style != run_style:
                    flush_run()
                    run_style = style
                run_chars.append(ch)
            flush_run()
            if pair_idx + 1 < rows_out:
                out.append("\n")

        return out


def _build_hex3d_app():
    """Build compact, centered 78x24 studio card matching PyKuai's core tools (`ifc`/`ytd`)."""
    from textual import events
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Center, Horizontal, Vertical
    from textual.widgets import Button, Static

    from pykuai.core.tui import (
        ActionChip,
        CYBER_TUI_CSS,
        HelpModalScreen,
        PyKuaiStudioApp,
        SfxToggleChip,
        StudioHeader,
    )

    hex_css = CYBER_TUI_CSS + """
    #studio-card {
        width: 78;
        max-width: 96%;
        height: 24;
        max-height: 96%;
        padding: 0 2;
    }

    #hex-hud {
        width: 100%;
        height: 1;
        text-align: center;
        color: #9ae6b4;
    }

    #viewport-wrap {
        width: 100%;
        height: auto;
        align: center middle;
    }

    #hex-viewport {
        border: round #22d3ee;
        background: #070910;
        padding: 0;
        content-align: center middle;
    }

    #hex-viewport.-fault {
        border: round #FF5252;
    }

    #hex-viewport.-victory {
        border: round #FACC15;
    }

    #status-line {
        width: 100%;
        height: 1;
        text-align: center;
        color: #E0E0E0;
    }
    """

    class Hex3DApp(PyKuaiStudioApp):
        CSS = hex_css
        HELP_TITLE = "PyKuai: Hex 3D · Story & Controls"
        HELP_TEXT = HEX3D_HELP
        BINDINGS = [
            *PyKuaiStudioApp.BINDINGS,
            Binding("question_mark", "show_help", "Help", show=False),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.engine = _Hex3DEngine()
            self._timer = None
            self.pix_w = DEFAULT_PIX_W
            self.pix_h = DEFAULT_PIX_H

        def _recompute_viewport(self) -> None:
            tw = max(46, self.size.width)
            th = max(20, self.size.height)
            card = self.query_one("#studio-card", Vertical)
            card_w = min(78, int(tw * 0.96))
            card_h = min(24, int(th * 0.96))
            card.styles.width = card_w
            card.styles.height = card_h

            # Fit cleanly centered inside card chrome (6 cols H, 9 rows V)
            view_cols = max(36, min(DEFAULT_PIX_W, card_w - 10))
            if view_cols % 2 == 1:
                view_cols -= 1
            view_rows = max(9, min(DEFAULT_PIX_H // 2, card_h - 11))
            self.pix_w = view_cols
            self.pix_h = view_rows * 2

            vp = self.query_one("#hex-viewport", Static)
            vp.styles.width = view_cols + 2
            vp.styles.height = view_rows + 2

        def compose(self) -> ComposeResult:
            with Vertical(id="studio-card"):
                yield StudioHeader("🐍 PyKuai: Hex 3D")
                yield Static("", id="hex-hud")
                with Center(id="viewport-wrap"):
                    yield Static("", id="hex-viewport")
                yield Static("", id="status-line")

                with Horizontal(classes="action-bar"):
                    yield ActionChip("↻ Restart", variant_class="-preset", id="btn-restart")
                    yield ActionChip("▶ Start", variant_class="-file", id="btn-pause")
                    yield ActionChip("✕ Back", variant_class="-danger", id="btn-back")
                    yield Static("", classes="action-spacer")
                    yield SfxToggleChip(id="btn-sfx")

        def on_mount(self) -> None:
            play_sfx("snake")
            self._recompute_viewport()
            self._sync_view()
            self._timer = self.set_interval(1.0 / 36.0, self._on_tick)

        def on_resize(self, event: events.Resize) -> None:
            self._recompute_viewport()
            self._sync_view()

        def _sync_view(self) -> None:
            e = self.engine
            stage_name = str(STAGES[e.stage_idx]["name"])
            hud = (
                f"[bold #00FF00]SCORE[/] {e.score:<4} "
                f"[bold #FF9800]BEST[/] {e.best_score:<4} "
                f"[bold #22d3ee]{stage_name}[/] ({e.stage_orbs}/{e.stage_goal}) "
                f"[bold #f472b6]RIGHT-ONLY[/]"
            )
            self.query_one("#hex-hud", Static).update(hud)

            vp = self.query_one("#hex-viewport", Static)
            vp.update(e.render_frame(self.pix_w, self.pix_h))
            vp.set_class(e.left_fault_ticks > 0 or e.phase == "gameover", "-fault")
            vp.set_class(e.phase == "victory", "-victory")

            st_w = self.query_one("#status-line", Static)
            line = e.status_line
            if len(line) > self.pix_w + 6:
                line = line[: self.pix_w + 5] + "…"
            if e.left_fault_ticks > 0 or e.phase == "gameover":
                st_w.update(f"[bold #FF5252]{line}[/bold #FF5252]")
            elif e.phase == "victory":
                st_w.update(f"[bold #FACC15]{line}[/bold #FACC15]")
            else:
                st_w.update(f"[#cbd5e1]{line}[/#cbd5e1]")

            pause_btn = self.query_one("#btn-pause", ActionChip)
            if e.phase == "intro":
                pause_btn.label = "▶ Start"
            elif e.phase == "paused":
                pause_btn.label = "▶ Resume"
            else:
                pause_btn.label = "⏸ Pause"

        def _on_tick(self) -> None:
            if isinstance(self.screen, HelpModalScreen):
                return
            ev = self.engine.advance_frame(1.0 / 36.0)
            if ev == "orb":
                play_sfx("key")
            elif ev == "stage":
                play_sfx("enter")
            elif ev == "rim":
                play_sfx("paste")
            elif ev in ("gameover", "victory"):
                play_sfx("snake" if ev == "victory" else "paste")
            self._sync_view()

        def _toggle_pause(self) -> None:
            if self.engine.phase == "intro":
                play_sfx("enter")
                self.engine.start_if_intro()
            elif self.engine.phase == "playing":
                play_sfx("click")
                self.engine.phase = "paused"
                self.engine.status_line = "PAUSED (Press Space / P to resume)"
            elif self.engine.phase == "paused":
                play_sfx("click")
                self.engine.phase = "playing"
                self.engine.status_line = "Tap D / -> to pivot right toward star!"
            self._sync_view()

        def _restart(self) -> None:
            record_high_score("hex", self.engine.score)
            play_sfx("snake")
            self.engine.reset(show_intro=False)
            self._sync_view()

        def _exit_game(self) -> None:
            record_high_score("hex", self.engine.score)
            play_sfx("click")
            self.exit(0)

        def action_cancel(self) -> None:
            self._exit_game()

        def on_key(self, event: events.Key) -> None:
            if isinstance(self.screen, HelpModalScreen):
                return
            k = event.key.lower()
            if k in ("right", "d"):
                event.stop()
                fb = self.engine.input_turn_right()
                play_sfx("enter" if fb == "start" else "click")
                self._sync_view()
            elif k in ("left", "a"):
                event.stop()
                self.engine.input_turn_left_fault()
                play_sfx("paste")
                self._sync_view()
            elif k in ("space", "p"):
                event.stop()
                self._toggle_pause()
            elif k == "r":
                event.stop()
                self._restart()
            elif k in ("q", "escape"):
                event.stop()
                self._exit_game()
            elif event.character == "?":
                event.stop()
                self.action_show_help()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            btn = event.button
            if isinstance(btn, SfxToggleChip):
                return
            if btn.id == "btn-restart":
                self._restart()
            elif btn.id == "btn-pause":
                self._toggle_pause()
            elif btn.id == "btn-back":
                self._exit_game()

    return Hex3DApp()


class PyKuaiHex3DGame(ArcadeGame):
    """Registered `ArcadeGame` entry for PyKuai: Hex 3D."""

    code = "hex"
    title = "PyKuai: Hex 3D"
    tagline = "Multicolored 3D Hex & Spotted Snake"
    order = 10
    help_text = HEX3D_HELP

    def run(self, console: Console) -> int:
        from pykuai.core.tui import is_interactive_tty

        if not is_interactive_tty():
            print_error("PyKuai: Hex 3D requires an interactive terminal (TTY).")
            return 1

        result = _build_hex3d_app().run(mouse=True)
        return 0 if result is None else int(result)
