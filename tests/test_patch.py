import tempfile
import unittest
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from ptt_font_tool.audit import audit_font
from ptt_font_tool.patch import patch_font_metrics


def _empty_glyph():
    pen = TTGlyphPen(None)
    return pen.glyph()


def _build_patch_fixture(path: Path) -> None:
    glyph_order = [".notdef", "A", "uni6F22", "uni02C7"]
    glyphs = {glyph_name: _empty_glyph() for glyph_name in glyph_order}

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({
        ord("A"): "A",
        ord("漢"): "uni6F22",
        ord("ˇ"): "uni02C7",
    })
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        ".notdef": (500, 0),
        "A": (794, 20),
        "uni6F22": (900, 43),
        "uni02C7": (766, 200),
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": "Patch Fixture",
        "styleName": "Regular",
        "uniqueFontIdentifier": "Patch Fixture Regular",
        "fullName": "Patch Fixture Regular",
        "psName": "PatchFixture-Regular",
    })
    builder.setupPost()
    builder.save(path)


class PatchFontMetricsTest(unittest.TestCase):
    def test_patches_sample_glyph_advance_widths_to_term_ptt_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_patch_fixture(input_path)

            result = patch_font_metrics(input_path, output_path, sample_text="A漢ˇ")

            audited = audit_font(output_path, sample_text="A漢ˇ")

        self.assertTrue(audited.ok)
        patched = {item.character: item for item in result.patched_glyphs}
        self.assertEqual(patched["A"].old_advance, 794)
        self.assertEqual(patched["A"].new_advance, 500)
        self.assertEqual(patched["漢"].old_advance, 900)
        self.assertEqual(patched["漢"].new_advance, 1000)
        self.assertEqual(patched["ˇ"].old_advance, 766)
        self.assertEqual(patched["ˇ"].new_advance, 1000)

    def test_preserves_missing_characters_as_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_patch_fixture(input_path)

            result = patch_font_metrics(input_path, output_path, sample_text="A好")

        skipped = {item.character: item for item in result.skipped_glyphs}
        self.assertEqual(skipped["好"].reason, "missing")


if __name__ == "__main__":
    unittest.main()
