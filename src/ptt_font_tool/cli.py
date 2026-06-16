from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .audit import FontAuditResult, GlyphAudit, audit_font
from .patch import default_output_path, patch_font


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "audit":
        result = audit_font(args.input, sample_text=args.sample_text)
        print(_format_audit_result(result))
        return 0

    if args.command == "verify":
        result = audit_font(args.input, sample_text=args.sample_text)
        print(_format_audit_result(result))
        return 0 if result.ok else 1

    if args.command == "patch":
        output_path = Path(args.output) if args.output else default_output_path(args.input)
        patch_font(
            args.input,
            output_path,
            sample_text=args.sample_text,
            family_name=args.family_name,
            strategy=args.strategy,
        )
        print(output_path)
        return 0

    parser.error("a command is required")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ptt-font",
        description="Adapt fonts to PTT terminal cell metrics.",
    )
    subparsers = parser.add_subparsers(dest="command")

    audit_parser = subparsers.add_parser(
        "audit",
        help="Report font metric differences from PTT terminal cell metrics.",
    )
    audit_parser.add_argument("input", type=Path)
    audit_parser.add_argument(
        "--sample-text",
        help="Characters to audit. Defaults to every Unicode character mapped by the font cmap.",
    )

    patch_parser = subparsers.add_parser(
        "patch",
        help="Patch a font for PTT terminal cell metrics.",
    )
    patch_parser.add_argument("input", type=Path)
    patch_parser.add_argument("--output", type=Path)
    patch_parser.add_argument(
        "--sample-text",
        help="Characters to patch. Defaults to every Unicode character mapped by the font cmap.",
    )
    patch_parser.add_argument("--family-name")
    patch_parser.add_argument(
        "--strategy",
        choices=["center", "fit"],
        default="center",
        help="center preserves glyph shape and centers it; fit scales oversized glyphs horizontally before centering.",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="Exit with failure when a font does not match PTT terminal cell metrics.",
    )
    verify_parser.add_argument("input", type=Path)
    verify_parser.add_argument(
        "--sample-text",
        help="Characters to verify. Defaults to every Unicode character mapped by the font cmap.",
    )

    return parser


def _format_audit_result(result: FontAuditResult) -> str:
    if result.ok:
        return (
            f"OK: {result.path} matches PTT cell metrics "
            f"({len(result.checks)} checks)."
        )

    lines = [
        (
            f"FAIL: {result.path} has {len(result.failures)} issue(s) "
            f"out of {len(result.checks)} checks."
        )
    ]
    lines.extend(_format_audit_failure(failure) for failure in result.failures)
    return "\n".join(lines)


def _format_audit_failure(failure: GlyphAudit) -> str:
    glyph_name = failure.glyph_name or "missing"
    actual_advance = (
        str(failure.actual_advance)
        if failure.actual_advance is not None
        else "missing"
    )
    return (
        f"U+{failure.codepoint:04X} {failure.character!r} "
        f"glyph={glyph_name} "
        f"expected={failure.expected_advance} "
        f"actual={actual_advance} "
        f"status={failure.status}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
