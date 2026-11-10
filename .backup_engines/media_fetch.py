# -*- coding: utf-8 -*-
"""
音视频链接获取引擎 (基于 yt-dlp + ffmpeg 的全能网络流媒体捕获器)
"""
import os
import argparse
import subprocess
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from pykuai.core.base import BaseEngine
from pykuai.core.tools import get_ytdlp, get_ffmpeg
from pykuai.core.ui import print_success, print_error, print_warning, print_info, print_step


class MediaFetchEngine(BaseEngine):
    name = "media-fetch"
    aliases = ["download", "ytdl", "video-get"]
    description = "音视频链接获取引擎 (解析下载 Bilibili/YouTube/X 视频或提取纯音频 MP3)"
    category = "多媒体与图像"

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("url", help="目标音视频资源网页链接")
        parser.add_argument("-f", "--format", choices=["video", "audio"], default="video", help="下载模式: video(最佳画质mp4) 或 audio(提取mp3)")
        parser.add_argument("-p", "--playlist", action="store_true", help="允许下载完整播放列表或合集")
        parser.add_argument("-o", "--output-dir", default=".", help="保存目录 (默认当前目录)")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        return self._download(args.url, args.format == "audio", args.playlist, os.path.abspath(args.output_dir), console)

    def run_interactive(self, console: Console) -> int:
        console.print("[bold #FF9800]📡 启动音视频链接获取引擎[/bold #FF9800]")
        console.print("[dim]调用底层 yt-dlp 协议雷达，支持单集抓取、列表多卷捕获与高品质 MP3 提取。[/dim]\n")

        url = Prompt.ask("[#10b981]?[/#10b981] 请输入要下载的网页视频链接")
        if not url.strip():
            print_error("未提供有效网址。")
            return 1

        mode_choice = Prompt.ask(
            "[#10b981]?[/#10b981] 请选择提取协议",
            choices=["1", "2"],
            default="1"
        )
        # 1: 最佳视频+音频, 2: 纯音频提取
        audio_only = (mode_choice == "2")

        scope_choice = Prompt.ask(
            "[#10b981]?[/#10b981] 请选择抓取范围: [1] 仅当前单集  [2] 整个合集/列表",
            choices=["1", "2"],
            default="1"
        )
        is_playlist = (scope_choice == "2")

        out_input = Prompt.ask("[#10b981]?[/#10b981] 请输入保存目录", default=".")
        out_dir = os.path.abspath(out_input.strip('\"\''))

        return self._download(url.strip(), audio_only, is_playlist, out_dir, console)

    def _download(self, url: str, audio_only: bool, is_playlist: bool, save_dir: str, console: Console) -> int:
        ytdlp_bin = get_ytdlp()
        ffmpeg_bin = get_ffmpeg()

        if not ytdlp_bin:
            print_error("未找到 yt-dlp 核心引擎！请确保 pykuai/tools/ 目录下有 yt-dlp.exe 或已安装在系统 PATH。")
            return 1

        os.makedirs(save_dir, exist_ok=True)
        print_step(f"捕获雷达已启动，目标定位: [bold]{url}[/bold]")

        cmd = [
            ytdlp_bin,
            "--newline",
            "-o", os.path.join(save_dir, "%(title)s.%(ext)s")
        ]

        if ffmpeg_bin:
            cmd.extend(["--ffmpeg-location", ffmpeg_bin])

        if not is_playlist:
            cmd.append("--no-playlist")
        else:
            cmd.append("--yes-playlist")

        if audio_only:
            print_info("协议模式: [bold #00FF00]纯音频提取 (MP3 320k)[/bold #00FF00]")
            cmd.extend([
                "-f", "bestaudio/best",
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "0"
            ])
        else:
            print_info("协议模式: [bold #00FF00]最佳画质整合 (MP4)[/bold #00FF00]")
            cmd.extend(["-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4"])

        cmd.append(url)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL
            )

            for line_bytes in iter(process.stdout.readline, b''):
                try:
                    clean_line = line_bytes.decode('utf-8').strip()
                except UnicodeDecodeError:
                    clean_line = line_bytes.decode('gb18030', errors='replace').strip()

                if clean_line:
                    if "[download]" in clean_line or "[ExtractAudio]" in clean_line or "[Merger]" in clean_line:
                        console.print(f"[#10b981]> {clean_line}[/#10b981]")

            process.wait()
            if process.returncode == 0:
                print_success("流媒体资源捕获入库完毕！")
                print_info(f"保存目录: [bold]{save_dir}[/bold]")
                return 0
            else:
                print_error("下载异常终止，可能链接失效或需要特定网络代理。")
                return 1
        except Exception as e:
            print_error(f"调用引擎崩溃: {e}")
            return 1
