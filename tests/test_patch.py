import tempfile
import unittest
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from ptt_font_tool.audit import audit_font
from ptt_font_tool.patch import default_output_path, patch_font


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
    _add_typographic_family_name(path, "Patch Fixture Typographic")


def _build_shared_glyph_fixture(path: Path) -> None:
    glyph_order = [".notdef", "shared"]
    glyphs = {glyph_name: _empty_glyph() for glyph_name in glyph_order}

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({
        ord("A"): "shared",
        ord("Ａ"): "shared",
    })
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        ".notdef": (500, 0),
        "shared": (800, 0),
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": "Shared Fixture",
        "styleName": "Regular",
        "uniqueFontIdentifier": "Shared Fixture Regular",
        "fullName": "Shared Fixture Regular",
        "psName": "SharedFixture-Regular",
    })
    builder.setupPost()
    builder.save(path)


def _rectangle_glyph(x_min: int, x_max: int):
    pen = TTGlyphPen(None)
    pen.moveTo((x_min, 0))
    pen.lineTo((x_max, 0))
    pen.lineTo((x_max, 700))
    pen.lineTo((x_min, 700))
    pen.closePath()
    return pen.glyph()


def _component_glyph(base_glyph_name: str):
    pen = TTGlyphPen({base_glyph_name: None})
    pen.addComponent(base_glyph_name, (1, 0, 0, 1, 0, 0))
    return pen.glyph()


def _build_outline_fixture(path: Path) -> None:
    glyph_order = [".notdef", "wide"]
    glyphs = {
        ".notdef": _empty_glyph(),
        "wide": _rectangle_glyph(20, 780),
    }

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({ord("A"): "wide"})
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        ".notdef": (500, 0),
        "wide": (800, 20),
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": "Outline Fixture",
        "styleName": "Regular",
        "uniqueFontIdentifier": "Outline Fixture Regular",
        "fullName": "Outline Fixture Regular",
        "psName": "OutlineFixture-Regular",
    })
    builder.setupPost()
    builder.save(path)


def _build_ligature_fixture(
    path: Path,
    *,
    doublef_bounds: tuple[int, int] = (100, 860),
) -> None:
    glyph_order = [".notdef", "f", "doublef"]
    glyphs = {
        ".notdef": _empty_glyph(),
        "f": _rectangle_glyph(100, 420),
        "doublef": _rectangle_glyph(*doublef_bounds),
    }

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({ord("f"): "f"})
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        ".notdef": (500, 0),
        "f": (700, 100),
        "doublef": (760, 100),
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": "Ligature Fixture",
        "styleName": "Regular",
        "uniqueFontIdentifier": "Ligature Fixture Regular",
        "fullName": "Ligature Fixture Regular",
        "psName": "LigatureFixture-Regular",
    })
    builder.setupPost()
    builder.save(path)

    font = TTFont(path)
    try:
        addOpenTypeFeaturesFromString(font, "feature liga { sub f f by doublef; } liga;")
        font.save(path)
    finally:
        font.close()


def _build_mixed_ligature_fixture(path: Path) -> None:
    glyph_order = [".notdef", "f", "i", "fi"]
    glyphs = {
        ".notdef": _empty_glyph(),
        "f": _rectangle_glyph(100, 420),
        "i": _rectangle_glyph(100, 260),
        "fi": _rectangle_glyph(100, 700),
    }

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({
        ord("f"): "f",
        ord("i"): "i",
    })
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        ".notdef": (500, 0),
        "f": (700, 100),
        "i": (300, 100),
        "fi": (760, 100),
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": "Mixed Ligature Fixture",
        "styleName": "Regular",
        "uniqueFontIdentifier": "Mixed Ligature Fixture Regular",
        "fullName": "Mixed Ligature Fixture Regular",
        "psName": "MixedLigatureFixture-Regular",
    })
    builder.setupPost()
    builder.save(path)

    font = TTFont(path)
    try:
        addOpenTypeFeaturesFromString(font, "feature liga { sub f i by fi; } liga;")
        font.save(path)
    finally:
        font.close()


def _build_pair_positioning_fixture(path: Path) -> None:
    glyph_order = [".notdef", "A", "V"]
    glyphs = {
        ".notdef": _empty_glyph(),
        "A": _rectangle_glyph(100, 500),
        "V": _rectangle_glyph(100, 500),
    }

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({
        ord("A"): "A",
        ord("V"): "V",
    })
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        ".notdef": (500, 0),
        "A": (700, 100),
        "V": (700, 100),
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": "Pair Positioning Fixture",
        "styleName": "Regular",
        "uniqueFontIdentifier": "Pair Positioning Fixture Regular",
        "fullName": "Pair Positioning Fixture Regular",
        "psName": "PairPositioningFixture-Regular",
    })
    builder.setupPost()
    builder.save(path)

    font = TTFont(path)
    try:
        addOpenTypeFeaturesFromString(font, "feature kern { pos A V -120; } kern;")
        font.save(path)
    finally:
        font.close()


def _build_composite_outline_fixture(path: Path) -> None:
    glyph_order = [".notdef", "base", "composite"]
    glyphs = {
        ".notdef": _empty_glyph(),
        "base": _rectangle_glyph(20, 780),
        "composite": _component_glyph("base"),
    }

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({
        ord("A"): "base",
        ord("B"): "composite",
    })
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        ".notdef": (500, 0),
        "base": (800, 20),
        "composite": (800, 20),
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": "Composite Fixture",
        "styleName": "Regular",
        "uniqueFontIdentifier": "Composite Fixture Regular",
        "fullName": "Composite Fixture Regular",
        "psName": "CompositeFixture-Regular",
    })
    builder.setupPost()
    builder.save(path)


def _draw_cff_rectangle(pen, x_min: int, x_max: int) -> None:
    pen.moveTo((x_min, 0))
    pen.lineTo((x_max, 0))
    pen.lineTo((x_max, 700))
    pen.lineTo((x_min, 700))
    pen.closePath()


def _build_cff_outline_fixture(path: Path) -> None:
    glyph_order = [".notdef", "wide"]
    char_strings = {}
    for glyph_name in glyph_order:
        pen = T2CharStringPen(800, None)
        if glyph_name == "wide":
            _draw_cff_rectangle(pen, 20, 780)
        char_strings[glyph_name] = pen.getCharString()

    builder = FontBuilder(1000, isTTF=False)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({ord("A"): "wide"})
    builder.setupCFF(
        "CFFOutlineFixture-Regular",
        {"FullName": "CFF Outline Fixture Regular"},
        char_strings,
        {},
    )
    builder.setupHorizontalMetrics({
        ".notdef": (500, 0),
        "wide": (800, 20),
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": "CFF Outline Fixture",
        "styleName": "Regular",
        "uniqueFontIdentifier": "CFF Outline Fixture Regular",
        "fullName": "CFF Outline Fixture Regular",
        "psName": "CFFOutlineFixture-Regular",
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


def _glyph_bounds_by_name(font_path: Path, glyph_name: str):
    font = TTFont(font_path)
    try:
        glyph_set = font.getGlyphSet()
        pen = BoundsPen(glyph_set)
        glyph_set[glyph_name].draw(pen)
        return pen.bounds
    finally:
        font.close()


def _glyph_metrics(font_path: Path, glyph_name: str) -> tuple[int, int]:
    font = TTFont(font_path)
    try:
        return font["hmtx"].metrics[glyph_name]
    finally:
        font.close()


def _gpos_lookup_types(font_path: Path) -> list[int]:
    font = TTFont(font_path)
    try:
        if "GPOS" not in font:
            return []

        lookup_list = font["GPOS"].table.LookupList
        return [lookup.LookupType for lookup in lookup_list.Lookup]
    finally:
        font.close()


def _family_names(font_path: Path) -> set[str]:
    return _names_by_id(font_path, {1, 4, 6, 16})


def _names_by_id(font_path: Path, name_ids: set[int]) -> set[str]:
    font = TTFont(font_path)
    try:
        return {
            record.toUnicode()
            for record in font["name"].names
            if record.nameID in name_ids
        }
    finally:
        font.close()


def _add_typographic_family_name(font_path: Path, family_name: str) -> None:
    font = TTFont(font_path)
    try:
        font["name"].setName(family_name, 16, 3, 1, 0x409)
        font.save(font_path)
    finally:
        font.close()


class PatchFontTest(unittest.TestCase):
    def test_patches_sample_glyph_advance_widths_to_term_ptt_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_patch_fixture(input_path)

            result = patch_font(input_path, output_path, sample_text="A漢ˇ")

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

            result = patch_font(input_path, output_path, sample_text="A好")

        skipped = {item.character: item for item in result.skipped_glyphs}
        self.assertEqual(skipped["好"].reason, "missing")

    def test_shared_glyph_uses_the_widest_target_advance(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_shared_glyph_fixture(input_path)

            patch_font(input_path, output_path, sample_text="AＡ")

            font = TTFont(output_path)
            try:
                self.assertEqual(font["hmtx"].metrics["shared"][0], 1000)
            finally:
                font.close()

    def test_center_strategy_preserves_outline_width_and_centers_the_glyph(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_outline_fixture(input_path)

            patch_font(input_path, output_path, sample_text="A", strategy="center")

            bounds = _glyph_bounds(output_path, "A")

        self.assertEqual(bounds, (-130, 0, 630, 700))

    def test_fit_strategy_scales_oversized_outline_and_centers_the_glyph(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_outline_fixture(input_path)

            patch_font(input_path, output_path, sample_text="A", strategy="fit")

            bounds = _glyph_bounds(output_path, "A")

        self.assertEqual(bounds, (0, 0, 500, 700))

    def test_patches_ligature_advance_to_component_advance_sum_and_centers_it(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_ligature_fixture(input_path)

            patch_font(input_path, output_path, sample_text="f", strategy="center")

            ligature_metrics = _glyph_metrics(output_path, "doublef")
            ligature_bounds = _glyph_bounds_by_name(output_path, "doublef")

        self.assertEqual(ligature_metrics, (1000, 120))
        self.assertEqual(ligature_bounds, (120, 0, 880, 700))

    def test_ligature_uses_original_advance_for_unpatched_components(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_mixed_ligature_fixture(input_path)

            patch_font(input_path, output_path, sample_text="f", strategy="center")

            ligature_metrics = _glyph_metrics(output_path, "fi")

        self.assertEqual(ligature_metrics, (800, 100))

    def test_fit_strategy_scales_oversized_ligature_to_component_advance_sum(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_ligature_fixture(input_path, doublef_bounds=(0, 1400))

            patch_font(input_path, output_path, sample_text="f", strategy="fit")

            ligature_metrics = _glyph_metrics(output_path, "doublef")
            ligature_bounds = _glyph_bounds_by_name(output_path, "doublef")

        self.assertEqual(ligature_metrics, (1000, 0))
        self.assertEqual(ligature_bounds, (0, 0, 1000, 700))

    def test_removes_pair_positioning_that_breaks_terminal_cell_advances(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_pair_positioning_fixture(input_path)

            original_lookup_types = _gpos_lookup_types(input_path)
            patch_font(input_path, output_path, sample_text="AV", strategy="center")

            patched_lookup_types = _gpos_lookup_types(output_path)

        self.assertIn(2, original_lookup_types)
        self.assertNotIn(2, patched_lookup_types)

    def test_glyf_strategy_decomposes_composites_before_transforming(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_composite_outline_fixture(input_path)

            patch_font(input_path, output_path, sample_text="AB", strategy="center")

            base_bounds = _glyph_bounds(output_path, "A")
            composite_bounds = _glyph_bounds(output_path, "B")
            font = TTFont(output_path)
            try:
                is_composite = font["glyf"]["composite"].isComposite()
            finally:
                font.close()

        self.assertEqual(base_bounds, (-130, 0, 630, 700))
        self.assertEqual(composite_bounds, base_bounds)
        self.assertFalse(is_composite)

    def test_center_strategy_supports_cff_outlines(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.otf"
            output_path = Path(directory) / "output.otf"
            _build_cff_outline_fixture(input_path)

            patch_font(input_path, output_path, sample_text="A", strategy="center")

            bounds = _glyph_bounds(output_path, "A")

        self.assertEqual(bounds, (-130, 0, 630, 700))

    def test_fit_strategy_supports_cff_outlines(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.otf"
            output_path = Path(directory) / "output.otf"
            _build_cff_outline_fixture(input_path)

            patch_font(input_path, output_path, sample_text="A", strategy="fit")

            bounds = _glyph_bounds(output_path, "A")

        self.assertEqual(bounds, (0, 0, 500, 700))

    def test_renames_the_output_font_with_ptt_suffix_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_patch_fixture(input_path)

            patch_font(input_path, output_path, sample_text="A")

            names = _family_names(output_path)
            typographic_family_names = _names_by_id(output_path, {16})

        self.assertIn("Patch Fixture PTT", names)
        self.assertIn("Patch Fixture PTT Regular", names)
        self.assertIn("PatchFixturePTT-Regular", names)
        self.assertEqual(typographic_family_names, {"Patch Fixture PTT"})

    def test_allows_custom_output_family_name(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_patch_fixture(input_path)

            patch_font(
                input_path,
                output_path,
                sample_text="A",
                family_name="Custom PTT",
            )

            names = _family_names(output_path)
            typographic_family_names = _names_by_id(output_path, {16})

        self.assertIn("Custom PTT", names)
        self.assertIn("Custom PTT Regular", names)
        self.assertIn("CustomPTT-Regular", names)
        self.assertEqual(typographic_family_names, {"Custom PTT"})

    def test_truncates_postscript_name_to_open_type_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.ttf"
            output_path = Path(directory) / "output.ttf"
            _build_patch_fixture(input_path)

            patch_font(
                input_path,
                output_path,
                sample_text="A",
                family_name="Very Long Custom PTT Family Name " * 4,
            )

            postscript_names = _names_by_id(output_path, {6})

        self.assertTrue(postscript_names)
        self.assertTrue(all(len(name) <= 63 for name in postscript_names))

    def test_default_output_path_adds_ptt_before_extension(self):
        self.assertEqual(
            default_output_path(Path("lithue-1.1.otf")),
            Path("lithue-1.1-ptt.otf"),
        )


if __name__ == "__main__":
    unittest.main()
