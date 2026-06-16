from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union

from .profile import TermPttProfile


@dataclass(frozen=True)
class GlyphAudit:
    character: str
    codepoint: int
    glyph_name: Optional[str]
    expected_advance: int
    actual_advance: Optional[int]
    status: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class FontAuditResult:
    path: Path
    units_per_em: int
    checks: Sequence[GlyphAudit]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def failures(self) -> Sequence[GlyphAudit]:
        return [check for check in self.checks if not check.ok]


def audit_font(
    font_path: Union[str, Path],
    *,
    sample_text: Union[str, Iterable[str]],
    profile: Optional[TermPttProfile] = None,
) -> FontAuditResult:
    """Audit glyph advance widths against the Term PTT cell profile."""

    try:
        from fontTools.ttLib import TTFont
    except ImportError as error:
        raise RuntimeError("fonttools is required to audit fonts") from error

    path = Path(font_path)
    font = TTFont(path)
    try:
        units_per_em = int(font["head"].unitsPerEm)
        active_profile = profile or TermPttProfile.from_units_per_em(units_per_em)
        cmap = font.getBestCmap() or {}
        hmtx = font["hmtx"].metrics
        checks = [
            _audit_character(character, cmap, hmtx, active_profile)
            for character in _unique_characters(sample_text)
        ]
        return FontAuditResult(path=path, units_per_em=units_per_em, checks=checks)
    finally:
        font.close()


def _audit_character(character, cmap, hmtx, profile: TermPttProfile) -> GlyphAudit:
    glyph_name = cmap.get(ord(character))
    expected_advance = profile.target_advance(character)

    if glyph_name is None:
        return GlyphAudit(
            character=character,
            codepoint=ord(character),
            glyph_name=None,
            expected_advance=expected_advance,
            actual_advance=None,
            status="missing",
        )

    actual_advance = int(hmtx[glyph_name][0])
    status = "ok" if actual_advance == expected_advance else "mismatch"

    return GlyphAudit(
        character=character,
        codepoint=ord(character),
        glyph_name=glyph_name,
        expected_advance=expected_advance,
        actual_advance=actual_advance,
        status=status,
    )


def _unique_characters(sample_text: Union[str, Iterable[str]]) -> List[str]:
    characters = list(sample_text)
    unique = list(dict.fromkeys(characters))

    for character in unique:
        if len(character) != 1:
            raise ValueError("sample_text must contain single Unicode code points")

    return unique
