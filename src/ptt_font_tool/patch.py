from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
class PatchMetricsResult:
    input_path: Path
    output_path: Path
    units_per_em: int
    patched_glyphs: Sequence[PatchedGlyph]
    skipped_glyphs: Sequence[SkippedGlyph]


def patch_font_metrics(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    *,
    sample_text: Union[str, Iterable[str]],
    profile: Optional[TermPttProfile] = None,
) -> PatchMetricsResult:
    """Patch glyph advance widths to match the Term PTT cell profile."""

    try:
        from fontTools.ttLib import TTFont
    except ImportError as error:
        raise RuntimeError("fonttools is required to patch fonts") from error

    source_path = Path(input_path)
    target_path = Path(output_path)
    font = TTFont(source_path)

    try:
        units_per_em = int(font["head"].unitsPerEm)
        active_profile = profile or TermPttProfile.from_units_per_em(units_per_em)
        cmap = font.getBestCmap() or {}
        hmtx = font["hmtx"].metrics
        patched: List[PatchedGlyph] = []
        skipped: List[SkippedGlyph] = []

        for character in _unique_characters(sample_text):
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
            hmtx[glyph_name] = (new_advance, old_left_side_bearing)

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

        target_path.parent.mkdir(parents=True, exist_ok=True)
        font.save(target_path)

        return PatchMetricsResult(
            input_path=source_path,
            output_path=target_path,
            units_per_em=units_per_em,
            patched_glyphs=patched,
            skipped_glyphs=skipped,
        )
    finally:
        font.close()


def _unique_characters(sample_text: Union[str, Iterable[str]]) -> List[str]:
    characters = list(sample_text)
    unique = list(dict.fromkeys(characters))

    for character in unique:
        if len(character) != 1:
            raise ValueError("sample_text must contain single Unicode code points")

    return unique
