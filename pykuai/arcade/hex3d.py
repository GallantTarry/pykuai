# -*- coding: utf-8 -*-
"""
Hex 3D (`hex`)
Compact Multicolored 3D Honeycomb Snake — Broken-Left Edition.

Backstory:
  When TuKuai was young, his older brother gave him a Nokia phone whose center square D-pad
  had a broken LEFT switch — it could only click RIGHT. TuKuai beat the entire game anyway.
"""
from __future__ import annotations

from collections import deque
import math
import random
import time
from typing import Optional

from rich.console import Console
from rich.text import Text

from pykuai.arcade import ArcadeGame, get_high_score, record_high_score
from pykuai.core.audio import play_sfx
from pykuai.core.ui import print_error

CubeCoord = tuple[int, int, int]
RGB = tuple[int, int, int]

DEFAULT_PIX_W = 140  # 70 terminal cols x 2 quadrant sub-pixels
DEFAULT_PIX_H = 32   # 16 terminal rows x 2 quadrant sub-pixels inside exact 78x24 card
VOID_RGB: RGB = (7, 9, 16)
VOID_INT: int = (7 << 16) | (9 << 8) | 16
VOID_HEX = "#070910"

# 4-bit (TL=8, TR=4, BL=2, BR=1) lookup into BMP Block Elements / Quadrants
QUAD_CHARS: tuple[str, ...] = (
    " ", "▗", "▖", "▄",
    "▝", "▐", "▞", "▟",
    "▘", "▚", "▌", "▙",
    "▀", "▜", "▛", "█",
)

# Clockwise cube directions matching (+wx, +wz) right-handed top-down orientation
HEX_DIRS: tuple[CubeCoord, ...] = (
    (1, 0, -1),
    (0, 1, -1),
    (-1, 1, 0),
    (-1, 0, 1),
    (0, -1, 1),
    (1, -1, 0),
)

# Multicolored 6-hue jewel mosaic palette (no green so the green spotted snake pops clearly)
MOSAIC_TILES: tuple[tuple[RGB, RGB, RGB], ...] = (
    ((18, 114, 146), (72, 232, 255), (12, 70, 96)),    # Electric Cyan
    ((66, 58, 194), (146, 158, 255), (38, 34, 126)),   # Royal Indigo
    ((132, 42, 206), (214, 154, 255), (76, 26, 128)),  # Amethyst Violet
    ((188, 34, 102), (255, 134, 198), (112, 20, 64)),  # Neon Rose
    ((184, 92, 20), (255, 204, 68), (108, 52, 14)),    # Amber Gold
    ((32, 88, 214), (112, 182, 255), (18, 54, 136)),   # Cobalt Blue
)

STAGES: tuple[dict[str, object], ...] = (
    {"name": "SECTOR 1", "radius": 4, "goal": 6, "step_sec": 0.34, "palette_shift": 0},
    {"name": "SECTOR 2", "radius": 4, "goal": 8, "step_sec": 0.30, "palette_shift": 2},
    {"name": "SECTOR 3", "radius": 5, "goal": 10, "step_sec": 0.27, "palette_shift": 4},
)

HEX3D_HELP = """\
[bold #22d3ee]Hex 3D (hex) · Broken-Left Legend[/]
  [italic #a5f3fc]When TuKuai was young, his older brother gave him a Nokia phone.[/]
  [italic #a5f3fc]Its square center D-pad was broken on the LEFT — it could only click RIGHT.[/]
  [italic #a5f3fc]Spinning right on the spot, TuKuai conquered the entire 3D hex arena anyway.[/]

[bold #22d3ee]Steering & Controls[/]
  • [bold #00FF00]→ / D (Tap 1–4x)[/] Snap aim reticle clockwise (+60 deg) immediately.
    Tap 1x = +60 deg Right | Tap 2x = +120 deg | Tap 4x = Left (-60 deg).
    Rapid multi-taps hold a brief turn grace window so combos complete cleanly.
  • [bold #e5e7eb]↑ / W[/]         Quick-step forward 1 tile immediately.
  • [bold #FF5252]← / A Locked[/]    Left D-pad is broken and triggers a hardware fault warning.
  • [bold #e5e7eb]Space / P[/]     Start or Pause
  • [bold #e5e7eb]R[/]             Restart
  • [bold #e5e7eb]Esc / Q[/]       Save & Exit"""


_HEX_STR_CACHE: dict[int, str] = {}
_STAR_OFFSETS: tuple[tuple[int, int, RGB], ...] = (
    (12, 2, (28, 38, 64)),
    (38, 1, (38, 52, 84)),
    (68, 3, (26, 36, 60)),
    (102, 2, (42, 56, 88)),
    (126, 4, (32, 42, 70)),
    (24, 6, (28, 38, 62)),
    (116, 7, (34, 46, 76)),
)


def _pack_rgb(rgb: RGB) -> int:
    return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


def _int_to_hex(key: int) -> str:
    cached = _HEX_STR_CACHE.get(key)
    if cached is None:
        cached = f"#{key:06x}"
        if len(_HEX_STR_CACHE) < 16384:
            _HEX_STR_CACHE[key] = cached
    return cached


def _mix_int(c_a: int, c_b: int, t: float) -> int:
    if t <= 0.0:
        return c_a
    if t >= 1.0:
        return c_b
    inv = 1.0 - t
    r = int(((c_a >> 16) & 255) * inv + ((c_b >> 16) & 255) * t)
    g = int(((c_a >> 8) & 255) * inv + ((c_b >> 8) & 255) * t)
    b = int((c_a & 255) * inv + (c_b & 255) * t)
    return (r << 16) | (g << 8) | b


def _solve_quad_cell(c0: int, c1: int, c2: int, c3: int) -> tuple[str, int, int]:
    """
    Pack a 2x2 sub-pixel block (TL=c0, TR=c1, BL=c2, BR=c3) into (glyph, fg_int, bg_int).
    Uses exact lookup for <=2 colors and farthest-pair 2-means clustering for 3-4 colors.
    """
    if c0 == c1 == c2 == c3:
        if c0 == VOID_INT:
            return " ", VOID_INT, VOID_INT
        return "█", c0, VOID_INT

    if c0 == c1 and c2 == c3:
        if c0 == VOID_INT:
            return "▄", c2, VOID_INT
        return "▀", c0, c2

    if c0 == c2 and c1 == c3:
        if c0 == VOID_INT:
            return "▐", c1, VOID_INT
        return "▌", c0, c1

    # Check if at most 2 distinct colors exist (exact zero-error quadrant mask)
    b_col = -1
    if c1 != c0:
        b_col = c1
    elif c2 != c0:
        b_col = c2
    elif c3 != c0:
        b_col = c3

    if (c1 == c0 or c1 == b_col) and (c2 == c0 or c2 == b_col) and (c3 == c0 or c3 == b_col):
        if c0 == VOID_INT:
            fg, bg = b_col, c0
        else:
            fg, bg = c0, b_col
        mask = (8 if c0 == fg else 0) | (4 if c1 == fg else 0) | (2 if c2 == fg else 0) | (1 if c3 == fg else 0)
        return QUAD_CHARS[mask], fg, bg

    # 3-4 distinct colors (SSAA anti-aliased edge): 2-means split by farthest RGB pair
    r0, g0, b0 = (c0 >> 16) & 255, (c0 >> 8) & 255, c0 & 255
    r1, g1, b1 = (c1 >> 16) & 255, (c1 >> 8) & 255, c1 & 255
    r2, g2, b2 = (c2 >> 16) & 255, (c2 >> 8) & 255, c2 & 255
    r3, g3, b3 = (c3 >> 16) & 255, (c3 >> 8) & 255, c3 & 255

    cols = ((r0, g0, b0), (r1, g1, b1), (r2, g2, b2), (r3, g3, b3))
    best_d = -1
    pa_r = pa_g = pa_b = 0
    pb_r = pb_g = pb_b = 0
    for i in range(3):
        ri, gi, bi = cols[i]
        for j in range(i + 1, 4):
            rj, gj, bj = cols[j]
            dr = ri - rj
            dg = gi - gj
            db = bi - bj
            d = dr * dr + dg * dg + db * db
            if d > best_d:
                best_d = d
                pa_r, pa_g, pa_b = ri, gi, bi
                pb_r, pb_g, pb_b = rj, gj, bj

    mask = 0
    sa_r = sa_g = sa_b = na = 0
    sb_r = sb_g = sb_b = nb = 0
    bits = (8, 4, 2, 1)
    for k in range(4):
        rk, gk, bk = cols[k]
        da = (rk - pa_r) ** 2 + (gk - pa_g) ** 2 + (bk - pa_b) ** 2
        db_v = (rk - pb_r) ** 2 + (gk - pb_g) ** 2 + (bk - pb_b) ** 2
        if da <= db_v:
            mask |= bits[k]
            sa_r += rk
            sa_g += gk
            sa_b += bk
            na += 1
        else:
            sb_r += rk
            sb_g += gk
            sb_b += bk
            nb += 1

    if na == 0:
        avg_b = ((sb_r // nb) << 16) | ((sb_g // nb) << 8) | (sb_b // nb)
        return "█", avg_b, VOID_INT
    if nb == 0:
        avg_a = ((sa_r // na) << 16) | ((sa_g // na) << 8) | (sa_b // na)
        return "█", avg_a, VOID_INT

    fg_i = ((sa_r // na) << 16) | ((sa_g // na) << 8) | (sa_b // na)
    bg_i = ((sb_r // nb) << 16) | ((sb_g // nb) << 8) | (sb_b // nb)
    return QUAD_CHARS[mask], fg_i, bg_i


_STYLE_PAIR_CACHE: dict[tuple[int, int], str] = {}
_STYLE_SOLID_CACHE: dict[int, str] = {}
_VOID_STYLE = f"on {VOID_HEX}"


def _pack_quadrant_buffer(pbuf: list[int], width: int, height: int) -> Text:
    """Pack a `width x height` RGB int buffer into `width//2 x height//2` Quadrant characters."""
    out = Text()
    rows_out = height // 2
    cols_out = width // 2
    append = out.append
    solid_cache = _STYLE_SOLID_CACHE
    pair_cache = _STYLE_PAIR_CACHE
    qchars = QUAD_CHARS
    solve = _solve_quad_cell
    void_i = VOID_INT
    void_st = _VOID_STYLE

    for cy_i in range(rows_out):
        top_off = (cy_i * 2) * width
        bot_off = top_off + width
        run_chars: list[str] = []
        run_style: Optional[str] = None

        for cx_i in range(cols_out):
            sx_base = cx_i * 2
            c0 = pbuf[top_off + sx_base]
            c1 = pbuf[top_off + sx_base + 1]
            c2 = pbuf[bot_off + sx_base]
            c3 = pbuf[bot_off + sx_base + 1]

            if c0 == c1 == c2 == c3:
                if c0 == void_i:
                    ch = " "
                    style = void_st
                else:
                    ch = "█"
                    style = solid_cache.get(c0)
                    if style is None:
                        style = f"{_int_to_hex(c0)} on {VOID_HEX}"
                        if len(solid_cache) < 8192:
                            solid_cache[c0] = style
            else:
                fg_i = c0
                bg_i = -1
                two_color = True
                if c1 != fg_i:
                    bg_i = c1
                if c2 != fg_i:
                    if bg_i == -1:
                        bg_i = c2
                    elif c2 != bg_i:
                        two_color = False
                if two_color and c3 != fg_i:
                    if bg_i == -1:
                        bg_i = c3
                    elif c3 != bg_i:
                        two_color = False

                if two_color and bg_i != -1:
                    mask = (8 if c0 == fg_i else 0) | (4 if c1 == fg_i else 0) | (2 if c2 == fg_i else 0) | (1 if c3 == fg_i else 0)
                    ch = qchars[mask]
                    key = (fg_i, bg_i)
                    style = pair_cache.get(key)
                    if style is None:
                        style = f"{_int_to_hex(fg_i)} on {_int_to_hex(bg_i)}"
                        if len(pair_cache) < 16384:
                            pair_cache[key] = style
                else:
                    ch, fg_s, bg_s = solve(c0, c1, c2, c3)
                    if ch == " ":
                        style = void_st
                    elif ch == "█":
                        style = solid_cache.get(fg_s)
                        if style is None:
                            style = f"{_int_to_hex(fg_s)} on {VOID_HEX}"
                            if len(solid_cache) < 8192:
                                solid_cache[fg_s] = style
                    else:
                        key = (fg_s, bg_s)
                        style = pair_cache.get(key)
                        if style is None:
                            style = f"{_int_to_hex(fg_s)} on {_int_to_hex(bg_s)}"
                            if len(pair_cache) < 16384:
                                pair_cache[key] = style

            if style != run_style:
                if run_chars:
                    append("".join(run_chars), style=run_style or "")
                    run_chars.clear()
                run_style = style
            run_chars.append(ch)
        if run_chars:
            append("".join(run_chars), style=run_style or "")
            run_chars.clear()
        if cy_i + 1 < rows_out:
            append("\n")
    return out


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
    return hex_size * 1.7320508075688772 * (q + r * 0.5), hex_size * 1.5 * r


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
    """Deterministic cube-grid 3D snake with instant steering, fine relief & spotted serpent."""

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
            else "Tap D / -> to spin aim right (+60 deg) · W / ↑ to dash."
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
        r_outer = 0.90
        r_inner = 0.76
        floor_y = -0.68

        # Key directional light vector for 3D cliff shading
        lx, lz = -0.62, -0.78

        # (cell, h, outer_verts, inner_verts, fill_rgb, rim_rgb)
        self._mesh_tiles: list[
            tuple[
                CubeCoord,
                float,
                list[tuple[float, float, float]],
                list[tuple[float, float, float]],
                RGB,
                RGB,
            ]
        ] = []
        self._mesh_cliffs: list[
            tuple[
                tuple[float, float, float],
                tuple[float, float, float],
                tuple[float, float, float],
                tuple[float, float, float],
                float,
                float,
                RGB,
            ]
        ] = []

        cell_centers = {c: _cube_to_world_xz(c) for c in self.valid_cells}
        for cell, h in self.heights.items():
            wx, wz = cell_centers[cell]
            q, r, _ = cell
            color_idx = (q * 2 + r * 3 + palette_shift) % len(MOSAIC_TILES)
            fill_base, rim_base, cliff_base = MOSAIC_TILES[color_idx]

            outer_verts = [(wx + r_outer * math.cos(a), h, wz + r_outer * math.sin(a)) for a in corner_angles]
            inner_verts = [(wx + r_inner * math.cos(a), h + 0.016, wz + r_inner * math.sin(a)) for a in corner_angles]
            elev_mul = max(0.82, min(1.32, 0.88 + h * 0.30))
            tile_col = _scale_rgb(fill_base, elev_mul)
            rim_col = _scale_rgb(rim_base, min(1.16, elev_mul))
            self._mesh_tiles.append((cell, h, outer_verts, inner_verts, tile_col, rim_col))

            for i in range(6):
                a_pt = outer_verts[i]
                b_pt = outer_verts[(i + 1) % 6]
                mx = (a_pt[0] + b_pt[0]) * 0.5 - wx
                mz = (a_pt[2] + b_pt[2]) * 0.5 - wz
                n_len = math.hypot(mx, mz) or 1.0
                nx, nz = mx / n_len, mz / n_len
                px_out = wx + nx * 1.732
                pz_out = wz + nz * 1.732
                drop_y = floor_y
                is_exterior = True
                for nc, (nwx, nwz) in cell_centers.items():
                    if nc != cell and (nwx - px_out) ** 2 + (nwz - pz_out) ** 2 < 0.6:
                        is_exterior = False
                        drop_y = self.heights[nc] if h > self.heights[nc] + 0.12 else h
                        break
                if is_exterior or drop_y < h - 0.10:
                    bot_a = (a_pt[0], drop_y, a_pt[2])
                    bot_b = (b_pt[0], drop_y, b_pt[2])
                    ndotl = max(0.0, nx * lx + nz * lz)
                    shade = 0.68 + 0.52 * ndotl
                    self._mesh_cliffs.append((a_pt, b_pt, bot_b, bot_a, nx, nz, _scale_rgb(cliff_base, shade)))

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
            self.status_line = "Tap D / -> to pivot right · W / ↑ to quick-step."

    def input_turn_right(self) -> str:
        """Instant clockwise +60 deg heading pivot with rapid-tap combo grace."""
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

        # Combo grace window: keep rapid 2x-4x taps from triggering an accidental mid-turn step
        grace_cap = max(0.0, self.step_interval - 0.115)
        if self.step_accum > grace_cap:
            self.step_accum = grace_cap
        return "turn_right"

    def input_quick_step(self) -> Optional[str]:
        """Immediately advance one tile when pressing Up / W for crisp manual pacing."""
        if self.phase == "intro":
            self.start_if_intro()
            return "start"
        if self.phase != "playing":
            return None
        self.step_accum = 0.0
        return self._logic_step()

    def input_turn_left_fault(self) -> str:
        self.left_fault_ticks = 14
        self.status_line = "LEFT KEY BROKEN! Tap D / -> clockwise (4x = Left)."
        return "fault_left"

    def serialize_state(self) -> bytes:
        """Serialize current 3D snake run into a compact JSON save-state payload."""
        import json

        payload = {
            "version": 1,
            "stage_idx": self.stage_idx,
            "score": self.score,
            "total_orbs": self.total_orbs,
            "stage_orbs": self.stage_orbs,
            "dir_idx": self.dir_idx,
            "snake": [list(c) for c in self.snake],
            "prev_snake": [list(c) for c in self.prev_snake],
            "orb": list(self.orb),
            "phase": "paused" if self.phase == "playing" else self.phase,
            "cam_yaw": round(self.cam_yaw, 4),
        }
        return json.dumps(payload).encode("utf-8")

    def deserialize_state(self, raw: bytes) -> bool:
        """Restore a saved 3D snake run from JSON state bytes."""
        import json

        try:
            data = json.loads(raw.decode("utf-8"))
            stage_idx = int(data.get("stage_idx", 0))
            if not (0 <= stage_idx < len(STAGES)):
                return False
            self._load_stage(stage_idx)
            self.score = int(data.get("score", 0))
            self.total_orbs = int(data.get("total_orbs", 0))
            self.stage_orbs = int(data.get("stage_orbs", 0))
            self.dir_idx = int(data.get("dir_idx", 0)) % 6
            snake_raw = data.get("snake", [])
            if snake_raw:
                self.snake = deque((int(c[0]), int(c[1]), int(c[2])) for c in snake_raw)
                self.prev_snake = list(self.snake)
            orb_raw = data.get("orb")
            if isinstance(orb_raw, list) and len(orb_raw) == 3:
                cand_orb = (int(orb_raw[0]), int(orb_raw[1]), int(orb_raw[2]))
                if cand_orb in self.valid_cells:
                    self.orb = cand_orb
            hx, hz = _cube_to_world_xz(self.snake[0])
            self.cam_target_x = hx
            self.cam_target_y = self.heights.get(self.snake[0], 0.2)
            self.cam_target_z = hz
            self.cam_yaw = float(data.get("cam_yaw", self.dir_idx * (math.pi / 3.0)))
            self.phase = "paused"
            self.status_line = f"STATE LOADED · Score {self.score} (Space / D to resume)"
            return True
        except Exception:
            return False

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
            self.cam_yaw = (self.cam_yaw + dt * 0.45) % (2.0 * math.pi)
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
            self.cam_yaw = (self.cam_yaw + yaw_diff * min(1.0, dt * 8.5)) % (2.0 * math.pi)

            t = min(1.0, self.step_accum / max(0.01, self.step_interval))
            hx1, hz1 = _cube_to_world_xz(self.snake[0])
            hy1 = self.heights[self.snake[0]]
            hx0, hz0 = _cube_to_world_xz(self.prev_snake[0])
            hy0 = self.heights[self.prev_snake[0]]
            tx = hx0 + (hx1 - hx0) * t
            ty = hy0 + (hy1 - hy0) * t
            tz = hz0 + (hz1 - hz0) * t
            self.cam_target_x += (tx - self.cam_target_x) * min(1.0, dt * 11.0)
            self.cam_target_y += (ty - self.cam_target_y) * min(1.0, dt * 9.0)
            self.cam_target_z += (tz - self.cam_target_z) * min(1.0, dt * 11.0)
        elif self.phase == "victory":
            self.cam_yaw = (self.cam_yaw + dt * 0.65) % (2.0 * math.pi)

        return event

    def render_frame(self, width: int = DEFAULT_PIX_W, height: int = DEFAULT_PIX_H) -> Text:
        """Render 140x32 Quadrant-packed multicolored 3D hex terrain with 2x SSAA edges."""
        n_pix = width * height
        zbuf = [1e9] * n_pix
        pbuf = [VOID_INT] * n_pix

        # Subtle sparse backdrop stars so floating 3D island has depth without clutter
        for sx_i, sy_i, s_col in _STAR_OFFSETS:
            if sx_i < width and sy_i < height:
                twinkle = 0.65 + 0.35 * math.sin(self.elapsed * 2.3 + sx_i)
                pbuf[sy_i * width + sx_i] = _pack_rgb(_scale_rgb(s_col, twinkle))

        fwd_x = math.cos(self.cam_yaw)
        fwd_z = math.sin(self.cam_yaw)
        right_x = -fwd_z
        right_z = fwd_x

        pitch = 0.65  # Crisp ~37 deg vantage showing terrain relief cleanly across 6-8 tiles
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)

        if self.phase == "intro":
            cam_dist = 11.4
            cam_x = -fwd_x * cam_dist
            cam_y = cam_dist * math.tan(pitch) * 0.96
            cam_z = -fwd_z * cam_dist
        else:
            cam_dist = 10.2
            la_x = self.cam_target_x + fwd_x * 1.15
            la_y = self.cam_target_y + 0.14
            la_z = self.cam_target_z + fwd_z * 1.15
            cam_x = la_x - fwd_x * cam_dist
            cam_y = la_y + cam_dist * math.tan(pitch) * 0.96
            cam_z = la_z - fwd_z * cam_dist

        # Quadrant 2x2 sub-pixels are 0.5x wide per physical cell unit -> fov_x = 2 * fov_y keeps circles round
        fov_y = height * 1.44
        fov_x = fov_y * 2.0
        cx = width * 0.5
        cy = height * 0.54

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
            inv_z = 1.0 / cz_local
            return cx + cx_local * (fov_x * inv_z), cy - cy_local * (fov_y * inv_z), cz_local

        def raster_poly_ssaa(
            pts: list[tuple[float, float, float]],
            base_rgb: RGB,
            z_bias: float = 0.0,
        ) -> None:
            """
            Seam-free convex polygon rasterizer (quads & hexagons) with edge-aware
            2x2 supersampling anti-aliasing (280x64 edge precision).
            """
            n_v = len(pts)
            x0, y0, z0 = pts[0]
            x1, y1, z1 = pts[1]
            x2, y2, z2 = pts[2]
            area = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
            if abs(area) < 0.08:
                return
            sign = 1.0 if area > 0.0 else -1.0

            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            min_x = max(0, int(min(xs) - 0.5))
            max_x = min(width - 1, int(max(xs) + 0.5))
            min_y = max(0, int(min(ys) - 0.5))
            max_y = min(height - 1, int(max(ys) + 0.5))
            if min_x > max_x or min_y > max_y:
                return

            # Normalized screen-pixel distance edge functions: e_k(x, y) = A*x + B*y + C
            edges: list[tuple[float, float, float]] = []
            for i in range(n_v):
                ax, ay, _ = pts[i]
                bx, by, _ = pts[(i + 1) % n_v]
                dx_e = bx - ax
                dy_e = by - ay
                norm = math.hypot(dx_e * 0.5, dy_e)
                if norm < 1e-6:
                    continue
                inv_n = sign / norm
                A = -dy_e * inv_n
                B = dx_e * inv_n
                C = (dy_e * ax - dx_e * ay) * inv_n
                edges.append((A, B, C))
            if len(edges) < 3:
                return

            # Plane depth equation z(x, y) from first 3 non-collinear vertices
            inv_area = 1.0 / area
            dz_dx = ((y1 - y2) * z0 + (y2 - y0) * z1 + (y0 - y1) * z2) * inv_area
            dz_dy = ((x2 - x1) * z0 + (x0 - x2) * z1 + (x1 - x0) * z2) * inv_area
            z_base = z0 - dz_dx * x0 - dz_dy * y0 + z_bias

            c_packed = _pack_rgb(base_rgb)
            sx_start = min_x + 0.5
            for py in range(min_y, max_y + 1):
                py_c = py + 0.5
                row_off = py * width
                depth = z_base + dz_dx * sx_start + dz_dy * py_c
                e_vals = [A * sx_start + B * py_c + C for A, B, C in edges]
                n_e = len(edges)

                for px in range(min_x, max_x + 1):
                    min_d = 1e9
                    for val in e_vals:
                        if val < min_d:
                            min_d = val

                    if min_d >= 0.65:
                        idx = row_off + px
                        if depth < zbuf[idx]:
                            zbuf[idx] = depth
                            fog = (depth - 7.8) * 0.048
                            if fog <= 0.0:
                                pbuf[idx] = c_packed
                            elif fog >= 0.44:
                                pbuf[idx] = _mix_int(c_packed, VOID_INT, 0.44)
                            else:
                                pbuf[idx] = _mix_int(c_packed, VOID_INT, fog)
                    elif min_d > -0.65:
                        # Boundary 2x2 sub-sample SSAA check (+/- 0.25 sub-pixel grid)
                        h00 = h10 = h01 = h11 = 1
                        for k_e in range(n_e):
                            ev = e_vals[k_e]
                            Ak, Bk, _ = edges[k_e]
                            qax = Ak * 0.25
                            qby = Bk * 0.25
                            if ev - qax - qby < 0.0:
                                h00 = 0
                            if ev + qax - qby < 0.0:
                                h10 = 0
                            if ev - qax + qby < 0.0:
                                h01 = 0
                            if ev + qax + qby < 0.0:
                                h11 = 0
                        hits = h00 + h10 + h01 + h11
                        if hits > 0:
                            idx = row_off + px
                            fog = (depth - 7.8) * 0.048
                            if fog <= 0.0:
                                shaded = c_packed
                            elif fog >= 0.44:
                                shaded = _mix_int(c_packed, VOID_INT, 0.44)
                            else:
                                shaded = _mix_int(c_packed, VOID_INT, fog)
                            if hits == 4:
                                if depth < zbuf[idx]:
                                    zbuf[idx] = depth
                                    pbuf[idx] = shaded
                            elif depth < zbuf[idx] + 0.18:
                                pbuf[idx] = _mix_int(pbuf[idx], shaded, hits * 0.25)

                    for k_e in range(n_e):
                        e_vals[k_e] += edges[k_e][0]
                    depth += dz_dx

        def raster_tri_ssaa(
            p0: tuple[float, float, float],
            p1: tuple[float, float, float],
            p2: tuple[float, float, float],
            base_rgb: RGB,
            z_bias: float = 0.0,
        ) -> None:
            raster_poly_ssaa([p0, p1, p2], base_rgb, z_bias=z_bias)

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
            rx_px = max(1.05, radius_world * (fov_x / cz))
            ry_px = max(0.75, radius_world * (fov_y / cz) * (0.52 if flat_shadow else 1.0))
            inv_rx = 1.0 / rx_px
            inv_ry = 1.0 / ry_px

            x0 = max(0, int(sx - rx_px - 0.6))
            x1 = min(width - 1, int(sx + rx_px + 0.6))
            y0 = max(0, int(sy - ry_px - 0.6))
            y1 = min(height - 1, int(sy + ry_px + 0.6))
            depth = cz + z_bias
            fog = 0.0 if flat_shadow else max(0.0, min(0.30, (depth - 7.5) / 22.0))
            c_main = _pack_rgb(core_rgb if flat_shadow else _mix_rgb(core_rgb, VOID_RGB, fog))
            c_spot = _pack_rgb(spot_rgb if flat_shadow else _mix_rgb(spot_rgb, VOID_RGB, fog * 0.55))

            for py in range(y0, y1 + 1):
                ny = ((py + 0.5) - sy) * inv_ry
                ny2 = ny * ny
                row_off = py * width
                for px in range(x0, x1 + 1):
                    nx = ((px + 0.5) - sx) * inv_rx
                    nd2 = nx * nx + ny2
                    if nd2 <= 1.22:
                        idx = row_off + px
                        if nd2 <= 0.78:
                            if depth < zbuf[idx]:
                                zbuf[idx] = depth
                                if flat_shadow:
                                    pbuf[idx] = c_main
                                elif spot_center:
                                    pbuf[idx] = c_spot if nd2 <= 0.24 else c_main
                                else:
                                    pbuf[idx] = c_spot if (nx < -0.18 and ny < -0.18) or nd2 < 0.18 else c_main
                        elif depth < zbuf[idx] + 0.18:
                            cov = max(0.0, min(1.0, (1.10 - math.sqrt(nd2)) * 3.1))
                            if cov > 0.05:
                                pbuf[idx] = _mix_int(pbuf[idx], c_main, cov)

        head_cell = self.snake[0]
        aim_cell = self._next_cell()
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 6.5)

        # 1. Back-to-front Lambert-Shaded 3D Cliffs (clean SSAA edge blending over sky/lower tiles)
        cliff_draw: list[tuple[float, list[tuple[float, float, float]], RGB]] = []
        for pa_t, pb_t, pb_b, pa_b, nx, nz, c_col in self._mesh_cliffs:
            if (pa_t[0] - cam_x) * nx + (pa_t[2] - cam_z) * nz >= 0.12:
                continue
            p0 = project(*pa_t)
            p1 = project(*pb_t)
            p2 = project(*pb_b)
            p3 = project(*pa_b)
            if p0 and p1 and p2 and p3:
                cz_avg = (p0[2] + p1[2] + p2[2] + p3[2]) * 0.25
                cliff_draw.append((cz_avg, [p0, p1, p2, p3], c_col))
        cliff_draw.sort(key=lambda item: item[0], reverse=True)
        for _, qpts, c_col in cliff_draw:
            raster_poly_ssaa(qpts, c_col, z_bias=0.05)

        # 2. Back-to-front Multicolored 3D Honeycomb Plateaus with seam-free SSAA bevels
        tile_draw: list[tuple[float, list[tuple[float, float, float]], list[tuple[float, float, float]], RGB, RGB]] = []
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
                bezel_rgb = (186, 255, 212) if self.right_flash_ticks == 0 else (255, 255, 255)
                plate_rgb = _mix_rgb(tile_col, (110, 231, 183), 0.25 + 0.20 * pulse)
            elif cell == head_cell:
                bezel_rgb = (210, 255, 224)
                plate_rgb = _scale_rgb(tile_col, 1.18)
            else:
                bezel_rgb = rim_col
                plate_rgb = tile_col

            cz_mid = sum(pt[2] for pt in po) / 6.0
            tile_draw.append((cz_mid, po, pi, bezel_rgb, plate_rgb))

        tile_draw.sort(key=lambda item: item[0], reverse=True)
        for _, po, pi, bezel_rgb, plate_rgb in tile_draw:
            raster_poly_ssaa(po, bezel_rgb, z_bias=0.02)
            raster_poly_ssaa(pi, plate_rgb, z_bias=0.0)

        # 3. 3D Faceted Diamond Beacon Crystal + Subtle Sky Beam
        ox, oz = _cube_to_world_xz(self.orb)
        oh = self.heights[self.orb]
        oy = oh + 0.44 + 0.12 * math.sin(self.elapsed * 5.0)
        stamp_disk(ox, oh + 0.03, oz, 0.26, (6, 8, 16), (6, 8, 16), z_bias=-0.04, flat_shadow=True)
        for step_h in (0.90, 1.24, 1.56):
            stamp_disk(ox, oh + step_h, oz, 0.065, (254, 240, 138), (255, 255, 240), z_bias=-0.20)
        spin = self.elapsed * 2.4
        r_gem = 0.26
        apex = project(ox, oy + 0.34, oz)
        nadir = project(ox, oy - 0.24, oz)
        ring_pts = [
            project(ox + r_gem * math.cos(spin + k * math.pi * 0.5), oy + 0.04, oz + r_gem * math.sin(spin + k * math.pi * 0.5))
            for k in range(4)
        ]
        if apex and nadir and all(pt is not None for pt in ring_pts):
            rp = [pt for pt in ring_pts if pt is not None]
            gem_shades = ((254, 249, 195), (250, 204, 21), (234, 179, 8), (202, 138, 4))
            for k in range(4):
                nk = (k + 1) % 4
                raster_tri_ssaa(apex, rp[k], rp[nk], gem_shades[k], z_bias=-0.38)
                raster_tri_ssaa(nadir, rp[nk], rp[k], _scale_rgb(gem_shades[k], 0.78), z_bias=-0.36)
        else:
            stamp_disk(ox, oy, oz, 0.24, (250, 204, 21), (255, 255, 235), z_bias=-0.38)

        # 4. Crisp Visual Aim Pointer (dotted sight-line onto aim_cell so turns feel instantaneous)
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
            seg_pos.append((wx, ground_y + 0.23, wz, ground_y))

        hx_w, hy_w, hz_w, _ = seg_pos[0]
        head_ang = self.dir_idx * (math.pi / 3.0)
        fx, fz = math.cos(head_ang), math.sin(head_ang)
        rx, rz = -fz, fx

        if self.phase == "playing":
            aim_ok = aim_cell in self.valid_cells and aim_cell not in set(list(self.snake)[:-1])
            dot_col = (248, 113, 113) if not aim_ok else ((255, 255, 255) if self.right_flash_ticks > 0 else (110, 255, 175))
            ax, az = _cube_to_world_xz(aim_cell)
            ay = self.heights.get(aim_cell, hy_w - 0.23) + 0.09
            for frac in (0.42, 0.72):
                stamp_disk(
                    hx_w + (ax - hx_w) * frac,
                    hy_w - 0.08 + (ay - (hy_w - 0.08)) * frac,
                    hz_w + (az - hz_w) * frac,
                    0.072 if frac < 0.6 else 0.105,
                    dot_col,
                    (255, 255, 255),
                    z_bias=-0.28,
                )

        # 5. Sleek Green Spotted Snake (`pykuai`) with dense interpolated spine
        for idx in range(seg_count - 1, -1, -1):
            wx, wy, wz, gy = seg_pos[idx]
            ratio = idx / max(1, seg_count - 1)
            stamp_disk(wx, gy + 0.025, wz, 0.21 - 0.05 * ratio, (4, 6, 12), (4, 6, 12), z_bias=-0.05, flat_shadow=True)

            if self.phase == "gameover":
                body_rgb = (239, 68, 68) if idx == 0 else (153, 27, 27)
                spot_rgb = (254, 202, 202)
                rad = 0.26 if idx == 0 else max(0.14, 0.22 - 0.06 * ratio)
            elif idx == 0:
                body_rgb = (22, 198, 86) if self.right_flash_ticks == 0 else (74, 232, 132)
                spot_rgb = (187, 247, 208)
                rad = 0.27
            else:
                base_g = int(206 - 50 * ratio)
                body_rgb = (16, base_g, 62)
                spot_rgb = (217, 249, 157) if idx % 2 == 1 else (6, 78, 42)
                rad = max(0.13, 0.23 - 0.08 * ratio)

            if idx < seg_count - 1:
                nx_w, ny_w, nz_w, _ = seg_pos[idx + 1]
                bridge_rgb = (18, 178, 62) if self.phase != "gameover" else (153, 27, 27)
                for bfrac in (0.34, 0.68):
                    stamp_disk(
                        wx + (nx_w - wx) * bfrac,
                        wy + (ny_w - wy) * bfrac,
                        wz + (nz_w - wz) * bfrac,
                        max(0.11, rad * 0.80),
                        bridge_rgb,
                        (74, 222, 128),
                        z_bias=-0.27,
                    )

            stamp_disk(
                wx,
                wy,
                wz,
                rad,
                body_rgb,
                spot_rgb,
                z_bias=-0.34,
                spot_center=(idx > 0 and self.phase != "gameover"),
            )

        # Tiny twin eyes + flicking coral tongue on green snake head facing `dir_idx`
        eye_rgb = (8, 30, 14) if self.right_flash_ticks == 0 else (255, 255, 255)
        for side in (-0.11, 0.11):
            stamp_disk(
                hx_w + fx * 0.19 + rx * side,
                hy_w + 0.09,
                hz_w + fz * 0.19 + rz * side,
                0.062,
                eye_rgb,
                eye_rgb,
                z_bias=-0.46,
            )
        if self.phase in ("playing", "intro") and math.sin(self.elapsed * 9.0) > 0.15:
            stamp_disk(
                hx_w + fx * 0.30,
                hy_w - 0.02,
                hz_w + fz * 0.30,
                0.045,
                (251, 113, 133),
                (254, 205, 211),
                z_bias=-0.44,
            )

        # 6. Pack 2x2 Quadrant Characters
        return _pack_quadrant_buffer(pbuf, width, height)


def _build_hex3d_app():
    """Build compact, centered 78x24 studio card without title, SFX button, or RIGHT-ONLY tag."""
    from textual import events
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Center, Horizontal, Vertical
    from textual.widgets import Button, Static

    from pykuai.core.tui import (
        ActionChip,
        CYBER_TUI_CSS,
        HelpChip,
        HelpModalScreen,
        PyKuaiStudioApp,
    )

    hex_css = CYBER_TUI_CSS + """
    #studio-card {
        width: 78;
        max-width: 96%;
        height: 24;
        max-height: 96%;
        padding: 0 1;
    }

    #hud-row {
        width: 100%;
        height: 1;
        margin-bottom: 0;
    }

    #hex-hud {
        width: 1fr;
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

    .hex-actions {
        height: 1;
        layout: horizontal;
        margin-top: 1;
        margin-bottom: 0;
    }
    """

    class Hex3DApp(PyKuaiStudioApp):
        CSS = hex_css
        HELP_TITLE = "Hex 3D · Story & Controls"
        HELP_TEXT = HEX3D_HELP
        BINDINGS = [
            *PyKuaiStudioApp.BINDINGS,
            Binding("question_mark", "show_help", "Help", show=False, priority=True),
            Binding("right", "turn_right", "Turn Right", show=False, priority=True),
            Binding("d", "turn_right", "Turn Right", show=False, priority=True),
            Binding("D", "turn_right", "Turn Right", show=False, priority=True),
            Binding("left", "fault_left", "Broken Left", show=False, priority=True),
            Binding("a", "fault_left", "Broken Left", show=False, priority=True),
            Binding("A", "fault_left", "Broken Left", show=False, priority=True),
            Binding("up", "quick_step", "Quick Step", show=False, priority=True),
            Binding("w", "quick_step", "Quick Step", show=False, priority=True),
            Binding("W", "quick_step", "Quick Step", show=False, priority=True),
            Binding("space", "toggle_pause", "Start/Pause", show=False, priority=True),
            Binding("p", "toggle_pause", "Start/Pause", show=False, priority=True),
            Binding("P", "toggle_pause", "Start/Pause", show=False, priority=True),
            Binding("r", "restart_game", "Restart", show=False, priority=True),
            Binding("R", "restart_game", "Restart", show=False, priority=True),
            Binding("q", "exit_game", "Exit", show=False, priority=True),
            Binding("Q", "exit_game", "Exit", show=False, priority=True),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.engine = _Hex3DEngine()
            self._timer = None
            self._last_tick = time.perf_counter()
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

            # Fit cleanly centered inside exact 78x24 card chrome (70x16 cells = 140x32 Quadrant sub-pixels)
            view_cols = max(36, min(DEFAULT_PIX_W // 2, card_w - 8))
            if view_cols % 2 == 1:
                view_cols -= 1
            view_rows = max(9, min(DEFAULT_PIX_H // 2, card_h - 8))
            self.pix_w = view_cols * 2
            self.pix_h = view_rows * 2

            vp = self.query_one("#hex-viewport", Static)
            vp.styles.width = view_cols + 2
            vp.styles.height = view_rows + 2

        def compose(self) -> ComposeResult:
            with Vertical(id="studio-card"):
                with Horizontal(id="hud-row"):
                    yield Static("", id="hex-hud")
                    yield HelpChip(tooltip="Help (F1 / ?)")
                with Center(id="viewport-wrap"):
                    yield Static("", id="hex-viewport")
                yield Static("", id="status-line")

                with Horizontal(classes="hex-actions"):
                    yield ActionChip("↻ Restart", variant_class="-preset", id="btn-restart")
                    yield ActionChip("▶ Start", variant_class="-file", id="btn-pause")
                    yield ActionChip("✕ Back", variant_class="-danger", id="btn-back")

        def on_mount(self) -> None:
            for chip in self.query(ActionChip):
                chip.can_focus = False
            self.query_one("#btn-help", HelpChip).can_focus = False
            play_sfx("snake")
            self._recompute_viewport()
            self._sync_view()
            self._last_tick = time.perf_counter()
            self._timer = self.set_interval(1.0 / 32.0, self._on_tick)

        def on_resize(self, event: events.Resize) -> None:
            self._recompute_viewport()
            self._sync_view()

        def _sync_view(self) -> None:
            e = self.engine
            stage_name = str(STAGES[e.stage_idx]["name"])
            hud = (
                f"[bold #00FF00]SCORE[/] {e.score:<4} "
                f"[bold #FF9800]BEST[/] {e.best_score:<4} "
                f"[bold #22d3ee]{stage_name}[/] ({e.stage_orbs}/{e.stage_goal})"
            )
            self.query_one("#hex-hud", Static).update(hud)

            vp = self.query_one("#hex-viewport", Static)
            vp.update(e.render_frame(self.pix_w, self.pix_h))
            vp.set_class(e.left_fault_ticks > 0 or e.phase == "gameover", "-fault")
            vp.set_class(e.phase == "victory", "-victory")

            st_w = self.query_one("#status-line", Static)
            line = e.status_line
            max_chars = max(40, (self.pix_w // 2) + 4)
            if len(line) > max_chars:
                line = line[: max_chars - 1] + "…"
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

        def _play_step_event(self, ev: Optional[str]) -> None:
            if ev == "orb":
                play_sfx("key")
            elif ev == "stage":
                play_sfx("enter")
            elif ev == "rim":
                play_sfx("paste")
            elif ev in ("gameover", "victory"):
                play_sfx("snake" if ev == "victory" else "paste")

        def _on_tick(self) -> None:
            now = time.perf_counter()
            dt = min(0.08, max(0.005, now - self._last_tick))
            self._last_tick = now
            if isinstance(self.screen, HelpModalScreen):
                return
            ev = self.engine.advance_frame(dt)
            self._play_step_event(ev)
            self._sync_view()

        def action_turn_right(self) -> None:
            if isinstance(self.screen, HelpModalScreen):
                return
            fb = self.engine.input_turn_right()
            play_sfx("enter" if fb == "start" else "click")
            self._sync_view()

        def action_fault_left(self) -> None:
            if isinstance(self.screen, HelpModalScreen):
                return
            self.engine.input_turn_left_fault()
            play_sfx("paste")
            self._sync_view()

        def action_quick_step(self) -> None:
            if isinstance(self.screen, HelpModalScreen):
                return
            ev = self.engine.input_quick_step()
            self._play_step_event(ev)
            self._sync_view()

        def action_toggle_pause(self) -> None:
            if isinstance(self.screen, HelpModalScreen):
                return
            self._toggle_pause()

        def action_restart_game(self) -> None:
            if isinstance(self.screen, HelpModalScreen):
                return
            self._restart()

        def action_exit_game(self) -> None:
            if isinstance(self.screen, HelpModalScreen):
                self.screen.action_dismiss_help()
                return
            self._exit_game()

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
                self.engine.status_line = "Tap D / -> to pivot right · W / ↑ to quick-step."
            self._sync_view()

        def _restart(self) -> None:
            record_high_score("hex", self.engine.score)
            play_sfx("snake")
            self.engine.reset(show_intro=False)
            self._last_tick = time.perf_counter()
            self._sync_view()

        def _exit_game(self) -> None:
            record_high_score("hex", self.engine.score)
            play_sfx("click")
            self.exit(0)

        def action_cancel(self) -> None:
            self._exit_game()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            btn = event.button
            if btn.id == "btn-restart":
                self._restart()
            elif btn.id == "btn-pause":
                self._toggle_pause()
            elif btn.id == "btn-back":
                self._exit_game()

    return Hex3DApp()


class PyKuaiHex3DGame(ArcadeGame):
    """Registered `ArcadeGame` entry for Hex 3D."""

    code = "hex"
    title = "Hex 3D"
    tagline = "Multicolored 3D Hex & Spotted Snake"
    order = 10
    help_text = HEX3D_HELP

    def run(self, console: Console) -> int:
        from pykuai.core.tui import is_interactive_tty

        if not is_interactive_tty():
            print_error("Hex 3D requires an interactive terminal (TTY).")
            return 1

        result = _build_hex3d_app().run(mouse=True)
        return 0 if result is None else int(result)
