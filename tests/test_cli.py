import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from ptt_font_tool.cli import main
from ptt_font_tool.audit import audit_font


def _empty_glyph():
    pen = TTGlyphPen(None)
    return pen.glyph()


def _build_cli_fixture(
    path: Path,
    metrics: Optional[dict[str, tuple[int, int]]] = None,
) -> None:
    active_metrics = metrics or {
        "A": (794, 20),
        "uni6F22": (900, 43),
    }
    glyph_order = [".notdef", "A", "uni6F22"]
    glyphs = {glyph_name: _empty_glyph() for glyph_name in glyph_order}

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({
        ord("A"): "A",
        ord("漢"): "uni6F22",
    })
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        ".notdef": (500, 0),
        "A": active_metrics["A"],
        "uni6F22": active_metrics["uni6F22"],
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": "CLI Fixture",
        "styleName": "Regular",
        "uniqueFontIdentifier": "CLI Fixture Regular",
        "fullName": "CLI Fixture Regular",
        "psName": "CLIFixture-Regular",
    })
    builder.setupPost()
    builder.save(path)


def _build_cli_symbol_fallback(path: Path) -> None:
    glyph_order = [".notdef", "leftArrow"]
    glyphs = {glyph_name: _empty_glyph() for glyph_name in glyph_order}

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({ord("←"): "leftArrow"})
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        ".notdef": (500, 0),
        "leftArrow": (1000, 0),
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": path.stem,
        "styleName": "Regular",
        "uniqueFontIdentifier": f"{path.stem} Regular",
        "fullName": f"{path.stem} Regular",
        "psName": f"{path.stem}-Regular",
    })
    builder.setupPost()
    builder.save(path)


def _family_names(font_path: Path) -> set[str]:
    font = TTFont(font_path)
    try:
        return {
            record.toUnicode()
            for record in font["name"].names
            if record.nameID in {1, 4, 6}
        }
    finally:
        font.close()


class CliTest(unittest.TestCase):
    def test_audit_reports_failures_without_failing_the_command(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "fixture.otf"
            _build_cli_fixture(input_path)
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "audit",
                    str(input_path),
                    "--sample-text",
                    "A漢",
                ])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("FAIL:", output)
        self.assertIn("U+0041", output)
        self.assertIn("expected=500", output)
        self.assertIn("actual=794", output)
        self.assertIn("U+6F22", output)
        self.assertIn("expected=1000", output)
        self.assertIn("actual=900", output)

    def test_verify_returns_zero_for_ptt_compatible_fonts(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "fixture.otf"
            _build_cli_fixture(
                input_path,
                metrics={
                    "A": (500, 0),
                    "uni6F22": (1000, 0),
                },
            )
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "verify",
                    str(input_path),
                    "--sample-text",
                    "A漢",
                ])

        self.assertEqual(exit_code, 0)
        self.assertIn("OK:", stdout.getvalue())

    def test_verify_returns_one_for_metric_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "fixture.otf"
            _build_cli_fixture(input_path)
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "verify",
                    str(input_path),
                    "--sample-text",
                    "A漢",
                ])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("FAIL:", output)
        self.assertIn("U+0041", output)

    def test_verify_scans_cmap_when_sample_text_is_omitted(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "fixture.otf"
            _build_cli_fixture(
                input_path,
                metrics={
                    "A": (500, 0),
                    "uni6F22": (900, 0),
                },
            )
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main(["verify", str(input_path)])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("U+6F22", output)
        self.assertIn("actual=900", output)

    def test_patch_writes_default_ptt_output_and_custom_family_name(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "fixture.otf"
            output_path = Path(directory) / "fixture-ptt.otf"
            _build_cli_fixture(input_path)

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main([
                    "patch",
                    str(input_path),
                    "--family-name",
                    "CLI Custom PTT",
                ])

            names = _family_names(output_path)
            audit = audit_font(output_path, sample_text="A漢")

        self.assertEqual(exit_code, 0)
        self.assertIn("CLI Custom PTT", names)
        self.assertIn("CLI Custom PTT Regular", names)
        self.assertTrue(audit.ok)

    def test_patch_accepts_fit_strategy_and_explicit_output(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "fixture.otf"
            output_path = Path(directory) / "custom-output.otf"
            _build_cli_fixture(input_path)

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main([
                    "patch",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--sample-text",
                    "A漢",
                    "--strategy",
                    "fit",
                ])

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())

    def test_build_accepts_primary_and_fallback_stack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "fixture.ttf"
            fallback_path = root / "symbols.ttf"
            output_path = root / "built.ttf"
            _build_cli_fixture(input_path)
            _build_cli_symbol_fallback(fallback_path)

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                exit_code = main([
                    "build",
                    str(input_path),
                    str(fallback_path),
                    "--output",
                    str(output_path),
                    "--required-fallback-chars",
                    "←",
                    "--sample-text",
                    "A漢←",
                    "--noto",
                    "off",
                ])

            audit = audit_font(output_path, sample_text="A漢←")

        self.assertEqual(exit_code, 0)
        self.assertTrue(audit.ok)
        self.assertIn(str(output_path), stdout.getvalue())

    def test_build_uses_env_fallback_when_no_explicit_fallback_is_given(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "fixture.ttf"
            fallback_path = root / "symbols.ttf"
            output_path = root / "built.ttf"
            _build_cli_fixture(input_path)
            _build_cli_symbol_fallback(fallback_path)

            with patch.dict("os.environ", {"PTT_FONT_TOOL_FALLBACK_FONTS": str(fallback_path)}, clear=True):
                with contextlib.redirect_stdout(io.StringIO()):
                    exit_code = main([
                        "build",
                        str(input_path),
                        "--output",
                        str(output_path),
                        "--required-fallback-chars",
                        "←",
                        "--sample-text",
                        "A漢←",
                        "--noto",
                        "off",
                    ])

            audit = audit_font(output_path, sample_text="A漢←")

        self.assertEqual(exit_code, 0)
        self.assertTrue(audit.ok)

    def test_noto_path_uses_fonts_dir_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            fonts_dir = Path(directory) / "fonts"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "noto",
                    "path",
                    "--fonts-dir",
                    str(fonts_dir),
                    "--noto",
                    "serif",
                ])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), str(fonts_dir / "noto"))

    def test_noto_status_reports_missing_assets_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            fonts_dir = Path(directory) / "fonts"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "noto",
                    "status",
                    "--fonts-dir",
                    str(fonts_dir),
                    "--noto",
                    "sans",
                ])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn(f"Noto cache: {fonts_dir / 'noto'}", output)
        self.assertIn("Missing: Noto Sans Symbols 2, Noto Sans TC, SIL Open Font License 1.1", output)


if __name__ == "__main__":
    unittest.main()
