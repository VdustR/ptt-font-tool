import tempfile
import unittest
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from ptt_font_tool.audit import audit_font


def _empty_glyph():
    pen = TTGlyphPen(None)
    return pen.glyph()


def _build_test_font(path: Path, metrics: dict[str, tuple[int, int]]) -> None:
    glyph_order = [".notdef", "A", "uni6F22", "uni02C7"]
    glyphs = {glyph_name: _empty_glyph() for glyph_name in glyph_order}

    builder = FontBuilder(1200, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({
        ord("A"): "A",
        ord("漢"): "uni6F22",
        ord("ˇ"): "uni02C7",
    })
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        ".notdef": (600, 0),
        "A": metrics["A"],
        "uni6F22": metrics["uni6F22"],
        "uni02C7": metrics["uni02C7"],
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": "Audit Fixture",
        "styleName": "Regular",
        "uniqueFontIdentifier": "Audit Fixture Regular",
        "fullName": "Audit Fixture Regular",
        "psName": "AuditFixture-Regular",
    })
    builder.setupPost()
    builder.save(path)


class AuditFontTest(unittest.TestCase):
    def test_reports_expected_and_actual_advance_widths(self):
        with tempfile.TemporaryDirectory() as directory:
            font_path = Path(directory) / "fixture.ttf"
            _build_test_font(
                font_path,
                {
                    "A": (600, 0),
                    "uni6F22": (1200, 0),
                    "uni02C7": (700, 0),
                },
            )

            result = audit_font(font_path, sample_text="A漢ˇ")

        self.assertEqual(result.units_per_em, 1200)
        checks = {check.character: check for check in result.checks}

        self.assertTrue(checks["A"].ok)
        self.assertEqual(checks["A"].glyph_name, "A")
        self.assertEqual(checks["A"].expected_advance, 600)
        self.assertEqual(checks["A"].actual_advance, 600)

        self.assertTrue(checks["漢"].ok)
        self.assertEqual(checks["漢"].expected_advance, 1200)
        self.assertEqual(checks["漢"].actual_advance, 1200)

        self.assertFalse(checks["ˇ"].ok)
        self.assertEqual(checks["ˇ"].glyph_name, "uni02C7")
        self.assertEqual(checks["ˇ"].expected_advance, 1200)
        self.assertEqual(checks["ˇ"].actual_advance, 700)

    def test_reports_missing_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            font_path = Path(directory) / "fixture.ttf"
            _build_test_font(
                font_path,
                {
                    "A": (600, 0),
                    "uni6F22": (1200, 0),
                    "uni02C7": (1200, 0),
                },
            )

            result = audit_font(font_path, sample_text="A好")

        checks = {check.character: check for check in result.checks}

        self.assertTrue(checks["A"].ok)
        self.assertFalse(checks["好"].ok)
        self.assertEqual(checks["好"].status, "missing")
        self.assertIsNone(checks["好"].actual_advance)


if __name__ == "__main__":
    unittest.main()
