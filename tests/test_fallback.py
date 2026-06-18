import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from ptt_font_tool.audit import audit_font
from ptt_font_tool.fallback import (
    PTT_REQUIRED_SYMBOLS,
    find_missing_glyphs,
    merge_missing_glyphs,
)


def _empty_glyph():
    pen = TTGlyphPen(None)
    return pen.glyph()


def _rectangle_glyph(x_min: int, x_max: int):
    pen = TTGlyphPen(None)
    pen.moveTo((x_min, 0))
    pen.lineTo((x_max, 0))
    pen.lineTo((x_max, 700))
    pen.lineTo((x_min, 700))
    pen.closePath()
    return pen.glyph()


def _build_ttf(path: Path, cmap: dict[str, str], widths: dict[str, int]) -> None:
    glyph_order = [".notdef", *dict.fromkeys(cmap.values())]
    glyphs = {".notdef": _empty_glyph()}
    for glyph_name in glyph_order:
        if glyph_name == ".notdef":
            continue
        glyphs[glyph_name] = _rectangle_glyph(100, widths[glyph_name] - 100)

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({ord(character): glyph for character, glyph in cmap.items()})
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        glyph_name: (widths.get(glyph_name, 500), 0)
        for glyph_name in glyph_order
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


def _glyph_bounds(font_path: Path, character: str):
    font = TTFont(font_path)
    try:
        cmap = font.getBestCmap() or {}
        glyph_name = cmap[ord(character)]
        glyph_set = font.getGlyphSet()
        pen = BoundsPen(glyph_set)
        glyph_set[glyph_name].draw(pen)
        return pen.bounds
    finally:
        font.close()


class FallbackTest(unittest.TestCase):
    def test_ptt_required_symbols_include_common_navigation_and_blocks(self):
        for character in "←→↑↓◎○●◆◇★☆│─█▁▂▃▄▅▆▇【】":
            self.assertIn(character, PTT_REQUIRED_SYMBOLS)

    def test_find_missing_glyphs_reports_required_characters_not_in_cmap(self):
        with tempfile.TemporaryDirectory() as directory:
            font_path = Path(directory) / "target.ttf"
            _build_ttf(font_path, {"A": "A"}, {"A": 500})

            missing = find_missing_glyphs(font_path, "A←→")

        self.assertEqual(missing, ["←", "→"])

    def test_merge_missing_glyphs_uses_ordered_fallback_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_path = root / "target.ttf"
            fallback_one = root / "fallback-one.ttf"
            fallback_two = root / "fallback-two.ttf"
            output_path = root / "merged.ttf"
            _build_ttf(target_path, {"A": "A"}, {"A": 500})
            _build_ttf(fallback_one, {"←": "leftArrow"}, {"leftArrow": 1000})
            _build_ttf(
                fallback_two,
                {"←": "leftArrowAlt", "→": "rightArrow"},
                {"leftArrowAlt": 1000, "rightArrow": 1000},
            )

            result = merge_missing_glyphs(
                target_path,
                output_path,
                fallback_paths=[fallback_one, fallback_two],
                required_chars="A←→◎",
            )
            audited = audit_font(output_path, sample_text="A←→")
            unresolved = find_missing_glyphs(output_path, "A←→◎")

        self.assertEqual(result.added, ["←", "→"])
        self.assertEqual(result.unresolved, ["◎"])
        self.assertEqual(result.sources["←"], fallback_one)
        self.assertEqual(result.sources["→"], fallback_two)
        self.assertTrue(audited.ok)
        self.assertEqual(unresolved, ["◎"])

    def test_merge_missing_glyphs_fits_oversized_fallback_glyphs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_path = root / "target.ttf"
            fallback_path = root / "fallback.ttf"
            output_path = root / "merged.ttf"
            _build_ttf(target_path, {"A": "A"}, {"A": 500})
            _build_ttf(fallback_path, {"←": "leftArrow"}, {"leftArrow": 1600})

            merge_missing_glyphs(
                target_path,
                output_path,
                fallback_paths=[fallback_path],
                required_chars="←",
            )
            x_min, _, x_max, _ = _glyph_bounds(output_path, "←")

        self.assertGreaterEqual(x_min, 0)
        self.assertLessEqual(x_max, 1000)

    def test_merge_missing_glyphs_closes_open_fonts_if_fallback_open_fails(self):
        closed_fonts: list[str] = []

        class FakeFont:
            def __init__(self, label: str) -> None:
                self.label = label

            def __contains__(self, key: str) -> bool:
                return key == "glyf"

            def getBestCmap(self) -> dict[int, str]:
                return {}

            def close(self) -> None:
                closed_fonts.append(self.label)

        def open_font(path: Path):
            name = Path(path).name
            if name == "fallback-two.ttf":
                raise RuntimeError("failed to open fallback")

            return FakeFont(name)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("ptt_font_tool.fallback._open_font", side_effect=open_font):
                with self.assertRaises(RuntimeError):
                    merge_missing_glyphs(
                        root / "target.ttf",
                        root / "merged.ttf",
                        fallback_paths=[
                            root / "fallback-one.ttf",
                            root / "fallback-two.ttf",
                        ],
                        required_chars="←",
                    )

        self.assertCountEqual(closed_fonts, ["target.ttf", "fallback-one.ttf"])


if __name__ == "__main__":
    unittest.main()
