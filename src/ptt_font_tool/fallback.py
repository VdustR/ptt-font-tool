from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence, Union

from .profile import TermPttProfile


PTT_REQUIRED_SYMBOLS = "←→↑↓◎○●◆◇★☆│─█▁▂▃▄▅▆▇【】"


@dataclass(frozen=True)
class MergeGlyphsResult:
    output_path: Path
    added: Sequence[str]
    unresolved: Sequence[str]
    sources: Mapping[str, Path]


def find_missing_glyphs(
    font_path: Union[str, Path],
    required_chars: Union[str, Iterable[str]],
) -> list[str]:
    font = _open_font(font_path)
    try:
        cmap = font.getBestCmap() or {}
        return [
            character
            for character in _unique_characters(required_chars)
            if ord(character) not in cmap
        ]
    finally:
        font.close()


def merge_missing_glyphs(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    *,
    fallback_paths: Sequence[Union[str, Path]],
    required_chars: Union[str, Iterable[str]],
) -> MergeGlyphsResult:
    target_path = Path(input_path)
    with ExitStack() as stack:
        target = _open_managed_font(stack, target_path)
        _validate_glyf_font(target, target_path)
        fallback_fonts = []
        for path in fallback_paths:
            fallback_path = Path(path)
            fallback_font = _open_managed_font(stack, fallback_path)
            _validate_glyf_font(fallback_font, fallback_path)
            fallback_fonts.append((
                fallback_path,
                fallback_font,
                fallback_font.getBestCmap() or {},
            ))

        profile = TermPttProfile.from_units_per_em(int(target["head"].unitsPerEm))
        target_cmap = target.getBestCmap() or {}
        added: list[str] = []
        unresolved: list[str] = []
        sources: dict[str, Path] = {}

        for character in _unique_characters(required_chars):
            if ord(character) in target_cmap:
                continue

            source = _find_fallback_glyph(character, fallback_fonts)
            if source is None:
                unresolved.append(character)
                continue

            source_path, source_font, source_glyph_name = source
            target_glyph_name = _next_glyph_name(target, f"uni{ord(character):04X}")
            _copy_glyf_outline(
                source_font,
                source_glyph_name,
                target,
                target_glyph_name,
                profile.target_advance(character),
            )
            target_cmap[ord(character)] = target_glyph_name
            added.append(character)
            sources[character] = source_path

        _write_unicode_cmaps(target, target_cmap)
        saved_path = Path(output_path)
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        target.save(saved_path)

        return MergeGlyphsResult(
            output_path=saved_path,
            added=added,
            unresolved=unresolved,
            sources=sources,
        )


def _open_font(font_path: Union[str, Path]):
    try:
        from fontTools.ttLib import TTFont
    except ImportError as error:
        raise RuntimeError("fonttools is required to merge fallback glyphs") from error

    return TTFont(Path(font_path))


def _open_managed_font(stack: ExitStack, font_path: Union[str, Path]):
    font = _open_font(font_path)
    stack.callback(font.close)
    return font


def _validate_glyf_font(font, path: Path) -> None:
    if "glyf" not in font:
        raise ValueError(f"fallback glyph merge currently supports TrueType/glyf fonts only: {path}")


def _find_fallback_glyph(character: str, fallback_fonts):
    codepoint = ord(character)
    for path, font, cmap in fallback_fonts:
        glyph_name = cmap.get(codepoint)
        if glyph_name is not None:
            return path, font, glyph_name

    return None


def _copy_glyf_outline(
    source_font,
    source_glyph_name: str,
    target_font,
    target_glyph_name: str,
    target_advance: int,
) -> None:
    from fontTools.misc.transform import Transform
    from fontTools.pens.filterPen import DecomposingFilterPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    source_glyph_set = source_font.getGlyphSet()
    source_bounds = _glyph_bounds(source_glyph_set, source_glyph_name)
    target_glyph_set = target_font.getGlyphSet()
    pen = TTGlyphPen(target_glyph_set)

    if source_bounds is None:
        target_font["glyf"][target_glyph_name] = pen.glyph()
        target_font["hmtx"].metrics[target_glyph_name] = (target_advance, 0)
        _append_glyph_order(target_font, target_glyph_name)
        return

    source_upem = int(source_font["head"].unitsPerEm)
    target_upem = int(target_font["head"].unitsPerEm)
    unit_scale = target_upem / source_upem
    x_min, _, x_max, _ = source_bounds
    outline_width = (x_max - x_min) * unit_scale
    horizontal_scale = min(1.0, target_advance / outline_width) if outline_width else 1.0
    fitted_width = outline_width * horizontal_scale
    scale_x = unit_scale * horizontal_scale
    scale_y = unit_scale
    dx = (target_advance - fitted_width) / 2 - x_min * scale_x

    transform_pen = TransformPen(pen, Transform(scale_x, 0, 0, scale_y, dx, 0))
    decomposing_pen = DecomposingFilterPen(transform_pen, source_glyph_set)
    source_glyph_set[source_glyph_name].draw(decomposing_pen)
    _append_glyph_order(target_font, target_glyph_name)
    target_font["glyf"][target_glyph_name] = pen.glyph()
    target_font["hmtx"].metrics[target_glyph_name] = (
        target_advance,
        round((target_advance - fitted_width) / 2),
    )


def _glyph_bounds(glyph_set, glyph_name: str):
    from fontTools.pens.boundsPen import BoundsPen

    pen = BoundsPen(glyph_set)
    glyph_set[glyph_name].draw(pen)
    return pen.bounds


def _append_glyph_order(font, glyph_name: str) -> None:
    glyph_order = font.getGlyphOrder()
    if glyph_name in glyph_order:
        return

    font.setGlyphOrder([*glyph_order, glyph_name])


def _next_glyph_name(font, base_name: str) -> str:
    glyph_names = set(font.getGlyphOrder())
    if base_name not in glyph_names:
        return base_name

    index = 1
    while f"{base_name}.{index}" in glyph_names:
        index += 1

    return f"{base_name}.{index}"


def _write_unicode_cmaps(font, cmap: Mapping[int, str]) -> None:
    unicode_tables = [
        table
        for table in font["cmap"].tables
        if table.isUnicode()
    ]
    if not unicode_tables:
        raise ValueError("target font has no Unicode cmap table")

    for table in unicode_tables:
        table.cmap = dict(cmap)


def _unique_characters(required_chars: Union[str, Iterable[str]]) -> list[str]:
    characters = list(required_chars)
    unique = list(dict.fromkeys(characters))

    for character in unique:
        if len(character) != 1:
            raise ValueError("required_chars must contain single Unicode code points")

    return unique
