# -*- coding: utf-8 -*-
"""
万能视频极限压缩引擎 (基于 FFmpeg 码率推算与精准体积压制)
"""
import os
import re
import argparse
import subprocess
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from pykuai.core.base import BaseEngine
from pykuai.core.tools import get_ffmpeg, get_ffprobe
from pykuai.core.ui import print_success, print_error, print_warning, print_info, print_step, create_progress


class VideoCompressEngine(BaseEngine):
    name = "video-compress"
    aliases = ["compress-video", "vid-min", "vcompress"]
    description = "万能视频极限压缩引擎 (自动解析时长推算最佳码率，压缩至指定 MB 体积)"
    category = "多媒体与图像"

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="待压缩的源视频文件路径")
        parser.add_argument("-t", "--target-mb", type=float, default=25.0, help="期望压缩到的目标体积 (MB，默认 25)")
        parser.add_argument("-o", "--output", help="输出视频文件路径 (默认 *_min.mp4)")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        video_path = os.path.abspath(args.file.strip('\"\''))
        return self._compress(video_path, args.target_mb, args.output, console)

    def run_interactive(self, console: Console) -> int:
        console.print("[bold #FF9800]🎬 启动万能视频极限压缩引擎[/bold #FF9800]")
        console.print("[dim]基于 FFmpeg 底层算法，根据目标 MB 精准分配音视频码率，压制大体积视频。[/dim]\n")

        file_input = Prompt.ask("[#10b981]?[/#10b981] 请输入源视频文件路径")
        video_path = os.path.abspath(file_input.strip('\"\''))

        mb_str = Prompt.ask("[#10b981]?[/#10b981] 请输入期望目标体积 (MB，例如 50 或 25)", default="25")
        try:
            target_mb = float(mb_str)
        except ValueError:
            target_mb = 25.0

        return self._compress(video_path, target_mb, None, console)

    def _get_duration(self, ffprobe_path: str, video_path: str) -> float | None:
        cmd = [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            return None

    def _compress(self, video_path: str, target_mb: float, out_path: str | None, console: Console) -> int:
        ffmpeg_bin = get_ffmpeg()
        ffprobe_bin = get_ffprobe()

        if not ffmpeg_bin or not ffprobe_bin:
            print_error("缺少 ffmpeg 或 ffprobe 工具！请确保 pykuai/tools/ 目录下包含对应可执行文件或已配置在系统 PATH。")
            return 1

        if not os.path.isfile(video_path):
            print_error(f"源视频文件不存在: {video_path}")
            return 1

        print_step(f"正在分析视频流元信息: [bold]{os.path.basename(video_path)}[/bold]")
        duration = self._get_duration(ffprobe_bin, video_path)
        if not duration or duration <= 0:
            print_error("无法读取视频时长，可能是文件已损坏或格式不受支持。")
            return 1

        audio_bitrate_kbps = 128
        target_total_bitrate = (target_mb * 8192) / duration
        target_video_bitrate = target_total_bitrate - audio_bitrate_kbps

        if target_video_bitrate <= 50:
            print_error(f"目标体积 {target_mb}MB 过小，无法为 {duration:.1f} 秒时长的视频分配足够码率！请调大目标 MB。")
            return 1

        video_bitrate_str = f"{int(target_video_bitrate)}k"
        print_info(f"视频时长: [bold #00FF00]{duration:.2f}s[/bold #00FF00] | 分配视频码率: [bold #00FF00]{video_bitrate_str}[/bold #00FF00]")

        if not out_path:
            base_dir = os.path.dirname(video_path)
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            out_path = os.path.join(base_dir, f"{base_name}_min.mp4")

        cmd = [
            ffmpeg_bin, "-y",
            "-i", video_path,
            "-c:v", "libx264",
            "-b:v", video_bitrate_str,
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate_kbps}k",
            out_path
        ]

        print_step("正在启动 FFmpeg 核心引擎进行高压缩比重编码...")
        try:
            with create_progress() as progress:
                task = progress.add_task("[#10b981]视频压制中...", total=int(duration))
                process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, encoding="utf-8", errors="replace")

                time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
                while True:
                    line = process.stderr.readline()
                    if not line and process.poll() is not None:
                        break
                    match = time_pattern.search(line)
                    if match:
                        hours, mins, secs = match.groups()
                        cur_time = int(hours) * 3600 + int(mins) * 60 + float(secs)
                        progress.update(task, completed=min(int(duration), int(cur_time)))

                if process.returncode != 0:
                    print_error("FFmpeg 转码过程异常终止！")
                    return 1

            new_size_mb = os.path.getsize(out_path) / (1024 * 1024)
            print_success(f"视频极限压制完成！导出体积: [bold #00FF00]{new_size_mb:.2f} MB[/bold #00FF00]")
            print_info(f"保存至: [bold]{out_path}[/bold]")
            return 0
        except Exception as e:
            print_error(f"执行压缩崩溃: {e}")
            return 1
