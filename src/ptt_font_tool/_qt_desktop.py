from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
from typing import Optional, Sequence

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .desktop_app import (
    DEFAULT_PREVIEW_TEXT,
    format_audit_summary,
    format_export_status,
    format_fallback_status,
    format_font_details,
    format_patch_preview_status,
)
from .desktop_model import (
    DesktopFontState,
    PatchedFontState,
    create_font_state,
    create_patch_preview,
    export_patched_font,
    build_fallback_status,
)
from .fallback import PTT_REQUIRED_SYMBOLS
from .update_check import UpdateCheckError, UpdateCheckResult, check_for_update


class WorkerSignals(QObject):
    font_loaded = Signal(object)
    font_load_failed = Signal(object)
    preview_done = Signal(object)
    preview_failed = Signal(object)
    export_done = Signal(object)
    export_failed = Signal(str)
    update_done = Signal(object)
    update_failed = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._font_id: Optional[int] = None
        self._state: Optional[DesktopFontState] = None
        self._patch_preview_path: Optional[Path] = None
        self._custom_fallback_paths: list[Path] = []
        self._noto_fallback_paths = _default_noto_fallback_paths()
        self._temp_dir = tempfile.TemporaryDirectory(prefix="ptt-font-tool-")
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ptt-font-tool")
        self._load_future: Optional[Future] = None
        self._preview_future: Optional[Future] = None
        self._export_future: Optional[Future] = None
        self._update_future: Optional[Future] = None
        self._load_request_id = 0
        self._preview_request_id = 0
        self._busy_messages: dict[str, str] = {}
        self._signals = WorkerSignals()
        self._signals.font_loaded.connect(self._font_loaded)
        self._signals.font_load_failed.connect(self._font_load_failed)
        self._signals.preview_done.connect(self._patch_preview_done)
        self._signals.preview_failed.connect(self._patch_preview_failed)
        self._signals.export_done.connect(self._export_done)
        self._signals.export_failed.connect(self._export_failed)
        self._signals.update_done.connect(self._update_done)
        self._signals.update_failed.connect(self._update_failed)
        self._updating_ui = False

        self.setWindowTitle("PTT Font Tool")
        app_icon = _app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.resize(1120, 820)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("PTT Font Tool")
        title.setObjectName("Title")
        self.busy_label = QLabel()
        self.busy_label.setObjectName("BusyStatus")
        self.busy_label.hide()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedWidth(150)
        self.progress_bar.hide()
        self.update_button = QPushButton("Check updates")
        self.update_button.setObjectName("SecondaryButton")
        self.update_button.clicked.connect(self._check_for_updates)
        self.open_button = QPushButton("Open font...")
        self.open_button.clicked.connect(self._open_font)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.busy_label)
        header.addWidget(self.progress_bar)
        header.addWidget(self.update_button)
        header.addWidget(self.open_button)
        root_layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_preview())
        splitter.setSizes([380, 740])
        root_layout.addWidget(splitter, 1)

        self.setCentralWidget(root)
        self._apply_style()
        self._set_empty_state()

    def _build_sidebar(self) -> QWidget:
        sidebar_content = QWidget()
        layout = QVBoxLayout(sidebar_content)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(12)

        self.font_group = QGroupBox("Font")
        self.font_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        font_layout = QVBoxLayout(self.font_group)
        self.font_details = self._detail_label()
        font_layout.addWidget(self.font_details)

        self.audit_group = QGroupBox("Audit")
        self.audit_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        audit_layout = QVBoxLayout(self.audit_group)
        self.audit_details = self._detail_label()
        audit_layout.addWidget(self.audit_details)

        self.fallback_group = QGroupBox("Fallback glyphs")
        self.fallback_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        fallback_layout = QVBoxLayout(self.fallback_group)
        self.fallback_details = self._detail_label()
        self.fallback_fonts = self._detail_label()
        fallback_buttons = QHBoxLayout()
        self.add_fallback_button = QPushButton("Add fallback font...")
        self.add_fallback_button.setObjectName("SecondaryButton")
        self.add_fallback_button.clicked.connect(self._add_fallback_font)
        self.clear_fallback_button = QPushButton("Clear")
        self.clear_fallback_button.setObjectName("SecondaryButton")
        self.clear_fallback_button.clicked.connect(self._clear_fallback_fonts)
        fallback_buttons.addWidget(self.add_fallback_button)
        fallback_buttons.addWidget(self.clear_fallback_button)
        fallback_layout.addWidget(self.fallback_details)
        fallback_layout.addWidget(self.fallback_fonts)
        fallback_layout.addLayout(fallback_buttons)

        self.strategy_group = QGroupBox("Strategy")
        self.strategy_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        strategy_layout = QVBoxLayout(self.strategy_group)
        self.center_radio = QRadioButton("Center")
        self.center_radio.setToolTip("Preserve glyph shape and center it inside the PTT cell.")
        self.fit_radio = QRadioButton("Fit")
        self.fit_radio.setToolTip("Shrink oversized glyphs horizontally before centering.")
        self.center_radio.setChecked(True)
        self.center_radio.toggled.connect(self._patch_inputs_changed)
        self.fit_radio.toggled.connect(self._patch_inputs_changed)
        strategy_layout.addWidget(self.center_radio)
        strategy_layout.addWidget(self.fit_radio)

        self.output_group = QGroupBox("Output")
        self.output_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        output_layout = QGridLayout(self.output_group)
        self.family_input = QLineEdit()
        self.family_input.textChanged.connect(self._patch_inputs_changed)
        self.output_input = QLineEdit()
        self.export_button = QPushButton("Export font")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_font)
        self.export_status = self._detail_label()
        self.export_status.setObjectName("StatusLabel")
        output_layout.addWidget(QLabel("Family"), 0, 0)
        output_layout.addWidget(self.family_input, 0, 1)
        output_layout.addWidget(QLabel("Path"), 1, 0)
        output_layout.addWidget(self.output_input, 1, 1)
        output_layout.addWidget(self.export_button, 2, 1)
        output_layout.addWidget(self.export_status, 3, 0, 1, 2)

        layout.addWidget(self.font_group)
        layout.addWidget(self.audit_group)
        layout.addWidget(self.fallback_group)
        layout.addWidget(self.strategy_group)
        layout.addWidget(self.output_group)
        layout.addStretch(1)

        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setWidget(sidebar_content)
        self.sidebar_scroll.setMinimumWidth(360)
        return self.sidebar_scroll

    def _build_preview(self) -> QWidget:
        preview = QWidget()
        layout = QVBoxLayout(preview)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)

        self.preview_text = QPlainTextEdit()
        self.preview_text.setMaximumHeight(118)
        self.preview_text.setPlainText(DEFAULT_PREVIEW_TEXT)
        self.preview_text.textChanged.connect(self._sync_preview_text)

        self.rendered_preview = QPlainTextEdit()
        self.rendered_preview.setReadOnly(True)
        self.rendered_preview.setFrameShape(QFrame.Shape.NoFrame)
        self.rendered_preview.setPlainText(DEFAULT_PREVIEW_TEXT)
        self.rendered_preview.setObjectName("TerminalPreview")

        layout.addWidget(QLabel("Preview text"))
        layout.addWidget(self.preview_text)

        preview_header = QHBoxLayout()
        preview_header.addWidget(QLabel("Rendered preview"))
        preview_header.addStretch(1)
        self.original_radio = QRadioButton("Original")
        self.patched_radio = QRadioButton("Patched")
        self.refresh_preview_button = QPushButton("Refresh patched preview")
        self.original_radio.setChecked(True)
        self.original_radio.toggled.connect(self._preview_mode_changed)
        self.patched_radio.toggled.connect(self._preview_mode_changed)
        self.refresh_preview_button.setObjectName("SecondaryButton")
        self.refresh_preview_button.clicked.connect(self._refresh_patch_preview)
        preview_header.addWidget(self.original_radio)
        preview_header.addWidget(self.patched_radio)
        preview_header.addWidget(self.refresh_preview_button)
        layout.addLayout(preview_header)
        self.preview_status = QLabel()
        self.preview_status.setWordWrap(True)
        self.preview_status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.preview_status)
        layout.addWidget(self.rendered_preview, 1)
        return preview

    def _detail_label(self) -> QLabel:
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        label.setContentsMargins(0, 2, 0, 4)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setWordWrap(True)
        return label

    def _set_empty_state(self) -> None:
        self.font_details.setText("Open a local .otf or .ttf file.")
        self.audit_details.setText("Audit results will appear after a font is opened.")
        self.fallback_details.setText("Fallback coverage will appear after a font is opened.")
        self.fallback_fonts.setText(self._fallback_fonts_text())
        self.preview_status.setText("Open a font to generate a patched preview.")
        self.export_status.clear()
        self.family_input.clear()
        self.output_input.clear()
        self._set_font_controls_enabled(False)

    def _open_font(self, *_args) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Open font",
            "",
            "Font files (*.otf *.ttf *.ttc *.otc);;All files (*)",
        )
        if selected:
            self._load_font(Path(selected))

    def _add_fallback_font(self, *_args) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Add fallback font",
            "",
            "Font files (*.otf *.ttf *.ttc *.otc);;All files (*)",
        )
        if not selected:
            return

        fallback_path = Path(selected)
        if fallback_path not in self._custom_fallback_paths:
            self._custom_fallback_paths.append(fallback_path)
        self._refresh_fallback_status()

    def _clear_fallback_fonts(self, *_args) -> None:
        self._custom_fallback_paths.clear()
        self._refresh_fallback_status()

    def _refresh_fallback_status(self) -> None:
        if self._state is None:
            self.fallback_fonts.setText(self._fallback_fonts_text())
            self.clear_fallback_button.setEnabled(False)
            return

        try:
            fallback = build_fallback_status(
                self._state.metadata.path,
                custom_fallback_paths=self._custom_fallback_paths,
                noto_fallback_paths=self._noto_fallback_paths,
            )
        except Exception as error:
            self.fallback_details.setText(f"Fallback check failed: {error}")
            return

        self._state = DesktopFontState(
            metadata=self._state.metadata,
            audit=self._state.audit,
            fallback=fallback,
            output_path=self._state.output_path,
            family_name=self._state.family_name,
        )
        self.fallback_details.setText(format_fallback_status(fallback))
        self.fallback_fonts.setText(self._fallback_fonts_text())
        self.clear_fallback_button.setEnabled(bool(self._custom_fallback_paths))
        self._patch_inputs_changed()

    def _load_font(self, path: Path) -> None:
        self._load_request_id += 1
        request_id = self._load_request_id
        self._preview_request_id += 1
        self._state = None
        self._patch_preview_path = None
        self._load_future = self._executor.submit(
            create_font_state,
            path,
            custom_fallback_paths=tuple(self._custom_fallback_paths),
            noto_fallback_paths=tuple(self._noto_fallback_paths),
        )
        self._load_future.add_done_callback(
            lambda future: self._font_load_finished(request_id, future)
        )

        self._updating_ui = True
        self._set_font_controls_enabled(False)
        self.font_details.setText(f"Opening {path.name}...")
        self.audit_details.setText("Waiting for audit results...")
        self.fallback_details.setText("Waiting for fallback coverage...")
        self.fallback_fonts.setText(self._fallback_fonts_text())
        self.preview_status.setText("Loading font...")
        self.export_status.clear()
        self.patched_radio.setEnabled(False)
        self.patched_radio.setChecked(True)
        self._updating_ui = False
        self._set_busy("load", "Loading font...")

    def _font_load_finished(self, request_id: int, future: Future) -> None:
        try:
            state = future.result()
        except Exception as error:
            self._signals.font_load_failed.emit((request_id, str(error)))
            return

        self._signals.font_loaded.emit((request_id, state))

    def _font_loaded(self, payload) -> None:
        request_id, state = payload
        if request_id != self._load_request_id:
            return

        self._load_future = None
        self._set_busy("load", None)
        self._updating_ui = True
        self._state = state
        self._patch_preview_path = None
        self.font_details.setText(format_font_details(state.metadata))
        self.audit_details.setText(format_audit_summary(state.audit))
        self.fallback_details.setText(format_fallback_status(state.fallback))
        self.fallback_fonts.setText(self._fallback_fonts_text())
        self._set_font_controls_enabled(True)
        self.family_input.setText(state.family_name)
        self.output_input.setText(str(state.output_path))
        self.export_status.clear()
        self.patched_radio.setChecked(True)
        self._updating_ui = False
        self._refresh_patch_preview(select_preview=True)
        self._reset_sidebar_scroll()

    def _font_load_failed(self, payload) -> None:
        request_id, error = payload
        if request_id != self._load_request_id:
            return

        self._load_future = None
        self._set_busy("load", None)
        self._set_empty_state()
        QMessageBox.critical(self, "Could not open font", error)

    def _set_font_controls_enabled(self, enabled: bool) -> None:
        busy = bool(self._busy_messages)
        export_busy = self._export_future is not None and not self._export_future.done()
        self.family_input.setEnabled(enabled and not busy)
        self.output_input.setEnabled(enabled and not busy)
        self.add_fallback_button.setEnabled(enabled and not busy)
        self.clear_fallback_button.setEnabled(
            enabled and not busy and bool(self._custom_fallback_paths)
        )
        self.center_radio.setEnabled(enabled and not busy)
        self.fit_radio.setEnabled(enabled and not busy)
        self.original_radio.setEnabled(enabled)
        self.patched_radio.setEnabled(enabled and self._patch_preview_path is not None)
        self.preview_text.setEnabled(not busy)
        self.refresh_preview_button.setEnabled(enabled and not busy)
        self.export_button.setEnabled(enabled and not busy and not export_busy)

    def _set_busy(self, key: str, message: Optional[str]) -> None:
        if message is None:
            self._busy_messages.pop(key, None)
        else:
            self._busy_messages[key] = message

        if self._busy_messages:
            current_message = next(reversed(self._busy_messages.values()))
            self.busy_label.setText(current_message)
            self.busy_label.show()
            self.progress_bar.show()
        else:
            self.busy_label.clear()
            self.busy_label.hide()
            self.progress_bar.hide()

        self.open_button.setEnabled(not self._busy_messages)
        self.update_button.setEnabled(not self._busy_messages and self._update_future is None)

    def _check_for_updates(self, *_args) -> None:
        if self._update_future is not None and not self._update_future.done():
            return

        self._set_busy("update", "Checking updates...")
        self._set_font_controls_enabled(self._state is not None)
        self._update_future = self._executor.submit(check_for_update)
        self._update_future.add_done_callback(self._update_check_finished)

    def _update_check_finished(self, future: Future) -> None:
        try:
            result = future.result()
        except Exception as error:
            self._signals.update_failed.emit(str(error))
            return

        self._signals.update_done.emit(result)

    def _update_done(self, result: UpdateCheckResult) -> None:
        self._update_future = None
        self._set_busy("update", None)
        self._set_font_controls_enabled(self._state is not None)
        if not result.update_available:
            QMessageBox.information(
                self,
                "No update available",
                f"PTT Font Tool {result.current_version} is the latest release.",
            )
            return

        message = QMessageBox(self)
        message.setWindowTitle("Update available")
        message.setText(
            f"PTT Font Tool {result.latest.version} is available.\n"
            f"You are using {result.current_version}."
        )
        message.setInformativeText("Open the GitHub release page to download it.")
        open_button = message.addButton("Open release", QMessageBox.ButtonRole.AcceptRole)
        message.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
        message.exec()
        if message.clickedButton() == open_button:
            QDesktopServices.openUrl(QUrl(result.latest.url))

    def _update_failed(self, error: str) -> None:
        self._update_future = None
        self._set_busy("update", None)
        self._set_font_controls_enabled(self._state is not None)
        message = error if error else str(UpdateCheckError("Could not check for updates."))
        QMessageBox.warning(self, "Could not check for updates", message)

    def _reset_sidebar_scroll(self) -> None:
        def reset() -> None:
            scrollbar = self.sidebar_scroll.verticalScrollBar()
            scrollbar.setValue(scrollbar.minimum())

        QTimer.singleShot(0, reset)
        QTimer.singleShot(50, reset)
        QTimer.singleShot(200, reset)

    def _load_preview_font(self, path: Path) -> str:
        self._remove_preview_font()
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            raise ValueError(f"Could not load font for preview: {path}")

        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            QFontDatabase.removeApplicationFont(font_id)
            raise ValueError(f"Loaded font has no preview family: {path}")

        self._font_id = font_id
        return families[0]

    def _remove_preview_font(self) -> None:
        if self._font_id is not None:
            QFontDatabase.removeApplicationFont(self._font_id)
            self._font_id = None

    def _apply_preview_font(self, family: str) -> None:
        font = QFont(family)
        font.setPointSize(20)
        self.rendered_preview.setFont(font)

    def _sync_preview_text(self) -> None:
        self.rendered_preview.setPlainText(self.preview_text.toPlainText())
        self._patch_inputs_changed()

    def _patch_inputs_changed(self, *_args) -> None:
        if self._updating_ui or self._state is None:
            return

        self._preview_request_id += 1
        self._patch_preview_path = None
        self.patched_radio.setEnabled(False)
        self.preview_status.setText("Patched preview needs refresh.")
        if self.patched_radio.isChecked():
            self.original_radio.setChecked(True)
            self._show_original_preview()

    def _preview_mode_changed(self, *_args) -> None:
        if self._updating_ui or self._state is None:
            return

        if self.original_radio.isChecked():
            self._show_original_preview()
            return

        if self.patched_radio.isChecked():
            self._show_patched_preview()
        self._reset_sidebar_scroll()

    def _show_original_preview(self) -> None:
        if self._state is None:
            return

        preview_family = self._load_preview_font(self._state.metadata.path)
        self._apply_preview_font(preview_family)

    def _show_patched_preview(self) -> None:
        if self._patch_preview_path is None:
            self._refresh_patch_preview(select_preview=True)
            return

        preview_family = self._load_preview_font(self._patch_preview_path)
        self._apply_preview_font(preview_family)

    def _refresh_patch_preview(self, _checked: bool = False, *, select_preview: bool = False) -> None:
        if self._state is None:
            return

        self._preview_request_id += 1
        request_id = self._preview_request_id
        output_path = self._patch_preview_output_path()
        self._patch_preview_path = None
        self.patched_radio.setEnabled(False)
        self.preview_status.setText("Generating patched preview...")
        self._set_busy("preview", "Generating patched preview...")
        self._set_font_controls_enabled(True)
        self._preview_future = self._executor.submit(
            create_patch_preview,
            self._state.metadata.path,
            output_path,
            family_name=self.family_input.text(),
            strategy=self._selected_strategy(),
            sample_text=self.preview_text.toPlainText(),
            fallback_paths=tuple(self._fallback_chain()),
        )
        self._preview_future.add_done_callback(
            lambda future: self._patch_preview_finished(request_id, select_preview, future)
        )

    def _patch_preview_finished(
        self,
        request_id: int,
        select_preview: bool,
        future: Future,
    ) -> None:
        try:
            result = future.result()
        except Exception as error:
            self._signals.preview_failed.emit((request_id, str(error)))
            return

        self._signals.preview_done.emit((request_id, select_preview, result))

    def _patch_preview_done(self, payload) -> None:
        request_id, select_preview, result = payload
        if request_id != self._preview_request_id:
            return

        self._preview_future = None
        self._set_busy("preview", None)
        self._patch_preview_path = result.output_path
        self.patched_radio.setEnabled(True)
        self.preview_status.setText(format_patch_preview_status(result.audit))
        self._set_font_controls_enabled(self._state is not None)

        if select_preview:
            self.patched_radio.setChecked(True)

        if self.patched_radio.isChecked():
            self._show_patched_preview()

    def _patch_preview_failed(self, payload) -> None:
        request_id, error = payload
        if request_id != self._preview_request_id:
            return

        self._preview_future = None
        self._set_busy("preview", None)
        self._patch_preview_path = None
        self.patched_radio.setEnabled(False)
        self.preview_status.setText(f"Patched preview failed: {error}")
        self._set_font_controls_enabled(self._state is not None)
        if self.patched_radio.isChecked():
            self.original_radio.setChecked(True)
            self._show_original_preview()

    def _export_font(self, *_args) -> None:
        if self._state is None:
            return

        if self._export_future is not None and not self._export_future.done():
            return

        self._set_busy("export", "Exporting font...")
        self._set_font_controls_enabled(True)
        self.export_button.setEnabled(False)
        self.export_status.setText("Exporting and verifying...")
        self._export_future = self._executor.submit(
            export_patched_font,
            self._state.metadata.path,
            Path(self.output_input.text()).expanduser(),
            family_name=self.family_input.text(),
            strategy=self._selected_strategy(),
            fallback_paths=self._fallback_chain(),
            required_fallback_chars=PTT_REQUIRED_SYMBOLS,
        )
        self._export_future.add_done_callback(self._export_finished)

    def _export_finished(self, future: Future) -> None:
        try:
            result = future.result()
        except Exception as error:
            self._signals.export_failed.emit(str(error))
            return

        self._signals.export_done.emit(result)

    def _export_done(self, result: PatchedFontState) -> None:
        self.export_status.setText(format_export_status(result.output_path, result.audit))
        self._export_future = None
        self._set_busy("export", None)
        self._set_font_controls_enabled(self._state is not None)

    def _export_failed(self, error: str) -> None:
        self.export_status.setText(f"Export failed: {error}")
        self._export_future = None
        self._set_busy("export", None)
        self._set_font_controls_enabled(self._state is not None)

    def _selected_strategy(self) -> str:
        if self.fit_radio.isChecked():
            return "fit"

        return "center"

    def _patch_preview_output_path(self) -> Path:
        assert self._state is not None
        source = self._state.metadata.path
        return Path(self._temp_dir.name) / f"{source.stem}-{self._selected_strategy()}-preview{source.suffix}"

    def _fallback_chain(self) -> list[Path]:
        return [*self._custom_fallback_paths, *self._noto_fallback_paths]

    def _fallback_fonts_text(self) -> str:
        custom = (
            ", ".join(path.name for path in self._custom_fallback_paths)
            if self._custom_fallback_paths
            else "none"
        )
        noto = (
            ", ".join(path.name for path in self._noto_fallback_paths)
            if self._noto_fallback_paths
            else "not found"
        )
        return f"Custom: {custom}\nNoto safety net: {noto}"

    def closeEvent(self, event) -> None:
        self._remove_preview_font()
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._temp_dir.cleanup()
        super().closeEvent(event)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                color: #1f2825;
            }
            QMainWindow {
                background: #f6f4ef;
                color: #1f2825;
            }
            QLabel {
                color: #1f2825;
                font-size: 13px;
            }
            QLabel#Title {
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#BusyStatus {
                color: #47524d;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#StatusLabel {
                padding-top: 4px;
                padding-bottom: 6px;
            }
            QScrollArea {
                background: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QGroupBox {
                border: 1px solid #cfc7b8;
                border-radius: 8px;
                color: #1f2825;
                margin-top: 12px;
                padding: 12px 10px 10px;
                font-weight: 700;
            }
            QGroupBox::title {
                background: #f6f4ef;
                color: #1f2825;
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QRadioButton {
                color: #1f2825;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #3f4944;
                background: #fffdf8;
            }
            QRadioButton::indicator:hover {
                border-color: #0d7265;
            }
            QRadioButton:focus::indicator {
                border-color: #0d7265;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #0d7265;
                background: qradialgradient(
                    cx: 0.5,
                    cy: 0.5,
                    radius: 0.5,
                    fx: 0.5,
                    fy: 0.5,
                    stop: 0 #0d7265,
                    stop: 0.38 #0d7265,
                    stop: 0.42 #fffdf8,
                    stop: 1 #fffdf8
                );
            }
            QRadioButton::indicator:disabled {
                border-color: #b9b0a2;
                background: #e9e4da;
            }
            QRadioButton::indicator:checked:disabled {
                border-color: #8d8477;
                background: qradialgradient(
                    cx: 0.5,
                    cy: 0.5,
                    radius: 0.5,
                    fx: 0.5,
                    fy: 0.5,
                    stop: 0 #6b716d,
                    stop: 0.38 #6b716d,
                    stop: 0.42 #e9e4da,
                    stop: 1 #e9e4da
                );
            }
            QPushButton {
                background: #0d7265;
                border: 1px solid #0a5d53;
                border-radius: 6px;
                color: white;
                font-weight: 700;
                padding: 7px 12px;
            }
            QPushButton:disabled {
                background: #d9d4ca;
                border-color: #c8c0b2;
                color: #6b716d;
            }
            QPushButton#SecondaryButton {
                background: #eee9df;
                border-color: #bfb6a7;
                color: #1f2825;
            }
            QPushButton#SecondaryButton:hover {
                background: #e4ded2;
            }
            QPushButton#SecondaryButton:disabled {
                background: #dad4ca;
                border-color: #c8c0b2;
                color: #5f6763;
            }
            QLineEdit,
            QPlainTextEdit {
                background: #fffdf8;
                border: 1px solid #cfc7b8;
                border-radius: 6px;
                color: #1f2825;
                padding: 7px;
                selection-background-color: #0d7265;
                selection-color: #ffffff;
            }
            QLineEdit:disabled,
            QPlainTextEdit:disabled {
                background: #eee9df;
                color: #5b645f;
            }
            QSplitter::handle {
                background: transparent;
                width: 1px;
            }
            QProgressBar {
                background: #e7e1d6;
                border: 1px solid #c9c0b1;
                border-radius: 4px;
                height: 8px;
            }
            QProgressBar::chunk {
                background: #0d7265;
                border-radius: 3px;
            }
            QPlainTextEdit#TerminalPreview {
                background: #101412;
                border: 1px solid #26302c;
                color: #e3f1e8;
                padding: 14px;
            }
            """
        )


def run(argv: Optional[Sequence[str]] = None) -> int:
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app_icon = _app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    window = MainWindow()
    window.show()
    return app.exec()


def _default_noto_fallback_paths() -> list[Path]:
    candidates = [
        *(_package_font_dir() / name for name in [
            "NotoSansSymbols2-Regular.ttf",
            "NotoSansTC-VariableFont_wght.ttf",
            "NotoSansTC-Regular.otf",
            "NotoSansCJKtc-Regular.otf",
        ]),
        Path.home() / "Library/Fonts/NotoSansSymbols2-Regular.ttf",
        Path.home() / "Library/Fonts/NotoSansTC-VariableFont_wght.ttf",
        Path.home() / "Library/Fonts/NotoSansTC-Regular.otf",
        Path("/Library/Fonts/NotoSansSymbols2-Regular.ttf"),
        Path("/Library/Fonts/NotoSansTC-VariableFont_wght.ttf"),
        Path("/Library/Fonts/NotoSansTC-Regular.otf"),
        Path("/System/Library/Fonts/Supplemental/NotoSansSymbols2-Regular.ttf"),
        Path("/System/Library/Fonts/Supplemental/NotoSansTC-Regular.otf"),
    ]
    seen: set[Path] = set()
    existing: list[Path] = []
    for path in candidates:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        existing.append(path)
    return existing


def _package_font_dir() -> Path:
    return Path(__file__).with_name("fonts")


def _app_icon() -> QIcon:
    icon_path = Path(__file__).with_name("assets") / "app_icon" / "ptt-font-tool.png"
    if not icon_path.exists():
        return QIcon()

    return QIcon(str(icon_path))
