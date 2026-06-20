from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .desktop_model import AuditSummary, FallbackLayerStatus, FallbackStatus, FontMetadata


DEFAULT_PREVIEW_TEXT = "\n".join([
    "A漢A ㄅㄆㄇ PTT 文章列表 │─█",
    "導覽 ←→↑↓ 票數 ◎○● 標記 ◆◇★☆ 括號 【】",
    "區塊 ▁▂▃▄▅▆▇ ASCII red yellow blue / 中文寬度測試",
])


def desktop_dependency_message() -> str:
    return "PySide6 is required for the desktop app. Install it with: pip install -e .[desktop]"


def format_font_details(metadata: FontMetadata) -> str:
    return "\n".join([
        f"Family: {metadata.family_name}",
        f"Style: {metadata.style_name}",
        f"Format: {metadata.format}",
        f"Units per em: {metadata.units_per_em}",
        f"Glyphs mapped: {metadata.glyph_count:,}",
    ])


def format_audit_summary(summary: AuditSummary) -> str:
    return "\n".join([
        f"Checked: {summary.total:,}",
        f"OK: {summary.ok:,}",
        f"Missing: {summary.missing:,}",
        f"Mismatched: {summary.mismatch:,}",
    ])


def format_patch_preview_status(summary: AuditSummary) -> str:
    return f"Built font: {summary.ok:,}/{summary.total:,} checks OK"


def format_export_status(output_path: Path, summary: AuditSummary) -> str:
    return "\n".join([
        "Exported:",
        str(output_path),
        f"Verified: {summary.ok:,}/{summary.total:,} checks OK.",
    ])


@dataclass(frozen=True)
class UnavailableFallbackLayer:
    label: str
    reason: str


def format_fallback_summary(
    status: FallbackStatus,
    *,
    unavailable_layers: Sequence[UnavailableFallbackLayer] = (),
) -> str:
    if unavailable_layers and status.unresolved:
        count = len(status.unresolved)
        noun = "glyph" if count == 1 else "glyphs"
        verb = "needs" if count == 1 else "need"
        return (
            f"{count:,} PTT {noun} still {verb} Noto fallback. "
            "Download Noto to continue the coverage check."
        )

    if status.unresolved:
        count = len(status.unresolved)
        noun = "glyph is" if count == 1 else "glyphs are"
        return f"Warning: {count:,} PTT {noun} still missing after all fallback fonts."

    return "All required PTT glyphs are covered."


def format_fallback_status(
    status: FallbackStatus,
    *,
    unavailable_layers: Sequence[UnavailableFallbackLayer] = (),
) -> str:
    if not status.layers:
        return format_fallback_summary(status, unavailable_layers=unavailable_layers)

    lines = [
        _format_fallback_layer(index, layer)
        for index, layer in enumerate(status.layers, start=1)
    ]
    next_index = len(lines) + 1
    for offset, layer in enumerate(unavailable_layers):
        lines.append(_format_unavailable_fallback_layer(next_index + offset, layer))

    return "\n".join(lines)


def _format_fallback_layer(index: int, layer: FallbackLayerStatus) -> str:
    missing_count = len(layer.missing_after)
    missing = "0 missing" if missing_count == 0 else f"{missing_count:,} missing"
    prefix = f"{index}. {layer.label}"
    if layer.added:
        return f"{prefix}: adds {len(layer.added):,}, {missing} after this layer"

    if layer.kind == "primary":
        return f"{prefix}: {missing} after input font"

    return f"{prefix}: adds 0, {missing} after this layer"


def _format_unavailable_fallback_layer(index: int, layer: UnavailableFallbackLayer) -> str:
    return f"{index}. {layer.label}: needs download ({layer.reason})"


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        from ._qt_desktop import run
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith("PySide6"):
            print(desktop_dependency_message())
            return 1
        raise

    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
