# -*- coding: utf-8 -*-
"""
GitHub Video (`ghv`) prepares a local video for sharing as a mobile-friendly MP4.
Detect logo regions, normalize audio and fit H.264 High@3.1 within a decimal size limit.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from typing import Callable, Optional

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt

from pykuai.core.base import BaseEngine
from pykuai.core.ui import print_error, print_step, print_warning

VIDEO_EXTENSIONS = (
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".m4v", ".3gp",
    ".ts", ".mts", ".m2ts", ".mpg", ".mpeg", ".f4v", ".ogv", ".vob",
)

# --- H.264 High Profile @ Level 3.1 hard limits (ITU-T H.264 Table A-1, High = 1.25x cpbBrNalFactor) ---
LEVEL31_MAX_FS = 3600            # macroblocks per frame (1280x720 = 80x45 MBs)
LEVEL31_MAX_MBPS = 108000        # macroblocks per second (720p @ 30 fps)
LEVEL31_MAX_DPB_MBS = 18000      # decoded picture buffer in macroblocks
LEVEL31_HIGH_MAX_KBPS = 17500    # 14000 kbps x 1.25 (High profile)
LEVEL31_HIGH_MAX_CPB_KBIT = 17500

# --- Output policy ---
DEFAULT_MAX_MB = 100.0
DEFAULT_LUFS = -14.0             # Golden listening zone for phones & streaming platforms
TARGET_TRUE_PEAK = -1.5
TARGET_LRA = 11.0
MAX_WIDTH = 1280
MAX_HEIGHT = 720
QUALITY_CRF = 14                 # High-quality capped CRF when Level 3.1 itself limits the bitrate
MIN_BPP = 0.040                  # Bits-per-pixel floor before stepping resolution down
MIN_VIDEO_KBPS = 1               # x264 accepts target rates in whole kbps
SIZE_SAFETY = 0.965              # Reserve for MP4 container overhead & rate-control variance
STANDARD_FPS = (
    Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001), Fraction(30),
    Fraction(48), Fraction(50), Fraction(60000, 1001), Fraction(60),
)
X264_PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow")


# ============================================================================================
# Data Models
# ============================================================================================
@dataclass
class VideoInfo:
    path: str
    size_bytes: int
    duration: float
    width: int                   # Decoded frame width after auto-rotation (storage pixels)
    height: int
    sar: Fraction
    fps: Fraction
    codec: str
    pix_fmt: str
    color_transfer: str
    rotation: int
    video_index: int
    audio_index: Optional[int]
    audio_codec: str = ""
    audio_channels: int = 0

    @property
    def display_width(self) -> float:
        return self.width * float(self.sar)

    @property
    def is_hdr(self) -> bool:
        return self.color_transfer in ("smpte2084", "arib-std-b67")


@dataclass
class WatermarkBox:
    x: int
    y: int
    w: int
    h: int
    t0: Optional[float] = None
    t1: Optional[float] = None

    def to_filter(self, show: bool = False) -> str:
        region = f"x={self.x}:y={self.y}:w={self.w}:h={self.h}"
        parts = f"drawbox={region}:color=lime:t=2" if show else f"delogo={region}"
        if self.t0 is not None and self.t1 is not None:
            parts += f":enable='gte(t,{self.t0:.6f})*lt(t,{self.t1:.6f})'"
        return parts

    def describe(self) -> str:
        span = "full video" if self.t0 is None else f"{_fmt_clock(self.t0)}-{_fmt_clock(self.t1 or 0.0)}"
        return f"{self.w}x{self.h} @ ({self.x},{self.y}) · {span}"


@dataclass
class EncodePlan:
    out_w: int
    out_h: int
    fps: Fraction
    mode: str                    # "crf" (capped CRF) or "2pass" (size-targeted two-pass ABR)
    video_kbps: int
    audio_kbps: int
    maxrate: int
    bufsize: int
    refs: int
    gop: int
    budget_bytes: int
    hdr_tonemap: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class VidOptions:
    max_mb: float = DEFAULT_MAX_MB
    wm_mode: str = "auto"        # auto | off
    wm_boxes: list[WatermarkBox] = field(default_factory=list)
    show_wm: bool = False
    lufs: Optional[float] = DEFAULT_LUFS
    preset: str = "slow"
    analyze_only: bool = False


# ============================================================================================
# Small Helpers
# ============================================================================================
def _clean_path(raw: str) -> str:
    """Clean dragged/pasted paths by stripping whitespace and surrounding quotes."""
    clean = (raw or "").strip()
    if clean.startswith("& "):  # PowerShell drag-and-drop prefix: & 'C:\path\file.mp4'
        clean = clean[2:].strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in "\"'":
        clean = clean[1:-1].replace("''", "'") if clean[0] == "'" else clean[1:-1]
    return os.path.expanduser(clean)


def _same_file(first: str, second: str) -> bool:
    if os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second)):
        return True
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def _even(value: float) -> int:
    return max(2, int(round(value / 2.0)) * 2)


def _fmt_clock(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    m, s = divmod(int(round(seconds)), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _fmt_mb(num_bytes: float) -> str:
    return f"{num_bytes / 1_000_000:.1f} MB"


def _fmt_fps(fps: Fraction) -> str:
    val = float(fps)
    return f"{val:.3f}".rstrip("0").rstrip(".")


def _parse_rate(raw: str) -> Fraction:
    try:
        if not raw or raw in ("0/0", "N/A"):
            return Fraction(0)
        return Fraction(raw).limit_denominator(1_001_000)
    except (ValueError, ZeroDivisionError):
        return Fraction(0)


def _parse_wm_box(raw: str) -> WatermarkBox:
    try:
        x, y, w, h = (int(p) for p in raw.replace(",", ":").split(":"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Watermark box must be X:Y:W:H in source pixels (e.g. 20:20:240:80).") from exc
    if w < 4 or h < 4 or x < 0 or y < 0:
        raise argparse.ArgumentTypeError("Watermark box needs X,Y >= 0 and W,H >= 4 pixels.")
    return WatermarkBox(x, y, w, h)


def _default_output_path(src: str, preview: bool = False) -> str:
    base_dir = os.path.dirname(src)
    stem = os.path.splitext(os.path.basename(src))[0]
    suffix = "_regions.mp4" if preview else "_mobile.mp4"
    return os.path.join(base_dir, stem + suffix)


def _run_capture(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)


_FILTER_CACHE: dict[str, set[str]] = {}


def _ffmpeg_capabilities(ffmpeg: str) -> set[str]:
    """Return available filter + encoder names of this FFmpeg build (cached per binary)."""
    if ffmpeg in _FILTER_CACHE:
        return _FILTER_CACHE[ffmpeg]
    names: set[str] = set()
    for flag in ("-filters", "-encoders"):
        try:
            res = _run_capture([ffmpeg, "-hide_banner", flag], timeout=20)
            for line in res.stdout.decode("utf-8", "replace").splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    names.add(parts[1])
        except Exception:
            pass
    _FILTER_CACHE[ffmpeg] = names
    return names


# ============================================================================================
# Probing
# ============================================================================================
def probe_video(path: str, ffprobe: str) -> VideoInfo:
    """Inspect streams via ffprobe and normalize geometry for auto-rotated decoding."""
    res = _run_capture(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        timeout=60,
    )
    if res.returncode != 0:
        msg = res.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ValueError(msg[-1] if msg else "ffprobe could not read this file.")
    data = json.loads(res.stdout.decode("utf-8", "replace") or "{}")
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    video = next(
        (s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")),
        None,
    )
    if video is None:
        raise ValueError("No video stream found.")
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    audio = next((s for s in audios if s.get("disposition", {}).get("default")), audios[0] if audios else None)

    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError("Video stream reports invalid dimensions.")

    rotation = 0
    for side in video.get("side_data_list", []) or []:
        if "rotation" in side:
            try:
                rotation = int(round(float(side["rotation"])))
            except (TypeError, ValueError):
                pass
    if not rotation:
        try:
            rotation = int(float(video.get("tags", {}).get("rotate", 0)))
        except (TypeError, ValueError):
            rotation = 0
    if abs(rotation) % 180 == 90:
        width, height = height, width

    sar = _parse_rate(video.get("sample_aspect_ratio", "1:1").replace(":", "/"))
    if sar <= 0:
        sar = Fraction(1)
    if abs(rotation) % 180 == 90 and sar != 1:
        sar = 1 / sar

    fps = _parse_rate(video.get("avg_frame_rate", ""))
    if fps <= 0 or fps > 240:
        fps = _parse_rate(video.get("r_frame_rate", ""))
    if fps <= 0 or fps > 240:
        fps = Fraction(30)

    duration = 0.0
    for raw in (fmt.get("duration"), video.get("duration")):
        try:
            duration = float(raw)
            if math.isfinite(duration) and duration > 0:
                break
        except (TypeError, ValueError):
            continue
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Unable to determine video duration.")

    try:
        size_bytes = int(fmt.get("size") or os.path.getsize(path))
    except (TypeError, ValueError, OSError):
        size_bytes = 0

    return VideoInfo(
        path=path,
        size_bytes=size_bytes,
        duration=duration,
        width=width,
        height=height,
        sar=sar,
        fps=fps,
        codec=str(video.get("codec_name", "?")),
        pix_fmt=str(video.get("pix_fmt", "?")),
        color_transfer=str(video.get("color_transfer", "") or ""),
        rotation=rotation,
        video_index=int(video.get("index", 0)),
        audio_index=int(audio["index"]) if audio else None,
        audio_codec=str(audio.get("codec_name", "")) if audio else "",
        audio_channels=int(audio.get("channels") or 0) if audio else 0,
    )


def _summarize_source(info: VideoInfo) -> str:
    audio = f"{info.audio_codec} {info.audio_channels}ch" if info.audio_index is not None else "no audio"
    hdr = " · HDR" if info.is_hdr else ""
    return (
        f"{int(round(info.display_width))}×{info.height} · {_fmt_fps(info.fps)} fps · {info.codec}/{info.pix_fmt}"
        f"{hdr} · {audio} · {_fmt_clock(info.duration)} · {_fmt_mb(info.size_bytes)}"
    )


# ============================================================================================
# Encode Planning (Level 3.1 geometry, frame rate & size budget)
# ============================================================================================
def _fit_dimensions(display_w: float, display_h: float, height_cap: int = MAX_HEIGHT) -> tuple[int, int]:
    """Fit the display aspect into a landscape bounding box, including portrait sources."""
    width_cap = _even(height_cap * MAX_WIDTH / MAX_HEIGHT)
    # libx264/yuv420p needs even dimensions. Round small, odd frames down to avoid upscaling.
    max_w = min(width_cap, max(2, int(display_w) // 2 * 2))
    max_h = min(height_cap, max(2, int(display_h) // 2 * 2))
    scale = min(max_w / display_w, max_h / display_h)
    return _even(display_w * scale), _even(display_h * scale)


def _macroblocks(w: int, h: int) -> int:
    return math.ceil(w / 16) * math.ceil(h / 16)


def _snap_fps(fps: Fraction) -> Fraction:
    closest = min(STANDARD_FPS, key=lambda rate: abs(rate - fps))
    if abs(closest - fps) <= closest / 10_000:
        return closest
    return fps.limit_denominator(1001)


def _choose_fps(src_fps: Fraction, w: int, h: int) -> Fraction:
    """Keep source cadence when Level 3.1 allows it, otherwise divide by an integer (60 -> 30, 50 -> 25)."""
    fps = _snap_fps(src_fps)
    max_fps = Fraction(LEVEL31_MAX_MBPS, _macroblocks(w, h))
    return fps / max(1, math.ceil(fps / max_fps))


def plan_encode(info: VideoInfo, max_mb: float, ffmpeg_caps: set[str]) -> EncodePlan:
    """Choose resolution, frame rate, audio bitrate and rate-control mode that fit the size budget."""
    if not 1 <= max_mb <= DEFAULT_MAX_MB:
        raise ValueError("--max-mb must be between 1 and 100.")
    max_bytes = int(max_mb * 1_000_000)
    # MP4 sample tables grow with duration even for very low-bitrate encodes.
    table_bytes = math.ceil(info.duration * (400 if info.audio_index is not None else 180))
    reserve = max(math.ceil(max_bytes * (1 - SIZE_SAFETY)), table_bytes)
    budget_bytes = max_bytes - 4096 - reserve
    total_kbps = budget_bytes * 8 / 1000 / info.duration
    notes: list[str] = []

    audio_kbps = 0
    if info.audio_index is not None:
        rates = (160, 128, 96, 64, 48, 32, 24, 16, 8)
        audio_kbps = next((rate for rate in rates if rate <= total_kbps * 0.22), 8)
    video_kbps = int(total_kbps - audio_kbps)
    if video_kbps < MIN_VIDEO_KBPS:
        raise ValueError(
            f"The {max_mb:g} MB budget leaves less than 1 kbps for video after audio and MP4 overhead. "
            "Shorten the input or select a larger size budget."
        )

    display_w, display_h = info.display_width, float(info.height)
    # Preserve source cadence at the top rungs. At small budgets trade pixels
    # and then frames for a usable amount of data per encoded picture.
    for height_cap, fps_cap in ((720, None), (540, None), (480, 30), (360, 30), (240, 24),
                                (180, 20), (144, 15), (90, 8)):
        out_w, out_h = _fit_dimensions(display_w, display_h, height_cap)
        fps = _choose_fps(info.fps, out_w, out_h)
        if fps_cap and fps > fps_cap:
            fps /= math.ceil(fps / fps_cap)
        bpp = video_kbps * 1000 / (out_w * out_h * float(fps))
        if bpp >= MIN_BPP:
            break
    if min(out_w, out_h) < min(_fit_dimensions(display_w, display_h)):
        notes.append(f"Long video: resolution stepped down to {out_w}×{out_h} to stay under {max_mb:g} MB.")

    if _snap_fps(info.fps) != fps:
        notes.append(f"Frame rate {_fmt_fps(info.fps)} → {_fmt_fps(fps)} fps to fit Level 3.1 and the size budget.")

    if video_kbps >= LEVEL31_HIGH_MAX_KBPS:
        mode = "crf"
        maxrate = LEVEL31_HIGH_MAX_KBPS
    else:
        mode = "2pass"
        maxrate = min(int(video_kbps * 2), LEVEL31_HIGH_MAX_KBPS)
    bufsize = min(maxrate * 2, LEVEL31_HIGH_MAX_CPB_KBIT)

    refs = max(1, min(4, LEVEL31_MAX_DPB_MBS // _macroblocks(out_w, out_h)))
    gop = max(12, int(round(float(fps) * 2)))

    if info.is_hdr:
        if not {"zscale", "tonemap"} <= ffmpeg_caps:
            raise ValueError("This HDR input requires the FFmpeg zscale and tonemap filters for 8-bit SDR output.")
        notes.append("HDR source tone-mapped to SDR BT.709 (Hable) for 8-bit yuv420p.")

    return EncodePlan(
        out_w=out_w,
        out_h=out_h,
        fps=fps,
        mode=mode,
        video_kbps=video_kbps,
        audio_kbps=audio_kbps,
        maxrate=maxrate,
        bufsize=bufsize,
        refs=refs,
        gop=gop,
        budget_bytes=budget_bytes,
        hdr_tonemap=info.is_hdr,
        notes=notes,
    )


# ============================================================================================
# Automatic Watermark Detection (temporal median of signed gradients)
# ============================================================================================
def _analysis_size(w: int, h: int, long_side: int = 480) -> tuple[int, int]:
    if max(w, h) <= long_side:
        return _even(w), _even(h)
    if w >= h:
        return long_side, _even(long_side * h / w)
    return _even(long_side * w / h), long_side


def _extract_gray_frame(ffmpeg: str, info: VideoInfo, t: float, aw: int, ah: int):
    import numpy as np

    cmd = [
        ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
        "-ss", f"{t:.6f}", "-threads", "1", "-filter_threads", "1", "-i", info.path,
        "-map", f"0:{info.video_index}", "-frames:v", "1", "-vf", f"scale={aw}:{ah}:flags=area",
        "-threads", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    try:
        res = _run_capture(cmd, timeout=90)
    except (subprocess.TimeoutExpired, OSError):
        return None
    need = aw * ah
    if res.returncode != 0 or len(res.stdout) < need:
        return None
    return np.frombuffer(res.stdout[:need], dtype=np.uint8).reshape(ah, aw)


def _median_gradient_map(stack):
    """Visible watermarks keep a constant-sign gradient over changing backgrounds; scenery averages out."""
    import numpy as np

    f = stack.astype(np.int16)

    def stable_gradient(axis):
        gradients = np.diff(f, axis=axis)
        # A large median alone frequently picks up texture on a panning camera.
        votes = np.maximum((gradients > 3).sum(axis=0), (gradients < -3).sum(axis=0))
        median = np.abs(np.median(gradients, axis=0)).astype(np.float32)
        return np.where(votes >= 0.90 * len(f), median, 0)

    gx = stable_gradient(2)
    gy = stable_gradient(1)
    h, w = f.shape[1:]
    m = np.zeros((h, w), np.float32)
    m[:, :-1] += gx
    m[:, 1:] += gx
    m[:-1, :] += gy
    m[1:, :] += gy
    return m * 0.5


def _dilate(mask, r: int):
    import numpy as np

    k = 2 * r + 1
    padded = np.pad(mask.astype(np.int32), r)
    ii = np.pad(padded.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    window = ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]
    return window > 0


def _label_components(mask) -> list[tuple[int, int, int, int, list[tuple[int, int]]]]:
    """4-connected component labeling returning (x0, y0, x1, y1, pixels)."""
    import numpy as np

    h, w = mask.shape
    grid = mask.tolist()
    seen = np.zeros((h, w), dtype=bool).tolist()
    comps = []
    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if seen[sy][sx]:
            continue
        seen[sy][sx] = True
        stack = [(sy, sx)]
        pixels = []
        x0 = x1 = sx
        y0 = y1 = sy
        while stack:
            y, x = stack.pop()
            pixels.append((y, x))
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and grid[ny][nx] and not seen[ny][nx]:
                    seen[ny][nx] = True
                    stack.append((ny, nx))
        comps.append((x0, y0, x1, y1, pixels))
    return comps


def _detect_boxes_in_frames(frames) -> tuple[list[tuple[int, int, int, int, float]], bool]:
    """Find persistent edge groups backed by evidence of a changing local background."""
    import numpy as np

    moving = np.std(frames, axis=0, dtype=np.float32) > 6
    if moving.mean() < 0.02:
        return [], True
    m = _median_gradient_map(frames)
    h, w = m.shape
    thresh = max(9.0, float(np.percentile(m, 99.5)) * 0.25)
    strong = m > thresh

    # Drop long straight lines (letterbox / pillarbox borders, static UI rules).
    strong[strong.mean(axis=1) > 0.35, :] = False
    strong[:, strong.mean(axis=0) > 0.35] = False

    if strong.mean() > 0.12:
        return [], True

    r = max(2, int(round(min(h, w) / 70)))
    merged = _dilate(strong, r)
    boxes = []
    for x0, y0, x1, y1, pixels in _label_components(merged):
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        area_ratio = bw * bh / float(w * h)
        if not 0.0004 <= area_ratio <= 0.08 or bw > 0.55 * w or bh > 0.30 * h:
            continue
        py = np.fromiter((p[0] for p in pixels), dtype=np.int32, count=len(pixels))
        px = np.fromiter((p[1] for p in pixels), dtype=np.int32, count=len(pixels))
        strong_count = int(strong[py, px].sum())
        if strong_count < 15 or strong_count / float(bw * bh) < 0.04:
            continue
        cx, cy = (x0 + x1) / 2.0 / w, (y0 + y1) / 2.0 / h
        if not (cx < 0.30 or cx > 0.70 or cy < 0.22 or cy > 0.78):
            continue
        # A still corner in a shot with motion elsewhere is ambiguous. Look at a
        # ring outside the suspected logo so an opaque logo can qualify as well.
        pad = max(6, bh // 2)
        around = moving[
            max(0, y0 - pad):min(h, y1 + pad + 1),
            max(0, x0 - pad):min(w, x1 + pad + 1),
        ]
        inside = moving[y0:y1 + 1, x0:x1 + 1]
        if around.sum() - inside.sum() < 0.2 * (around.size - inside.size):
            continue
        boxes.append((x0, y0, x1, y1, float(m[py, px].mean())))
    return boxes, False


def _box_iou(a, b) -> float:
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix1 - ix0 + 1) * max(0, iy1 - iy0 + 1)
    area_a = (a[2] - a[0] + 1) * (a[3] - a[1] + 1)
    area_b = (b[2] - b[0] + 1) * (b[3] - b[1] + 1)
    return inter / float(area_a + area_b - inter) if inter else 0.0


def _logo_runs(frames, reference, box, times, duration):
    """Match signed logo edges per frame to delimit intervals when a corner is occupied."""
    import numpy as np

    x0, y0, x1, y1 = box[:4]
    patch = frames[:, y0:y1 + 1, x0:x1 + 1].astype(np.int16)
    dx = np.diff(patch, axis=2).reshape(len(frames), -1)
    dy = np.diff(patch, axis=1).reshape(len(frames), -1)
    gradients = np.concatenate((dx, dy), axis=1)
    ref = gradients[reference]
    median = np.median(ref, axis=0)
    votes = (ref * np.sign(median) > 3).sum(axis=0)
    reliable = (np.abs(median) >= 10) & (votes >= 0.9 * len(ref))
    x_edges = reliable[:dx.shape[1]].sum()
    y_edges = reliable[dx.shape[1]:].sum()
    if x_edges < 8 or y_edges < 8 or x_edges + y_edges < 30:
        return []
    # A moving object near a still graphic can pass the outer-ring test.
    # Require the scene to vary at the actual logo contours: the contrast
    # retains its sign while the luma on at least one side of the edge changes.
    moving = patch[reference].std(axis=0, dtype=np.float32) > 10
    changing_sides = np.concatenate(((moving[:, :-1] | moving[:, 1:]).ravel(),
                                     (moving[:-1, :] | moving[1:, :]).ravel()))
    if changing_sides[reliable].mean() < 0.5:
        return []
    expected = median[reliable]
    aligned = gradients[:, reliable] * np.sign(expected)
    score = (aligned >= np.maximum(3, 0.27 * np.abs(expected))).mean(axis=1)
    if np.median(score[reference]) < 0.84:
        return []
    present = score >= 0.67
    boundaries = [0.0] + [(a + b) / 2 for a, b in zip(times, times[1:])] + [duration]
    # Ignore isolated hits. A single noisy sample inside a stable run may miss the logo.
    present[1:-1] |= present[:-2] & present[2:]
    transitions = np.flatnonzero(np.diff(np.r_[False, present, False]))
    return [(boundaries[a], boundaries[b]) for a, b in transitions.reshape(-1, 2) if b - a >= 3]


def detect_watermarks(
    ffmpeg: str,
    info: VideoInfo,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> tuple[list[WatermarkBox], str]:
    """Sample frames across time windows and locate persistent overlays (incl. mid-video position switches)."""
    import numpy as np

    aw, ah = _analysis_size(info.width, info.height)
    frame_count = max(1, round(float(info.fps) * info.duration))
    windows = min(4, max(2, int(info.duration // 3)), max(1, frame_count // 10))
    per_window = min(16 if windows == 1 else 12, frame_count // windows)
    span = info.duration / windows
    jobs: list[tuple[int, float]] = []
    for wi in range(windows):
        for j in range(per_window):
            t = wi * span + (j + 0.5) * span / per_window
            jobs.append((wi, math.floor(t * float(info.fps)) / float(info.fps)))

    decoded, times = [], []
    indices = [[] for _ in range(windows)]
    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
        futures = [pool.submit(_extract_gray_frame, ffmpeg, info, t, aw, ah) for _, t in jobs]
        for done, ((wi, t), fut) in enumerate(zip(jobs, futures), 1):
            frame = fut.result()
            if frame is not None:
                indices[wi].append(len(decoded))
                decoded.append(frame)
                times.append(t)
            if progress_cb:
                progress_cb(done, len(futures))

    if len(decoded) < 6:
        return [], "Not enough decodable frames for watermark analysis."
    all_frames = np.stack(decoded)
    candidates = []
    static_hits = 0
    groups = [slice(None)] + [group for group in indices if windows > 1 and len(group) >= 6]
    for group in groups:
        found, static = _detect_boxes_in_frames(all_frames[group])
        static_hits += int(static)
        candidates.extend((box, group) for box in found)
    if static_hits == len(groups):
        return [], "Footage is mostly static; auto-detection skipped (use --wm-box X:Y:W:H)."

    sx, sy = info.width / float(aw), info.height / float(ah)
    regions = []
    boxes = []
    for box, reference in sorted(candidates, key=lambda c: c[0][4], reverse=True):
        if any(_box_iou(box, other) >= 0.25 for other in regions):
            continue
        x0, y0, x1, y1, _ = box
        bx = max(1, int(math.floor((x0 - 2) * sx)))
        by = max(1, int(math.floor((y0 - 2) * sy)))
        bx2 = min(info.width - 1, int(math.ceil((x1 + 3) * sx)))
        by2 = min(info.height - 1, int(math.ceil((y1 + 3) * sy)))
        if bx2 - bx < 4 or by2 - by < 4:
            continue
        runs = _logo_runs(all_frames, reference, box, times, info.duration)
        if not runs:
            continue
        regions.append(box)
        for t0, t1 in runs:
            full = t0 <= 0.0 and t1 >= info.duration
            boxes.append(WatermarkBox(bx, by, bx2 - bx, by2 - by, None if full else t0, None if full else t1))
        if len(regions) == 4:
            break
    if not boxes:
        note = "No static watermark detected."
        if static_hits:
            note += " Some segments were static; pass --wm-box X:Y:W:H if a logo remains."
        return [], note
    return boxes, f"Detected {len(regions)} watermark region(s)."


# ============================================================================================
# Loudness (two-pass EBU R128)
# ============================================================================================
def _parse_loudnorm_json(stderr_text: str) -> Optional[dict]:
    end = stderr_text.rfind("}")
    start = stderr_text.rfind("{", 0, end)
    if start < 0 or end < 0:
        return None
    try:
        stats = json.loads(stderr_text[start:end + 1])
        for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset"):
            float(stats[key])
        return stats
    except (KeyError, TypeError, ValueError):
        return None


def _loudnorm_args(lufs: float) -> str:
    return f"I={lufs:g}:TP={TARGET_TRUE_PEAK:g}:LRA={TARGET_LRA:g}"


def has_measurable_loudness(stats: Optional[dict]) -> bool:
    # FFmpeg reports -inf LUFS and inf gain for digital silence or audio
    # shorter than the 400 ms integration window.
    keys = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    return bool(stats and all(math.isfinite(float(stats[key])) for key in keys))


_STEREO_FORMAT = "aformat=sample_rates=48000:channel_layouts=stereo"


def audio_measure_filter(lufs: float) -> str:
    # Measure the mix that listeners actually hear. A multichannel downmix
    # after normalization would change both the integrated loudness and peaks.
    return f"{_STEREO_FORMAT},highpass=f=40,loudnorm={_loudnorm_args(lufs)}:print_format=json"


def build_audio_filter(measured: Optional[dict], lufs: Optional[float]) -> str:
    chain = [_STEREO_FORMAT]
    if measured is not None and lufs is not None and has_measurable_loudness(measured):
        chain.append("highpass=f=40")
        chain.append(
            f"loudnorm={_loudnorm_args(lufs)}"
            f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true:print_format=summary"
        )
    chain.append("aresample=48000")
    return ",".join(chain)


def _limit_transients(measured: dict, lufs: float) -> str:
    """Recover listening level on transient-heavy mixes with a look-ahead peak limiter."""
    gain_db = lufs - float(measured["input_i"]) + 2.5
    # Leave room for peaks introduced by resampling and lossy AAC encoding.
    limit = 10 ** ((TARGET_TRUE_PEAK - 1.5) / 20)
    return (
        f"{_STEREO_FORMAT},highpass=f=40,volume={gain_db:.2f}dB,aresample=192000,"
        f"alimiter=limit={limit:.6f}:attack=3:release=12:level=0:latency=1,aresample=48000"
    )


# ============================================================================================
# Video Filter Graph
# ============================================================================================
def build_video_filter(info: VideoInfo, plan: EncodePlan, boxes: list[WatermarkBox], show_wm: bool) -> str:
    chain = [f"fps={plan.fps.numerator}/{plan.fps.denominator}"]
    if plan.hdr_tonemap:
        chain.append(
            "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
            "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv"
        )
    if boxes:
        chain.append("format=yuv420p")
        chain.extend(b.to_filter(show_wm) for b in boxes)
    chain.append(f"scale={plan.out_w}:{plan.out_h}:flags=lanczos:out_color_matrix=bt709:out_range=tv")
    chain.append("setsar=1")
    chain.append("format=yuv420p")
    return ",".join(chain)


# ============================================================================================
# FFmpeg Execution & Verification
# ============================================================================================
def _run_ffmpeg_progress(
    cmd: list[str],
    duration: float,
    on_progress: Optional[Callable[[float], None]] = None,
) -> tuple[int, str]:
    """Run FFmpeg with -progress on stdout; stderr is spooled to a temp file to avoid pipe deadlocks."""
    with tempfile.TemporaryFile() as err_file:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err_file, stdin=subprocess.DEVNULL)
        try:
            assert proc.stdout is not None
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    try:
                        seconds = int(line.split("=", 1)[1]) / 1_000_000
                    except ValueError:
                        continue
                    if on_progress and duration > 0:
                        on_progress(min(1.0, max(0.0, seconds / duration)))
                elif line == "progress=end" and on_progress:
                    on_progress(1.0)
            proc.wait()
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if proc.stdout is not None:
                proc.stdout.close()
        # Only the final diagnostics and loudnorm JSON are needed, even for a
        # multi-hour input that emits a warning on every frame.
        err_file.seek(max(0, err_file.seek(0, os.SEEK_END) - 65536))
        stderr_text = err_file.read().decode("utf-8", "replace")
    return proc.returncode, stderr_text


def _has_faststart(path: str) -> bool:
    """Walk top-level MP4 atoms and confirm `moov` precedes `mdat`."""
    try:
        with open(path, "rb") as fh:
            file_size = os.fstat(fh.fileno()).st_size
            offset = 0
            found_moov = False
            while offset + 8 <= file_size:
                fh.seek(offset)
                header = fh.read(16)
                size = int.from_bytes(header[:4], "big")
                kind = header[4:8]
                header_size = 8
                if size == 1:
                    size = int.from_bytes(header[8:16], "big")
                    header_size = 16
                elif size == 0:
                    size = file_size - offset
                if size < header_size or size > file_size - offset:
                    return False
                if kind == b"mdat":
                    return found_moov
                if kind == b"moov":
                    found_moov = True
                offset += size
    except OSError:
        return False
    return False


def verify_output(ffprobe: str, path: str, max_bytes: int, expect_audio: bool) -> list[tuple[str, str, bool]]:
    res = _run_capture([ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path])
    if res.returncode:
        raise ValueError(res.stderr.decode("utf-8", "replace").strip() or "FFprobe could not verify the encoded MP4.")
    data = json.loads(res.stdout.decode("utf-8", "replace") or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    size = os.path.getsize(path)
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    fps = _parse_rate(v.get("avg_frame_rate", ""))
    mb_count = _macroblocks(w, h)
    faststart = _has_faststart(path)
    level = int(v.get("level") or 0)
    checks = [
        ("Codec", f"{v.get('codec_name', '?')} ({v.get('codec_tag_string', '?')})",
         v.get("codec_name") == "h264" and v.get("codec_tag_string") == "avc1"),
        ("Profile", str(v.get("profile", "?")), v.get("profile") == "High"),
        ("Level", f"{level / 10:.1f}" if level else "?", level == 31),
        ("Pix Fmt", str(v.get("pix_fmt", "?")), v.get("pix_fmt") == "yuv420p"),
        ("Resolution", f"{w}×{h}", 0 < w <= MAX_WIDTH and 0 < h <= MAX_HEIGHT
         and v.get("sample_aspect_ratio") == "1:1"),
        ("Cadence", f"{_fmt_fps(fps)} fps", 0 < mb_count <= LEVEL31_MAX_FS
         and 0 < mb_count * fps <= LEVEL31_MAX_MBPS),
    ]
    if a is not None:
        checks.append(
            ("Audio", f"{a.get('codec_name', '?')} ({a.get('codec_tag_string', '?')}) {a.get('sample_rate', '?')} Hz",
             expect_audio and a.get("codec_name") == "aac" and a.get("codec_tag_string") == "mp4a"
             and a.get("profile") == "LC" and a.get("sample_rate") == "48000" and a.get("channels") == 2)
        )
    elif expect_audio:
        checks.append(("Audio", "missing", False))
    checks.append(("Faststart", "moov before mdat" if faststart else "moov missing or misplaced", faststart))
    checks.append(("Size", f"{size:,} bytes (< {max_bytes / 1_000_000:g} MB)", size < max_bytes))
    return checks


# ============================================================================================
# Interactive Studio (Textual)
# ============================================================================================
VID_HELP_TITLE = "ghv · GitHub Video"
VID_HELP_TEXT = """[bold #FF9800]Process a video[/]
Drop a file path into the PyKuai prompt and press Enter to use the defaults.
In this Studio, enter the source path, adjust any settings, then choose Optimize.
The MP4 is saved beside the source as <source>_mobile.mp4.

[bold #FF9800]Picture and file size[/]
The output fits within 1280×720 and keeps the display aspect ratio. It uses H.264
High Profile, Level 3.1 (avc1), 8-bit yuv420p and a front-loaded MP4 index.
Short clips use high-quality encoding. Tighter size limits use two-pass encoding
and may reduce resolution or frame rate. The file must be smaller than the cap.

[bold #FF9800]Watermarks[/]
Auto looks for stationary logos and overlays that switch positions across moving
scenes. FFmpeg fills detected regions from their surroundings. For missed logos,
supply a rectangle in the displayed source frame with --wm-box X:Y:W:H.

[bold #FF9800]Audio[/]
The default target is -14 LUFS integrated with a -1.5 dBTP true-peak target.
Peak protection may keep sharp percussion quieter. The result shows the measured level.
Choose -16 LUFS for quieter playback or Off to retain the original levels.
Audio tracks are exported as AAC-LC stereo at 48 kHz.

[bold #FF9800]Examples[/]
pykuai tt ghv clip.mp4
pykuai tt ghv clip.mp4 --max-mb 50 --lufs -16 -o smaller.mp4
pykuai tt ghv clip.mp4 --analyze
pykuai tt ghv clip.mp4 --wm-box 20:20:260:90

Press Esc to cancel or F1 for help."""

def _inspect_video(path: str) -> tuple[bool, str]:
    clean = _clean_path(path)
    if not clean:
        return False, ""
    abs_p = os.path.abspath(clean)
    try:
        stat = os.stat(abs_p)
    except OSError:
        return False, "Not found"
    from pykuai.core.tools import get_ffprobe

    if not os.path.isfile(abs_p):
        return False, "Choose a video file"
    return _inspect_file(abs_p, get_ffprobe(), stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=32)
def _inspect_file(path: str, ffprobe: Optional[str], size: int, modified_ns: int) -> tuple[bool, str]:
    """Cache probe results only while the file and tool are unchanged."""
    if not ffprobe:
        return path.lower().endswith(VIDEO_EXTENSIONS), "File found (FFprobe unavailable)"
    try:
        info = probe_video(path, ffprobe)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False, "Invalid video"
    return True, (
        f"✓ {int(round(info.display_width))}×{info.height} · {_fmt_fps(info.fps)}fps · "
        f"{_fmt_clock(info.duration)} · {_fmt_mb(info.size_bytes)}"
    )


def _build_vid_studio_app(initial_path: str = ""):
    """Construct the Cyber-Dark clickable Video Optimizer Textual App (lazy-loaded)."""
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal, VerticalScroll
    from textual.widgets import Button, Input, Static
    from pykuai.core.tui import ActionChip, StudioHeader, ToggleChip, ToolStudioApp

    init_clean = os.path.abspath(_clean_path(initial_path)) if _clean_path(initial_path) else ""

    groups = {
        "wm": [("Auto", "auto"), ("Off", "off")],
        "loud": [("-14 LUFS", -14.0), ("-16 LUFS", -16.0), ("Off", None)],
        "cap": [("100 MB", 100.0), ("50 MB", 50.0), ("25 MB", 25.0)],
        "spd": [("Best", "slow"), ("Balanced", "medium"), ("Fast", "veryfast")],
    }
    labels = {"wm": "Watermark", "loud": "Loudness", "cap": "Size cap", "spd": "Speed"}

    class VidStudioApp(ToolStudioApp):
        AUTO_FOCUS = "#src-input"
        HELP_TITLE = VID_HELP_TITLE
        HELP_TEXT = VID_HELP_TEXT

        def compose(self) -> ComposeResult:
            ok, status_text = _inspect_video(init_clean)
            status_cls = "status-ok" if ok else ("status-err" if init_clean else "status-dim")
            with Container(id="studio-card"):
                yield StudioHeader.for_tool("ghv", "GitHub Video")
                with VerticalScroll(id="studio-scroll"):
                    with Horizontal(classes="field-header"):
                        yield Static("Video", classes="field-label")
                        yield Static(status_text, id="vid-status", classes=status_cls)
                    yield Input(
                        value=init_clean,
                        placeholder="Drop a video or enter its path",
                        id="src-input",
                        classes="cyber-input",
                    )
                    for key, options in groups.items():
                        with Horizontal(classes="compact-row option-row"):
                            yield Static(labels[key], classes="field-label")
                            for idx, (label, value) in enumerate(options):
                                yield ToggleChip(label, value=value, active=(idx == 0), id=f"{key}-{idx}")
                    with Horizontal(classes="compact-tight"):
                        yield Static("Output", classes="field-label")
                        yield Input(placeholder="<source>_mobile.mp4", id="out-input", classes="cyber-slim")
                    yield Static("H.264 High 3.1 · 8-bit yuv420p · AAC · faststart · ≤1280×720", classes="studio-note")

                yield Static("", id="form-error", classes="hidden-err", markup=False)
                with Horizontal(classes="action-bar"):
                    yield ActionChip("⚡ Optimize", variant_class="-primary", id="btn-run")
                    yield ActionChip("✕ Cancel", variant_class="-danger", id="btn-cancel")

        def on_mount(self) -> None:
            if init_clean:
                self.query_one("#btn-run", ActionChip).focus()

        def _group_value(self, key: str):
            for chip in self.query(ToggleChip):
                if chip.id and chip.id.startswith(f"{key}-") and chip.active:
                    return groups[key][int(chip.id.split("-")[1])][1]
            return groups[key][0][1]

        def _refresh_status(self, value: str) -> None:
            ok, msg = _inspect_video(value)
            badge = self.query_one("#vid-status", Static)
            badge.update(msg)
            badge.set_classes("status-ok" if ok else ("status-err" if _clean_path(value) else "status-dim"))

        def _set_error(self, message: str = "") -> None:
            err = self.query_one("#form-error", Static)
            err.update(message)
            err.set_classes("shown-err" if message else "hidden-err")

        def on_input_changed(self, event: Input.Changed) -> None:
            if event.input.id == "src-input":
                self._refresh_status(event.value)
                self._set_error("")

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "src-input":
                self._submit()
            elif event.input.id == "out-input":
                self._submit()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            btn = event.button
            bid = btn.id or ""
            self._set_error("")
            group = bid.split("-", 1)[0]
            if isinstance(btn, ToggleChip) and group in groups:
                for chip in self.query(ToggleChip):
                    if chip.id and chip.id.startswith(f"{group}-"):
                        chip.active = chip.id == bid
                return
            if bid == "btn-run":
                self._submit()
            elif bid == "btn-cancel":
                self.exit(None)

        def _submit(self) -> None:
            src = _clean_path(self.query_one("#src-input", Input).value)
            if not src:
                self._set_error("Drop a video or enter its path.")
                self.query_one("#src-input", Input).focus()
                return
            ok, msg = _inspect_video(src)
            if not ok:
                self._set_error(f"Invalid source video: {msg}")
                self.query_one("#src-input", Input).focus()
                return
            raw_out = _clean_path(self.query_one("#out-input", Input).value)
            out_path = os.path.abspath(raw_out) if raw_out else None
            if out_path:
                if _same_file(src, out_path):
                    self._set_error("Output path must differ from the source video.")
                elif os.path.isdir(out_path):
                    self._set_error("Choose an output file path, not a directory.")
                elif not out_path.lower().endswith(".mp4"):
                    self._set_error("Output must be an .mp4 file.")
                if self.query_one("#form-error", Static).has_class("shown-err"):
                    self.query_one("#out-input", Input).focus()
                    return
            opts = VidOptions(
                max_mb=float(self._group_value("cap")),
                wm_mode=str(self._group_value("wm")),
                lufs=self._group_value("loud"),
                preset=str(self._group_value("spd")),
            )
            self.exit((os.path.abspath(src), out_path, opts))

    return VidStudioApp()


def _launch_vid_studio(initial_path: str = ""):
    app = _build_vid_studio_app(initial_path=initial_path)
    result = app.run(mouse=True)
    sys.stdout.flush()
    return result


# ============================================================================================
# Engine
# ============================================================================================
class VidEngine(BaseEngine):
    name = "ghv"
    description = "GitHub Video (FFmpeg + NumPy)"
    usage = "tt ghv <video> [--max-mb 100] [--lufs -14] [--wm auto|off] [-o out.mp4]"
    drop_extensions = VIDEO_EXTENSIONS
    category = "Media & Video"
    requires = ["numpy>=1.24.0"]
    help_text = VID_HELP_TEXT

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("video", nargs="?", default="", help="Source video path (mp4, mov, mkv, avi, webm, flv, ...)")
        parser.add_argument("-o", "--output", help="Output .mp4 path (default: <source>_mobile.mp4)")
        parser.add_argument("--max-mb", type=float, default=DEFAULT_MAX_MB, help="Size limit from 1 to 100 decimal MB (default: 100)")
        parser.add_argument("--wm", choices=("auto", "off"), default="auto", help="Automatic watermark removal (default: auto)")
        parser.add_argument("--wm-box", type=_parse_wm_box, action="append", default=[], metavar="X:Y:W:H",
                            help="Manual watermark rectangle in source pixels; repeatable; overrides auto detection")
        parser.add_argument("--show-wm", action="store_true", help="Outline watermark regions instead of removing them (preview)")
        parser.add_argument("--lufs", type=float, default=DEFAULT_LUFS, help="Integrated loudness target in LUFS (default: -14)")
        parser.add_argument("--no-loudnorm", action="store_true", help="Keep original audio levels")
        parser.add_argument("--preset", choices=X264_PRESETS, default="slow", help="x264 speed/quality preset (default: slow)")
        parser.add_argument("--analyze", action="store_true", help="Probe, detect watermarks and print the encode plan without encoding")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        src = _clean_path(getattr(args, "video", "") or "")
        if not src:
            return self.run_interactive(console)
        if not -40.0 <= args.lufs <= -5.0:
            print_error("--lufs must be between -40 and -5.")
            return 1
        opts = VidOptions(
            max_mb=args.max_mb,
            wm_mode=args.wm,
            wm_boxes=list(args.wm_box or []),
            show_wm=args.show_wm,
            lufs=None if args.no_loudnorm else args.lufs,
            preset=args.preset,
            analyze_only=args.analyze,
        )
        out = _clean_path(args.output or "") or None
        return self._optimize(os.path.abspath(src), os.path.abspath(out) if out else None, opts, console)

    def launch_with_path(self, console: Console, path: str) -> int:
        """Process a video dropped into PyKuai using the default settings."""
        return self._optimize(os.path.abspath(_clean_path(path)), None, VidOptions(), console)

    def run_interactive(self, console: Console, initial_path: str = "") -> int:
        from pykuai.core.tui import is_interactive_tty

        if is_interactive_tty():
            selection = _launch_vid_studio(initial_path=initial_path)
            if not selection:
                console.print("[dim]› Cancelled.[/dim]")
                return 0
            src, out, opts = selection
            return self._optimize(src, out, opts, console)

        if sys.stdin is None or not sys.stdin.isatty():
            print_error("Pass a source video with pykuai tt ghv <video> [options].")
            return 1
        console.print("[bold #FF9800]GitHub Video (ghv)[/bold #FF9800]")
        try:
            raw = initial_path or Prompt.ask("[#10b981]?[/#10b981] Source video path")
        except EOFError:
            print_error("Input ended before a source video was supplied.")
            return 1
        return self._optimize(os.path.abspath(_clean_path(raw)), None, VidOptions(), console)

    # ----------------------------------------------------------------------------------------
    def _optimize(self, src: str, out_path: Optional[str], opts: VidOptions, console: Console) -> int:
        try:
            return self._process_video(src, out_path, opts, console)
        except KeyboardInterrupt:
            console.print("\n[dim]Encoding cancelled.[/dim]")
            return 130
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            print_error(escape(str(exc)))
            return 1

    def _process_video(self, src: str, out_path: Optional[str], opts: VidOptions, console: Console) -> int:
        from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeRemainingColumn
        from pykuai.core.tools import ensure_ffmpeg, get_ffprobe

        if not os.path.isfile(src):
            print_error(f"File not found: {escape(src)}")
            return 1
        out_path = out_path or _default_output_path(src, preview=opts.show_wm)
        if _same_file(src, out_path):
            print_error("Output path must differ from the source video.")
            return 1
        if not out_path.lower().endswith(".mp4") or os.path.isdir(out_path):
            print_error("Output must be an .mp4 file.")
            return 1

        ffmpeg = ensure_ffmpeg(console=console)
        ffprobe = get_ffprobe()
        if not ffmpeg or not ffprobe:
            print_error("FFmpeg and FFprobe are required. Run: pykuai tt ytd --install-ffmpeg")
            return 1
        caps = _ffmpeg_capabilities(ffmpeg)
        if caps and "libx264" not in caps:
            print_error("This FFmpeg build has no libx264 encoder. Install a GPL build (e.g. pykuai tt ytd --install-ffmpeg).")
            return 1

        print_step(f"Reading video: [bold]{escape(os.path.basename(src))}[/bold]")
        info = probe_video(src, ffprobe)
        plan = plan_encode(info, opts.max_mb, caps)

        max_bytes = int(opts.max_mb * 1_000_000)
        console.print(f"  [dim]Source:[/dim] {escape(_summarize_source(info))}")
        rc_label = (
            f"capped CRF {QUALITY_CRF} ≤ {plan.maxrate} kbps" if plan.mode == "crf"
            else f"2-pass {plan.video_kbps} kbps"
        )
        audio_target = f"AAC {plan.audio_kbps} kbps" if plan.audio_kbps else "no audio"
        console.print(
            f"  [dim]Target:[/dim] [bold #00FF00]{plan.out_w}×{plan.out_h}[/bold #00FF00] · {_fmt_fps(plan.fps)} fps · "
            f"H.264 High@L3.1 · {rc_label} · {audio_target} · < {opts.max_mb:g} MB"
        )
        for note in plan.notes:
            console.print(f"  [#FF9800]• {escape(note)}[/#FF9800]")

        def _progress() -> Progress:
            return Progress(
                SpinnerColumn(style="#00FF00"),
                TextColumn("[#10b981]{task.description}[/#10b981]"),
                BarColumn(complete_style="#00FF00", finished_style="#00FF00"),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console,
                transient=True,
            )

        # --- 1. Watermarks ---
        boxes: list[WatermarkBox] = []
        if opts.wm_boxes:
            for b in opts.wm_boxes:
                # delogo needs a neighbouring pixel on each side for interpolation.
                x, y = max(1, b.x), max(1, b.y)
                w = min(info.width - 1, b.x + b.w) - x
                h = min(info.height - 1, b.y + b.h) - y
                if w < 4 or h < 4:
                    raise ValueError(f"Watermark rectangle {b.x}:{b.y}:{b.w}:{b.h} is outside the usable frame.")
                boxes.append(WatermarkBox(x, y, w, h))
            console.print(f"  [dim]Watermark:[/dim] {len(boxes)} manual region(s)")
        elif opts.wm_mode == "auto":
            with _progress() as prog:
                task = prog.add_task("Scanning for watermarks", total=1)
                boxes, note = detect_watermarks(
                    ffmpeg, info, progress_cb=lambda d, t: prog.update(task, completed=d, total=t)
                )
            console.print(f"  [dim]Watermark:[/dim] {escape(note)}")
        else:
            console.print("  [dim]Watermark:[/dim] removal off")
        if boxes and not opts.show_wm and caps and "delogo" not in caps:
            raise ValueError("Watermark removal requires an FFmpeg build with the delogo filter.")
        for b in boxes:
            console.print(f"    [#38BDF8]▸ {escape(b.describe())}[/#38BDF8]")

        if opts.analyze_only:
            vf = build_video_filter(info, plan, boxes, opts.show_wm)
            console.print(f"  [dim]Filter:[/dim] {escape(vf)}")
            console.print("[dim]› Analyze only: no file written.[/dim]")
            return 0

        def run_ffmpeg(cmd: list[str], label: str) -> str:
            with _progress() as prog:
                task = prog.add_task(label, total=1.0)
                code, err = _run_ffmpeg_progress(cmd, info.duration, lambda f: prog.update(task, completed=f))
            if code:
                raise ValueError(f"{label} failed.\n" + "\n".join(err.splitlines()[-8:]))
            return err

        def measure_audio(path: str, stream: str, audio_filter: str, label: str) -> dict:
            cmd = [
                ffmpeg, "-hide_banner", "-nostdin", "-progress", "pipe:1", "-nostats",
                "-i", path, "-map", stream, "-af", audio_filter, "-f", "null", "-",
            ]
            stats = _parse_loudnorm_json(run_ffmpeg(cmd, label))
            if stats is None:
                raise ValueError(f"{label} returned no loudness measurements.")
            return stats

        measured = None
        lufs = opts.lufs if info.audio_index is not None else None
        if lufs is not None:
            measured = measure_audio(src, f"0:{info.audio_index}", audio_measure_filter(lufs), "Measuring loudness")
            if not has_measurable_loudness(measured):
                console.print("  [dim]Loudness:[/dim] too short or quiet to measure, levels kept")
                measured = None
            else:
                console.print(
                    f"  [dim]Loudness:[/dim] {float(measured['input_i']):.1f} LUFS → [bold #00FF00]{lufs:g} LUFS[/bold #00FF00] "
                    f"(TP {TARGET_TRUE_PEAK:g} dBTP)"
                )
        af = build_audio_filter(measured, lufs)
        vf = build_video_filter(info, plan, boxes, opts.show_wm)

        # --- 3. Encode (with automatic size verification & retry) ---
        out_dir = os.path.dirname(out_path) or "."
        os.makedirs(out_dir, exist_ok=True)
        aac_options = [
            "-c:a", "aac", "-profile:a", "aac_low", "-tag:a", "mp4a",
            "-b:a", f"{plan.audio_kbps}k", "-ar", "48000", "-ac", "2",
        ]
        mux_options = [
            "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
            "-tag:v", "avc1", "-movflags", "+faststart", "-f", "mp4",
        ]

        def _encode_cmd(pass_no: int) -> list[str]:
            cmd = [
                ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "warning", "-progress", "pipe:1", "-nostats",
                "-i", src, "-map", f"0:{info.video_index}",
            ]
            with_audio = pass_no != 1 and info.audio_index is not None and plan.audio_kbps > 0
            if with_audio:
                cmd += ["-map", f"0:{info.audio_index}"]
            cmd += [
                "-vf", vf, "-c:v", "libx264", "-preset", opts.preset, "-profile:v", "high", "-level:v", "3.1",
                "-8x8dct", "1", "-pix_fmt", "yuv420p", "-refs", str(plan.refs), "-g", str(plan.gop),
                "-keyint_min", str(max(1, plan.gop // 2)),
                "-colorspace", "bt709", "-color_range", "tv",
            ]
            if plan.mode == "crf":
                cmd += ["-crf", str(QUALITY_CRF), "-maxrate", f"{plan.maxrate}k", "-bufsize", f"{plan.bufsize}k"]
            else:
                cmd += [
                    "-b:v", f"{plan.video_kbps}k", "-maxrate", f"{plan.maxrate}k", "-bufsize", f"{plan.bufsize}k",
                    "-pass", str(pass_no), "-passlogfile", passlog,
                ]
            if pass_no == 1:
                return cmd + ["-an", "-sn", "-dn", "-f", "null", "-"]
            if with_audio:
                cmd += ["-af", af, *aac_options]
            else:
                cmd += ["-an"]
            return cmd + mux_options + [tmp_out]

        def check_audio(candidate: str, scratch: str) -> tuple[float, float]:
            """Verify decoded AAC and, when necessary, remix only the original audio."""
            probe_filter = f"loudnorm={_loudnorm_args(lufs)}:print_format=json"
            audio_filter = af
            corrected = os.path.join(scratch, "audio-corrected.mp4")
            for attempt in range(4):
                stats = measure_audio(candidate, "0:a:0", probe_filter, "Verifying AAC loudness")
                loudness, peak = float(stats["input_i"]), float(stats["input_tp"])
                if not math.isfinite(loudness) or not math.isfinite(peak):
                    raise ValueError("The encoded AAC track has no measurable audio.")
                if peak <= TARGET_TRUE_PEAK and loudness <= lufs + 1.0:
                    if attempt or loudness >= lufs - 1.0:
                        return loudness, peak
                if attempt == 3:
                    raise ValueError(f"AAC verification measured {loudness:.1f} LUFS and {peak:.1f} dBTP.")
                if attempt == 0 and loudness < lufs - 1.0:
                    audio_filter = _limit_transients(measured, lufs)
                else:
                    margin = 0.2 if attempt == 0 else 0.6
                    attenuation = max(peak - TARGET_TRUE_PEAK, loudness - lufs, 0.0) + margin
                    audio_filter += f",volume=-{attenuation:.2f}dB"
                run_ffmpeg([
                    ffmpeg, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats",
                    "-i", candidate, "-i", src, "-map", "0:v:0", "-c:v", "copy",
                    "-map", f"1:{info.audio_index}", "-af", audio_filter, *aac_options, *mux_options, corrected,
                ], "Correcting AAC loudness")
                os.replace(corrected, candidate)

        with tempfile.TemporaryDirectory(prefix=".ghv-", dir=out_dir) as work_dir:
            # Keep the candidate on the destination volume so publication is atomic.
            tmp_out = os.path.join(work_dir, "candidate.mp4")
            passlog = os.path.join(work_dir, "x264pass")
            output_audio = None
            for attempt in range(3):
                for p in ([0] if plan.mode == "crf" else [1, 2]):
                    run_ffmpeg(_encode_cmd(p), "Encoding (CRF)" if p == 0 else f"Encoding pass {p}/2")
                size = os.path.getsize(tmp_out)
                if size < max_bytes and measured is not None:
                    output_audio = check_audio(tmp_out, work_dir)
                    size = os.path.getsize(tmp_out)
                if size < max_bytes:
                    break
                if attempt == 2:
                    raise ValueError(f"The encoded file still reached or exceeded the {opts.max_mb:g} MB limit.")
                # Subtract the measured excess from the video budget. Audio and mux overhead remain.
                excess_kbps = math.ceil((size - max_bytes * 0.95) * 8 / (1000 * info.duration))
                base_kbps = min(plan.video_kbps, plan.maxrate)
                new_kbps = max(MIN_VIDEO_KBPS, base_kbps - excess_kbps)
                if new_kbps >= base_kbps:
                    raise ValueError("The audio and MP4 overhead leave too little room for video.")
                print_warning(f"Candidate is {size:,} bytes. Retrying at {new_kbps} kbps.")
                plan.mode = "2pass"
                plan.video_kbps = new_kbps
                plan.maxrate = min(plan.video_kbps * 2, LEVEL31_HIGH_MAX_KBPS)
                plan.bufsize = min(plan.maxrate * 2, LEVEL31_HIGH_MAX_CPB_KBIT)

            checks = verify_output(ffprobe, tmp_out, max_bytes, expect_audio=info.audio_index is not None)
            if output_audio is not None:
                loudness, peak = output_audio
                if loudness < lufs - 1.0:
                    print_warning(f"Peak protection kept the audio at {loudness:.1f} LUFS (target {lufs:g}).")
                checks.append(("Loudness", f"{loudness:.1f} LUFS · TP {peak:.1f} dBTP", True))
            failures = [f"{label}: {value}" for label, value, ok in checks if not ok]
            if failures:
                raise ValueError("Output failed verification. " + ", ".join(failures))
            os.replace(tmp_out, out_path)

        lines = [
            "[bold #00FF00]Mobile-ready MP4 written[/bold #00FF00]",
            f"  [bold #E0E0E0]Out:[/bold #E0E0E0]    [bold #00FF00]{escape(out_path)}[/bold #00FF00]",
            f"  [bold #E0E0E0]Mark:[/bold #E0E0E0]   "
            + (f"{len(boxes)} region(s) {'outlined' if opts.show_wm else 'removed'}" if boxes else "none"),
        ]
        for label, value, ok in checks:
            mark = "[#00FF00]✓[/#00FF00]" if ok else "[#FF5252]✗[/#FF5252]"
            lines.append(f"  {mark} [bold #E0E0E0]{label + ':':<11}[/bold #E0E0E0] {escape(value)}")
        console.print()
        console.print(Panel("\n".join(lines), border_style="#10b981", box=box.ROUNDED, expand=False))
        return 0
