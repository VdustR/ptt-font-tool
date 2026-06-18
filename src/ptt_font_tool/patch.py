from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, List, Optional, Sequence, Union

from .profile import TermPttProfile


@dataclass(frozen=True)
class PatchedGlyph:
    character: str
    codepoint: int
    glyph_name: str
    old_advance: int
    new_advance: int


@dataclass(frozen=True)
class SkippedGlyph:
    character: str
    codepoint: int
    reason: str


@dataclass(frozen=True)
class PatchFontResult:
    input_path: Path
    output_path: Path
    units_per_em: int
    patched_glyphs: Sequence[PatchedGlyph]
    skipped_glyphs: Sequence[SkippedGlyph]


def default_output_path(input_path: Union[str, Path]) -> Path:
    path = Path(input_path)
    return path.with_name(f"{path.stem}-ptt{path.suffix}")


def patch_font(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    *,
    sample_text: Optional[Union[str, Iterable[str]]] = None,
    family_name: Optional[str] = None,
    profile: Optional[TermPttProfile] = None,
    strategy: str = "center",
) -> PatchFontResult:
    """Patch a font to match the Term PTT cell profile."""

    try:
        from fontTools.ttLib import TTFont
    except ImportError as error:
        raise RuntimeError("fonttools is required to patch fonts") from error

    source_path = Path(input_path)
    target_path = Path(output_path) if output_path is not None else default_output_path(source_path)
    _validate_strategy(strategy)
    font = TTFont(source_path)

    try:
        units_per_em = int(font["head"].unitsPerEm)
        active_profile = profile or TermPttProfile.from_units_per_em(units_per_em)
        cmap = font.getBestCmap() or {}
        hmtx = font["hmtx"].metrics
        patched: List[PatchedGlyph] = []
        skipped: List[SkippedGlyph] = []
        glyph_target_advances = {}

        for character in _target_characters(sample_text, cmap):
            glyph_name = cmap.get(ord(character))
            if glyph_name is None:
                skipped.append(
                    SkippedGlyph(
                        character=character,
                        codepoint=ord(character),
                        reason="missing",
                    )
                )
                continue

            old_advance, old_left_side_bearing = hmtx[glyph_name]
            new_advance = active_profile.target_advance(character)
            glyph_target_advance = max(
                new_advance,
                glyph_target_advances.get(glyph_name, 0),
            )
            glyph_target_advances[glyph_name] = glyph_target_advance
            hmtx[glyph_name] = (glyph_target_advance, old_left_side_bearing)

            if old_advance != new_advance:
                patched.append(
                    PatchedGlyph(
                        character=character,
                        codepoint=ord(character),
                        glyph_name=glyph_name,
                        old_advance=int(old_advance),
                        new_advance=new_advance,
                    )
                )

        _patch_ligature_glyph_advances(font, glyph_target_advances)
        _remove_pair_positioning(font)
        _fit_glyphs(font, glyph_target_advances, strategy)
        _rename_font(font, family_name or _default_family_name(font))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        font.save(target_path)

        return PatchFontResult(
            input_path=source_path,
            output_path=target_path,
            units_per_em=units_per_em,
            patched_glyphs=patched,
            skipped_glyphs=skipped,
        )
    finally:
        font.close()


def _validate_strategy(strategy: str) -> None:
    if strategy not in {"center", "fit"}:
        raise ValueError("strategy must be 'center' or 'fit'")


def _patch_ligature_glyph_advances(font, glyph_target_advances) -> None:
    if "GSUB" not in font or not glyph_target_advances:
        return

    hmtx = font["hmtx"].metrics
    for first_glyph, ligatures in _gsub_ligature_sets(font):
        for ligature in ligatures:
            component_glyphs = [first_glyph, *ligature.Component]
            component_advances = []
            for glyph_name in component_glyphs:
                advance = glyph_target_advances.get(glyph_name)
                if advance is None:
                    glyph_metrics = hmtx.get(glyph_name)
                    if glyph_metrics is None:
                        component_advances = []
                        break

                    advance = glyph_metrics[0]

                component_advances.append(advance)

            if not component_advances:
                continue

            target_advance = sum(component_advances)
            if target_advance <= 0:
                continue

            _, old_left_side_bearing = hmtx.get(
                ligature.LigGlyph,
                (target_advance, 0),
            )
            glyph_target_advances[ligature.LigGlyph] = max(
                target_advance,
                glyph_target_advances.get(ligature.LigGlyph, 0),
            )
            hmtx[ligature.LigGlyph] = (
                glyph_target_advances[ligature.LigGlyph],
                old_left_side_bearing,
            )


def _gsub_ligature_sets(font):
    gsub = font["GSUB"].table
    lookup_list = getattr(gsub, "LookupList", None)
    if lookup_list is None:
        return

    for lookup in lookup_list.Lookup:
        if lookup.LookupType != 4:
            continue

        for subtable in lookup.SubTable:
            for first_glyph, ligatures in getattr(subtable, "ligatures", {}).items():
                yield first_glyph, ligatures


def _remove_pair_positioning(font) -> None:
    if "GPOS" not in font:
        return

    gpos = font["GPOS"].table
    lookup_list = getattr(gpos, "LookupList", None)
    if lookup_list is None:
        return

    old_lookups = list(lookup_list.Lookup)
    removed_lookup_indices = {
        index
        for index, lookup in enumerate(old_lookups)
        if lookup.LookupType == 2
    }
    if not removed_lookup_indices:
        return

    index_map = {}
    new_lookups = []
    for index, lookup in enumerate(old_lookups):
        if index in removed_lookup_indices:
            continue

        index_map[index] = len(new_lookups)
        new_lookups.append(lookup)

    feature_index_map = _remove_empty_gpos_features(gpos, index_map)
    if not new_lookups or not feature_index_map:
        del font["GPOS"]
        return

    lookup_list.Lookup = new_lookups
    lookup_list.LookupCount = len(new_lookups)
    _remap_gpos_script_features(gpos, feature_index_map)


def _remove_empty_gpos_features(gpos, lookup_index_map) -> dict[int, int]:
    feature_list = getattr(gpos, "FeatureList", None)
    if feature_list is None:
        return {}

    feature_index_map = {}
    new_feature_records = []
    for feature_index, feature_record in enumerate(feature_list.FeatureRecord):
        new_lookup_indices = [
            lookup_index_map[index]
            for index in feature_record.Feature.LookupListIndex
            if index in lookup_index_map
        ]
        if not new_lookup_indices:
            continue

        feature_record.Feature.LookupListIndex = new_lookup_indices
        feature_record.Feature.LookupCount = len(new_lookup_indices)
        feature_index_map[feature_index] = len(new_feature_records)
        new_feature_records.append(feature_record)

    feature_list.FeatureRecord = new_feature_records
    feature_list.FeatureCount = len(new_feature_records)
    return feature_index_map


def _remap_gpos_script_features(gpos, feature_index_map: dict[int, int]) -> None:
    script_list = getattr(gpos, "ScriptList", None)
    if script_list is None:
        return

    for script_record in script_list.ScriptRecord:
        script = script_record.Script
        default_lang_sys = getattr(script, "DefaultLangSys", None)
        if default_lang_sys is not None:
            _remap_lang_sys_features(default_lang_sys, feature_index_map)

        for lang_sys_record in getattr(script, "LangSysRecord", []):
            _remap_lang_sys_features(lang_sys_record.LangSys, feature_index_map)


def _remap_lang_sys_features(lang_sys, feature_index_map: dict[int, int]) -> None:
    lang_sys.FeatureIndex = [
        feature_index_map[index]
        for index in lang_sys.FeatureIndex
        if index in feature_index_map
    ]
    lang_sys.FeatureCount = len(lang_sys.FeatureIndex)

    if lang_sys.ReqFeatureIndex == 0xFFFF:
        return

    lang_sys.ReqFeatureIndex = feature_index_map.get(
        lang_sys.ReqFeatureIndex,
        0xFFFF,
    )


def _fit_glyphs(font, glyph_target_advances, strategy: str) -> None:
    if not glyph_target_advances:
        return

    if "glyf" in font:
        _fit_glyf_glyphs(font, glyph_target_advances, strategy)
        return

    if "CFF " in font:
        _fit_cff_glyphs(font, glyph_target_advances, strategy)
        return


def _fit_glyf_glyphs(font, glyph_target_advances, strategy: str) -> None:
    from fontTools.misc.transform import Transform
    from fontTools.pens.filterPen import DecomposingFilterPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    glyf = font["glyf"]
    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"].metrics
    transformed_glyphs = {}
    transformed_metrics = {}

    for glyph_name, target_advance in glyph_target_advances.items():
        if glyph_name not in glyf:
            continue

        bounds = _glyph_bounds(glyph_set, glyph_name)
        if bounds is None:
            transformed_metrics[glyph_name] = (target_advance, 0)
            continue

        x_min, _, x_max, _ = bounds
        outline_width = x_max - x_min
        if outline_width <= 0:
            transformed_metrics[glyph_name] = (target_advance, 0)
            continue

        scale_x = _horizontal_scale(outline_width, target_advance, strategy)
        fitted_width = outline_width * scale_x
        dx = (target_advance - fitted_width) / 2 - x_min * scale_x

        pen = TTGlyphPen(glyph_set)
        transform_pen = TransformPen(pen, Transform(scale_x, 0, 0, 1, dx, 0))
        decomposing_pen = DecomposingFilterPen(transform_pen, glyph_set)
        glyph_set[glyph_name].draw(decomposing_pen)
        transformed_glyphs[glyph_name] = pen.glyph()
        transformed_metrics[glyph_name] = (
            target_advance,
            round((target_advance - fitted_width) / 2),
        )

    for glyph_name, glyph in transformed_glyphs.items():
        glyf[glyph_name] = glyph

    for glyph_name, metrics in transformed_metrics.items():
        hmtx[glyph_name] = metrics


def _fit_cff_glyphs(font, glyph_target_advances, strategy: str) -> None:
    from fontTools.misc.transform import Transform
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.pens.transformPen import TransformPen

    cff = font["CFF "].cff
    top_dict = cff.topDictIndex[0]
    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"].metrics

    for glyph_name, target_advance in glyph_target_advances.items():
        if glyph_name not in top_dict.CharStrings:
            continue

        bounds = _glyph_bounds(glyph_set, glyph_name)
        if bounds is None:
            hmtx[glyph_name] = (target_advance, 0)
            continue

        x_min, _, x_max, _ = bounds
        outline_width = x_max - x_min
        if outline_width <= 0:
            hmtx[glyph_name] = (target_advance, 0)
            continue

        scale_x = _horizontal_scale(outline_width, target_advance, strategy)
        fitted_width = outline_width * scale_x
        dx = (target_advance - fitted_width) / 2 - x_min * scale_x
        char_string = top_dict.CharStrings[glyph_name]
        private = getattr(char_string, "private", None)
        pen = T2CharStringPen(width=target_advance, glyphSet=glyph_set)
        transform_pen = TransformPen(pen, Transform(scale_x, 0, 0, 1, dx, 0))
        glyph_set[glyph_name].draw(transform_pen)
        top_dict.CharStrings[glyph_name] = pen.getCharString(
            private=private,
            globalSubrs=cff.GlobalSubrs,
        )
        hmtx[glyph_name] = (target_advance, round((target_advance - fitted_width) / 2))


def _glyph_bounds(glyph_set, glyph_name: str):
    from fontTools.pens.boundsPen import BoundsPen

    pen = BoundsPen(glyph_set)
    glyph_set[glyph_name].draw(pen)
    return pen.bounds


def _horizontal_scale(outline_width: float, target_advance: int, strategy: str) -> float:
    if strategy == "fit":
        return min(1.0, target_advance / outline_width)

    return 1.0


def _default_family_name(font) -> str:
    current_family_name = font["name"].getDebugName(1) or "PTT Font"
    return f"{current_family_name} PTT"


def _rename_font(font, family_name: str) -> None:
    name_table = font["name"]
    style_name = name_table.getDebugName(2) or "Regular"
    full_name = f"{family_name} {style_name}".strip()
    postscript_name = _postscript_name(family_name, style_name)

    replacements = {
        1: family_name,
        4: full_name,
        6: postscript_name,
        16: family_name,
    }

    for record in name_table.names:
        if record.nameID not in replacements:
            continue

        encoding = record.getEncoding()
        if encoding is None:
            continue

        record.string = replacements[record.nameID].encode(
            encoding,
            errors="replace",
        )


def _postscript_name(family_name: str, style_name: str) -> str:
    normalized_family = re.sub(r"[^A-Za-z0-9]", "", family_name)
    normalized_style = re.sub(r"[^A-Za-z0-9]", "", style_name) or "Regular"
    return f"{normalized_family}-{normalized_style}"[:63]


def _unique_characters(sample_text: Union[str, Iterable[str]]) -> List[str]:
    characters = list(sample_text)
    unique = list(dict.fromkeys(characters))

    for character in unique:
        if len(character) != 1:
            raise ValueError("sample_text must contain single Unicode code points")

    return unique


def _target_characters(
    sample_text: Optional[Union[str, Iterable[str]]],
    cmap,
) -> List[str]:
    if sample_text is not None:
        return _unique_characters(sample_text)

    return [chr(codepoint) for codepoint in sorted(cmap)]
