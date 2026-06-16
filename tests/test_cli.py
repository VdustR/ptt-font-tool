import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from typing import Optional

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


if __name__ == "__main__":
    unittest.main()
