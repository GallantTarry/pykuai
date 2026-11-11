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

    def test_chrome_cookie_lock_falls_back_to_cookieless_and_succeeds(self):
        engine = ytd.YtdEngine()
        console = Console(file=io.StringIO(), color_system=None)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            stack.enter_context(patch.object(ytd, "_discover_cookies_file", return_value=""))
            stack.enter_context(patch.object(ytd, "resolve_ytdlp_runner", return_value=(["yt-dlp"], "2026.10.26")))
            stack.enter_context(patch.object(ytd, "get_ffmpeg", return_value="ffmpeg"))
            stack.enter_context(patch.object(ytd, "get_js_runtimes", return_value=[("node", "node")]))
            for name in ("print_step", "print_info", "print_warning", "print_error"):
                stack.enter_context(patch.object(ytd, name))
            run = stack.enter_context(patch.object(engine, "_run_subprocess", side_effect=[
                (1, ["ERROR: Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271"], [], None),
                (0, [], [], None),
            ]))
            code = engine._download("https://www.youtube.com/watch?v=1D9AN0TB3ho", "best", False, False, "chrome", "", folder, "", console)
            self.assertEqual(code, 0)
            self.assertEqual(run.call_count, 2)
            first_cmd = run.call_args_list[0].args[0]
            retry_cmd = run.call_args_list[1].args[0]
            self.assertIn("--cookies-from-browser", first_cmd)
            self.assertNotIn("--cookies-from-browser", retry_cmd)
            self.assertNotIn("--cookies", retry_cmd)

    def test_chrome_cookie_lock_uses_discovered_cookies_file_and_keeps_it_for_format_fallback(self):
        engine = ytd.YtdEngine()
        console = Console(file=io.StringIO(), color_system=None)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            cookie_file = os.path.join(folder, "cookies.txt")
            with open(cookie_file, "w", encoding="utf-8") as fh:
                fh.write("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t1893456000\tPREF\ttz=UTC\n")
            non_cookie = os.path.join(folder, "notes.txt")
            with open(non_cookie, "w", encoding="utf-8") as fh:
                fh.write("just plain notes\n")
            self.assertFalse(ytd._looks_like_netscape_cookies(non_cookie))
            self.assertTrue(ytd._looks_like_netscape_cookies(cookie_file))
            self.assertEqual(ytd._discover_cookies_file(folder), os.path.abspath(cookie_file))

            stack.enter_context(patch.object(ytd, "resolve_ytdlp_runner", return_value=(["yt-dlp"], "2026.10.26")))
            stack.enter_context(patch.object(ytd, "get_ffmpeg", return_value="ffmpeg"))
            stack.enter_context(patch.object(ytd, "get_js_runtimes", return_value=[]))
            for name in ("print_step", "print_info", "print_warning", "print_error"):
                stack.enter_context(patch.object(ytd, name))
            run = stack.enter_context(patch.object(engine, "_run_subprocess", side_effect=[
                (1, ["ERROR: Failed to decrypt with DPAPI"], [], None),
                (1, ["ERROR: HTTP Error 403"], [], None),
                (0, [], [], None),
            ]))
            code = engine._download("https://www.youtube.com/watch?v=123", "1080p", False, False, "chrome", "", folder, "", console)
            self.assertEqual(code, 0)
            self.assertEqual(run.call_count, 3)
            for call in run.call_args_list[1:]:
                cmd_args = call.args[0]
                self.assertNotIn("--cookies-from-browser", cmd_args)
                self.assertIn("--cookies", cmd_args)
                self.assertEqual(cmd_args[cmd_args.index("--cookies") + 1], os.path.abspath(cookie_file))

    def test_probe_also_recovers_from_locked_chrome_cookies(self):
        engine = ytd.YtdEngine()
        console = Console(file=io.StringIO(), color_system=None)
        with ExitStack() as stack:
            stack.enter_context(patch.object(ytd, "_discover_cookies_file", return_value=""))
            stack.enter_context(patch.object(ytd, "resolve_ytdlp_runner", return_value=(["yt-dlp"], "2026.10.26")))
            stack.enter_context(patch.object(ytd, "get_ffmpeg", return_value="ffmpeg"))
            stack.enter_context(patch.object(ytd, "get_js_runtimes", return_value=[]))
            for name in ("print_step", "print_info", "print_warning", "print_error"):
                stack.enter_context(patch.object(ytd, name))
            run = stack.enter_context(patch.object(engine, "_run_subprocess", side_effect=[
                (1, ["ERROR: Could not copy Chrome cookie database."], [], None),
                (0, [], [], None),
            ]))
            code = engine._list_formats("https://www.youtube.com/watch?v=123", False, "chrome", "", "", console)
            self.assertEqual(code, 0)
            self.assertEqual(run.call_count, 2)
            self.assertNotIn("--cookies-from-browser", run.call_args_list[1].args[0])


class DownloaderCookieAndStudioTests(unittest.IsolatedAsyncioTestCase):
    def test_equal_ytdlp_versions_prefer_bundled_binary_when_curl_cffi_missing(self):
        from pykuai.core import tools

        with ExitStack() as stack:
            stack.enter_context(patch.object(tools.importlib.util, "find_spec", side_effect=lambda name: object() if name == "yt_dlp" else None))
            stack.enter_context(patch.object(tools.importlib.metadata, "version", return_value="2026.10.26"))
            stack.enter_context(patch.object(tools, "get_ytdlp", return_value="C:\\tools\\yt-dlp.exe"))
            stack.enter_context(patch.object(tools, "_get_binary_ytdlp_version", return_value="2026.10.26"))
            cmd, ver = tools.resolve_ytdlp_runner()
            self.assertEqual(cmd, ["C:\\tools\\yt-dlp.exe"])
            self.assertEqual(ver, "2026.10.26")

    async def test_studio_supports_cookies_file_and_windows_chrome_note(self):
        from textual.widgets import Input

        with tempfile.TemporaryDirectory() as folder:
            cookie_file = os.path.join(folder, "cookies.txt")
            with open(cookie_file, "w", encoding="utf-8") as fh:
                fh.write("# Netscape HTTP Cookie File\n")

            with ExitStack() as stack:
                for name in ("warmup_sfx", "play_sfx"):
                    stack.enter_context(patch(f"pykuai.core.tui.{name}"))
                stack.enter_context(patch.object(ytd, "_discover_cookies_file", return_value=""))
                stack.enter_context(patch.object(ytd, "resolve_ytdlp_runner", return_value=(["yt-dlp.exe"], "2026.10.26")))
                stack.enter_context(patch.object(ytd, "get_ffmpeg", return_value="ffmpeg.exe"))
                stack.enter_context(patch.object(ytd, "get_js_runtimes", return_value=[]))

                app = ytd._build_ytd_studio_app("https://www.youtube.com/watch?v=123")
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause()
                    await pilot.click("#ck-chrome")
                    await pilot.pause()
                    note = app.query_one("#cookie-note")
                    self.assertEqual(note.has_class("hidden-section"), os.name != "nt")

                    await pilot.click("#ck-file")
                    await pilot.pause()
                    self.assertTrue(note.has_class("hidden-section"))
                    self.assertFalse(app.query_one("#cookies-row").has_class("hidden-section"))
                    app.query_one("#cookies-input", Input).value = cookie_file
                    await pilot.click("#btn-run")
                    await pilot.pause()

                self.assertEqual(
                    app.return_value,
                    ("download", "https://www.youtube.com/watch?v=123", "best", False, False, "none", cookie_file, os.getcwd(), ""),
                )


class TestFfmpegInstaller(unittest.TestCase):
    @staticmethod
    def _make_zip_bytes(entries: dict[str, bytes]) -> bytes:
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in entries.items():
                zf.writestr(name, data)
        return buf.getvalue()

    @staticmethod
    def _fake_urlopen(mapping: dict[str, bytes]):
        import io

        class _FakeResponse:
            def __init__(self, payload: bytes):
                self._bio = io.BytesIO(payload)
                self.headers = {"Content-Length": str(len(payload))}

            def read(self, n: int = -1) -> bytes:
                return self._bio.read(n)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def _opener(req, timeout=60):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url not in mapping:
                raise AssertionError(f"Unexpected URL requested: {url}")
            return _FakeResponse(mapping[url])

        return _opener

    def test_install_ffmpeg_binaries_verifies_sha256_and_extracts(self):
        import hashlib
        import tempfile
        from pathlib import Path
        from unittest import mock
        from pykuai.core import tools

        zip_bytes = self._make_zip_bytes(
            {
                "ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe": b"FAKE-FFMPEG-BIN",
                "ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe": b"FAKE-FFPROBE-BIN",
                "ffmpeg-9.0.2-essentials_build/README.txt": b"ignore-me",
            }
        )
        digest = hashlib.sha256(zip_bytes).hexdigest()
        sha_payload = f"{digest}  ffmpeg-release-essentials.zip\n".encode("utf-8")
        events: list[tuple[int, int | None]] = []

        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            with (
                mock.patch.object(tools.os, "name", "nt"),
                mock.patch.object(
                    tools.urllib.request,
                    "urlopen",
                    side_effect=self._fake_urlopen(
                        {
                            tools.FFMPEG_WIN_SHA256_URL: sha_payload,
                            tools.FFMPEG_WIN_ZIP_URL: zip_bytes,
                        }
                    ),
                ),
            ):
                ffmpeg_exe, ffprobe_exe = tools.install_ffmpeg_binaries(
                    target_dir=dest_dir, progress_cb=lambda d, t: events.append((d, t))
                )

            self.assertEqual(ffmpeg_exe, dest_dir / "ffmpeg.exe")
            self.assertEqual(ffprobe_exe, dest_dir / "ffprobe.exe")
            self.assertEqual(ffmpeg_exe.read_bytes(), b"FAKE-FFMPEG-BIN")
            self.assertEqual(ffprobe_exe.read_bytes(), b"FAKE-FFPROBE-BIN")
            self.assertEqual(sorted(p.name for p in dest_dir.iterdir()), ["ffmpeg.exe", "ffprobe.exe"])
            self.assertIn((len(zip_bytes), len(zip_bytes)), events)

    def test_install_ffmpeg_binaries_rejects_sha256_mismatch(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from pykuai.core import tools

        zip_bytes = self._make_zip_bytes(
            {
                "bin/ffmpeg.exe": b"FF",
                "bin/ffprobe.exe": b"FP",
            }
        )
        bad_sha = ("0" * 64 + "\n").encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            with (
                mock.patch.object(tools.os, "name", "nt"),
                mock.patch.object(
                    tools.urllib.request,
                    "urlopen",
                    side_effect=self._fake_urlopen(
                        {
                            tools.FFMPEG_WIN_SHA256_URL: bad_sha,
                            tools.FFMPEG_WIN_ZIP_URL: zip_bytes,
                        }
                    ),
                ),
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    tools.install_ffmpeg_binaries(target_dir=dest_dir)
            self.assertIn("SHA256 mismatch", str(ctx.exception))
            self.assertEqual(list(dest_dir.iterdir()), [])

    def test_install_ffmpeg_binaries_rejects_incomplete_archive(self):
        import hashlib
        import tempfile
        from pathlib import Path
        from unittest import mock
        from pykuai.core import tools

        zip_bytes = self._make_zip_bytes({"bin/ffmpeg.exe": b"ONLY-FFMPEG"})
        digest = hashlib.sha256(zip_bytes).hexdigest().encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            with (
                mock.patch.object(tools.os, "name", "nt"),
                mock.patch.object(
                    tools.urllib.request,
                    "urlopen",
                    side_effect=self._fake_urlopen(
                        {
                            tools.FFMPEG_WIN_SHA256_URL: digest,
                            tools.FFMPEG_WIN_ZIP_URL: zip_bytes,
                        }
                    ),
                ),
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    tools.install_ffmpeg_binaries(target_dir=dest_dir)
            self.assertIn("missing required executable", str(ctx.exception))
            self.assertEqual(list(dest_dir.iterdir()), [])

    def test_ensure_ffmpeg_returns_existing_and_handles_prompts(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from pykuai.core import tools

        with (
            mock.patch.object(tools, "get_ffmpeg", return_value="C:\\bin\\ffmpeg.exe"),
            mock.patch.object(tools, "install_ffmpeg_binaries", side_effect=AssertionError("should not install")),
        ):
            self.assertEqual(tools.ensure_ffmpeg(interactive=True), "C:\\bin\\ffmpeg.exe")

        with (
            mock.patch.object(tools.os, "name", "nt"),
            mock.patch.object(tools, "get_ffmpeg", return_value=None),
            mock.patch("builtins.input", side_effect=AssertionError("should not prompt")),
            mock.patch.object(tools, "install_ffmpeg_binaries", side_effect=AssertionError("should not install")),
        ):
            self.assertIsNone(tools.ensure_ffmpeg(interactive=False))

        with (
            mock.patch.object(tools.os, "name", "nt"),
            mock.patch.object(tools, "get_ffmpeg", return_value=None),
            mock.patch("builtins.input", return_value="n"),
            mock.patch.object(tools, "install_ffmpeg_binaries", side_effect=AssertionError("should not install")),
        ):
            self.assertIsNone(tools.ensure_ffmpeg(interactive=True))

        with tempfile.TemporaryDirectory() as tmp:
            fake_ff = Path(tmp) / "ffmpeg.exe"
            fake_fp = Path(tmp) / "ffprobe.exe"
            with (
                mock.patch.object(tools.os, "name", "nt"),
                mock.patch.object(tools, "get_ffmpeg", return_value=None),
                mock.patch("builtins.input", return_value="y"),
                mock.patch.object(tools, "install_ffmpeg_binaries", return_value=(fake_ff, fake_fp)) as mock_inst,
            ):
                res = tools.ensure_ffmpeg(interactive=True, target_dir=Path(tmp))
            self.assertEqual(res, str(fake_ff))
            mock_inst.assert_called_once()

    def test_ytd_download_and_cli_install_ffmpeg_integration(self):
        import argparse
        import tempfile
        from unittest import mock
        from rich.console import Console
        from pykuai.engines import ytd

        engine = ytd.YtdEngine()
        console = Console(quiet=True)

        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(ytd, "get_ffmpeg", return_value=None),
                mock.patch.object(ytd, "ensure_ffmpeg", return_value="C:\\users\\.pykuai\\tools\\ffmpeg.exe") as mock_ensure,
                mock.patch.object(ytd, "resolve_ytdlp_runner", return_value=(["yt-dlp"], "2026.10.26")),
                mock.patch.object(ytd, "get_js_runtimes", return_value=[("node", "node")]),
                mock.patch.object(engine, "_run_with_cookie_recovery", return_value=(0, [], "out.mp4", False)) as mock_run,
            ):
                rc = engine._download(
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "best",
                    False,
                    False,
                    "none",
                    "",
                    tmp,
                    "",
                    console,
                )
            self.assertEqual(rc, 0)
            mock_ensure.assert_called_once()
            self.assertEqual(mock_run.call_args.args[4], "C:\\users\\.pykuai\\tools\\ffmpeg.exe")

        args = argparse.Namespace(install_ffmpeg=True, url="")
        with mock.patch.object(ytd, "ensure_ffmpeg", return_value="C:\\users\\.pykuai\\tools\\ffmpeg.exe") as mock_ensure:
            self.assertEqual(engine.run_direct(args, console), 0)
            mock_ensure.assert_called_once_with(console=console, interactive=False, auto_confirm=True)

    def test_bundled_tools_dir_excludes_heavy_ffmpeg_binaries(self):
        from pathlib import Path
        import pykuai

        tools_dir = Path(pykuai.__file__).resolve().parent / "tools"
        names = {p.name for p in tools_dir.iterdir()}
        self.assertNotIn("ffmpeg.exe", names)
        self.assertNotIn("ffprobe.exe", names)
        self.assertTrue({"yt-dlp.exe", "UnRAR.exe", "zpix.ttf"}.issubset(names))


class TestYouTubeAuthHelper(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncio

        asyncio.get_running_loop().set_debug(False)

    def test_cookies_to_netscape_filters_domains_and_parses_with_cookiejar(self):
        import http.cookiejar
        import tempfile
        from pathlib import Path
        from pykuai.core import yt_auth
        from pykuai.engines import ytd

        raw = [
            {
                "domain": ".youtube.com",
                "path": "/",
                "secure": True,
                "session": False,
                "expires": 1893456000.7,
                "name": "SAPISID",
                "value": "sapi-val",
            },
            {
                "domain": ".google.com",
                "path": "/",
                "secure": True,
                "session": True,
                "expires": -1,
                "name": "SID",
                "value": "sid\tval\n",
            },
            {
                "domain": ".example.com",
                "path": "/",
                "secure": False,
                "session": False,
                "expires": 1893456000,
                "name": "TRACKER",
                "value": "drop-me",
            },
        ]

        self.assertFalse(yt_auth.has_youtube_auth_cookies([{"domain": ".youtube.com", "name": "PREF", "value": "1"}]))
        self.assertTrue(yt_auth.has_youtube_auth_cookies(raw))

        with tempfile.TemporaryDirectory() as tmp:
            out = yt_auth.write_cookies_file(raw, Path(tmp) / "cookies.txt")
            self.assertTrue(ytd._looks_like_netscape_cookies(str(out)))
            jar = http.cookiejar.MozillaCookieJar(str(out))
            jar.load(ignore_discard=True, ignore_expires=True)
            names = {c.name: c.value for c in jar}
            self.assertEqual(names["SAPISID"], "sapi-val")
            self.assertEqual(names["SID"], "sid val")
            self.assertNotIn("TRACKER", names)

    def test_login_youtube_and_save_cookies_flow(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from pykuai.core import yt_auth

        class _FakeProc:
            def __init__(self):
                self._rc = None

            def poll(self):
                return self._rc

            def wait(self, timeout=None):
                self._rc = 0
                return 0

            def terminate(self):
                self._rc = 0

            def kill(self):
                self._rc = -9

        class _FakeCdp:
            def __init__(self, ws_url, timeout=5.0):
                self.polls = 0
                self.closed_browser = False

            def call(self, method, params=None):
                if method == "Storage.getCookies":
                    self.polls += 1
                    if self.polls < 3:
                        return {"cookies": [{"domain": ".youtube.com", "name": "PREF", "value": "1"}]}
                    return {
                        "cookies": [
                            {"domain": ".youtube.com", "name": "SAPISID", "value": "auth-token", "path": "/", "secure": True, "expires": 1893456000},
                            {"domain": ".youtube.com", "name": "SID", "value": "sid-token", "path": "/", "secure": True, "expires": 1893456000},
                        ]
                    }
                if method == "Target.getTargets":
                    url = "https://accounts.google.com/ServiceLogin" if self.polls < 3 else "https://www.youtube.com/"
                    return {"targetInfos": [{"type": "page", "url": url}]}
                if method == "Browser.close":
                    self.closed_browser = True
                    return {}
                return {}

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "cookies.txt"
            prof = Path(tmp) / "yt-session"
            proc = _FakeProc()
            with (
                mock.patch.object(yt_auth, "find_chromium_browser", return_value=("Edge", "C:\\msedge.exe")),
                mock.patch.object(yt_auth.subprocess, "Popen", return_value=proc),
                mock.patch.object(yt_auth, "_fetch_cdp_version_ws", return_value="ws://127.0.0.1:9222/devtools/browser/1"),
                mock.patch.object(yt_auth, "_CdpClient", _FakeCdp),
                mock.patch.object(yt_auth.time, "sleep"),
            ):
                saved = yt_auth.login_youtube_and_save_cookies(
                    cookies_path=dest,
                    profile_dir=prof,
                    timeout_seconds=10,
                    poll_interval=0.0,
                )
            self.assertEqual(saved, dest)
            self.assertTrue(dest.is_file())
            self.assertIn("auth-token", dest.read_text(encoding="utf-8"))

            # Closing early without signing in must NOT clobber existing cookies.txt.
            class _AbortedProc(_FakeProc):
                def poll(self):
                    return 0

            with (
                mock.patch.object(yt_auth, "find_chromium_browser", return_value=("Edge", "C:\\msedge.exe")),
                mock.patch.object(yt_auth.subprocess, "Popen", return_value=_AbortedProc()),
                mock.patch.object(yt_auth, "_fetch_cdp_version_ws", return_value="ws://127.0.0.1:9222/devtools/browser/1"),
                mock.patch.object(
                    yt_auth,
                    "_CdpClient",
                    lambda *a, **k: type("_AnonCdp", (), {"call": lambda *a, **k: {"cookies": []}, "close": lambda self: None})(),
                ),
            ):
                aborted = yt_auth.login_youtube_and_save_cookies(cookies_path=dest, profile_dir=prof)
            self.assertIsNone(aborted)
            self.assertIn("auth-token", dest.read_text(encoding="utf-8"))

    async def test_studio_login_button_fits_narrow_and_submits_without_url(self):
        from unittest import mock
        from rich.cells import cell_len
        from pykuai.engines import ytd

        for size in ((100, 30), (40, 16)):
            with (
                mock.patch("pykuai.core.tui.warmup_sfx"),
                mock.patch("pykuai.core.tui.play_sfx"),
                mock.patch("pykuai.engines.ytd.resolve_ytdlp_runner", return_value=None),
                mock.patch("pykuai.engines.ytd.get_ffmpeg", return_value=None),
                mock.patch("pykuai.engines.ytd.get_js_runtimes", return_value=[]),
                mock.patch("pykuai.engines.ytd._discover_cookies_file", return_value=""),
            ):
                app = ytd._build_ytd_studio_app("")
                async with app.run_test(size=size) as pilot:
                    login_btn = app.query_one("#btn-login")
                    login_btn.scroll_visible(animate=False)
                    await pilot.pause()
                    self.assertLessEqual(cell_len(str(login_btn.label)), login_btn.content_size.width)
                    self.assertTrue(await pilot.click("#btn-login"))
                self.assertIsNotNone(app.return_value)
                self.assertEqual(app.return_value[0], "login")

    def test_ytd_download_bot_check_login_recovery_and_cli_login(self):
        import argparse
        import tempfile
        from pathlib import Path
        from unittest import mock
        from rich.console import Console
        from pykuai.engines import ytd

        engine = ytd.YtdEngine()
        console = Console(quiet=True)

        with tempfile.TemporaryDirectory() as tmp:
            fake_cookies = Path(tmp) / "cookies.txt"
            fake_cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            responses = [
                (1, ["ERROR: [youtube] xyz: Sign in to confirm you're not a bot."], None, False),
                (0, [], "downloaded.mp4", False),
            ]
            with (
                mock.patch.object(ytd, "resolve_ytdlp_runner", return_value=(["yt-dlp"], "2026.10.26")),
                mock.patch.object(ytd, "get_ffmpeg", return_value="ffmpeg.exe"),
                mock.patch.object(ytd, "get_js_runtimes", return_value=[("node", "node")]),
                mock.patch("pykuai.core.tui.is_interactive_tty", return_value=True),
                mock.patch("builtins.input", return_value="y"),
                mock.patch.object(ytd, "login_youtube_and_save_cookies", return_value=fake_cookies) as mock_login,
                mock.patch.object(engine, "_run_with_cookie_recovery", side_effect=responses) as mock_run,
            ):
                rc = engine._download(
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "best",
                    False,
                    False,
                    "none",
                    "",
                    tmp,
                    "",
                    console,
                )
            self.assertEqual(rc, 0)
            mock_login.assert_called_once()
            self.assertEqual(mock_run.call_count, 2)
            self.assertEqual(mock_run.call_args_list[1].kwargs["cookies_file"], str(fake_cookies))

        args = argparse.Namespace(install_ffmpeg=False, login=True, proxy="http://127.0.0.1:7897", url="")
        with mock.patch.object(ytd, "login_youtube_and_save_cookies", return_value=Path("cookies.txt")) as mock_cli_login:
            self.assertEqual(engine.run_direct(args, console), 0)
            mock_cli_login.assert_called_once_with(proxy_url="http://127.0.0.1:7897", console=console)

    def test_cdp_client_handles_fragmented_frames_and_ping(self):
        import json
        import socket
        import struct
        import threading
        from pykuai.core.yt_auth import _CdpClient

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def _server_worker():
            conn, _ = server.accept()
            with conn:
                buf = b""
                while b"\r\n\r\n" not in buf:
                    buf += conn.recv(4096)
                conn.sendall(
                    b"HTTP/1.1 101 Switching Protocols\r\n"
                    b"Upgrade: websocket\r\nConnection: Upgrade\r\n\r\n"
                )
                # Read masked client text frame
                b1, b2 = conn.recv(2)
                length = b2 & 0x7F
                mask = conn.recv(4)
                masked = conn.recv(length)
                req = json.loads(bytes(b ^ mask[i % 4] for i, b in enumerate(masked)).decode())

                def _send_srv_frame(opcode_fin: int, data: bytes):
                    hdr = bytearray([opcode_fin])
                    hdr.append(len(data))
                    conn.sendall(bytes(hdr) + data)

                # Send PING, async event to skip, and fragmented JSON response
                _send_srv_frame(0x89, b"hi")
                b_pong_hdr = conn.recv(2)
                pong_mask = conn.recv(4)
                pong_len = b_pong_hdr[1] & 0x7F
                conn.recv(pong_len)
                _send_srv_frame(0x81, json.dumps({"method": "Target.targetCreated"}).encode())
                reply = json.dumps({"id": req["id"], "result": {"cookies": [{"name": "SID"}]}}).encode()
                mid = len(reply) // 2
                _send_srv_frame(0x01, reply[:mid])  # FIN=0 TEXT
                _send_srv_frame(0x80, reply[mid:])  # FIN=1 CONTINUATION

        th = threading.Thread(target=_server_worker, daemon=True)
        th.start()
        try:
            with _CdpClient(f"ws://127.0.0.1:{port}/devtools/browser/test", timeout=3.0) as client:
                res = client.call("Storage.getCookies")
            self.assertEqual(res["cookies"][0]["name"], "SID")
        finally:
            th.join(timeout=3.0)
            server.close()


if __name__ == "__main__":
    unittest.main()
