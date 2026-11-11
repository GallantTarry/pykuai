"""Navigation contracts for the Tool Tray and its console entry points."""

import argparse
import io
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from unittest.mock import patch

from rich.console import Console

from pykuai.core import tray
from pykuai.core.base import BaseEngine


class FakeEngine(BaseEngine):
    description = "Navigation test tool"
    usage = "tt fake [image] [--quality N]"

    def __init__(self, name, exit_code=0):
        self.name = name
        self.exit_code = exit_code
        self.calls = []

    def register_args(self, parser: argparse.ArgumentParser):
        parser.add_argument("image", nargs="?", default="")
        parser.add_argument("--quality", type=int, default=92)

    def run_interactive(self, console):
        self.calls.append(("interactive",))
        return self.exit_code

    def run_direct(self, args, console):
        self.calls.append(("direct", args.image, args.quality))
        return self.exit_code

    def launch_with_path(self, console, path):
        self.calls.append(("path", path))
        return self.exit_code


class ToolTrayNavigationTests(unittest.TestCase):
    def setUp(self):
        self.console = Console(file=io.StringIO(), color_system=None)
        self.ifc = FakeEngine("ifc")
        self.ytd = FakeEngine("ytd")
        self.engines = {engine.name: engine for engine in (self.ifc, self.ytd)}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(tray, "load_all_engines", return_value=self.engines))
        self.stack.enter_context(patch.object(tray, "get_engine", side_effect=self.engines.get))
        self.tty = self.stack.enter_context(patch("pykuai.core.tui.is_interactive_tty", return_value=True))
        self.launcher = self.stack.enter_context(patch.object(tray, "_build_tt_app"))
        self.launcher.return_value.run.return_value = None
        self.table = self.stack.enter_context(patch.object(tray, "print_tool_tray_table"))
        self.stack.enter_context(patch.object(tray, "print_error"))

    def test_tools_return_to_tray_until_tray_is_closed(self):
        # Cancellation and successful completion both currently return zero.
        self.launcher.return_value.run.side_effect = [self.ifc, self.ytd, None]

        result = tray.run_tool_tray(self.console)

        self.assertEqual(result, 0)
        self.assertEqual(self.ifc.calls, [("interactive",)])
        self.assertEqual(self.ytd.calls, [("interactive",)])
        self.assertEqual(self.launcher.return_value.run.call_count, 3)

    def test_failed_tool_returns_to_tray(self):
        self.ifc.exit_code = 1
        self.launcher.return_value.run.side_effect = [self.ifc, self.ytd, None]

        tray.run_tool_tray(self.console)

        self.assertEqual(self.ytd.calls, [("interactive",)])
        self.assertEqual(self.launcher.return_value.run.call_count, 3)

    def test_external_visual_tray_also_loops(self):
        self.launcher.return_value.run.side_effect = [self.ifc, None]

        tray.run_tool_tray(self.console, interactive=False)

        self.assertEqual(self.ifc.calls, [("interactive",)])
        self.assertEqual(self.launcher.return_value.run.call_count, 2)

    def test_console_shortcut_returns_to_tray(self):
        tray.run_tool_tray(self.console, ["ifc"], interactive=True)

        self.assertEqual(self.ifc.calls, [("interactive",)])
        self.launcher.return_value.run.assert_called_once()

    def test_console_path_shortcut_returns_to_tray(self):
        path = r"C:\Images\my picture.png"

        tray.run_tool_tray(self.console, ["ifc", path], interactive=True)

        self.assertEqual(self.ifc.calls, [("path", path)])
        self.launcher.return_value.run.assert_called_once()

    def test_console_option_command_returns_to_tray(self):
        tray.run_tool_tray(self.console, ["ifc", "picture.png", "--quality", "90"], interactive=True)

        self.assertEqual(self.ifc.calls, [("direct", "picture.png", 90)])
        self.launcher.return_value.run.assert_called_once()

    def test_external_direct_command_preserves_exit_code(self):
        self.ifc.exit_code = 7

        result = tray.run_tool_tray(self.console, ["ifc", "picture.png"], interactive=False)

        self.assertEqual(result, 7)
        self.assertEqual(self.ifc.calls, [("direct", "picture.png", 92)])
        self.launcher.assert_not_called()

    def test_external_named_tool_runs_once(self):
        self.ifc.exit_code = 7

        result = tray.run_tool_tray(self.console, ["ifc"], interactive=False)

        self.assertEqual(result, 7)
        self.assertEqual(self.ifc.calls, [("interactive",)])
        self.launcher.assert_not_called()

    def test_non_tty_without_tool_prints_table_once(self):
        self.tty.return_value = False

        self.assertEqual(tray.run_tool_tray(self.console), 0)

        self.table.assert_called_once_with(self.engines, self.console)
        self.launcher.assert_not_called()

    def test_non_tty_command_does_not_start_navigation_loop(self):
        self.tty.return_value = False
        self.ifc.exit_code = 3

        result = tray.run_tool_tray(self.console, ["ifc", "--quality", "90"], interactive=True)

        self.assertEqual(result, 3)
        self.assertEqual(self.ifc.calls, [("direct", "", 90)])
        self.launcher.assert_not_called()

    def test_tray_help_does_not_start_navigation_loop(self):
        self.assertEqual(tray.run_tool_tray(self.console, ["--help"]), 0)

        self.table.assert_called_once()
        self.launcher.assert_not_called()

    def test_engine_help_remains_visible_without_opening_tray(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = tray.run_tool_tray(self.console, ["ifc", "--help"], interactive=True)

        self.assertEqual(result, 0)
        self.assertIn("--quality", output.getvalue())
        self.assertEqual(self.ifc.calls, [])
        self.launcher.assert_not_called()

    def test_argument_error_remains_visible_without_opening_tray(self):
        output = io.StringIO()
        with redirect_stderr(output):
            result = tray.run_tool_tray(self.console, ["ifc", "--quality", "invalid"], interactive=True)

        self.assertEqual(result, 2)
        self.assertIn("invalid", output.getvalue())
        self.assertEqual(self.ifc.calls, [])
        self.launcher.assert_not_called()

    def test_unknown_tool_does_not_start_navigation_loop(self):
        self.assertEqual(tray.run_tool_tray(self.console, ["unknown"]), 1)

        self.launcher.assert_not_called()


class ConsoleImageDropRoutingTests(unittest.TestCase):
    def test_image_drop_uses_tray_dispatch(self):
        from pykuai import cli

        path = r"C:\Images\my picture.png"
        with ExitStack() as stack:
            for name in (
                "warmup_sfx", "clear_screen", "apply_terminal_identity",
                "print_banner", "play_console_greeting", "restore_terminal_identity",
            ):
                stack.enter_context(patch.object(cli, name))
            stack.enter_context(patch.object(cli, "console", Console(file=io.StringIO())))
            stack.enter_context(patch.object(cli, "_read_console_command", side_effect=[path, "gg"]))
            stack.enter_context(patch.object(cli.os.path, "exists", return_value=True))
            dispatch = stack.enter_context(patch.object(tray, "run_tool_tray", return_value=0))

            cli.run_interactive_console(skip_intro=True)

            dispatch.assert_called_once_with(cli.console, cli_args=["ifc", path], interactive=True)


if __name__ == "__main__":
    unittest.main()
