from __future__ import annotations

from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True)
class TermPttProfile:
    half_advance: int
    ambiguous_as_wide: bool = True

    @classmethod
    def from_units_per_em(cls, units_per_em: int) -> "TermPttProfile":
        return cls(half_advance=round(units_per_em / 2))

    @property
    def full_advance(self) -> int:
        return self.half_advance * 2

    def cell_width(self, character: str) -> int:
        _validate_single_character(character)
        east_asian_width = unicodedata.east_asian_width(character)

        if east_asian_width in {"F", "W"}:
            return 2

        if east_asian_width == "A" and self.ambiguous_as_wide:
            return 2

        return 1

    def target_advance(self, character: str) -> int:
        return self.half_advance * self.cell_width(character)


def _validate_single_character(character: str) -> None:
    if len(character) != 1:
        raise ValueError("expected exactly one Unicode code point")
