# -*- coding: utf-8 -*-
"""
PyKuai Retro SFX Audio Engine
Zero-dependency non-blocking sound effects powered by CC0 WAV assets.
"""
from __future__ import annotations

import atexit
from array import array
import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Optional

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "sfx"
_CONFIG_PATH = Path.home() / ".pykuai" / "settings.json"
_SFX_FILES = {
    "snake": "snake.wav",
    "type": "type.wav",
    "key": "key.wav",
    "enter": "enter.wav",
    "click": "click.wav",
    "paste": "paste.wav",
}
_SFX_CACHE: Optional[bool] = None
_PCM_CACHE: dict[str, Optional[array]] = {}
_PCM_LOCK = threading.Lock()

_TARGET_RATE = 44100
_TARGET_CHANNELS = 2
_CHUNK_FRAMES = 441  # 10 ms at 44.1 kHz
_CHUNK_SAMPLES = _CHUNK_FRAMES * _TARGET_CHANNELS
_CHUNK_BYTES = _CHUNK_SAMPLES * 2
_RING_BUFFERS = 6
_COLD_LEAD_IN_SEC = 0.14


def _load_wav_pcm(wav_path: Path) -> Optional[array]:
    """Decode an uncompressed PCM WAV asset into 44.1 kHz 16-bit interleaved stereo samples."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            if nframes <= 0 or nchannels <= 0:
                return None
            raw = wf.readframes(nframes)
    except Exception:
        return None

    if sampwidth == 1:
        samples = array("h", ((b - 128) << 8 for b in raw))
    elif sampwidth == 2:
        samples = array("h")
        samples.frombytes(raw)
        if sys.byteorder != "little":
            samples.byteswap()
    else:
        return None

    if nchannels == 1:
        stereo = array("h", [0]) * (len(samples) * 2)
        stereo[0::2] = samples
        stereo[1::2] = samples
    elif nchannels == 2:
        stereo = samples
    else:
        frame_count = len(samples) // nchannels
        stereo = array("h", [0]) * (frame_count * 2)
        stereo[0::2] = samples[0::nchannels]
        stereo[1::2] = samples[1::nchannels]

    if framerate != _TARGET_RATE and framerate > 0:
        src_frames = len(stereo) // 2
        if src_frames < 2:
            return stereo
        dst_frames = max(1, int(round(src_frames * _TARGET_RATE / framerate)))
        resampled = array("h", [0]) * (dst_frames * 2)
        scale = (src_frames - 1) / max(1, dst_frames - 1) if dst_frames > 1 else 0.0
        for i in range(dst_frames):
            pos = i * scale
            idx = int(pos)
            frac = pos - idx
            nxt = min(idx + 1, src_frames - 1)
            l0, r0 = stereo[idx * 2], stereo[idx * 2 + 1]
            l1, r1 = stereo[nxt * 2], stereo[nxt * 2 + 1]
            resampled[i * 2] = int(l0 + (l1 - l0) * frac)
            resampled[i * 2 + 1] = int(r0 + (r1 - r0) * frac)
        return resampled

    return stereo


def _finalize_stereo_pcm(
    buf_l: list[float],
    buf_r: list[float],
    rate: int,
    peak_limit: float = 20500.0,
) -> array:
    """Apply DC-removal, raised-cosine boundary fades, and soft limiting so zero clicks/pops occur."""
    import math

    n = min(len(buf_l), len(buf_r))
    if n <= 0:
        return array("h")

    # 1. Remove any tiny DC offset so endpoints sit cleanly at zero crossing
    mean_l = sum(buf_l) / n
    mean_r = sum(buf_r) / n

    fade_in = min(n // 4, max(1, int(rate * 0.008)))
    fade_out = min(n // 3, max(1, int(rate * 0.020)))

    # Compute raw peak for clean headroom normalization + soft tanh limiter
    max_abs = 1e-6
    for i in range(n):
        vl = abs(buf_l[i] - mean_l)
        vr = abs(buf_r[i] - mean_r)
        if vl > max_abs:
            max_abs = vl
        if vr > max_abs:
            max_abs = vr

    gain = 1.0 / max(1.0, max_abs)
    stereo = array("h", [0]) * (n * 2)
    for i in range(n):
        env = 1.0
        if i < fade_in:
            env *= 0.5 * (1.0 - math.cos(math.pi * i / fade_in))
        if i >= n - fade_out:
            rem = n - 1 - i
            env *= 0.5 * (1.0 - math.cos(math.pi * rem / fade_out))

        xl = (buf_l[i] - mean_l) * gain * env
        xr = (buf_r[i] - mean_r) * gain * env
        # Soft-knee tanh limiting prevents harsh digital clipping pops
        sl = int(math.tanh(xl * 1.15) / math.tanh(1.15) * peak_limit)
        sr = int(math.tanh(xr * 1.15) / math.tanh(1.15) * peak_limit)
        stereo[i * 2] = max(-32000, min(32000, sl))
        stereo[i * 2 + 1] = max(-32000, min(32000, sr))
    return stereo


def _synth_procedural_pcm(name: str) -> Optional[array]:
    """Synthesize smooth, click-free 44.1 kHz 16-bit stereo PCM for cutscene & XP SFX."""
    import math
    import random

    rate = _TARGET_RATE
    rng = random.Random(42)

    if name == "door_close":
        dur = 0.70
        n_frames = int(rate * dur)
        buf_l = [0.0] * n_frames
        buf_r = [0.0] * n_frames
        phase = 0.0
        lp = 0.0
        for i in range(n_frames):
            t = i / rate
            val = 0.0
            if t < 0.23:
                env = math.sin((t / 0.23) * math.pi) ** 1.4 * 0.18
                freq = 260.0 - 85.0 * (t / 0.23) + 14.0 * math.sin(t * 50.0)
                phase += 2.0 * math.pi * freq / rate
                val = (math.sin(phase) + 0.30 * math.sin(phase * 2.05)) * env
            elif 0.25 <= t < 0.30:
                dt = t - 0.25
                att = min(1.0, dt / 0.005)
                env = att * math.exp(-dt * 85.0) * 0.45
                latch_raw = math.sin(2.0 * math.pi * 1450.0 * dt) * 0.70 + rng.uniform(-0.22, 0.22)
                lp = lp * 0.72 + latch_raw * 0.28
                val = lp * env
            elif t >= 0.31:
                dt = t - 0.31
                # Smooth 6ms cosine attack ramp avoids instantaneous step pop!
                att = 0.5 * (1.0 - math.cos(math.pi * min(1.0, dt / 0.006)))
                env = att * math.exp(-dt * 14.0) * 0.88
                freq = 46.0 + 88.0 * math.exp(-dt * 26.0)
                phase += 2.0 * math.pi * freq / rate
                sub = math.sin(phase) + 0.38 * math.sin(phase * 1.5)
                noise = rng.uniform(-0.28, 0.28) * math.exp(-dt * 42.0)
                lp = lp * 0.84 + (sub + noise) * 0.16
                val = lp * env
            buf_l[i] = val
            buf_r[i] = val
        return _finalize_stereo_pcm(buf_l, buf_r, rate, peak_limit=20000.0)

    if name == "footsteps":
        dur = 0.94
        n_frames = int(rate * dur)
        buf_l = [0.0] * n_frames
        buf_r = [0.0] * n_frames
        step_times = (0.03, 0.21, 0.38, 0.54, 0.70)
        for st_idx, st_t in enumerate(step_times):
            start_i = int(st_t * rate)
            step_len = int(0.11 * rate)
            pan_l = 0.85 if st_idx % 2 == 0 else 0.55
            pan_r = 0.55 if st_idx % 2 == 0 else 0.85
            pitch_mul = 1.0 + (st_idx % 2) * 0.12
            lp = 0.0
            for k in range(step_len):
                idx = start_i + k
                if idx >= n_frames:
                    break
                dt = k / rate
                att = min(1.0, dt / 0.006)
                rel = min(1.0, (step_len - 1 - k) / (rate * 0.015))
                env = att * rel * math.exp(-dt * 42.0) * 0.48
                freq = (66.0 + 96.0 * math.exp(-dt * 52.0)) * pitch_mul
                raw = math.sin(2.0 * math.pi * freq * dt) + rng.uniform(-0.2, 0.2) * math.exp(-dt * 65.0)
                lp = lp * 0.72 + raw * 0.28
                buf_l[idx] += lp * env * pan_l
                buf_r[idx] += lp * env * pan_r
        return _finalize_stereo_pcm(buf_l, buf_r, rate, peak_limit=17500.0)

    if name == "pc_boot":
        # Clean mechanical switch click -> CRT degauss coil hum -> warm beveled BIOS POST beep (zero square step pops!)
        dur = 0.76
        n_frames = int(rate * dur)
        buf_l = [0.0] * n_frames
        buf_r = [0.0] * n_frames
        for i in range(n_frames):
            t = i / rate
            val = 0.0
            if 0.005 <= t < 0.065:
                dt = t - 0.005
                att = 0.5 * (1.0 - math.cos(math.pi * min(1.0, dt / 0.004)))
                env = att * math.exp(-dt * 72.0) * 0.55
                val += (math.sin(2.0 * math.pi * 920.0 * dt) * 0.75 + math.sin(2.0 * math.pi * 1840.0 * dt) * 0.25) * env
            if 0.08 <= t < 0.42:
                dt = t - 0.08
                env = math.sin((dt / 0.34) * math.pi) ** 1.2 * 0.34
                val += (
                    math.sin(2.0 * math.pi * 100.0 * dt) * 0.62
                    + math.sin(2.0 * math.pi * 200.0 * dt) * 0.28
                    + math.sin(2.0 * math.pi * 300.0 * dt) * 0.10
                ) * env
            if 0.44 <= t < 0.68:
                # Warm band-limited BIOS POST tone (8ms fade-in + 25ms fade-out = ZERO pop!)
                dt = t - 0.44
                att = 0.5 * (1.0 - math.cos(math.pi * min(1.0, dt / 0.008)))
                rem = 0.68 - t
                rel = 0.5 * (1.0 - math.cos(math.pi * min(1.0, rem / 0.025)))
                env = att * rel * 0.38
                w = 2.0 * math.pi * 880.0 * dt
                tone = math.sin(w) + 0.22 * math.sin(3.0 * w) + 0.08 * math.sin(5.0 * w)
                val += tone * env
            buf_l[i] = val
            buf_r[i] = val
        return _finalize_stereo_pcm(buf_l, buf_r, rate, peak_limit=18500.0)

    if name == "xp_startup":
        # Velvety E-flat major Windows XP chime (smooth cosine envelopes, zero clipping/crackle!)
        dur = 2.15
        n_frames = int(rate * dur)
        buf_l = [0.0] * n_frames
        buf_r = [0.0] * n_frames
        notes = (
            (0.02, 0.80, (311.13, 466.16, 783.99), -0.14),
            (0.38, 0.80, (207.65, 311.13, 523.25, 698.46), 0.14),
            (0.78, 0.72, (233.08, 349.23, 587.33), -0.10),
            (1.12, 0.98, (155.56, 311.13, 392.00, 466.16, 622.25), 0.0),
        )
        for st_t, n_dur, freqs, pan in notes:
            i0 = int(st_t * rate)
            n_len = int(n_dur * rate)
            gl = 0.85 - pan * 0.18
            gr = 0.85 + pan * 0.18
            norm_k = 0.34 / max(1.0, len(freqs) ** 0.55)
            for k in range(n_len):
                idx = i0 + k
                if idx >= n_frames:
                    break
                dt = k / rate
                att = 0.5 * (1.0 - math.cos(math.pi * min(1.0, dt / 0.032)))
                rel = 0.5 * (1.0 - math.cos(math.pi * min(1.0, (n_len - 1 - k) / (rate * 0.045))))
                decay = math.exp(-dt * 3.0)
                env = att * rel * decay * norm_k
                sig = 0.0
                for f in freqs:
                    w = 2.0 * math.pi * f * dt
                    sig += math.sin(w) + 0.24 * math.sin(w * 2.0) * math.exp(-dt * 5.0)
                sample = sig * env
                buf_l[idx] += sample * gl
                buf_r[idx] += sample * gr
        return _finalize_stereo_pcm(buf_l, buf_r, rate, peak_limit=19500.0)

    return None


def _get_cached_pcm(name: str, wav_path: Optional[Path] = None) -> Optional[array]:
    with _PCM_LOCK:
        if name in _PCM_CACHE:
            return _PCM_CACHE[name]
    data = _load_wav_pcm(wav_path) if (wav_path is not None and wav_path.is_file()) else _synth_procedural_pcm(name)
    with _PCM_LOCK:
        _PCM_CACHE.setdefault(name, data)
        return _PCM_CACHE[name]


def warmup_arcade_sfx() -> None:
    """Asynchronously pre-synthesize cutscene & XP startup SFX off the UI thread."""
    if sys.platform != "win32" or not is_sfx_enabled():
        return

    def _prewarm() -> None:
        for sfx_name in ("door_close", "footsteps", "pc_boot", "xp_startup"):
            try:
                _get_cached_pcm(sfx_name, None)
            except Exception:
                pass

    _MIXER.ensure_started()
    threading.Thread(target=_prewarm, name="pykuai-arcade-prewarm", daemon=True).start()


if sys.platform == "win32":
    from ctypes import wintypes

    class _WAVEFORMATEX(ctypes.Structure):
        _fields_ = [
            ("wFormatTag", ctypes.c_uint16),
            ("nChannels", ctypes.c_uint16),
            ("nSamplesPerSec", ctypes.c_uint32),
            ("nAvgBytesPerSec", ctypes.c_uint32),
            ("nBlockAlign", ctypes.c_uint16),
            ("wBitsPerSample", ctypes.c_uint16),
            ("cbSize", ctypes.c_uint16),
        ]

    class _WAVEHDR(ctypes.Structure):
        _fields_ = [
            ("lpData", ctypes.c_void_p),
            ("dwBufferLength", ctypes.c_uint32),
            ("dwBytesRecorded", ctypes.c_uint32),
            ("dwUser", ctypes.c_size_t),
            ("dwFlags", ctypes.c_uint32),
            ("dwLoops", ctypes.c_uint32),
            ("lpNext", ctypes.c_void_p),
            ("reserved", ctypes.c_size_t),
        ]


class _WinMMMixer:
    """
    Persistent low-latency polyphonic Windows waveOut audio mixer.
    Keeps the audio endpoint continuously open while SFX is enabled so ultra-short
    19-77 ms clicks/keystrokes are never swallowed by driver/Bluetooth/DSP fade-in.
    """

    _WAVE_MAPPER = 0xFFFFFFFF
    _CALLBACK_EVENT = 0x00050000
    _WHDR_DONE = 0x00000001
    _WHDR_PREPARED = 0x00000002

    def __init__(self) -> None:
        self._state_lock = threading.Lock()
        self._voices_lock = threading.Lock()
        self._voices: list[list] = []
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ready_event = threading.Event()
        self._started_ok = False
        self._unavailable = False
        self._opened_at = 0.0
        self._winmm = None
        self._kernel32 = None
        self._h_event: Optional[int] = None
        self._h_out: Optional[ctypes.c_void_p] = None
        self._buffers: list = []
        self._headers: list = []

    def _bind_apis(self) -> bool:
        if self._winmm is not None and self._kernel32 is not None:
            return True
        try:
            winmm = ctypes.WinDLL("winmm")
            kernel32 = ctypes.WinDLL("kernel32")

            winmm.waveOutOpen.argtypes = [
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.c_uint,
                ctypes.POINTER(_WAVEFORMATEX),
                ctypes.c_size_t,
                ctypes.c_size_t,
                ctypes.c_uint32,
            ]
            winmm.waveOutOpen.restype = ctypes.c_uint
            winmm.waveOutPrepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WAVEHDR), ctypes.c_uint]
            winmm.waveOutPrepareHeader.restype = ctypes.c_uint
            winmm.waveOutUnprepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WAVEHDR), ctypes.c_uint]
            winmm.waveOutUnprepareHeader.restype = ctypes.c_uint
            winmm.waveOutWrite.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WAVEHDR), ctypes.c_uint]
            winmm.waveOutWrite.restype = ctypes.c_uint
            winmm.waveOutReset.argtypes = [ctypes.c_void_p]
            winmm.waveOutReset.restype = ctypes.c_uint
            winmm.waveOutClose.argtypes = [ctypes.c_void_p]
            winmm.waveOutClose.restype = ctypes.c_uint

            kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateEventW.restype = ctypes.c_void_p
            kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel32.WaitForSingleObject.restype = ctypes.c_uint32
            kernel32.SetEvent.argtypes = [ctypes.c_void_p]
            kernel32.SetEvent.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = wintypes.BOOL

            self._winmm = winmm
            self._kernel32 = kernel32
            return True
        except Exception:
            return False

    def ensure_started(self) -> bool:
        if sys.platform != "win32" or self._unavailable:
            return False

        with self._state_lock:
            if self._thread is not None and self._thread.is_alive() and self._started_ok:
                return True
            if self._unavailable or not self._bind_apis():
                self._unavailable = True
                return False

            self._stop_event.clear()
            self._ready_event.clear()
            self._started_ok = False
            self._thread = threading.Thread(target=self._run, name="pykuai-sfx", daemon=True)
            self._thread.start()
            self._ready_event.wait(timeout=1.0)
            if not self._started_ok:
                self._unavailable = True
                return False
            return True

    def enqueue(self, pcm: array) -> bool:
        if not self.ensure_started():
            return False

        elapsed = time.monotonic() - self._opened_at
        if elapsed < _COLD_LEAD_IN_SEC:
            lead_frames = int((_COLD_LEAD_IN_SEC - elapsed) * _TARGET_RATE)
            start_pos = -(lead_frames * _TARGET_CHANNELS)
        else:
            start_pos = 0

        with self._voices_lock:
            # Cap simultaneous voices to prevent runaway clipping on key repeat bursts
            if len(self._voices) >= 16:
                self._voices.pop(0)
            self._voices.append([pcm, start_pos])
        return True

    def clear_voices(self) -> None:
        with self._voices_lock:
            self._voices.clear()

    def has_active_voices(self) -> bool:
        with self._voices_lock:
            return bool(self._voices)

    def close(self, drain_timeout: float = 0.0) -> None:
        if drain_timeout > 0:
            deadline = time.monotonic() + drain_timeout
            while time.monotonic() < deadline and self.has_active_voices():
                time.sleep(0.01)

        with self._state_lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_event.set()
            if self._kernel32 is not None and self._h_event:
                try:
                    self._kernel32.SetEvent(self._h_event)
                except Exception:
                    pass
            thread.join(timeout=0.5)
            self._thread = None
            self._started_ok = False
        self.clear_voices()

    def _mix_into(self, buf_ptr: int, scratch_out: array) -> None:
        with self._voices_lock:
            if not self._voices:
                ctypes.memset(buf_ptr, 0, _CHUNK_BYTES)
                return

            # Fast zero-copy path for single active voice without pre-roll offset
            if len(self._voices) == 1 and self._voices[0][1] >= 0:
                voice = self._voices[0]
                pcm, pos = voice[0], voice[1]
                avail = len(pcm) - pos
                if avail >= _CHUNK_SAMPLES:
                    pcm_addr = pcm.buffer_info()[0] + pos * 2
                    ctypes.memmove(buf_ptr, pcm_addr, _CHUNK_BYTES)
                    voice[1] = pos + _CHUNK_SAMPLES
                    if voice[1] >= len(pcm):
                        self._voices.clear()
                    return
                if avail > 0:
                    pcm_addr = pcm.buffer_info()[0] + pos * 2
                    copy_bytes = avail * 2
                    ctypes.memmove(buf_ptr, pcm_addr, copy_bytes)
                    ctypes.memset(buf_ptr + copy_bytes, 0, _CHUNK_BYTES - copy_bytes)
                else:
                    ctypes.memset(buf_ptr, 0, _CHUNK_BYTES)
                self._voices.clear()
                return

            acc = [0] * _CHUNK_SAMPLES
            surviving: list[list] = []
            for voice in self._voices:
                pcm, pos = voice[0], voice[1]
                skip = -pos if pos < 0 else 0
                if skip < _CHUNK_SAMPLES:
                    src_start = 0 if pos < 0 else pos
                    take = min(_CHUNK_SAMPLES - skip, len(pcm) - src_start)
                    for idx in range(take):
                        acc[skip + idx] += pcm[src_start + idx]
                new_pos = pos + _CHUNK_SAMPLES
                if new_pos < len(pcm):
                    voice[1] = new_pos
                    surviving.append(voice)
            self._voices = surviving

        for idx, sample in enumerate(acc):
            if sample > 32767:
                scratch_out[idx] = 32767
            elif sample < -32768:
                scratch_out[idx] = -32768
            else:
                scratch_out[idx] = sample
        ctypes.memmove(buf_ptr, scratch_out.buffer_info()[0], _CHUNK_BYTES)

    def _run(self) -> None:
        assert self._winmm is not None and self._kernel32 is not None
        winmm = self._winmm
        kernel32 = self._kernel32

        h_event = kernel32.CreateEventW(None, False, False, None)
        if not h_event:
            self._ready_event.set()
            return

        wfx = _WAVEFORMATEX(
            wFormatTag=1,
            nChannels=_TARGET_CHANNELS,
            nSamplesPerSec=_TARGET_RATE,
            nAvgBytesPerSec=_TARGET_RATE * _TARGET_CHANNELS * 2,
            nBlockAlign=_TARGET_CHANNELS * 2,
            wBitsPerSample=16,
            cbSize=0,
        )
        h_out = ctypes.c_void_p()
        rc = winmm.waveOutOpen(
            ctypes.byref(h_out),
            self._WAVE_MAPPER,
            ctypes.byref(wfx),
            int(h_event),
            0,
            self._CALLBACK_EVENT,
        )
        if rc != 0 or not h_out.value:
            kernel32.CloseHandle(h_event)
            self._ready_event.set()
            return

        self._h_event = h_event
        self._h_out = h_out
        buffers = [(ctypes.c_char * _CHUNK_BYTES)() for _ in range(_RING_BUFFERS)]
        headers = []
        hdr_size = ctypes.sizeof(_WAVEHDR)

        try:
            for buf in buffers:
                hdr = _WAVEHDR(
                    lpData=ctypes.addressof(buf),
                    dwBufferLength=_CHUNK_BYTES,
                    dwBytesRecorded=0,
                    dwUser=0,
                    dwFlags=0,
                    dwLoops=0,
                    lpNext=None,
                    reserved=0,
                )
                if winmm.waveOutPrepareHeader(h_out, ctypes.byref(hdr), hdr_size) != 0:
                    raise RuntimeError("waveOutPrepareHeader failed")
                headers.append(hdr)
                if winmm.waveOutWrite(h_out, ctypes.byref(hdr), hdr_size) != 0:
                    raise RuntimeError("waveOutWrite failed")

            self._buffers = buffers
            self._headers = headers
            self._opened_at = time.monotonic()
            self._started_ok = True
            self._ready_event.set()

            scratch_out = array("h", [0]) * _CHUNK_SAMPLES
            while not self._stop_event.is_set():
                kernel32.WaitForSingleObject(h_event, 100)
                if self._stop_event.is_set():
                    break
                for hdr in headers:
                    if hdr.dwFlags & self._WHDR_DONE:
                        self._mix_into(hdr.lpData, scratch_out)
                        winmm.waveOutWrite(h_out, ctypes.byref(hdr), hdr_size)
        except Exception:
            if not self._ready_event.is_set():
                self._ready_event.set()
        finally:
            try:
                winmm.waveOutReset(h_out)
                for hdr in headers:
                    if hdr.dwFlags & self._WHDR_PREPARED:
                        winmm.waveOutUnprepareHeader(h_out, ctypes.byref(hdr), hdr_size)
                winmm.waveOutClose(h_out)
            except Exception:
                pass
            try:
                kernel32.CloseHandle(h_event)
            except Exception:
                pass
            self._buffers = []
            self._headers = []
            self._h_out = None
            self._h_event = None


_MIXER = _WinMMMixer()


def _load_persisted_state() -> bool:
    env_override = os.environ.get("PYKUAI_SFX", "").strip().lower()
    if env_override in {"0", "false", "off", "no"}:
        return False
    if env_override in {"1", "true", "on", "yes"}:
        return True

    try:
        if _CONFIG_PATH.exists():
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "sfx_enabled" in data:
                return bool(data["sfx_enabled"])
    except Exception:
        pass
    return True


def _save_persisted_state(enabled: bool) -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {}
        if _CONFIG_PATH.exists():
            try:
                loaded = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload = loaded
            except Exception:
                pass
        payload["sfx_enabled"] = bool(enabled)
        _CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def is_sfx_enabled() -> bool:
    """Return whether retro UI & snake sound effects are currently enabled."""
    global _SFX_CACHE
    if _SFX_CACHE is None:
        _SFX_CACHE = _load_persisted_state()
    return _SFX_CACHE


def set_sfx_enabled(enabled: bool) -> bool:
    """Persist and apply retro SFX state."""
    global _SFX_CACHE
    _SFX_CACHE = bool(enabled)
    _save_persisted_state(_SFX_CACHE)
    if not _SFX_CACHE:
        stop_sfx()
        _MIXER.close()
    return _SFX_CACHE


def toggle_sfx() -> bool:
    """Flip SFX state; chime when enabled or silence immediately when muted."""
    new_state = set_sfx_enabled(not is_sfx_enabled())
    if new_state:
        play_sfx("click")
    return new_state


def warmup_sfx() -> None:
    """Pre-open the persistent audio mixer so the first keystroke/click is never clipped."""
    if sys.platform == "win32" and is_sfx_enabled():
        _MIXER.ensure_started()


def stop_sfx() -> None:
    """Immediately stop any active asynchronous Windows audio playback."""
    if sys.platform != "win32":
        return
    _MIXER.clear_voices()
    try:
        import winsound

        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


def shutdown_sfx() -> None:
    """Drain short trailing UI SFX briefly and close the persistent audio stream on exit."""
    if sys.platform == "win32":
        _MIXER.close(drain_timeout=0.18)


atexit.register(shutdown_sfx)


def play_sfx(name: str) -> None:
    """Play a named retro sound effect ('snake', 'type', 'key', 'enter', 'click', 'paste', 'door_close', 'footsteps', 'pc_boot') cleanly."""
    if not is_sfx_enabled():
        return

    if name in ("door_close", "footsteps", "pc_boot", "xp_startup"):
        if sys.platform == "win32":
            pcm = _get_cached_pcm(name, None)
            if pcm is not None:
                _MIXER.enqueue(pcm)
        return

    filename = _SFX_FILES.get(name)
    if not filename:
        return

    wav_path = _ASSETS_DIR / filename
    if not wav_path.is_file():
        return

    if sys.platform == "win32":
        pcm = _get_cached_pcm(name, wav_path)
        if pcm is not None and _MIXER.enqueue(pcm):
            return
        try:
            import winsound

            winsound.PlaySound(
                str(wav_path),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
        except Exception:
            pass
        return

    for player in ("afplay", "paplay", "aplay"):
        exe = shutil.which(player)
        if exe:
            try:
                subprocess.Popen(
                    [exe, str(wav_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
            return
