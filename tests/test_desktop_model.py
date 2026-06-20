import tempfile
import unittest
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from ptt_font_tool.desktop_model import (
    build_fallback_status,
    create_font_state,
    create_patch_preview,
    export_patched_font,
    summarize_audit,
)
from ptt_font_tool.audit import audit_font


def _empty_glyph():
    pen = TTGlyphPen(None)
    return pen.glyph()


def _build_desktop_fixture(path: Path) -> None:
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
        "A": (500, 0),
        "uni6F22": (900, 0),
        "uni02C7": (1000, 0),
    })
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2()
    builder.setupNameTable({
        "familyName": "Desktop Fixture",
        "styleName": "Regular",
        "uniqueFontIdentifier": "Desktop Fixture Regular",
        "fullName": "Desktop Fixture Regular",
        "psName": "DesktopFixture-Regular",
    })
    builder.setupPost()
    builder.save(path)


def _build_symbol_fallback(path: Path) -> None:
    glyph_order = [".notdef", "leftArrow", "rightArrow"]
    glyphs = {glyph_name: _empty_glyph() for glyph_name in glyph_order}

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({
        ord("←"): "leftArrow",
        ord("→"): "rightArrow",
    })
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({
        ".notdef": (500, 0),
        "leftArrow": (1000, 0),
        "rightArrow": (1000, 0),
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


def _add_typographic_family_name(font_path: Path, family_name: str) -> None:
    font = TTFont(font_path)
    try:
        font["name"].setName(family_name, 16, 3, 1, 0x409)
        font.save(font_path)
    finally:
        font.close()


class DesktopModelTest(unittest.TestCase):
    def test_create_font_state_inspects_metadata_and_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            font_path = Path(directory) / "desktop-fixture.ttf"
            _build_desktop_fixture(font_path)

            state = create_font_state(font_path, sample_text="A漢ˇ")

        self.assertEqual(state.metadata.path, font_path)
        self.assertEqual(state.metadata.family_name, "Desktop Fixture")
        self.assertEqual(state.metadata.style_name, "Regular")
        self.assertEqual(state.metadata.format, "TrueType/glyf")
        self.assertEqual(state.metadata.units_per_em, 1000)
        self.assertEqual(state.metadata.glyph_count, 3)
        self.assertEqual(state.output_path, font_path.with_name("desktop-fixture-ptt.ttf"))
        self.assertEqual(state.family_name, "Desktop Fixture PTT")
        self.assertEqual(state.audit.total, 3)
        self.assertEqual(state.audit.ok, 2)
        self.assertEqual(state.audit.missing, 0)
        self.assertEqual(state.audit.mismatch, 1)
        self.assertIn("←", state.fallback.missing)

    def test_summarize_audit_groups_missing_and_mismatch_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            font_path = Path(directory) / "desktop-fixture.ttf"
            _build_desktop_fixture(font_path)

            result = audit_font(font_path, sample_text="A漢好")
            summary = summarize_audit(result)

        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.ok, 1)
        self.assertEqual(summary.missing, 1)
        self.assertEqual(summary.mismatch, 1)

    def test_create_font_state_prefers_typographic_family_name(self):
        with tempfile.TemporaryDirectory() as directory:
            font_path = Path(directory) / "desktop-fixture.ttf"
            _build_desktop_fixture(font_path)
            _add_typographic_family_name(font_path, "Desktop Fixture Typographic")

            state = create_font_state(font_path, sample_text="A")

        self.assertEqual(state.metadata.family_name, "Desktop Fixture Typographic")
        self.assertEqual(state.family_name, "Desktop Fixture Typographic PTT")

    def test_create_patch_preview_patches_preview_text_to_temp_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root / "desktop-fixture.ttf"
            preview_path = root / "preview.ttf"
            _build_desktop_fixture(font_path)

            result = create_patch_preview(
                font_path,
                preview_path,
                family_name="Desktop Fixture Preview",
                strategy="center",
                sample_text="A漢",
            )

            audited = audit_font(preview_path, sample_text="A漢")

        self.assertEqual(result.output_path, preview_path)
        self.assertTrue(audited.ok)
        self.assertEqual(result.audit.total, 2)
        self.assertEqual(result.audit.ok, 2)

    def test_export_patched_font_patches_all_mapped_characters_and_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root / "desktop-fixture.ttf"
            output_path = root / "desktop-fixture-ptt.ttf"
            _build_desktop_fixture(font_path)

            result = export_patched_font(
                font_path,
                output_path,
                family_name="Desktop Fixture PTT",
                strategy="fit",
                required_fallback_chars="",
            )

            audited = audit_font(output_path)

        self.assertEqual(result.output_path, output_path)
        self.assertTrue(audited.ok)
        self.assertEqual(result.audit.total, 3)
        self.assertEqual(result.audit.mismatch, 0)
        self.assertEqual(result.fallback_added, [])
        self.assertEqual(result.fallback_unresolved, [])

    def test_build_fallback_status_separates_custom_noto_and_unresolved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root / "desktop-fixture.ttf"
            custom_fallback = root / "custom-symbols.ttf"
            noto_fallback = root / "noto-symbols.ttf"
            _build_desktop_fixture(font_path)
            _build_symbol_fallback(custom_fallback)
            _build_symbol_fallback(noto_fallback)

            status = build_fallback_status(
                font_path,
                required_chars="A←→◎",
                custom_fallback_paths=[custom_fallback],
                noto_fallback_paths=[noto_fallback],
            )

        self.assertEqual(status.missing, ["←", "→", "◎"])
        self.assertEqual(status.custom_resolved, ["←", "→"])
        self.assertEqual(status.noto_resolved, [])
        self.assertEqual(status.unresolved, ["◎"])
        self.assertEqual(
            [(layer.label, layer.kind, layer.added, layer.missing_after) for layer in status.layers],
            [
                ("desktop-fixture.ttf", "primary", [], ["←", "→", "◎"]),
                ("custom-symbols.ttf", "custom", ["←", "→"], ["◎"]),
                ("noto-symbols.ttf", "noto", [], ["◎"]),
            ],
        )

    def test_build_fallback_status_tracks_missing_counts_for_each_chain_layer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root / "desktop-fixture.ttf"
            custom_fallback = root / "custom-symbols.ttf"
            noto_fallback = root / "noto-symbols.ttf"
            _build_desktop_fixture(font_path)
            _build_symbol_fallback(custom_fallback)
            _build_symbol_fallback(noto_fallback)

            status = build_fallback_status(
                font_path,
                required_chars="A←→",
                custom_fallback_paths=[custom_fallback],
                noto_fallback_paths=[noto_fallback],
            )

        self.assertEqual(
            [(layer.label, len(layer.missing_after)) for layer in status.layers],
            [
                ("desktop-fixture.ttf", 2),
                ("custom-symbols.ttf", 0),
                ("noto-symbols.ttf", 0),
            ],
        )
        self.assertEqual(status.unresolved, [])

    def test_build_fallback_status_does_not_open_fallbacks_after_chain_is_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root / "desktop-fixture.ttf"
            invalid_fallback = root / "invalid.ttf"
            _build_desktop_fixture(font_path)
            invalid_fallback.write_text("not a font")

            status = build_fallback_status(
                font_path,
                required_chars="A",
                custom_fallback_paths=[invalid_fallback],
            )

        self.assertEqual(
            [(layer.label, len(layer.missing_after)) for layer in status.layers],
            [
                ("desktop-fixture.ttf", 0),
                ("invalid.ttf", 0),
            ],
        )
        self.assertEqual(status.unresolved, [])

    def test_export_patched_font_merges_fallbacks_before_patching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root / "desktop-fixture.ttf"
            fallback_path = root / "symbols.ttf"
            output_path = root / "desktop-fixture-ptt.ttf"
            _build_desktop_fixture(font_path)
            _build_symbol_fallback(fallback_path)

            result = export_patched_font(
                font_path,
                output_path,
                family_name="Desktop Fixture PTT",
                strategy="center",
                fallback_paths=[fallback_path],
                required_fallback_chars="←→",
            )

            audited = audit_font(output_path, sample_text="A←→")

        self.assertTrue(audited.ok)
        self.assertEqual(result.fallback_added, ["←", "→"])
        self.assertEqual(result.fallback_unresolved, [])

    def test_export_patched_font_audits_unresolved_required_glyphs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root / "desktop-fixture.ttf"
            output_path = root / "desktop-fixture-ptt.ttf"
            _build_desktop_fixture(font_path)

            result = export_patched_font(
                font_path,
                output_path,
                family_name="Desktop Fixture PTT",
                strategy="center",
                required_fallback_chars="←",
            )

        self.assertEqual(result.fallback_unresolved, [])
        self.assertEqual(result.audit.missing, 1)

    def test_export_patched_font_skips_fallback_merge_when_required_glyphs_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root / "desktop-fixture.ttf"
            fallback_path = root / "unsupported.otf"
            output_path = root / "desktop-fixture-ptt.ttf"
            _build_desktop_fixture(font_path)
            fallback_path.write_text("not a font")

            result = export_patched_font(
                font_path,
                output_path,
                family_name="Desktop Fixture PTT",
                strategy="center",
                fallback_paths=[fallback_path],
                required_fallback_chars="A",
            )

            audited = audit_font(output_path, sample_text="A")

        self.assertTrue(audited.ok)
        self.assertEqual(result.fallback_added, [])
        self.assertEqual(result.fallback_unresolved, [])

    def test_patch_helpers_reject_empty_family_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root / "desktop-fixture.ttf"
            output_path = root / "desktop-fixture-ptt.ttf"
            _build_desktop_fixture(font_path)

            with self.assertRaisesRegex(ValueError, "family name is required"):
                export_patched_font(
                    font_path,
                    output_path,
                    family_name=" ",
                    strategy="center",
                )


if __name__ == "__main__":
    unittest.main()
