from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import shutil
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
    QListWidget,
    QListWidgetItem,
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
    UnavailableFallbackLayer,
    format_audit_summary,
    format_export_status,
    format_fallback_summary,
    format_fallback_status,
    format_font_details,
    format_patch_preview_status,
)
from .desktop_model import (
    DesktopFontState,
    PatchedFontState,
    create_font_state,
    build_fallback_status,
)
from .fallback import PTT_REQUIRED_SYMBOLS
from .font_stack import build_font_stack, resolve_noto_cache_dir, resolve_noto_mode
from .noto_cache import (
    NotoCacheState,
    NotoTextStyle,
    clear_noto_cache,
    download_noto_assets,
    noto_cache_state,
)
from .update_check import UpdateCheckError, UpdateCheckResult, check_for_update


class WorkerSignals(QObject):
    font_loaded = Signal(object)
    font_load_failed = Signal(object)
    preview_done = Signal(object)
    preview_failed = Signal(object)
    export_done = Signal(object)
    export_failed = Signal(str)
    noto_done = Signal(object)
    noto_failed = Signal(str)
    update_done = Signal(object)
    update_failed = Signal(str)


class FontPreviewTextEdit(QPlainTextEdit):
    def wheelEvent(self, event) -> None:
        delta_y = event.angleDelta().y()
        if self._can_scroll_for_delta(delta_y):
            super().wheelEvent(event)
            return

        event.ignore()

    def _can_scroll_for_delta(self, delta_y: int) -> bool:
        scroll_bar = self.verticalScrollBar()
        if scroll_bar.maximum() <= scroll_bar.minimum():
            return False

        if delta_y > 0:
            return scroll_bar.value() > scroll_bar.minimum()

        if delta_y < 0:
            return scroll_bar.value() < scroll_bar.maximum()

        return False


class FontStackRow(QWidget):
    preview_changed = Signal(str)
    remove_requested = Signal(object)

    def __init__(
        self,
        path: Path,
        *,
        role: str,
        family: str,
        preview_text: str,
    ) -> None:
        super().__init__()
        self.path = path
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        handle = QLabel("⋮⋮")
        handle.setObjectName("StackHandle")
        handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(path.name)
        title.setObjectName("StackFontTitle")
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title.setWordWrap(True)
        detail = QLabel(f"{role} · {family}")
        detail.setObjectName("StackFontMeta")
        detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        detail.setWordWrap(True)
        self.coverage_label = QLabel("Coverage appears after the font opens.")
        self.coverage_label.setObjectName("StackCoverage")
        self.coverage_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.coverage_label.setWordWrap(True)
        remove_button = QPushButton("×")
        remove_button.setObjectName("RemoveButton")
        remove_button.setFixedSize(28, 28)
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self.path))

        self.preview = FontPreviewTextEdit()
        self.preview.setMaximumHeight(72)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.preview.setPlainText(preview_text)
        self.preview.textChanged.connect(self._preview_text_changed)

        layout.addWidget(handle, 0, 0, 3, 1)
        layout.addWidget(title, 0, 1)
        layout.addWidget(remove_button, 0, 2)
        layout.addWidget(detail, 1, 1, 1, 2)
        layout.addWidget(self.coverage_label, 2, 1, 1, 2)
        layout.addWidget(self.preview, 3, 1, 1, 2)

    def set_preview_font(self, family: str) -> None:
        font = QFont(family)
        font.setPointSize(13)
        self.preview.setFont(font)

    def set_preview_text(self, text: str) -> None:
        if self.preview.toPlainText() == text:
            return

        old_state = self.preview.blockSignals(True)
        self.preview.setPlainText(text)
        self.preview.blockSignals(old_state)

    def set_coverage_text(self, text: str) -> None:
        self.coverage_label.setText(text)

    def _preview_text_changed(self) -> None:
        self.preview_changed.emit(self.preview.toPlainText())


def _font_paths_from_mime(mime_data) -> list[Path]:
    if not mime_data.hasUrls():
        return []

    return [
        Path(url.toLocalFile())
        for url in mime_data.urls()
        if url.isLocalFile()
    ]


class FontDropGroup(QGroupBox):
    files_dropped = Signal(object)

    def __init__(self, title: str) -> None:
        super().__init__(title)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        if _font_paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
            return

        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if _font_paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
            return

        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        paths = _font_paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
            return

        super().dropEvent(event)


class FontStackList(QListWidget):
    files_dropped = Signal(object)
    order_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setSpacing(8)
        self._scroll_area: Optional[QScrollArea] = None
        self._auto_scroll_direction = 0
        self._auto_scroll_timer = QTimer(self)
        self._auto_scroll_timer.setInterval(40)
        self._auto_scroll_timer.timeout.connect(self._scroll_parent)

    def set_scroll_area(self, scroll_area: QScrollArea) -> None:
        self._scroll_area = scroll_area

    def dragEnterEvent(self, event) -> None:
        if _font_paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
            return

        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        self._update_parent_auto_scroll(event)
        if _font_paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
            return

        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        self._set_auto_scroll_direction(0)
        paths = _font_paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
            return

        before = self._paths()
        super().dropEvent(event)
        if self._paths() != before:
            self.order_changed.emit()

    def dragLeaveEvent(self, event) -> None:
        self._set_auto_scroll_direction(0)
        super().dragLeaveEvent(event)

    def _update_parent_auto_scroll(self, event) -> None:
        if self._scroll_area is None:
            return

        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        global_position = self.viewport().mapToGlobal(position)
        viewport_position = self._scroll_area.viewport().mapFromGlobal(global_position)
        margin = 48
        if viewport_position.y() < margin:
            self._set_auto_scroll_direction(-1)
            return

        if viewport_position.y() > self._scroll_area.viewport().height() - margin:
            self._set_auto_scroll_direction(1)
            return

        self._set_auto_scroll_direction(0)

    def _set_auto_scroll_direction(self, direction: int) -> None:
        self._auto_scroll_direction = direction
        if direction:
            if not self._auto_scroll_timer.isActive():
                self._auto_scroll_timer.start()
            return

        self._auto_scroll_timer.stop()

    def _scroll_parent(self) -> None:
        if self._scroll_area is None or not self._auto_scroll_direction:
            return

        scroll_bar = self._scroll_area.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.value() + self._auto_scroll_direction * 28)

    def _paths(self) -> list[Path]:
        paths: list[Path] = []
        for index in range(self.count()):
            item = self.item(index)
            path = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(path, Path):
                paths.append(path)
        return paths


def _copy_built_font(
    source_path: Path,
    output_path: Path,
    built_result: PatchedFontState,
) -> PatchedFontState:
    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target)
    return PatchedFontState(
        output_path=target,
        audit=built_result.audit,
        fallback_added=built_result.fallback_added,
        fallback_unresolved=built_result.fallback_unresolved,
    )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._preview_font_ids: dict[Path, int] = {}
        self._preview_families: dict[Path, str] = {}
        self._state: Optional[DesktopFontState] = None
        self._patch_preview_path: Optional[Path] = None
        self._built_result: Optional[PatchedFontState] = None
        self._build_dirty = True
        self._custom_fallback_paths: list[Path] = []
        self._font_stack_paths: list[Path] = []
        self._noto_text_style: NotoTextStyle = resolve_noto_mode() or "sans"
        self._noto_cache_state = noto_cache_state(
            self._noto_text_style,
            cache_dir=resolve_noto_cache_dir(),
        )
        self._noto_fallback_paths = self._noto_cache_state.fallback_paths
        self._preview_sample_text = DEFAULT_PREVIEW_TEXT
        self._syncing_preview_text = False
        self._rendering_font_stack = False
        self._export_after_preview = False
        self._temp_dir = tempfile.TemporaryDirectory(prefix="ptt-font-tool-")
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ptt-font-tool")
        self._load_future: Optional[Future] = None
        self._preview_future: Optional[Future] = None
        self._export_future: Optional[Future] = None
        self._noto_future: Optional[Future] = None
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
        self._signals.noto_done.connect(self._noto_download_done)
        self._signals.noto_failed.connect(self._noto_download_failed)
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
        self.update_button = QPushButton("Check updates")
        self.update_button.setObjectName("SecondaryButton")
        self.update_button.clicked.connect(self._check_for_updates)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.update_button)
        root_layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_preview())
        splitter.setSizes([420, 700])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, 1)

        self.setCentralWidget(root)
        self._apply_style()
        self._set_empty_state()

    def _build_sidebar(self) -> QWidget:
        sidebar_content = QWidget()
        sidebar_content.setObjectName("SidebarContent")
        sidebar_content.setAutoFillBackground(False)
        sidebar_content.setMinimumWidth(0)
        sidebar_content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(sidebar_content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        self.font_group = FontDropGroup("Font Stack")
        self.font_group.files_dropped.connect(self._add_font_paths)
        self.font_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        font_layout = QVBoxLayout(self.font_group)
        self.font_stack_hint = self._detail_label()
        self.font_stack_hint.setText(
            "First font is primary. Later fonts are fallback layers. "
            "Drop font files here or drag rows to reorder."
        )
        self.font_stack_list = FontStackList()
        self.font_stack_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.font_stack_list.files_dropped.connect(self._add_font_paths)
        self.font_stack_list.order_changed.connect(self._font_stack_order_changed)
        self.font_stack_list.currentRowChanged.connect(
            lambda *_args: self._set_font_controls_enabled(self._state is not None)
        )
        self.font_stack_placeholder = QLabel(
            "Drop .ttf, .otf, .ttc, or .otc files here to start a font stack."
        )
        self.font_stack_placeholder.setObjectName("StackPlaceholder")
        self.font_stack_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.font_stack_placeholder.setWordWrap(True)
        self.font_stack_placeholder.setMinimumHeight(96)
        font_buttons = QGridLayout()
        self.add_fonts_button = QPushButton("Add fonts...")
        self.add_fonts_button.setObjectName("SecondaryButton")
        self.add_fonts_button.clicked.connect(self._open_font)
        self.move_font_up_button = QPushButton("Move up")
        self.move_font_up_button.setObjectName("SecondaryButton")
        self.move_font_up_button.clicked.connect(lambda: self._move_selected_font(-1))
        self.move_font_down_button = QPushButton("Move down")
        self.move_font_down_button.setObjectName("SecondaryButton")
        self.move_font_down_button.clicked.connect(lambda: self._move_selected_font(1))
        font_buttons.addWidget(self.add_fonts_button, 0, 0, 1, 2)
        font_buttons.addWidget(self.move_font_up_button, 1, 0)
        font_buttons.addWidget(self.move_font_down_button, 1, 1)
        self.font_details = self._detail_label()
        font_layout.addWidget(self.font_stack_hint)
        font_layout.addWidget(self.font_stack_list)
        font_layout.addWidget(self.font_stack_placeholder)
        font_layout.addLayout(font_buttons)
        font_layout.addWidget(self.font_details)

        self.noto_stack_row = QWidget()
        self.noto_stack_row.setObjectName("LockedFallbackRow")
        noto_stack_layout = QGridLayout(self.noto_stack_row)
        noto_stack_layout.setContentsMargins(8, 8, 8, 8)
        noto_stack_layout.setHorizontalSpacing(8)
        noto_stack_layout.setVerticalSpacing(6)
        noto_title = QLabel("Noto fallback")
        noto_title.setObjectName("LockedFallbackTitle")
        noto_meta = QLabel("Locked final fallback for PTT symbols and CJK text.")
        noto_meta.setObjectName("LockedFallbackMeta")
        noto_meta.setWordWrap(True)
        self.noto_cache_details = self._detail_label()
        self.noto_cache_details.setObjectName("StackCoverage")
        self.noto_cache_details.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.MinimumExpanding,
        )
        self.noto_sans_radio = QRadioButton("Sans TC")
        self.noto_serif_radio = QRadioButton("Serif TC")
        if self._noto_text_style == "serif":
            self.noto_serif_radio.setChecked(True)
        else:
            self.noto_sans_radio.setChecked(True)
        self.noto_sans_radio.toggled.connect(self._noto_style_changed)
        self.noto_serif_radio.toggled.connect(self._noto_style_changed)
        noto_style_choices = QHBoxLayout()
        noto_style_choices.addWidget(self.noto_sans_radio)
        noto_style_choices.addWidget(self.noto_serif_radio)
        noto_style_choices.addStretch(1)
        self.noto_cache_button = QPushButton("Download Noto")
        self.noto_cache_button.clicked.connect(self._download_or_redownload_noto)
        self.open_noto_folder_button = QPushButton("Open folder")
        self.open_noto_folder_button.setObjectName("SecondaryButton")
        self.open_noto_folder_button.clicked.connect(self._open_noto_folder)
        self.clear_noto_button = QPushButton("Clear Noto")
        self.clear_noto_button.setObjectName("SecondaryButton")
        self.clear_noto_button.clicked.connect(self._clear_noto_cache)
        noto_download_buttons = QGridLayout()
        noto_download_buttons.addWidget(self.noto_cache_button, 0, 0, 1, 2)
        noto_download_buttons.addWidget(self.open_noto_folder_button, 1, 0)
        noto_download_buttons.addWidget(self.clear_noto_button, 1, 1)
        noto_stack_layout.addWidget(noto_title, 0, 0)
        noto_stack_layout.addWidget(noto_meta, 1, 0)
        noto_stack_layout.addLayout(noto_style_choices, 2, 0)
        noto_stack_layout.addWidget(self.noto_cache_details, 3, 0)
        noto_stack_layout.addLayout(noto_download_buttons, 4, 0)
        font_layout.addWidget(self.noto_stack_row)

        self.fallback_summary = self._detail_label()
        self.fallback_summary.setObjectName("FallbackSummary")
        self.fallback_details = self._detail_label()
        self.fallback_fonts = self._detail_label()
        font_layout.addWidget(self.fallback_summary)

        self.audit_group = QGroupBox("Audit")
        self.audit_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        audit_layout = QVBoxLayout(self.audit_group)
        self.audit_details = self._detail_label()
        audit_layout.addWidget(self.audit_details)

        self.settings_group = QGroupBox("Build Settings")
        self.settings_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        settings_layout = QVBoxLayout(self.settings_group)
        strategy_choices = QHBoxLayout()
        self.center_radio = QRadioButton("Center")
        self.center_radio.setToolTip("Preserve glyph shape and center it inside the PTT cell.")
        self.fit_radio = QRadioButton("Fit")
        self.fit_radio.setToolTip("Shrink oversized glyphs horizontally before centering.")
        self.center_radio.setChecked(True)
        self.center_radio.toggled.connect(self._strategy_changed)
        self.fit_radio.toggled.connect(self._strategy_changed)
        strategy_choices.addWidget(self.center_radio)
        strategy_choices.addWidget(self.fit_radio)
        strategy_choices.addStretch(1)
        self.strategy_help_label = QLabel()
        self.strategy_help_label.setObjectName("StrategyHelp")
        self.strategy_help_label.setWordWrap(True)

        settings_layout.addWidget(QLabel("Strategy"))
        settings_layout.addLayout(strategy_choices)
        settings_layout.addWidget(self.strategy_help_label)
        self._update_strategy_help()

        layout.addWidget(self.font_group, 1)
        layout.addWidget(self.settings_group)
        layout.addWidget(self.audit_group)

        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setObjectName("SidebarScroll")
        self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.sidebar_scroll.viewport().setAutoFillBackground(False)
        self.sidebar_scroll.setWidget(sidebar_content)
        self.sidebar_scroll.setMinimumWidth(420)
        self.sidebar_scroll.setMaximumWidth(460)
        self.sidebar_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.font_stack_list.set_scroll_area(self.sidebar_scroll)
        return self.sidebar_scroll

    def _build_preview(self) -> QWidget:
        preview = QWidget()
        layout = QVBoxLayout(preview)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(12)

        self.rendered_preview = QPlainTextEdit()
        self.rendered_preview.setFrameShape(QFrame.Shape.NoFrame)
        self.rendered_preview.setPlainText(DEFAULT_PREVIEW_TEXT)
        self.rendered_preview.setObjectName("TerminalPreview")
        self.rendered_preview.textChanged.connect(self._rendered_preview_text_changed)

        self.build_group = QGroupBox("Build")
        build_layout = QGridLayout(self.build_group)
        self.preview_status = QLabel()
        self.preview_status.setObjectName("BuildStatus")
        self.preview_status.setWordWrap(True)
        self.preview_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.build_progress_bar = QProgressBar()
        self.build_progress_bar.setRange(0, 0)
        self.build_progress_bar.setTextVisible(False)
        self.build_progress_bar.setObjectName("BuildProgress")
        self.build_progress_bar.setFixedHeight(8)
        self.build_progress_bar.hide()
        self.export_status = self._detail_label()
        self.export_status.setObjectName("StatusLabel")

        self.refresh_preview_button = QPushButton("Build preview")
        self.refresh_preview_button.setObjectName("SecondaryButton")
        self.refresh_preview_button.clicked.connect(self._refresh_patch_preview)

        self.family_input = QLineEdit()
        self.family_input.textChanged.connect(self._patch_inputs_changed)
        self.export_hint_label = self._detail_label()
        self.export_hint_label.setObjectName("ExportHint")
        self.export_hint_label.setText(
            "Export opens a save dialog. If the preview is stale, export builds first."
        )
        self.export_button = QPushButton("Export built font")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_font)

        output_name_stack = QWidget()
        output_name_stack.setObjectName("OutputNameStack")
        output_name_layout = QVBoxLayout(output_name_stack)
        output_name_layout.setContentsMargins(0, 0, 0, 0)
        output_name_layout.setSpacing(2)
        output_name_layout.addWidget(self.family_input)
        output_name_layout.addWidget(self.export_hint_label)

        build_layout.addWidget(self.preview_status, 0, 0, 1, 2)
        build_layout.addWidget(self.refresh_preview_button, 0, 2)
        build_layout.addWidget(self.build_progress_bar, 1, 0, 1, 3)
        build_layout.addWidget(QLabel("Output font name"), 2, 0)
        build_layout.addWidget(output_name_stack, 2, 1)
        build_layout.addWidget(self.export_button, 2, 2, alignment=Qt.AlignmentFlag.AlignTop)
        build_layout.addWidget(self.export_status, 3, 0, 1, 3)
        build_layout.setColumnStretch(1, 1)
        layout.addWidget(self.build_group)

        preview_header = QHBoxLayout()
        preview_header.addWidget(QLabel("Rendered preview"))
        preview_header.addStretch(1)
        self.original_radio = QRadioButton("Original")
        self.patched_radio = QRadioButton("Patched")
        self.original_radio.setChecked(True)
        self.original_radio.toggled.connect(self._preview_mode_changed)
        self.patched_radio.toggled.connect(self._preview_mode_changed)
        preview_header.addWidget(self.original_radio)
        preview_header.addWidget(self.patched_radio)
        layout.addLayout(preview_header)
        self.preview_hint_label = self._detail_label()
        self.preview_hint_label.setObjectName("PreviewHint")
        self.preview_hint_label.setText(
            "Edit sample text here. Build to see the patched font in this preview."
        )
        layout.addWidget(self.preview_hint_label)
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
        self._state = None
        self._patch_preview_path = None
        self._built_result = None
        self._build_dirty = True
        self._export_after_preview = False
        self._font_stack_paths.clear()
        self._custom_fallback_paths.clear()
        self._render_font_stack()
        self.font_details.setText("Add local .otf or .ttf files.")
        self.audit_details.setText("Audit results will appear after a font is opened.")
        self.fallback_summary.setText("Open a font to calculate fallback coverage.")
        self.fallback_details.setText("Fallback coverage appears in the font stack after a font is opened.")
        self.fallback_fonts.setText(self._fallback_fonts_text())
        self._set_noto_cache_details_text(self._noto_stack_coverage_text())
        self.preview_status.setText("Add a font to build a patched preview.")
        self.preview_hint_label.setText(
            "Drop or add fonts first. Build creates the patched preview shown here."
        )
        self._set_export_status("")
        self.family_input.clear()
        self._set_font_controls_enabled(False)

    def _open_font(self, *_args) -> None:
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Add fonts",
            "",
            "Font files (*.otf *.ttf *.ttc *.otc);;All files (*)",
        )
        if selected:
            self._add_font_paths([Path(path) for path in selected])

    def _add_font_paths(self, paths: Sequence[Path]) -> None:
        font_paths = [
            path
            for path in (Path(candidate).expanduser() for candidate in paths)
            if path.suffix.lower() in {".otf", ".ttf", ".ttc", ".otc"}
        ]
        if not font_paths:
            return

        had_primary = bool(self._font_stack_paths)
        for path in font_paths:
            if path not in self._font_stack_paths:
                self._font_stack_paths.append(path)

        self._sync_fallback_paths_from_stack()
        self._render_font_stack()
        if not had_primary and self._font_stack_paths:
            self._load_font(self._font_stack_paths[0])
            return

        self._refresh_fallback_status()

    def _remove_font_path(self, path: Path) -> None:
        if path not in self._font_stack_paths:
            return

        was_primary = self._font_stack_paths and self._font_stack_paths[0] == path
        self._font_stack_paths = [
            stack_path
            for stack_path in self._font_stack_paths
            if stack_path != path
        ]
        self._sync_fallback_paths_from_stack()
        self._render_font_stack()
        if not self._font_stack_paths:
            self._set_empty_state()
            return

        if was_primary:
            self._load_font(self._font_stack_paths[0])
            return

        self._refresh_fallback_status()

    def _move_selected_font(self, offset: int) -> None:
        row = self.font_stack_list.currentRow()
        if row < 0:
            return

        target = row + offset
        if target < 0 or target >= len(self._font_stack_paths):
            return

        self._font_stack_paths[row], self._font_stack_paths[target] = (
            self._font_stack_paths[target],
            self._font_stack_paths[row],
        )
        primary_changed = row == 0 or target == 0
        self._sync_fallback_paths_from_stack()
        self._render_font_stack(selected_row=target)
        if primary_changed:
            self._load_font(self._font_stack_paths[0])
            return

        self._refresh_fallback_status()

    def _font_stack_order_changed(self) -> None:
        if self._rendering_font_stack:
            return

        ordered_paths = self.font_stack_list._paths()
        if ordered_paths == self._font_stack_paths:
            return

        old_primary = self._font_stack_paths[0] if self._font_stack_paths else None
        self._font_stack_paths = ordered_paths
        self._sync_fallback_paths_from_stack()
        self._render_font_stack()
        if self._font_stack_paths and self._font_stack_paths[0] != old_primary:
            self._load_font(self._font_stack_paths[0])
            return

        self._refresh_fallback_status()

    def _sync_fallback_paths_from_stack(self) -> None:
        self._custom_fallback_paths = self._font_stack_paths[1:]

    def _render_font_stack(self, *, selected_row: int = -1) -> None:
        self._rendering_font_stack = True
        self.font_stack_list.clear()
        layers = self._fallback_layers_by_path()
        for index, path in enumerate(self._font_stack_paths):
            role = "Primary font" if index == 0 else f"Fallback layer {index}"
            kind = "primary" if index == 0 else "custom"
            family = self._preview_family_for_path(path, fallback=path.stem)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, path)
            row = FontStackRow(
                path,
                role=role,
                family=family,
                preview_text=self._preview_sample_text,
            )
            row.set_preview_font(family)
            row.set_coverage_text(self._stack_layer_coverage_text(layers.get((kind, path)), kind=kind))
            row.preview_changed.connect(self._font_row_preview_text_changed)
            row.remove_requested.connect(self._remove_font_path)
            item.setSizeHint(row.sizeHint())
            self.font_stack_list.addItem(item)
            self.font_stack_list.setItemWidget(item, row)

        if selected_row >= 0 and selected_row < self.font_stack_list.count():
            self.font_stack_list.setCurrentRow(selected_row)
        self._update_font_stack_list_height()
        self._rendering_font_stack = False

    def _update_font_stack_list_height(self) -> None:
        frame = self.font_stack_list.frameWidth() * 2
        padding = 16
        if self.font_stack_list.count() == 0:
            self.font_stack_list.hide()
            self.font_stack_placeholder.show()
            self.font_stack_list.setFixedHeight(0)
            return

        self.font_stack_placeholder.hide()
        self.font_stack_list.show()
        rows_height = sum(
            self.font_stack_list.item(index).sizeHint().height()
            for index in range(self.font_stack_list.count())
        )
        spacing = self.font_stack_list.spacing() * (self.font_stack_list.count() + 1)
        self.font_stack_list.setFixedHeight(frame + padding + rows_height + spacing)

    def _fallback_layers_by_path(self) -> dict[tuple[str, Path], object]:
        if self._state is None:
            return {}

        return {
            (layer.kind, Path(layer.path)): layer
            for layer in self._state.fallback.layers
        }

    def _stack_layer_coverage_text(self, layer, *, kind: str) -> str:
        if layer is None:
            return "Coverage appears after the font opens."

        missing = len(layer.missing_after)
        if kind == "primary":
            return f"{missing:,} missing after primary font."

        return f"adds {len(layer.added):,}, {missing:,} missing after this layer."

    def _noto_stack_coverage_text(self) -> str:
        cache_text = self._noto_cache_text()
        if self._noto_future is not None and not self._noto_future.done():
            return "\n".join([
                "Downloading Noto fallback...",
                cache_text,
            ])

        if self._state is None:
            return cache_text

        noto_layers = [
            layer for layer in self._state.fallback.layers
            if layer.kind == "noto"
        ]
        if noto_layers:
            added = sum(len(layer.added) for layer in noto_layers)
            missing = len(noto_layers[-1].missing_after)
            return "\n".join([
                f"adds {added:,}, {missing:,} missing after final fallback.",
                cache_text,
            ])

        if self._state.fallback.unresolved and self._noto_cache_state.missing_assets:
            return "\n".join([
                f"{len(self._state.fallback.unresolved):,} missing before Noto fallback.",
                "Download Noto to continue the coverage check.",
                cache_text,
            ])

        return cache_text

    def _set_noto_cache_details_text(self, text: str) -> None:
        self.noto_cache_details.setMinimumHeight(0)
        self.noto_cache_details.setText(text)
        self.noto_cache_details.setMinimumHeight(self.noto_cache_details.sizeHint().height())

    def _noto_style_changed(self, *_args) -> None:
        if self._updating_ui:
            return

        self._noto_text_style = self._selected_noto_text_style()
        self._refresh_fallback_status()

    def _download_or_redownload_noto(self, *_args) -> None:
        force = self._noto_cache_state.complete and self._noto_cache_state.has_cached_files
        self._download_noto_assets(force=force)

    def _download_noto_assets(self, *, force: bool) -> None:
        if self._noto_future is not None and not self._noto_future.done():
            return

        self._noto_text_style = self._selected_noto_text_style()
        self._set_busy("noto", "Downloading Noto fallback...")
        self._set_font_controls_enabled(self._state is not None)
        self.fallback_summary.setText("Downloading Noto fallback into the app cache...")
        self._set_noto_cache_details_text(self._noto_stack_coverage_text())
        self._noto_future = self._executor.submit(
            download_noto_assets,
            self._noto_text_style,
            cache_dir=self._noto_cache_state.cache_dir,
            force=force,
        )
        self._noto_future.add_done_callback(self._noto_download_finished)

    def _noto_download_finished(self, future: Future) -> None:
        try:
            state = future.result()
        except Exception as error:
            self._signals.noto_failed.emit(str(error))
            return

        self._signals.noto_done.emit(state)

    def _noto_download_done(self, state: NotoCacheState) -> None:
        self._noto_future = None
        self._set_busy("noto", None)
        self._noto_cache_state = state
        self._noto_text_style = state.text_style
        self._noto_fallback_paths = state.fallback_paths
        self._set_font_controls_enabled(self._state is not None)
        self._refresh_fallback_status()

    def _noto_download_failed(self, error: str) -> None:
        self._noto_future = None
        self._set_busy("noto", None)
        self._refresh_noto_cache_state()
        self.fallback_summary.setText(f"Noto download failed: {error}")
        self.fallback_fonts.setText(self._fallback_fonts_text())
        self._set_noto_cache_details_text(self._noto_stack_coverage_text())
        self._set_font_controls_enabled(self._state is not None)

    def _clear_noto_cache(self, *_args) -> None:
        clear_noto_cache(cache_dir=self._noto_cache_state.cache_dir)
        self._refresh_fallback_status()

    def _open_noto_folder(self, *_args) -> None:
        self._noto_cache_state.cache_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._noto_cache_state.cache_dir)))

    def _refresh_fallback_status(self) -> None:
        self._refresh_noto_cache_state()
        if self._state is None:
            self.fallback_summary.setText("Open a font to calculate fallback coverage.")
            self.fallback_fonts.setText(self._fallback_fonts_text())
            self._set_noto_cache_details_text(self._noto_stack_coverage_text())
            self._set_font_controls_enabled(False)
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
        self._set_fallback_labels(fallback)
        self._mark_build_dirty("Font stack changed")

    def _load_font(self, path: Path) -> None:
        self._load_request_id += 1
        request_id = self._load_request_id
        self._preview_request_id += 1
        self._state = None
        self._patch_preview_path = None
        self._built_result = None
        self._build_dirty = True
        self._load_future = self._executor.submit(
            create_font_state,
            path,
            custom_fallback_paths=tuple(self._custom_fallback_paths),
            noto_fallback_paths=tuple(self._noto_fallback_paths),
        )
        self._load_future.add_done_callback(
            lambda future: self._font_load_finished(request_id, future)
        )

        self._set_busy("load", "Loading font...")
        self._updating_ui = True
        self._set_font_controls_enabled(False)
        self.font_details.setText(f"Opening {path.name}...")
        self.audit_details.setText("Waiting for audit results...")
        self.fallback_summary.setText("Calculating fallback coverage...")
        self.fallback_details.setText("Waiting for fallback coverage...")
        self.fallback_fonts.setText(self._fallback_fonts_text())
        self.preview_status.setText("Loading font...")
        self.preview_hint_label.setText(
            "Loading coverage and metrics. Build after loading to inspect the patched font."
        )
        self._set_export_status("")
        self.patched_radio.setEnabled(False)
        self.original_radio.setChecked(True)
        self._updating_ui = False

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
        self._set_fallback_labels(state.fallback)
        self._set_font_controls_enabled(True)
        self.family_input.setText(state.family_name)
        self._set_export_status("")
        self.original_radio.setChecked(True)
        self.preview_status.setText("Ready to build. Export will build first if needed.")
        self.preview_hint_label.setText(
            "Original preview is shown. Build to switch to the patched preview."
        )
        self._updating_ui = False
        self._build_dirty = True
        self._set_font_controls_enabled(True)
        self._show_original_preview()

    def _font_load_failed(self, payload) -> None:
        request_id, error = payload
        if request_id != self._load_request_id:
            return

        self._load_future = None
        self._set_busy("load", None)
        self._set_empty_state()
        self._show_message(QMessageBox.Icon.Critical, "Could not open font", error)

    def _set_fallback_labels(self, fallback) -> None:
        unavailable_layers = self._unavailable_noto_layers(fallback)
        self.fallback_summary.setText(
            format_fallback_summary(fallback, unavailable_layers=unavailable_layers)
        )
        self.fallback_details.setText(
            format_fallback_status(fallback, unavailable_layers=unavailable_layers)
        )
        self.fallback_fonts.setText(self._fallback_fonts_text())
        self._set_noto_cache_details_text(self._noto_stack_coverage_text())
        self._render_font_stack(selected_row=self.font_stack_list.currentRow())

    def _unavailable_noto_layers(self, fallback) -> list[UnavailableFallbackLayer]:
        if not fallback.unresolved:
            return []

        return [
            UnavailableFallbackLayer(
                label=asset.label,
                reason="not downloaded",
            )
            for asset in self._noto_cache_state.missing_assets
            if asset.is_font
        ]

    def _set_font_controls_enabled(self, enabled: bool) -> None:
        busy = bool(self._busy_messages)
        export_busy = self._export_future is not None and not self._export_future.done()
        self.family_input.setEnabled(enabled and not busy)
        self.add_fonts_button.setEnabled(not busy)
        self.move_font_up_button.setEnabled(enabled and not busy and self.font_stack_list.currentRow() > 0)
        self.move_font_down_button.setEnabled(
            enabled
            and not busy
            and 0 <= self.font_stack_list.currentRow() < self.font_stack_list.count() - 1
        )
        self.center_radio.setEnabled(enabled and not busy)
        self.fit_radio.setEnabled(enabled and not busy)
        self.original_radio.setEnabled(enabled)
        self.patched_radio.setEnabled(enabled and self._patch_preview_path is not None)
        self.rendered_preview.setEnabled(not busy)
        self.refresh_preview_button.setEnabled(enabled and not busy and self._build_dirty)
        self._set_export_button_text(export_busy=export_busy)
        self.export_button.setEnabled(
            enabled
            and not busy
            and not export_busy
        )
        self.noto_sans_radio.setEnabled(not busy)
        self.noto_serif_radio.setEnabled(not busy)
        if self._noto_cache_state.complete and self._noto_cache_state.has_cached_files:
            noto_button_text = "Re-download Noto"
        elif self._noto_cache_state.has_cached_files:
            noto_button_text = "Download missing Noto"
        else:
            noto_button_text = "Download Noto"
        self.noto_cache_button.setText(noto_button_text)
        self.noto_cache_button.setEnabled(not busy)
        self.open_noto_folder_button.setEnabled(not busy)
        self.clear_noto_button.setEnabled(not busy and self._noto_cache_state.has_cached_files)

    def _set_export_button_text(self, *, export_busy: bool = False) -> None:
        if export_busy:
            self.export_button.setText("Exporting...")
            return

        if self._has_built_preview():
            self.export_button.setText("Export built font")
            return

        self.export_button.setText("Build and export")

    def _has_built_preview(self) -> bool:
        return (
            not self._build_dirty
            and self._patch_preview_path is not None
            and self._built_result is not None
        )

    def _set_busy(self, key: str, message: Optional[str]) -> None:
        if message is None:
            self._busy_messages.pop(key, None)
        else:
            self._busy_messages[key] = message

        build_busy = any(
            busy_key in self._busy_messages
            for busy_key in ("preview", "export")
        )
        self.build_progress_bar.setVisible(build_busy)
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
            self._show_message(
                QMessageBox.Icon.Information,
                "No update available",
                f"PTT Font Tool {result.current_version} is the latest release.",
            )
            return

        message = self._message_box(
            QMessageBox.Icon.Information,
            "Update available",
            f"PTT Font Tool {result.latest.version} is available.\n"
            f"You are using {result.current_version}.",
            informative_text="Open the GitHub release page to download it.",
        )
        open_button = message.addButton("Open release", QMessageBox.ButtonRole.AcceptRole)
        not_now_button = message.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
        not_now_button.setObjectName("SecondaryButton")
        message.exec()
        if message.clickedButton() == open_button:
            QDesktopServices.openUrl(QUrl(result.latest.url))

    def _update_failed(self, error: str) -> None:
        self._update_future = None
        self._set_busy("update", None)
        self._set_font_controls_enabled(self._state is not None)
        message = error if error else str(UpdateCheckError("Could not check for updates."))
        self._show_message(QMessageBox.Icon.Warning, "Could not check for updates", message)

    def _show_message(self, icon: QMessageBox.Icon, title: str, text: str) -> None:
        message = self._message_box(icon, title, text)
        message.setStandardButtons(QMessageBox.StandardButton.Ok)
        message.exec()

    def _message_box(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        *,
        informative_text: Optional[str] = None,
    ) -> QMessageBox:
        message = QMessageBox(self)
        message.setOption(QMessageBox.Option.DontUseNativeDialog, True)
        message.setStyleSheet(self.styleSheet())
        message.setIcon(icon)
        message.setWindowTitle(title)
        message.setText(text)
        if informative_text is not None:
            message.setInformativeText(informative_text)
        return message

    def _preview_family_for_path(self, path: Path, *, fallback: str = "monospace") -> str:
        normalized_path = Path(path)
        if normalized_path in self._preview_families:
            return self._preview_families[normalized_path]

        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            return fallback

        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            QFontDatabase.removeApplicationFont(font_id)
            return fallback

        self._preview_font_ids[normalized_path] = font_id
        self._preview_families[normalized_path] = families[0]
        return families[0]

    def _remove_preview_fonts(self) -> None:
        for font_id in self._preview_font_ids.values():
            QFontDatabase.removeApplicationFont(font_id)
        self._preview_font_ids.clear()
        self._preview_families.clear()

    def _apply_preview_font(self, family: str) -> None:
        font = QFont(family)
        font.setPointSize(20)
        self.rendered_preview.setFont(font)

    def _font_row_preview_text_changed(self, text: str) -> None:
        self._set_preview_sample_text(text, source=None)

    def _rendered_preview_text_changed(self) -> None:
        if self._syncing_preview_text:
            return

        self._set_preview_sample_text(self.rendered_preview.toPlainText(), source=self.rendered_preview)

    def _set_preview_sample_text(self, text: str, *, source) -> None:
        if self._syncing_preview_text:
            return

        self._preview_sample_text = text
        self._syncing_preview_text = True
        try:
            if source is not self.rendered_preview and self.rendered_preview.toPlainText() != text:
                self.rendered_preview.setPlainText(text)
            for index in range(self.font_stack_list.count()):
                item = self.font_stack_list.item(index)
                row = self.font_stack_list.itemWidget(item)
                if isinstance(row, FontStackRow):
                    row.set_preview_text(text)
        finally:
            self._syncing_preview_text = False

        self._mark_build_dirty("Preview text changed")

    def _patch_inputs_changed(self, *_args) -> None:
        self._mark_build_dirty("Build settings changed")

    def _strategy_changed(self, *_args) -> None:
        self._update_strategy_help()
        self._patch_inputs_changed()

    def _update_strategy_help(self) -> None:
        if self.fit_radio.isChecked():
            self.strategy_help_label.setText(
                "Fit shrinks oversized glyphs horizontally before centering. "
                "Use it when a font spills outside PTT cells."
            )
            return

        self.strategy_help_label.setText(
            "Center keeps the glyph shape and centers it inside each PTT cell. "
            "This is the best default for most fonts."
        )

    def _mark_build_dirty(self, reason: str) -> None:
        if self._updating_ui or self._state is None:
            return

        self._preview_request_id += 1
        self._patch_preview_path = None
        self._built_result = None
        self._build_dirty = True
        self._export_after_preview = False
        self.patched_radio.setEnabled(False)
        self.preview_status.setText(f"{reason}. Export will rebuild before saving.")
        self.preview_hint_label.setText(
            "Original preview is shown. Build again to inspect the patched font."
        )
        if self.patched_radio.isChecked():
            self.original_radio.setChecked(True)
            self._show_original_preview()
        self._set_font_controls_enabled(True)

    def _preview_mode_changed(self, *_args) -> None:
        if self._updating_ui or self._state is None:
            return

        if self.original_radio.isChecked():
            self._show_original_preview()
            return

        if self.patched_radio.isChecked():
            self._show_patched_preview()

    def _show_original_preview(self) -> None:
        if self._state is None:
            return

        preview_family = self._preview_family_for_path(self._state.metadata.path)
        self._apply_preview_font(preview_family)

    def _show_patched_preview(self) -> None:
        if self._patch_preview_path is None:
            self._refresh_patch_preview()
            return

        preview_family = self._preview_family_for_path(self._patch_preview_path)
        self._apply_preview_font(preview_family)

    def _refresh_patch_preview(self, _checked: bool = False) -> None:
        if self._state is None:
            return

        if not self._font_stack_paths:
            return

        if self._preview_future is not None and not self._preview_future.done():
            return

        self._preview_request_id += 1
        request_id = self._preview_request_id
        output_path = self._patch_preview_output_path()
        self._patch_preview_path = None
        self._built_result = None
        self.patched_radio.setEnabled(False)
        if self._export_after_preview:
            self.preview_status.setText("Building patched preview. Save dialog will open next.")
        else:
            self.preview_status.setText("Building patched preview...")
        self.preview_hint_label.setText(
            "Building the patched font. The preview switches when the build finishes."
        )
        self._set_busy("preview", "Building preview...")
        self._set_font_controls_enabled(True)
        self._preview_future = self._executor.submit(
            build_font_stack,
            tuple(self._font_stack_paths),
            output_path=output_path,
            family_name=self.family_input.text(),
            strategy=self._selected_strategy(),
            sample_text=self._preview_sample_text,
            required_fallback_chars=self._required_fallback_chars(),
            noto=self._noto_text_style,
        )
        self._preview_future.add_done_callback(
            lambda future: self._patch_preview_finished(request_id, future)
        )

    def _patch_preview_finished(
        self,
        request_id: int,
        future: Future,
    ) -> None:
        try:
            result = future.result()
        except Exception as error:
            self._signals.preview_failed.emit((request_id, str(error)))
            return

        self._signals.preview_done.emit((request_id, result))

    def _patch_preview_done(self, payload) -> None:
        request_id, result = payload
        if request_id != self._preview_request_id:
            return

        self._preview_future = None
        self._set_busy("preview", None)
        self._patch_preview_path = result.output_path
        self._built_result = result.patch
        self._build_dirty = False
        if self._state is not None:
            self._state = DesktopFontState(
                metadata=self._state.metadata,
                audit=self._state.audit,
                fallback=result.fallback,
                output_path=self._state.output_path,
                family_name=self._state.family_name,
            )
            self._set_fallback_labels(result.fallback)
        self.patched_radio.setEnabled(True)
        self.preview_status.setText(
            f"{format_patch_preview_status(result.patch.audit)}. Ready to export."
        )
        self.preview_hint_label.setText(
            "Patched preview is shown. Edit sample text and rebuild if you change settings."
        )
        self._set_font_controls_enabled(self._state is not None)

        self.patched_radio.setChecked(True)
        self._show_patched_preview()
        if self._export_after_preview:
            self._export_after_preview = False
            self._export_font()

    def _patch_preview_failed(self, payload) -> None:
        request_id, error = payload
        if request_id != self._preview_request_id:
            return

        self._preview_future = None
        self._set_busy("preview", None)
        self._patch_preview_path = None
        self._built_result = None
        self._build_dirty = True
        self._export_after_preview = False
        self.patched_radio.setEnabled(False)
        self.preview_status.setText(f"Patched preview failed: {error}")
        self.preview_hint_label.setText(
            "Build failed. Fix the font stack or settings, then build again."
        )
        self._set_font_controls_enabled(self._state is not None)
        if self.patched_radio.isChecked():
            self.original_radio.setChecked(True)
            self._show_original_preview()

    def _export_font(self, *_args) -> None:
        if self._state is None:
            return

        if self._export_future is not None and not self._export_future.done():
            return

        if not self._has_built_preview():
            self._export_after_preview = True
            self.preview_status.setText("Building patched preview before export...")
            self.preview_hint_label.setText(
                "Export needs a fresh build. The save dialog opens after the patched font is ready."
            )
            self._refresh_patch_preview()
            self._set_font_controls_enabled(True)
            return

        export_path = self._choose_export_path()
        if export_path is None:
            return

        self._set_busy("export", "Exporting font...")
        self._set_font_controls_enabled(True)
        self.export_button.setEnabled(False)
        self._set_export_status(f"Exporting to {export_path.name}...")
        self._export_future = self._executor.submit(
            _copy_built_font,
            self._patch_preview_path,
            export_path,
            self._built_result,
        )
        self._export_future.add_done_callback(self._export_finished)

    def _choose_export_path(self) -> Optional[Path]:
        if self._state is None:
            return None

        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export built font",
            str(self._state.output_path),
            "Font files (*.ttf *.otf);;All files (*)",
        )
        if not selected_path:
            return None

        target = Path(selected_path).expanduser()
        if target.suffix:
            return target

        fallback_suffix = self._patch_preview_path.suffix if self._patch_preview_path else self._state.output_path.suffix
        return target.with_suffix(fallback_suffix)

    def _export_finished(self, future: Future) -> None:
        try:
            result = future.result()
        except Exception as error:
            self._signals.export_failed.emit(str(error))
            return

        self._signals.export_done.emit(result)

    def _export_done(self, result: PatchedFontState) -> None:
        self._set_export_status(format_export_status(result.output_path, result.audit))
        self._export_future = None
        self._set_busy("export", None)
        self._set_font_controls_enabled(self._state is not None)

    def _export_failed(self, error: str) -> None:
        self._set_export_status(f"Export failed: {error}")
        self._export_future = None
        self._set_busy("export", None)
        self._set_font_controls_enabled(self._state is not None)

    def _selected_strategy(self) -> str:
        if self.fit_radio.isChecked():
            return "fit"

        return "center"

    def _selected_noto_text_style(self) -> NotoTextStyle:
        if self.noto_serif_radio.isChecked():
            return "serif"

        return "sans"

    def _patch_preview_output_path(self) -> Path:
        assert self._state is not None
        source = self._state.metadata.path
        return Path(self._temp_dir.name) / f"{source.stem}-{self._selected_strategy()}-preview{source.suffix}"

    def _required_fallback_chars(self) -> str:
        return "".join(dict.fromkeys(f"{PTT_REQUIRED_SYMBOLS}{self._preview_sample_text}"))

    def _refresh_noto_cache_state(self) -> None:
        self._noto_text_style = self._selected_noto_text_style()
        self._noto_cache_state = noto_cache_state(
            self._noto_text_style,
            cache_dir=self._noto_cache_state.cache_dir,
        )
        self._noto_fallback_paths = self._noto_cache_state.fallback_paths

    def _fallback_fonts_text(self) -> str:
        custom = (
            ", ".join(path.name for path in self._custom_fallback_paths)
            if self._custom_fallback_paths
            else "none"
        )
        available_font_assets = [
            asset for asset in self._noto_cache_state.available_assets
            if asset.is_font
        ]
        missing_font_assets = [
            asset for asset in self._noto_cache_state.missing_assets
            if asset.is_font
        ]
        available = (
            ", ".join(asset.label for asset in available_font_assets)
            if available_font_assets
            else "none"
        )
        missing = (
            ", ".join(asset.label for asset in missing_font_assets)
            if missing_font_assets
            else "none"
        )
        license_missing = any(
            not asset.is_font
            for asset in self._noto_cache_state.missing_assets
        )
        license_status = "missing" if license_missing else "downloaded"
        style = "Serif TC" if self._noto_text_style == "serif" else "Sans TC"
        return "\n".join([
            f"Stack fallbacks: {custom}",
            f"Noto text fallback: {style}",
            f"Noto available fonts: {available}",
            f"Noto missing fonts: {missing}",
            f"Noto license: {license_status}",
        ])

    def _noto_cache_text(self) -> str:
        available_font_assets = [
            asset for asset in self._noto_cache_state.available_assets
            if asset.is_font
        ]
        missing_font_assets = [
            asset for asset in self._noto_cache_state.missing_assets
            if asset.is_font
        ]
        available = (
            ", ".join(asset.label for asset in available_font_assets)
            if available_font_assets
            else "none"
        )
        missing = (
            ", ".join(asset.label for asset in missing_font_assets)
            if missing_font_assets
            else "none"
        )
        license_missing = any(
            not asset.is_font
            for asset in self._noto_cache_state.missing_assets
        )
        license_status = "missing" if license_missing else "downloaded"
        style = "Serif TC" if self._noto_text_style == "serif" else "Sans TC"
        return "\n".join([
            f"Text fallback: {style}",
            f"Available: {available}",
            f"Missing: {missing}",
            f"License: {license_status}",
        ])

    def _set_export_status(self, text: str) -> None:
        self.export_status.setText(text)
        self.export_status.setVisible(bool(text.strip()))

    def closeEvent(self, event) -> None:
        self._remove_preview_fonts()
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._temp_dir.cleanup()
        super().closeEvent(event)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                color: #1f2825;
            }
            QDialog,
            QMessageBox {
                background: #f6f4ef;
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
            QMessageBox QLabel {
                background: transparent;
                color: #1f2825;
                font-size: 14px;
            }
            QMessageBox QLabel#qt_msgbox_informativelabel {
                color: #47524d;
                font-size: 13px;
            }
            QLabel#Title {
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#BuildStatus {
                background: #edf7f4;
                border: 1px solid #8abbb2;
                border-radius: 6px;
                color: #193d37;
                font-weight: 650;
                padding: 7px 8px;
            }
            QLabel#StatusLabel {
                color: #33423d;
                padding-top: 4px;
                padding-bottom: 4px;
            }
            QLabel#PreviewHint {
                color: #47524d;
                font-size: 12px;
                padding: 0 0 4px;
            }
            QLabel#StrategyHelp {
                color: #5b6762;
                font-size: 12px;
                padding: 2px 0 4px;
            }
            QLabel#StackPlaceholder {
                background: #fbf8f1;
                border: 1px dashed #a99f8f;
                border-radius: 8px;
                color: #47524d;
                font-size: 13px;
                font-weight: 600;
                padding: 14px;
            }
            QLabel#ExportHint {
                color: #47524d;
                font-size: 12px;
                padding: 0;
            }
            QWidget#OutputNameStack {
                background: transparent;
            }
            QLabel#FallbackSummary {
                background: #edf7f4;
                border: 1px solid #8abbb2;
                border-radius: 6px;
                color: #193d37;
                padding: 8px;
                font-weight: 650;
            }
            QLabel#StackHandle {
                color: #5b6762;
                font-size: 16px;
                font-weight: 800;
            }
            QLabel#StackFontTitle {
                color: #1f2825;
                font-weight: 750;
            }
            QLabel#StackFontMeta {
                color: #5b6762;
                font-size: 12px;
            }
            QLabel#StackCoverage {
                background: #f3efe6;
                border: 1px solid #d6ccbb;
                border-radius: 5px;
                color: #33423d;
                font-size: 12px;
                font-weight: 600;
                padding: 6px;
            }
            QWidget#LockedFallbackRow {
                background: #fbf8f1;
                border: 1px solid #cfc7b8;
                border-radius: 8px;
            }
            QLabel#LockedFallbackTitle {
                color: #1f2825;
                font-weight: 750;
            }
            QLabel#LockedFallbackMeta {
                color: #5b6762;
                font-size: 12px;
            }
            QScrollArea#SidebarScroll {
                background: transparent;
                border: none;
            }
            QScrollArea#SidebarScroll QWidget#SidebarContent {
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
            QMessageBox QPushButton {
                min-width: 92px;
                padding: 8px 14px;
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
            QPushButton#RemoveButton {
                background: #fff6f3;
                border-color: #d1aca4;
                color: #a13528;
                padding: 0;
                font-size: 18px;
            }
            QListWidget {
                background: #fbf8f1;
                border: 1px dashed #a99f8f;
                border-radius: 8px;
                padding: 6px;
            }
            QListWidget::item {
                border: 1px solid #cfc7b8;
                border-radius: 6px;
                margin: 2px;
            }
            QListWidget::item:selected {
                border-color: #0d7265;
                background: #edf7f4;
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
            QProgressBar#BuildProgress {
                margin: 0 0 2px;
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


def _app_icon() -> QIcon:
    icon_path = Path(__file__).with_name("assets") / "app_icon" / "ptt-font-tool.png"
    if not icon_path.exists():
        return QIcon()

    return QIcon(str(icon_path))
