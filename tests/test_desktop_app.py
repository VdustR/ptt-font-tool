import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pathlib import Path

from ptt_font_tool.desktop_app import (
    DEFAULT_PREVIEW_TEXT,
    UnavailableFallbackLayer,
    desktop_dependency_message,
    format_audit_summary,
    format_export_status,
    format_fallback_summary,
    format_fallback_status,
    format_font_details,
    format_patch_preview_status,
)
from ptt_font_tool.desktop_model import (
    AuditSummary,
    DesktopFontState,
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
            "Built font: 12/12 checks OK",
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
                "1. A.ttf: 3 missing after input font",
                "2. B.ttf: adds 1, 2 missing after this layer",
                "3. C.ttf: adds 1, 1 missing after this layer",
            ]),
        )
        self.assertEqual(
            format_fallback_summary(status),
            "Warning: 1 PTT glyph is still missing after all fallback fonts.",
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

        self.assertEqual(
            format_fallback_status(status),
            "1. A.ttf: 0 missing after input font",
        )
        self.assertEqual(
            format_fallback_summary(status),
            "All required PTT glyphs are covered.",
        )

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
                "1. A.ttf: 2 missing after input font",
                "2. NotoSansTC.ttf: adds 2, 0 missing after this layer",
            ]),
        )

    def test_formats_unavailable_noto_layers_inside_ledger(self):
        status = FallbackStatus(
            missing=["←", "→"],
            custom_resolved=["←"],
            noto_resolved=[],
            unresolved=["→"],
            layers=[
                FallbackLayerStatus(
                    label="A.ttf",
                    kind="primary",
                    path=Path("/tmp/A.ttf"),
                    added=[],
                    missing_after=["←", "→"],
                ),
                FallbackLayerStatus(
                    label="Custom.ttf",
                    kind="custom",
                    path=Path("/tmp/Custom.ttf"),
                    added=["←"],
                    missing_after=["→"],
                ),
            ],
        )
        unavailable = [
            UnavailableFallbackLayer(
                label="Noto Sans Symbols 2",
                reason="not downloaded",
            ),
            UnavailableFallbackLayer(
                label="Noto Sans TC",
                reason="not downloaded",
            ),
        ]

        self.assertEqual(
            format_fallback_status(status, unavailable_layers=unavailable),
            "\n".join([
                "1. A.ttf: 2 missing after input font",
                "2. Custom.ttf: adds 1, 1 missing after this layer",
                "3. Noto Sans Symbols 2: needs download (not downloaded)",
                "4. Noto Sans TC: needs download (not downloaded)",
            ]),
        )
        self.assertEqual(
            format_fallback_summary(status, unavailable_layers=unavailable),
            "1 PTT glyph still needs Noto fallback. Download Noto to continue the coverage check.",
        )

    def test_qt_font_stack_accepts_dropped_local_files(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import (
                FontDropGroup,
                FontStackList,
                _font_paths_from_mime,
            )
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])

        class MimeData:
            def hasUrls(self):
                return True

            def urls(self):
                return [
                    QUrl.fromLocalFile("/tmp/A.ttf"),
                    QUrl.fromLocalFile("/tmp/B.otf"),
                ]

        class DropEvent:
            def __init__(self):
                self.accepted = False

            def mimeData(self):
                return MimeData()

            def acceptProposedAction(self):
                self.accepted = True

        expected_paths = [Path("/tmp/A.ttf"), Path("/tmp/B.otf")]
        self.assertEqual(_font_paths_from_mime(MimeData()), expected_paths)

        for widget in (FontDropGroup("Font Stack"), FontStackList()):
            with self.subTest(widget=type(widget).__name__):
                dropped_paths = []
                widget.files_dropped.connect(lambda paths: dropped_paths.extend(paths))

                event = DropEvent()
                widget.dropEvent(event)

                self.assertTrue(event.accepted)
                self.assertEqual(dropped_paths, expected_paths)

        app.quit()

    def test_qt_main_window_scrolls_sidebar_vertically_without_horizontal_overflow(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QScrollArea

            from ptt_font_tool._qt_desktop import MainWindow
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        window = MainWindow()

        try:
            window.resize(900, 620)
            window.show()
            app.processEvents()

            scroll_areas = window.findChildren(QScrollArea)
            self.assertEqual(scroll_areas, [window.sidebar_scroll])
            self.assertGreater(window.sidebar_scroll.verticalScrollBar().maximum(), 0)
            self.assertEqual(window.sidebar_scroll.horizontalScrollBar().maximum(), 0)
            self.assertFalse(hasattr(window, "output_input"))
            self.assertFalse(hasattr(window, "open_button"))
            self.assertFalse(hasattr(window, "busy_label"))
            self.assertFalse(hasattr(window, "progress_bar"))
            self.assertEqual(window.family_input.parentWidget().objectName(), "OutputNameStack")
            self.assertIs(window.family_input.parentWidget(), window.export_hint_label.parentWidget())
            self.assertIs(window.family_input.parentWidget().parentWidget(), window.build_group)
            self.assertIn("Export copies the last built font", window.export_hint_label.text())
            build_labels = [
                label.text()
                for label in window.build_group.findChildren(QLabel)
            ]
            self.assertNotIn("Output file", build_labels)
            self.assertIs(window.build_progress_bar.parentWidget(), window.build_group)
            self.assertIn("Build", window.preview_hint_label.text())
            self.assertTrue(window.build_progress_bar.isHidden())
            window._set_busy("update", "Checking updates...")
            self.assertTrue(window.build_progress_bar.isHidden())
            window._set_busy("update", None)
            window._set_busy("preview", "Building font...")
            self.assertFalse(window.build_progress_bar.isHidden())
            window._set_busy("preview", None)
            self.assertTrue(window.build_progress_bar.isHidden())
            self.assertIn("Center keeps", window.strategy_help_label.text())
            self.assertTrue(window.font_stack_placeholder.isVisible())
            self.assertFalse(window.font_stack_list.isVisible())
            self.assertEqual(window.font_stack_list.height(), 0)
            group_titles = {group.title() for group in window.findChildren(QGroupBox)}
            self.assertNotIn("Noto Cache", group_titles)
            self.assertNotIn("Fallback coverage ledger", group_titles)
            self.assertIs(window.noto_stack_row.parentWidget(), window.font_group)
        finally:
            window.close()
            app.quit()

    def test_qt_main_window_uses_noto_environment_defaults(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import MainWindow
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            fonts_dir = Path(directory)
            with patch.dict(
                os.environ,
                {
                    "PTT_FONT_TOOL_FONTS_DIR": str(fonts_dir),
                    "PTT_FONT_TOOL_NOTO_STYLE": "serif",
                },
            ):
                window = MainWindow()

        try:
            self.assertEqual(window._noto_text_style, "serif")
            self.assertEqual(window._noto_cache_state.cache_dir, fonts_dir / "noto")
            self.assertTrue(window.noto_serif_radio.isChecked())
            self.assertFalse(window.noto_sans_radio.isChecked())
        finally:
            window.close()
            app.quit()

    def test_qt_font_stack_height_grows_with_rows_and_autoscrolls_sidebar(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import MainWindow
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        window = MainWindow()

        try:
            window.resize(900, 520)
            window.show()
            app.processEvents()

            window._font_stack_paths = [Path("/tmp/A.ttf")]
            window._render_font_stack()
            app.processEvents()
            one_row_height = window.font_stack_list.height()
            self.assertFalse(window.font_stack_placeholder.isVisible())
            self.assertTrue(window.font_stack_list.isVisible())

            window._font_stack_paths = [Path(f"/tmp/Font-{index}.ttf") for index in range(10)]
            window._render_font_stack()
            app.processEvents()
            many_row_height = window.font_stack_list.height()
            self.assertGreater(many_row_height, one_row_height)

            scroll_bar = window.sidebar_scroll.verticalScrollBar()
            scroll_bar.setValue(0)
            window.font_stack_list._set_auto_scroll_direction(1)
            window.font_stack_list._scroll_parent()
            self.assertGreater(scroll_bar.value(), 0)
            window.font_stack_list._set_auto_scroll_direction(0)
        finally:
            window.close()
            app.quit()

    def test_qt_strategy_help_only_shows_selected_option(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import MainWindow
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        window = MainWindow()

        try:
            self.assertIn("Center keeps", window.strategy_help_label.text())
            self.assertNotIn("Fit shrinks", window.strategy_help_label.text())
            window.fit_radio.setChecked(True)
            self.assertIn("Fit shrinks", window.strategy_help_label.text())
            self.assertNotIn("Center keeps", window.strategy_help_label.text())
        finally:
            window.close()
            app.quit()

    def test_qt_font_stack_preview_wheel_only_bubbles_at_scroll_edges(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import FontStackRow
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        row = FontStackRow(
            Path("/tmp/A.ttf"),
            role="Primary font",
            family="A",
            preview_text="\n".join(str(index) for index in range(80)),
        )

        try:
            row.show()
            row.preview.resize(240, 56)
            app.processEvents()
            scroll_bar = row.preview.verticalScrollBar()
            self.assertGreater(scroll_bar.maximum(), scroll_bar.minimum())

            scroll_bar.setValue(scroll_bar.minimum())
            self.assertFalse(row.preview._can_scroll_for_delta(120))
            self.assertTrue(row.preview._can_scroll_for_delta(-120))

            scroll_bar.setValue(scroll_bar.maximum())
            self.assertTrue(row.preview._can_scroll_for_delta(120))
            self.assertFalse(row.preview._can_scroll_for_delta(-120))

            row.preview.setPlainText("one line")
            app.processEvents()
            self.assertFalse(row.preview._can_scroll_for_delta(-120))
            self.assertFalse(row.preview._can_scroll_for_delta(120))
        finally:
            row.close()
            app.quit()

    def test_qt_fallback_coverage_is_shown_on_font_stack_rows(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import FontStackRow, MainWindow
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        primary_path = Path("/tmp/A.ttf")
        custom_path = Path("/tmp/B.ttf")
        noto_path = Path("/tmp/NotoSansTC.ttf")
        summary = AuditSummary(total=1, ok=1, missing=0, mismatch=0)
        fallback = FallbackStatus(
            missing=["←", "→"],
            custom_resolved=["←"],
            noto_resolved=["→"],
            unresolved=[],
            layers=[
                FallbackLayerStatus(
                    label="A.ttf",
                    kind="primary",
                    path=primary_path,
                    added=[],
                    missing_after=["←", "→"],
                ),
                FallbackLayerStatus(
                    label="B.ttf",
                    kind="custom",
                    path=custom_path,
                    added=["←"],
                    missing_after=["→"],
                ),
                FallbackLayerStatus(
                    label="NotoSansTC.ttf",
                    kind="noto",
                    path=noto_path,
                    added=["→"],
                    missing_after=[],
                ),
            ],
        )
        window._font_stack_paths = [primary_path, custom_path]
        window._custom_fallback_paths = [custom_path]
        window._state = DesktopFontState(
            metadata=FontMetadata(
                path=primary_path,
                family_name="A",
                style_name="Regular",
                format="TrueType",
                units_per_em=1000,
                glyph_count=1,
            ),
            audit=summary,
            fallback=fallback,
            output_path=Path("/tmp/A-ptt.ttf"),
            family_name="A PTT",
        )

        try:
            window._set_fallback_labels(fallback)

            primary_row = window.font_stack_list.itemWidget(window.font_stack_list.item(0))
            custom_row = window.font_stack_list.itemWidget(window.font_stack_list.item(1))
            self.assertIsInstance(primary_row, FontStackRow)
            self.assertIsInstance(custom_row, FontStackRow)
            self.assertIn("2 missing", primary_row.coverage_label.text())
            self.assertIn("adds 1", custom_row.coverage_label.text())
            self.assertIn("1 missing", custom_row.coverage_label.text())
            self.assertIn("adds 1", window.noto_cache_details.text())
            self.assertIn("0 missing", window.noto_cache_details.text())
        finally:
            window.close()
            app.quit()

    def test_qt_export_uses_save_dialog_destination(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import MainWindow, _copy_built_font
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        summary = AuditSummary(total=1, ok=1, missing=0, mismatch=0)
        fallback = FallbackStatus(
            missing=[],
            custom_resolved=[],
            noto_resolved=[],
            unresolved=[],
            layers=[],
        )
        window._state = DesktopFontState(
            metadata=FontMetadata(
                path=Path("/tmp/source.ttf"),
                family_name="Source",
                style_name="Regular",
                format="TrueType",
                units_per_em=1000,
                glyph_count=1,
            ),
            audit=summary,
            fallback=fallback,
            output_path=Path("/tmp/source-ptt.ttf"),
            family_name="Source PTT",
        )
        window._patch_preview_path = Path("/tmp/source-preview.ttf")
        window._built_result = SimpleNamespace(
            audit=summary,
            fallback_added=[],
            fallback_unresolved=[],
        )
        window._build_dirty = False
        captured = {}

        class PendingFuture:
            def done(self):
                return False

            def add_done_callback(self, callback):
                self.callback = callback

        class FakeExecutor:
            def submit(self, function, *args, **kwargs):
                captured["function"] = function
                captured["args"] = args
                captured["kwargs"] = kwargs
                return PendingFuture()

        original_executor = window._executor
        window._executor = FakeExecutor()
        try:
            with patch(
                "ptt_font_tool._qt_desktop.QFileDialog.getSaveFileName",
                return_value=("/tmp/exported-font", "Font files (*.ttf *.otf)"),
            ):
                window._export_font()

            self.assertIs(captured["function"], _copy_built_font)
            self.assertEqual(captured["args"][1], Path("/tmp/exported-font.ttf"))
            self.assertIn("exported-font.ttf", window.export_status.text())
        finally:
            window._set_busy("export", None)
            window._executor = original_executor
            window.close()
            app.quit()

    def test_qt_export_builds_font_before_save_dialog_when_dirty(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import MainWindow
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        summary = AuditSummary(total=1, ok=1, missing=0, mismatch=0)
        fallback = FallbackStatus(
            missing=[],
            custom_resolved=[],
            noto_resolved=[],
            unresolved=[],
            layers=[],
        )
        window._state = DesktopFontState(
            metadata=FontMetadata(
                path=Path("/tmp/source.ttf"),
                family_name="Source",
                style_name="Regular",
                format="TrueType",
                units_per_em=1000,
                glyph_count=1,
            ),
            audit=summary,
            fallback=fallback,
            output_path=Path("/tmp/source-ptt.ttf"),
            family_name="Source PTT",
        )
        window._font_stack_paths = [Path("/tmp/source.ttf")]
        window._build_dirty = True

        try:
            window._set_font_controls_enabled(True)
            self.assertTrue(window.export_button.isEnabled())
            self.assertEqual(window.export_button.text(), "Build and export")
            with patch.object(window, "_refresh_patch_preview") as refresh_preview:
                window._export_font()

            refresh_preview.assert_called_once()
            self.assertTrue(window._export_after_preview)
            self.assertIn("Building font before export", window.preview_status.text())
        finally:
            window.close()
            app.quit()

    def test_qt_build_font_patches_all_glyphs_and_uses_preview_text_for_fallbacks(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import MainWindow
            from ptt_font_tool.font_stack import build_font_stack
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        summary = AuditSummary(total=1, ok=1, missing=0, mismatch=0)
        fallback = FallbackStatus(
            missing=[],
            custom_resolved=[],
            noto_resolved=[],
            unresolved=[],
            layers=[],
        )
        source_path = Path("/tmp/source.ttf")
        window._state = DesktopFontState(
            metadata=FontMetadata(
                path=source_path,
                family_name="Source",
                style_name="Regular",
                format="TrueType",
                units_per_em=1000,
                glyph_count=1,
            ),
            audit=summary,
            fallback=fallback,
            output_path=Path("/tmp/source-ptt.ttf"),
            family_name="Source PTT",
        )
        window._font_stack_paths = [source_path]
        window._preview_sample_text = "A漢"
        captured = {}

        class PendingFuture:
            def done(self):
                return False

            def add_done_callback(self, callback):
                self.callback = callback

        class FakeExecutor:
            def submit(self, function, *args, **kwargs):
                captured["function"] = function
                captured["args"] = args
                captured["kwargs"] = kwargs
                return PendingFuture()

        original_executor = window._executor
        window._executor = FakeExecutor()
        try:
            window.family_input.setText("Source PTT")
            window._refresh_patch_preview()

            self.assertIs(captured["function"], build_font_stack)
            self.assertIsNone(captured["kwargs"]["sample_text"])
            self.assertIn("A漢", captured["kwargs"]["required_fallback_chars"])
        finally:
            window._set_busy("preview", None)
            window._executor = original_executor
            window.close()
            app.quit()

    def test_qt_preview_text_change_keeps_built_font_visible_but_dirty(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import MainWindow
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        summary = AuditSummary(total=1, ok=1, missing=0, mismatch=0)
        fallback = FallbackStatus(
            missing=[],
            custom_resolved=[],
            noto_resolved=[],
            unresolved=[],
            layers=[],
        )
        output_path = Path("/tmp/source-built.ttf")
        window._state = DesktopFontState(
            metadata=FontMetadata(
                path=Path("/tmp/source.ttf"),
                family_name="Source",
                style_name="Regular",
                format="TrueType",
                units_per_em=1000,
                glyph_count=1,
            ),
            audit=summary,
            fallback=fallback,
            output_path=Path("/tmp/source-ptt.ttf"),
            family_name="Source PTT",
        )
        window._font_stack_paths = [Path("/tmp/source.ttf")]
        window._patch_preview_path = output_path
        window._built_result = SimpleNamespace(
            audit=summary,
            fallback_added=[],
            fallback_unresolved=[],
        )
        window._build_dirty = False

        try:
            window.patched_radio.setEnabled(True)
            window.patched_radio.setChecked(True)

            window._set_preview_sample_text("New preview text ◎", source=None)

            self.assertEqual(window._patch_preview_path, output_path)
            self.assertIsNotNone(window._built_result)
            self.assertTrue(window._build_dirty)
            self.assertTrue(window.patched_radio.isEnabled())
            self.assertTrue(window.patched_radio.isChecked())
            self.assertEqual(window.export_button.text(), "Build and export")
        finally:
            window.close()
            app.quit()

    def test_qt_dirty_settings_refresh_original_preview_once(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import MainWindow
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        summary = AuditSummary(total=1, ok=1, missing=0, mismatch=0)
        fallback = FallbackStatus(
            missing=[],
            custom_resolved=[],
            noto_resolved=[],
            unresolved=[],
            layers=[],
        )
        window._state = DesktopFontState(
            metadata=FontMetadata(
                path=Path("/tmp/source.ttf"),
                family_name="Source",
                style_name="Regular",
                format="TrueType",
                units_per_em=1000,
                glyph_count=1,
            ),
            audit=summary,
            fallback=fallback,
            output_path=Path("/tmp/source-ptt.ttf"),
            family_name="Source PTT",
        )
        window._font_stack_paths = [Path("/tmp/source.ttf")]
        window._patch_preview_path = Path("/tmp/source-built.ttf")
        window._built_result = SimpleNamespace(
            audit=summary,
            fallback_added=[],
            fallback_unresolved=[],
        )

        try:
            window.patched_radio.setEnabled(True)
            window.patched_radio.setChecked(True)
            with patch.object(window, "_show_original_preview") as show_original_preview:
                window._mark_build_dirty("Build settings changed")

            show_original_preview.assert_called_once()
        finally:
            window.close()
            app.quit()

    def test_qt_preview_build_completion_switches_to_patched_preview(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            from ptt_font_tool._qt_desktop import MainWindow
        except ImportError as error:
            self.skipTest(f"PySide6 is unavailable: {error}")

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        summary = AuditSummary(total=1, ok=1, missing=0, mismatch=0)
        fallback = FallbackStatus(
            missing=[],
            custom_resolved=[],
            noto_resolved=[],
            unresolved=[],
            layers=[],
        )
        output_path = Path("/tmp/source-ptt.ttf")
        window._preview_request_id = 7
        window._state = DesktopFontState(
            metadata=FontMetadata(
                path=Path("/tmp/source.ttf"),
                family_name="Source",
                style_name="Regular",
                format="TrueType",
                units_per_em=1000,
                glyph_count=1,
            ),
            audit=summary,
            fallback=fallback,
            output_path=output_path,
            family_name="Source PTT",
        )

        try:
            window._patch_preview_done((
                7,
                SimpleNamespace(
                    output_path=output_path,
                    patch=SimpleNamespace(
                        audit=summary,
                        fallback_added=[],
                        fallback_unresolved=[],
                    ),
                    fallback=fallback,
                ),
            ))

            self.assertTrue(window.patched_radio.isChecked())
            self.assertFalse(window.original_radio.isChecked())
            self.assertIn("Ready to export", window.preview_status.text())
            self.assertIn("Built font", window.preview_hint_label.text())
        finally:
            window.close()
            app.quit()


if __name__ == "__main__":
    unittest.main()
