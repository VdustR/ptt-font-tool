from __future__ import annotations

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
    return f"Patched preview: {summary.ok:,}/{summary.total:,} checks OK"


def format_export_status(output_path: Path, summary: AuditSummary) -> str:
    return "\n".join([
        "Exported:",
        str(output_path),
        f"Verified: {summary.ok:,}/{summary.total:,} checks OK.",
    ])


def format_fallback_status(status: FallbackStatus) -> str:
    if not status.layers:
        return "PTT fallback glyphs are covered."

    lines = [_format_fallback_layer(layer) for layer in status.layers]
    if status.unresolved:
        count = len(status.unresolved)
        noun = "glyph is" if count == 1 else "glyphs are"
        lines.append(
            f"Warning: {count:,} PTT {noun} still missing after all fallback fonts."
        )

    return "\n".join(lines)


def _format_fallback_layer(layer: FallbackLayerStatus) -> str:
    missing_count = len(layer.missing_after)
    missing = "✓ 0 missing" if missing_count == 0 else f"{missing_count:,} missing"
    if layer.added:
        return f"{layer.label}: {missing}, adds {len(layer.added):,}"

    return f"{layer.label}: {missing}"


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
