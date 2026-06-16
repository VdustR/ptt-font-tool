from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Optional, Sequence, Union

from .audit import FontAuditResult, audit_font
from .fallback import PTT_REQUIRED_SYMBOLS, find_missing_glyphs, merge_missing_glyphs
from .patch import default_output_path, patch_font


@dataclass(frozen=True)
class FontMetadata:
    path: Path
    family_name: str
    style_name: str
    format: str
    units_per_em: int
    glyph_count: int


@dataclass(frozen=True)
class AuditSummary:
    total: int
    ok: int
    missing: int
    mismatch: int


@dataclass(frozen=True)
class FallbackLayerStatus:
    label: str
    kind: str
    path: Path
    added: Sequence[str]
    missing_after: Sequence[str]


@dataclass(frozen=True)
class FallbackStatus:
    missing: Sequence[str]
    custom_resolved: Sequence[str]
    noto_resolved: Sequence[str]
    unresolved: Sequence[str]
    layers: Sequence[FallbackLayerStatus]


@dataclass(frozen=True)
class DesktopFontState:
    metadata: FontMetadata
    audit: AuditSummary
    fallback: FallbackStatus
    output_path: Path
    family_name: str


@dataclass(frozen=True)
class PatchedFontState:
    output_path: Path
    audit: AuditSummary
    fallback_added: Sequence[str]
    fallback_unresolved: Sequence[str]


def inspect_font(font_path: Union[str, Path]) -> FontMetadata:
    try:
        from fontTools.ttLib import TTFont
    except ImportError as error:
        raise RuntimeError("fonttools is required to inspect fonts") from error

    path = Path(font_path)
    font = TTFont(path)
    try:
        cmap = font.getBestCmap() or {}
        return FontMetadata(
            path=path,
            family_name=_font_name(font, 16, 1, fallback="Unknown Font"),
            style_name=_font_name(font, 17, 2, fallback="Regular"),
            format=_font_format(font),
            units_per_em=int(font["head"].unitsPerEm),
            glyph_count=len(cmap),
        )
    finally:
        font.close()


def create_font_state(
    font_path: Union[str, Path],
    *,
    sample_text: Optional[str] = None,
    custom_fallback_paths: Sequence[Union[str, Path]] = (),
    noto_fallback_paths: Sequence[Union[str, Path]] = (),
) -> DesktopFontState:
    metadata = inspect_font(font_path)
    audit = summarize_audit(audit_font(font_path, sample_text=sample_text))
    fallback = build_fallback_status(
        font_path,
        custom_fallback_paths=custom_fallback_paths,
        noto_fallback_paths=noto_fallback_paths,
    )
    return DesktopFontState(
        metadata=metadata,
        audit=audit,
        fallback=fallback,
        output_path=default_output_path(metadata.path),
        family_name=f"{metadata.family_name} PTT",
    )


def summarize_audit(result: FontAuditResult) -> AuditSummary:
    missing = sum(1 for check in result.checks if check.status == "missing")
    mismatch = sum(1 for check in result.checks if check.status == "mismatch")
    ok = sum(1 for check in result.checks if check.ok)
    return AuditSummary(
        total=len(result.checks),
        ok=ok,
        missing=missing,
        mismatch=mismatch,
    )


def create_patch_preview(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    *,
    family_name: str,
    strategy: str,
    sample_text: str,
    fallback_paths: Sequence[Union[str, Path]] = (),
) -> PatchedFontState:
    return _patch_and_audit(
        input_path,
        output_path,
        family_name=family_name,
        strategy=strategy,
        sample_text=sample_text,
        fallback_paths=fallback_paths,
        required_fallback_chars=sample_text,
    )


def export_patched_font(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    *,
    family_name: str,
    strategy: str,
    fallback_paths: Sequence[Union[str, Path]] = (),
    required_fallback_chars: Union[str, Sequence[str]] = PTT_REQUIRED_SYMBOLS,
) -> PatchedFontState:
    return _patch_and_audit(
        input_path,
        output_path,
        family_name=family_name,
        strategy=strategy,
        sample_text=None,
        fallback_paths=fallback_paths,
        required_fallback_chars=required_fallback_chars,
    )


def _patch_and_audit(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    *,
    family_name: str,
    strategy: str,
    sample_text: Optional[str],
    fallback_paths: Sequence[Union[str, Path]],
    required_fallback_chars: Union[str, Sequence[str]],
) -> PatchedFontState:
    normalized_family_name = family_name.strip()
    if not normalized_family_name:
        raise ValueError("family name is required")

    target_path = Path(output_path)
    patch_input_path = Path(input_path)
    fallback_added: Sequence[str] = []
    fallback_unresolved: Sequence[str] = []

    missing_fallback_chars = find_missing_glyphs(patch_input_path, required_fallback_chars)
    if fallback_paths and missing_fallback_chars:
        with tempfile.TemporaryDirectory(prefix="ptt-font-tool-fallback-") as directory:
            merged_path = Path(directory) / patch_input_path.name
            merge_result = merge_missing_glyphs(
                patch_input_path,
                merged_path,
                fallback_paths=fallback_paths,
                required_chars=missing_fallback_chars,
            )
            patch_font(
                merge_result.output_path,
                target_path,
                sample_text=sample_text,
                family_name=normalized_family_name,
                strategy=strategy,
            )
            audit = summarize_audit(audit_font(target_path, sample_text=sample_text))
            return PatchedFontState(
                output_path=target_path,
                audit=audit,
                fallback_added=merge_result.added,
                fallback_unresolved=merge_result.unresolved,
            )

    patch_font(
        patch_input_path,
        target_path,
        sample_text=sample_text,
        family_name=normalized_family_name,
        strategy=strategy,
    )
    audit = summarize_audit(audit_font(target_path, sample_text=sample_text))
    return PatchedFontState(
        output_path=target_path,
        audit=audit,
        fallback_added=fallback_added,
        fallback_unresolved=fallback_unresolved,
    )


def build_fallback_status(
    input_path: Union[str, Path],
    *,
    required_chars: Union[str, Sequence[str]] = PTT_REQUIRED_SYMBOLS,
    custom_fallback_paths: Sequence[Union[str, Path]] = (),
    noto_fallback_paths: Sequence[Union[str, Path]] = (),
) -> FallbackStatus:
    path = Path(input_path)
    missing = find_missing_glyphs(path, required_chars)
    custom_layers, remaining_after_custom = _fallback_layers_for_paths(
        missing,
        custom_fallback_paths,
        kind="custom",
    )
    custom_resolved = _flatten_added(custom_layers)
    noto_layers, unresolved = _fallback_layers_for_paths(
        remaining_after_custom,
        noto_fallback_paths,
        kind="noto",
    )
    noto_resolved = _flatten_added(noto_layers)

    return FallbackStatus(
        missing=missing,
        custom_resolved=custom_resolved,
        noto_resolved=noto_resolved,
        unresolved=unresolved,
        layers=[
            FallbackLayerStatus(
                label=path.name,
                kind="primary",
                path=path,
                added=[],
                missing_after=missing,
            ),
            *custom_layers,
            *noto_layers,
        ],
    )


def _fallback_layers_for_paths(
    initial_missing: Sequence[str],
    fallback_paths: Sequence[Union[str, Path]],
    *,
    kind: str,
) -> tuple[list[FallbackLayerStatus], list[str]]:
    unresolved = list(initial_missing)
    layers: list[FallbackLayerStatus] = []

    for fallback_path in fallback_paths:
        path = Path(fallback_path)
        if not unresolved:
            layers.append(
                FallbackLayerStatus(
                    label=path.name,
                    kind=kind,
                    path=path,
                    added=[],
                    missing_after=[],
                )
            )
            continue

        missing_from_fallback = set(find_missing_glyphs(path, unresolved))
        newly_resolved = [
            character
            for character in unresolved
            if character not in missing_from_fallback
        ]
        unresolved = [
            character
            for character in unresolved
            if character in missing_from_fallback
        ]
        layers.append(
            FallbackLayerStatus(
                label=path.name,
                kind=kind,
                path=path,
                added=newly_resolved,
                missing_after=unresolved,
            )
        )

    return layers, unresolved


def _flatten_added(layers: Sequence[FallbackLayerStatus]) -> list[str]:
    return [
        character
        for layer in layers
        for character in layer.added
    ]


def _font_format(font) -> str:
    if "glyf" in font:
        return "TrueType/glyf"

    if "CFF " in font:
        return "OpenType/CFF"

    if "CFF2" in font:
        return "OpenType/CFF2"

    return "OpenType"


def _font_name(font, *name_ids: int, fallback: str) -> str:
    for name_id in name_ids:
        name = font["name"].getDebugName(name_id)
        if name:
            return name

    return fallback
