"""Image conversion regressions using real encoders and failure injection."""

import argparse
import io
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import PIL
from PIL import Image
from rich.console import Console

from pykuai.engines import ifc


class ImageConversionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.source = self.root / "source.png"
        Image.new("RGBA", (80, 40), (20, 40, 200, 0)).save(self.source)
        self.engine = ifc.IfcEngine()
        self.console = Console(file=io.StringIO(), color_system=None)
        self.errors = self.stack.enter_context(patch.object(ifc, "print_error"))
        self.warnings = self.stack.enter_context(patch.object(ifc, "print_warning"))
        self.stack.enter_context(patch.object(ifc, "print_step"))

    def convert(self, target="png", output=None, sizes=None, quality=92, source=None):
        return self.engine._convert_image(
            str(source or self.source), target,
            ifc.STANDARD_ICO_SIZES if sizes is None else sizes,
            str(output) if output is not None else None,
            True, quality, self.console,
        )

    def test_registered_formats_produce_decodable_images(self):
        Image.init()
        for key, spec in ifc.FORMAT_SPECS.items():
            if spec.pillow_fmt not in Image.SAVE:
                continue
            with self.subTest(format=key):
                output = self.root / ("converted" + spec.ext)
                self.assertEqual(self.convert(key, output), 0)
                with Image.open(output) as result:
                    result.load()
                    self.assertEqual(result.format, spec.pillow_fmt)
                    if key != "ico":
                        self.assertEqual(result.size, (80, 40))
        self.assertEqual(list(self.root.glob(".ifc-*")), [])

    def test_jpeg_flattens_transparency_to_white(self):
        output = self.root / "white.jpg"
        self.assertEqual(self.convert("jpg", output), 0)
        with Image.open(output) as result:
            self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))

    def test_png_and_gif_retain_transparent_pixels(self):
        for target in ("png", "gif"):
            with self.subTest(target=target):
                output = self.root / ("transparent." + target)
                self.assertEqual(self.convert(target, output), 0)
                with Image.open(output) as result:
                    self.assertEqual(result.convert("RGBA").getpixel((0, 0))[3], 0)

    def test_exif_orientation_is_applied_once(self):
        source = self.root / "rotated.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (40, 20), "red").save(source, exif=exif)
        output = self.root / "oriented.png"
        self.assertEqual(self.convert(output=output, source=source), 0)
        with Image.open(output) as result:
            self.assertEqual(result.size, (20, 40))
            self.assertIsNone(result.getexif().get(274))

    def test_ico_contains_exact_requested_layers(self):
        output = self.root / "layers.ico"
        self.assertEqual(self.convert("ico", output, [16, 24, 48, 256, 24]), 0)
        with Image.open(output) as result:
            self.assertEqual(result.ico.sizes(), {(16, 16), (24, 24), (48, 48), (256, 256)})

    def test_invalid_ico_layers_do_not_silently_disappear(self):
        output = self.root / "invalid.ico"
        for sizes in ([512], [16, 512], [], [-1], [16.5]):
            with self.subTest(sizes=sizes):
                self.assertEqual(self.convert("ico", output, sizes), 1)
                self.assertFalse(output.exists())

    def test_very_wide_source_uses_only_output_sized_canvases(self):
        Image.new("RGBA", (30000, 1), "red").save(self.source)
        output = self.root / "wide.ico"
        with patch.object(Image, "new", wraps=Image.new) as new_image:
            self.assertEqual(self.convert("ico", output, [16, 256]), 0)
        for call in new_image.call_args_list:
            self.assertLessEqual(max(call.args[1]), 256)
        with Image.open(output) as result:
            self.assertEqual(result.ico.sizes(), {(16, 16), (256, 256)})

    def test_encoder_failure_preserves_existing_output(self):
        output = self.root / "preserved.png"
        output.write_bytes(b"existing output")

        def broken_encoder(image, stream, **kwargs):
            stream.write(b"partial encoding")
            raise OSError("encoder failure")

        with patch.object(Image.Image, "save", new=broken_encoder):
            self.assertEqual(self.convert(output=output), 1)
        self.assertEqual(output.read_bytes(), b"existing output")
        self.assertEqual(list(self.root.glob(".ifc-*")), [])

    def test_replace_failure_preserves_output_and_cleans_temporary_file(self):
        output = self.root / "locked.png"
        output.write_bytes(b"locked output")
        with patch.object(ifc.os, "replace", side_effect=PermissionError("locked")):
            self.assertEqual(self.convert(output=output), 1)
        self.assertEqual(output.read_bytes(), b"locked output")
        self.assertEqual(list(self.root.glob(".ifc-*")), [])

    def test_source_cannot_be_overwritten_through_same_path_or_hardlink(self):
        original = self.source.read_bytes()
        alias = self.root / "alias.png"
        os.link(self.source, alias)
        for output in (self.source, alias):
            with self.subTest(output=output):
                self.assertEqual(self.convert(output=output), 1)
                self.assertEqual(self.source.read_bytes(), original)

    def test_default_same_format_output_gets_converted_suffix(self):
        original = self.source.read_bytes()
        self.assertEqual(self.convert(), 0)
        self.assertTrue((self.root / "source_converted.png").exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_quoted_output_path_is_cleaned_before_format_inference(self):
        output = self.root / "quoted.jpg"
        args = argparse.Namespace(image=str(self.source), output=f'"{output}"', to="", sizes="16", quality=92)
        self.assertEqual(self.engine.run_direct(args, self.console), 0)
        with Image.open(output) as result:
            self.assertEqual(result.format, "JPEG")

    def test_malformed_cli_sizes_are_rejected(self):
        for value in ("16,nope", "16,,32", "", "16,-32", "16,512"):
            with self.subTest(value=value):
                args = argparse.Namespace(image=str(self.source), to="ico", sizes=value)
                self.assertEqual(self.engine.run_direct(args, self.console), 1)
                self.assertFalse((self.root / "source.ico").exists())

    def test_quality_outside_documented_range_is_rejected(self):
        for value in (0, 101, "bad"):
            with self.subTest(value=value):
                self.assertEqual(self.convert("jpg", self.root / "bad.jpg", quality=value), 1)
        self.assertFalse((self.root / "bad.jpg").exists())

    def test_missing_encoder_is_reported_without_creating_output(self):
        Image.init()
        output = self.root / "unsupported.avif"
        with patch.object(Image, "init"), patch.dict(Image.SAVE, {}, clear=True):
            self.assertEqual(self.convert("avif", output), 1)
        self.assertIn("cannot write AVIF", self.errors.call_args.args[0])
        self.assertFalse(output.exists())

    def test_multi_frame_input_reports_first_frame_conversion(self):
        source = self.root / "animated.gif"
        first = Image.new("RGB", (10, 10), "red")
        first.save(source, save_all=True, append_images=[Image.new("RGB", (10, 10), "blue")])
        output = self.root / "frame.png"
        self.assertEqual(self.convert(output=output, source=source), 0)
        self.warnings.assert_called_once()
        with Image.open(output) as result:
            self.assertEqual(result.convert("RGB").getpixel((0, 0)), (255, 0, 0))

    def test_legacy_pillow_resampling_constant_remains_supported(self):
        class LegacyImageAPI:
            LANCZOS = Image.Resampling.LANCZOS

            def __getattr__(self, name):
                if name == "Resampling":
                    raise AttributeError(name)
                return getattr(Image, name)

        with patch.object(PIL, "Image", LegacyImageAPI()):
            self.assertEqual(self.convert("ico", self.root / "legacy.ico", [16]), 0)

    def test_missing_source_in_pipeline_fails_without_prompting(self):
        with patch("pykuai.core.tui.is_interactive_tty", return_value=False), \
                patch.object(ifc.sys, "stdin", io.StringIO()), \
                patch.object(ifc.Prompt, "ask") as prompt:
            self.assertEqual(self.engine.run_interactive(self.console), 1)
        prompt.assert_not_called()
        self.assertIn("source path", self.errors.call_args.args[0])

    def test_fallback_prompt_eof_is_reported_without_crashing(self):
        with patch("pykuai.core.tui.is_interactive_tty", return_value=False), \
                patch.object(ifc.sys, "stdin") as stdin, \
                patch.object(ifc.Prompt, "ask", side_effect=EOFError):
            stdin.isatty.return_value = True
            self.assertEqual(self.engine.run_interactive(self.console), 1)
        self.assertIn("Input ended", self.errors.call_args.args[0])

    def test_redirected_stdout_still_allows_interactive_stdin(self):
        with patch("pykuai.core.tui.is_interactive_tty", return_value=False), \
                patch.object(ifc.sys, "stdin") as stdin, \
                patch.object(ifc.Prompt, "ask", side_effect=[str(self.source), "jpg"]) as prompt:
            stdin.isatty.return_value = True
            self.assertEqual(self.engine.run_interactive(self.console), 0)
        self.assertEqual(prompt.call_count, 2)
        self.assertTrue((self.root / "source.jpg").exists())


if __name__ == "__main__":
    unittest.main()
