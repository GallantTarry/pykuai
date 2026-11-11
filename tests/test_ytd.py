"""Offline regressions for downloader arguments, output handling, and cleanup."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from rich.console import Console

from pykuai.engines import ytd

try:
    import yt_dlp
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None


def command(profile="best", ffmpeg="ffmpeg", **kwargs):
    return ytd._build_ytdlp_command(
        [sys.executable, "-m", "yt_dlp"],
        "https://example.com/watch?v=123",
        ytd.FORMAT_PROFILES[profile],
        os.path.abspath("100% downloads"),
        ffmpeg,
        [],
        **kwargs,
    )


class DownloaderInputTests(unittest.TestCase):
    def test_rejects_bad_urls_before_launch(self):
        engine = ytd.YtdEngine()
        console = Console(file=io.StringIO())
        invalid = (
            "file:///etc/passwd", "https://", "https://example.com:invalid/path",
            "https://example.com/a b", "https://example.com/\x00name",
            "https://example.com/\x1b[31m", "--exec=anything",
        )
        with patch.object(ytd, "resolve_ytdlp_runner") as runner, patch.object(ytd, "print_error"):
            for url in invalid:
                with self.subTest(url=url):
                    self.assertFalse(ytd._validate_url(url)[0])
                    self.assertEqual(engine._list_formats(url, False, "none", "", "", console), 1)
            runner.assert_not_called()

    def test_site_badges_use_hostname_not_query_or_substrings(self):
        self.assertEqual(ytd._validate_url("https://www.youtube.com/watch?v=1")[1], "✓ YouTube")
        for url in (
            "https://youtube.com.evil.example/watch",
            "https://example.com/?next=https://youtube.com",
            "https://notx.com/watch",
        ):
            with self.subTest(url=url):
                self.assertEqual(ytd._validate_url(url), (True, "✓ URL"))

    def test_only_balanced_pasted_quotes_are_removed(self):
        self.assertEqual(ytd._clean_text('  "https://example.com/a"  '), "https://example.com/a")
        self.assertEqual(ytd._clean_text("https://example.com/it's'"), "https://example.com/it's'")

    def test_bad_connection_options_do_not_launch_probe(self):
        engine = ytd.YtdEngine()
        console = Console(file=io.StringIO())
        invalid = (
            ("chrome", "cookies.txt", ""),
            ("none", "", "http://localhost/\x00"),
            ("none", "missing-cookies-for-pykuai-test.txt", ""),
        )
        with patch.object(engine, "_run_subprocess") as run, patch.object(ytd, "print_error"):
            for browser, cookie_file, proxy in invalid:
                with self.subTest(browser=browser, cookie_file=cookie_file, proxy=proxy):
                    self.assertEqual(engine._list_formats("https://example.com/watch", False, browser, cookie_file, proxy, console), 1)
            run.assert_not_called()


class DownloaderCommandTests(unittest.TestCase):
    def test_literal_directory_is_separate_from_unique_filename_template(self):
        cmd = command()
        self.assertEqual(cmd[cmd.index("--paths") + 1], os.path.abspath("100% downloads"))
        template = cmd[cmd.index("-o") + 1]
        self.assertNotIn("100% downloads", template)
        self.assertIn("%(id)s", template)
        self.assertIn("%(ext)s", template)

    def test_video_retry_preserves_mp4_postprocessing(self):
        for fmt in ("best", "1080p", "720p"):
            for fallback in (False, True):
                with self.subTest(fmt=fmt, fallback=fallback):
                    cmd = command(fmt, use_fallback_format=fallback)
                    self.assertEqual(cmd[cmd.index("--merge-output-format") + 1], "mp4")
                    self.assertEqual(cmd[cmd.index("--remux-video") + 1], "mp4")

    def test_audio_retry_keeps_requested_encoding(self):
        for fmt in ("mp3", "m4a"):
            with self.subTest(fmt=fmt):
                cmd = command(fmt, use_fallback_format=True)
                self.assertIn("--extract-audio", cmd)
                self.assertEqual(cmd[cmd.index("--audio-format") + 1], fmt)

    def test_subtitles_embed_only_in_video_with_ffmpeg(self):
        for fmt, ffmpeg, embed in (("best", "ffmpeg", True), ("best", None, False), ("mp3", "ffmpeg", False), ("m4a", "ffmpeg", False)):
            with self.subTest(fmt=fmt, ffmpeg=ffmpeg):
                cmd = command(fmt, ffmpeg, subtitles=True)
                self.assertIn("--write-subs", cmd)
                self.assertEqual("--embed-subs" in cmd, embed)

    def test_probe_is_not_forced_to_download(self):
        cmd = command(list_formats=True)
        self.assertIn("-F", cmd)
        self.assertNotIn("--no-simulate", cmd)
        self.assertNotIn("--print", cmd)

    def test_download_output_is_visible_and_machine_readable(self):
        cmd = command()
        self.assertIn("--no-simulate", cmd)
        self.assertIn("--no-quiet", cmd)
        self.assertIn("--no-colors", cmd)
        self.assertIn("--ignore-config", cmd)
        self.assertIn("after_move:__PYKUAI_FILE__:%(filepath)j", cmd)

    @unittest.skipIf(YoutubeDL is None, "optional yt-dlp package is unavailable")
    def test_real_option_parser_keeps_download_enabled_and_directory_literal(self):
        parsed = yt_dlp.parse_options(command()[3:])
        self.assertFalse(parsed.ydl_opts["simulate"])
        self.assertFalse(parsed.ydl_opts["quiet"])
        self.assertEqual(parsed.ydl_opts["paths"]["home"], os.path.abspath("100% downloads"))
        self.assertEqual(parsed.ydl_opts["forceprint"]["after_move"], ["__PYKUAI_FILE__:%(filepath)j"])
        self.assertEqual(parsed.urls, ["https://example.com/watch?v=123"])

    @unittest.skipIf(YoutubeDL is None, "optional yt-dlp package is unavailable")
    def test_real_format_selector_never_exceeds_selected_height(self):
        # Only an oversized stream is available: the old '/b' fallback picked it.
        high = {"format_id": "4k", "height": 2160, "ext": "mp4", "vcodec": "avc1", "acodec": "aac", "url": "https://example.com/4k.mp4"}
        low = {**high, "format_id": "360p", "height": 360, "url": "https://example.com/360.mp4"}
        with YoutubeDL({"quiet": True, "no_warnings": True}) as downloader:
            for fmt in ("720p", "1080p"):
                profile = ytd.FORMAT_PROFILES[fmt]
                for expression in (profile.ffmpeg_expr, profile.fallback_expr):
                    with self.subTest(fmt=fmt, expression=expression):
                        selector = downloader.build_format_selector(expression)
                        self.assertEqual(downloader._select_formats([high], selector), [])
                        chosen = downloader._select_formats([low, high], selector)
                        self.assertTrue(chosen)
                        self.assertEqual(chosen[0]["height"], 360)


class DownloaderProcessTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.console = Console(file=self.output, color_system=None, width=200)
        self.engine = ytd.YtdEngine()

    def test_real_process_handles_unicode_final_path_and_literal_markup(self):
        final = os.path.abspath("下载 [bold] 'clip'.mp4")
        lines = [
            "[download] Destination: partial.webm",
            "[download] 20.0% of 10MiB",
            "[Merger] Merging formats into interim.mp4",
            "WARNING: title [bold] remains literal",
            "__PYKUAI_FILE__:" + json.dumps(final, ensure_ascii=False),
        ]
        script = "import json; [print(line) for line in json.loads(" + repr(json.dumps(lines)) + ")]"
        code, errors, warnings, path = self.engine._run_subprocess([sys.executable, "-c", script], self.console)
        self.assertEqual(code, 0)
        self.assertEqual(errors, [])
        self.assertEqual(path, final)
        self.assertEqual(warnings, [lines[3]])
        rendered = self.output.getvalue()
        self.assertIn("[download] 20.0%", rendered)
        self.assertIn("title [bold] remains literal", rendered)
        self.assertNotIn("[#10b981]", rendered)
        self.assertNotIn("[/#38BDF8]", rendered)
        self.assertNotIn("__PYKUAI_FILE__:", rendered)

    def test_real_process_preserves_nonzero_exit_and_errors(self):
        script = "import sys; print('ERROR: remote rejected the request'); sys.exit(4)"
        code, errors, _, _ = self.engine._run_subprocess([sys.executable, "-c", script], self.console)
        self.assertEqual(code, 4)
        self.assertEqual(errors, ["ERROR: remote rejected the request"])

    def test_start_failure_is_reported(self):
        with patch.object(ytd.subprocess, "Popen", side_effect=FileNotFoundError("missing runner")):
            code, errors, _, path = self.engine._run_subprocess(["missing"], self.console)
        self.assertNotEqual(code, 0)
        self.assertIn("missing runner", errors[0])
        self.assertIsNone(path)

    def test_exception_while_streaming_reaps_child_and_closes_pipe(self):
        process = Mock()
        process.stdout.readline.side_effect = RuntimeError("read failed")
        process.poll.return_value = None
        process.wait.return_value = 0
        with patch.object(ytd.subprocess, "Popen", return_value=process):
            try:
                self.engine._run_subprocess(["runner"], self.console)
            except RuntimeError:
                pass
        process.terminate.assert_called_once()
        self.assertGreaterEqual(process.wait.call_count, 1)
        process.stdout.close.assert_called_once()

    def test_cancellation_escalates_to_kill_if_child_ignores_terminate(self):
        process = Mock()
        process.stdout.readline.side_effect = KeyboardInterrupt
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("runner", 5), 0]
        with patch.object(ytd.subprocess, "Popen", return_value=process):
            code, _, _, _ = self.engine._run_subprocess(["runner"], self.console)
        self.assertEqual(code, 130)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)
        process.stdout.close.assert_called_once()


class DownloaderRetryTests(unittest.TestCase):
    def test_retry_does_not_erase_global_cache_or_force_youtube_client(self):
        engine = ytd.YtdEngine()
        console = Console(file=io.StringIO())
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.object(ytd, "resolve_ytdlp_runner", return_value=(["yt-dlp"], "test")))
            stack.enter_context(patch.object(ytd, "get_ffmpeg", return_value="ffmpeg"))
            stack.enter_context(patch.object(ytd, "get_js_runtimes", return_value=[]))
            for name in ("print_step", "print_info", "print_warning", "print_error"):
                stack.enter_context(patch.object(ytd, name))
            run = stack.enter_context(patch.object(engine, "_run_subprocess", side_effect=[
                (1, ["ERROR: HTTP Error 403"], [], None),
                (0, [], [], None),
            ]))
            code = engine._download("https://example.com/watch", "720p", False, False, "none", "", folder, "", console)
            self.assertEqual(code, 0)
            self.assertEqual(run.call_count, 2)
            retry = run.call_args.args[0]
            self.assertNotIn("--rm-cache-dir", retry)
            self.assertNotIn("--extractor-args", retry)
            self.assertIn("--remux-video", retry)

    def test_cancel_is_not_retried_even_after_error_output(self):
        engine = ytd.YtdEngine()
        console = Console(file=io.StringIO())
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.object(ytd, "resolve_ytdlp_runner", return_value=(["yt-dlp"], "test")))
            stack.enter_context(patch.object(ytd, "get_ffmpeg", return_value="ffmpeg"))
            stack.enter_context(patch.object(ytd, "get_js_runtimes", return_value=[]))
            for name in ("print_step", "print_info", "print_warning", "print_error"):
                stack.enter_context(patch.object(ytd, name))
            run = stack.enter_context(patch.object(engine, "_run_subprocess", return_value=(130, ["ERROR: HTTP Error 403"], [], None)))
            code = engine._download("https://example.com/watch", "720p", False, False, "none", "", folder, "", console)
            self.assertEqual(code, 130)
            run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
