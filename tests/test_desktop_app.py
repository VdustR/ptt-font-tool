import unittest
from pathlib import Path

from ptt_font_tool.desktop_app import (
    DEFAULT_PREVIEW_TEXT,
    desktop_dependency_message,
    format_audit_summary,
    format_export_status,
    format_fallback_status,
    format_font_details,
    format_patch_preview_status,
)
from ptt_font_tool.desktop_model import (
    AuditSummary,
    FallbackLayerStatus,
    FallbackStatus,
    FontMetadata,
)
from ptt_font_tool.fallback import PTT_REQUIRED_SYMBOLS


class DesktopAppTest(unittest.TestCase):
    def test_formats_font_details_for_sidebar(self):
        metadata = FontMetadata(
            path=Path("/tmp/lithue-1.1.otf"),
            family_name="Lithue 1.1",
            style_name="Regular",
            format="OpenType/CFF",
            units_per_em=1000,
            glyph_count=18432,
        )

        self.assertEqual(
            format_font_details(metadata),
            "\n".join([
                "Family: Lithue 1.1",
                "Style: Regular",
                "Format: OpenType/CFF",
                "Units per em: 1000",
                "Glyphs mapped: 18,432",
            ]),
        )

    def test_formats_audit_summary_for_sidebar(self):
        summary = AuditSummary(total=3, ok=1, missing=1, mismatch=1)

        self.assertEqual(
            format_audit_summary(summary),
            "\n".join([
                "Checked: 3",
                "OK: 1",
                "Missing: 1",
                "Mismatched: 1",
            ]),
        )

    def test_desktop_dependency_message_mentions_extra(self):
        self.assertIn("pip install -e .[desktop]", desktop_dependency_message())

    def test_default_preview_text_contains_mixed_width_characters_and_ptt_symbols(self):
        self.assertIn("A漢A", DEFAULT_PREVIEW_TEXT)
        self.assertIn("│─█", DEFAULT_PREVIEW_TEXT)
        for character in PTT_REQUIRED_SYMBOLS:
            self.assertIn(character, DEFAULT_PREVIEW_TEXT)

    def test_formats_patch_preview_status(self):
        summary = AuditSummary(total=12, ok=12, missing=0, mismatch=0)

        self.assertEqual(
            format_patch_preview_status(summary),
            "Patched preview: 12/12 checks OK",
        )

    def test_formats_export_status(self):
        summary = AuditSummary(total=18432, ok=18432, missing=0, mismatch=0)
        output_path = Path("/tmp/lithue-1.1-ptt.otf")

        self.assertEqual(
            format_export_status(output_path, summary),
            "\n".join([
                "Exported:",
                str(output_path),
                "Verified: 18,432/18,432 checks OK.",
            ]),
        )

    def test_formats_fallback_status_with_custom_noto_and_unresolved(self):
        status = FallbackStatus(
            missing=["←", "→", "◎"],
            custom_resolved=["←"],
            noto_resolved=["→"],
            unresolved=["◎"],
            layers=[
                FallbackLayerStatus(
                    label="A.ttf",
                    kind="primary",
                    path=Path("/tmp/A.ttf"),
                    added=[],
                    missing_after=["←", "→", "◎"],
                ),
                FallbackLayerStatus(
                    label="B.ttf",
                    kind="custom",
                    path=Path("/tmp/B.ttf"),
                    added=["←"],
                    missing_after=["→", "◎"],
                ),
                FallbackLayerStatus(
                    label="C.ttf",
                    kind="noto",
                    path=Path("/tmp/C.ttf"),
                    added=["→"],
                    missing_after=["◎"],
                ),
            ],
        )

        self.assertEqual(
            format_fallback_status(status),
            "\n".join([
                "A.ttf: 3 missing",
                "B.ttf: 2 missing, adds 1",
                "C.ttf: 1 missing, adds 1",
                "Warning: 1 PTT glyph is still missing after all fallback fonts.",
            ]),
        )

    def test_formats_fallback_status_when_no_glyphs_are_missing(self):
        status = FallbackStatus(
            missing=[],
            custom_resolved=[],
            noto_resolved=[],
            unresolved=[],
            layers=[
                FallbackLayerStatus(
                    label="A.ttf",
                    kind="primary",
                    path=Path("/tmp/A.ttf"),
                    added=[],
                    missing_after=[],
                ),
            ],
        )

        self.assertEqual(format_fallback_status(status), "A.ttf: ✓ 0 missing")

    def test_formats_fallback_status_omits_warning_when_noto_completes_chain(self):
        status = FallbackStatus(
            missing=["←", "→"],
            custom_resolved=[],
            noto_resolved=["←", "→"],
            unresolved=[],
            layers=[
                FallbackLayerStatus(
                    label="A.ttf",
                    kind="primary",
                    path=Path("/tmp/A.ttf"),
                    added=[],
                    missing_after=["←", "→"],
                ),
                FallbackLayerStatus(
                    label="NotoSansTC.ttf",
                    kind="noto",
                    path=Path("/tmp/NotoSansTC.ttf"),
                    added=["←", "→"],
                    missing_after=[],
                ),
            ],
        )

        self.assertEqual(
            format_fallback_status(status),
            "\n".join([
                "A.ttf: 2 missing",
                "NotoSansTC.ttf: ✓ 0 missing, adds 2",
            ]),
        )


if __name__ == "__main__":
    unittest.main()
