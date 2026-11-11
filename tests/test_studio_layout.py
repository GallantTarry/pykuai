"""Keep studio controls reachable in standard and narrow terminal windows."""

import asyncio
import os
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from rich.cells import cell_len
from textual.widgets import Button, Input

from pykuai.engines.ifc import _build_ifc_studio_app
from pykuai.engines.ytd import _build_ytd_studio_app


class StudioLayoutTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Textual creates many short-lived tasks; asyncio debug traces obscure failures.
        asyncio.get_running_loop().set_debug(False)

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name in ("warmup_sfx", "play_sfx"):
            self.stack.enter_context(patch(f"pykuai.core.tui.{name}"))
        self.stack.enter_context(patch("pykuai.engines.ytd.resolve_ytdlp_runner", return_value=None))
        self.stack.enter_context(patch("pykuai.engines.ytd.get_ffmpeg", return_value=None))
        self.stack.enter_context(patch("pykuai.engines.ytd.get_js_runtimes", return_value=[]))
        self.paths = [
            os.path.abspath(f"a_very_long_image_name_[red]_{'x' * 80}_{index}.png")
            for index in range(5)
        ]
        self.stack.enter_context(patch("pykuai.engines.ifc._discover_local_images", return_value=self.paths))

    def assert_buttons_fit(self, app):
        for button in app.query(Button):
            region = button.region
            if region.width == 0:
                continue  # A hidden format section has no layout box.
            with self.subTest(button=button.id):
                self.assertGreaterEqual(region.x, button.parent.region.x)
                self.assertLessEqual(region.right, button.parent.region.right)
                if not (button.id or "").startswith("pick-"):
                    self.assertLessEqual(cell_len(str(button.label)), button.content_size.width)
        content = app.query_one("#studio-card").content_region
        for selector in ("#btn-run", "#btn-cancel"):
            region = app.query_one(selector).region
            with self.subTest(action=selector):
                self.assertGreaterEqual(region.y, content.y)
                self.assertLessEqual(region.bottom, content.bottom)
                self.assertGreaterEqual(region.x, content.x)
                self.assertLessEqual(region.right, content.right)

    async def test_layout_keeps_actions_visible_and_options_within_rows(self):
        for build in (_build_ifc_studio_app, _build_ytd_studio_app):
            for size in ((100, 30), (80, 24), (60, 20), (40, 16)):
                with self.subTest(studio=build.__name__, size=size):
                    app = build()
                    async with app.run_test(size=size):
                        self.assert_buttons_fit(app)

    async def test_long_filenames_are_literal_and_last_file_can_be_selected(self):
        app = _build_ifc_studio_app()
        async with app.run_test(size=(40, 16)) as pilot:
            button = app.query_one("#pick-4")
            self.assertEqual(str(button.label), os.path.basename(self.paths[4]))
            self.assertEqual(button.tooltip, self.paths[4])
            button.scroll_visible(animate=False)
            await pilot.pause()
            self.assertTrue(await pilot.click("#pick-4"))
            self.assertEqual(app.query_one("#src-input", Input).value, self.paths[4])
            self.assert_buttons_fit(app)

    async def test_narrow_downloader_can_select_firefox(self):
        app = _build_ytd_studio_app()
        async with app.run_test(size=(40, 16)) as pilot:
            app.query_one("#ck-firefox").scroll_visible(animate=False)
            await pilot.pause()
            self.assertTrue(await pilot.click("#ck-firefox"))
            self.assertEqual(app._active_group_value("ck-", "none"), "firefox")
            self.assert_buttons_fit(app)

    async def test_converter_quality_controls_fit_after_format_switch(self):
        app = _build_ifc_studio_app()
        async with app.run_test(size=(40, 16)) as pilot:
            self.assertEqual(app._active_quality(), 92)
            app.query_one("#fmt-jpg").scroll_visible(animate=False)
            await pilot.pause()
            self.assertTrue(await pilot.click("#fmt-jpg"))
            app.query_one("#qual-100").scroll_visible(animate=False)
            await pilot.pause()
            self.assertTrue(await pilot.click("#qual-100"))
            self.assertEqual(app._active_quality(), 100)
            self.assert_buttons_fit(app)

    async def test_long_errors_wrap_without_displacing_cancel(self):
        for build in (_build_ifc_studio_app, _build_ytd_studio_app):
            with self.subTest(studio=build.__name__):
                app = build()
                async with app.run_test(size=(40, 16)) as pilot:
                    app._set_error("Please choose a valid image or video URL before continuing with this operation.")
                    await pilot.pause()
                    self.assertGreater(app.query_one("#form-error").region.height, 1)
                    self.assert_buttons_fit(app)
                    with patch.object(app, "exit", wraps=app.exit) as exited:
                        self.assertTrue(await pilot.click("#btn-cancel"))
                        exited.assert_called_once_with(None)

    async def test_invalid_output_is_reported_without_closing_converter(self):
        with patch("pykuai.engines.ifc._inspect_image", return_value=(True, "Valid image")):
            app = _build_ifc_studio_app(initial_path=self.paths[0])
            async with app.run_test(size=(40, 16)) as pilot:
                for output in (self.paths[0], os.path.abspath("wrong-extension.jpg"), os.getcwd()):
                    with self.subTest(output=output), patch.object(app, "exit") as exited:
                        app.query_one("#out-input", Input).value = output
                        app._submit()
                        await pilot.pause()
                        exited.assert_not_called()
                        self.assertTrue(app.query_one("#form-error").has_class("shown-err"))
                        self.assert_buttons_fit(app)

    async def test_resize_reflows_options_in_both_directions(self):
        for build in (_build_ifc_studio_app, _build_ytd_studio_app):
            with self.subTest(studio=build.__name__):
                app = build()
                async with app.run_test(size=(100, 30)) as pilot:
                    self.assertFalse(app.screen.has_class("narrow"))
                    await pilot.resize_terminal(40, 16)
                    self.assertTrue(app.screen.has_class("narrow"))
                    self.assert_buttons_fit(app)
                    await pilot.resize_terminal(100, 30)
                    self.assertFalse(app.screen.has_class("narrow"))
                    self.assert_buttons_fit(app)


if __name__ == "__main__":
    unittest.main()
