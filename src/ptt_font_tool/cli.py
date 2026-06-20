from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .audit import FontAuditResult, GlyphAudit, audit_font
from .font_stack import (
    build_font_stack,
    resolve_noto_cache_dir,
    resolve_noto_mode,
)
from .fallback import PTT_REQUIRED_SYMBOLS
from .noto_cache import clear_noto_cache, download_noto_assets, noto_cache_state
from .patch import default_output_path, patch_font


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command in {"audit", "verify"}:
        result = audit_font(args.input, sample_text=args.sample_text)
        print(_format_audit_result(result))
        return 0 if args.command == "audit" or result.ok else 1

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

    if args.command == "build":
        result = build_font_stack(
            args.fonts,
            output_path=args.output,
            family_name=args.family_name,
            sample_text=args.sample_text,
            strategy=args.strategy,
            required_fallback_chars=args.required_fallback_chars or PTT_REQUIRED_SYMBOLS,
            fonts_dir=args.fonts_dir,
            noto=args.noto,
            download_noto=args.download_noto,
        )
        if result.fallback.unresolved:
            print(
                "Warning: "
                f"{len(result.fallback.unresolved)} fallback glyph(s) remain unresolved."
            )
        print(result.output_path)
        return 0

    if args.command == "noto":
        return _run_noto_command(args)

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

    build_parser = subparsers.add_parser(
        "build",
        help="Build a patched font from a primary font and optional fallback font stack.",
    )
    build_parser.add_argument(
        "fonts",
        nargs="+",
        type=Path,
        help="Primary font followed by fallback fonts in priority order.",
    )
    build_parser.add_argument("--output", type=Path)
    build_parser.add_argument("--family-name")
    build_parser.add_argument(
        "--sample-text",
        help="Characters to patch and verify. Defaults to every Unicode character mapped by the font cmap.",
    )
    build_parser.add_argument(
        "--required-fallback-chars",
        default=None,
        help="Characters that should be resolved from fallback fonts before patching.",
    )
    build_parser.add_argument(
        "--strategy",
        choices=["center", "fit"],
        default="center",
        help="center preserves glyph shape and centers it; fit scales oversized glyphs horizontally before centering.",
    )
    build_parser.add_argument(
        "--noto",
        choices=["sans", "serif", "off"],
        help="Noto fallback mode. Defaults to PTT_FONT_TOOL_NOTO_STYLE or sans.",
    )
    build_parser.add_argument(
        "--download-noto",
        action="store_true",
        help="Download missing Noto fallback fonts before building.",
    )
    build_parser.add_argument(
        "--fonts-dir",
        type=Path,
        help="App-managed fonts directory. Noto cache is stored under its noto/ subdirectory.",
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

    noto_parser = subparsers.add_parser(
        "noto",
        help="Manage downloaded Noto fallback fonts.",
    )
    noto_subparsers = noto_parser.add_subparsers(dest="noto_command")
    for name, help_text in (
        ("status", "Report Noto fallback cache status."),
        ("path", "Print the resolved Noto cache directory."),
        ("clear", "Clear downloaded Noto fallback files."),
        ("download", "Download missing Noto fallback files."),
    ):
        subparser = noto_subparsers.add_parser(name, help=help_text)
        _add_noto_common_args(subparser)
        if name == "download":
            subparser.add_argument(
                "--force",
                action="store_true",
                help="Re-download Noto assets even when cached files already exist.",
            )

    return parser


def _add_noto_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--noto",
        choices=["sans", "serif"],
        help="Noto text fallback style. Defaults to PTT_FONT_TOOL_NOTO_STYLE or sans.",
    )
    parser.add_argument(
        "--fonts-dir",
        type=Path,
        help="App-managed fonts directory. Noto cache is stored under its noto/ subdirectory.",
    )


def _run_noto_command(args: argparse.Namespace) -> int:
    if args.noto_command is None:
        raise SystemExit("ptt-font noto requires a subcommand")

    text_style = resolve_noto_mode(args.noto)
    if text_style is None:
        raise SystemExit("ptt-font noto does not support --noto off")

    cache_dir = resolve_noto_cache_dir(args.fonts_dir)
    if args.noto_command == "path":
        print(noto_cache_state(text_style, cache_dir=cache_dir).cache_dir)
        return 0

    if args.noto_command == "clear":
        clear_noto_cache(cache_dir=cache_dir)
        print(noto_cache_state(text_style, cache_dir=cache_dir).cache_dir)
        return 0

    if args.noto_command == "download":
        state = download_noto_assets(
            text_style,
            cache_dir=cache_dir,
            force=args.force,
        )
        print(_format_noto_state(state))
        return 0

    if args.noto_command == "status":
        print(_format_noto_state(noto_cache_state(text_style, cache_dir=cache_dir)))
        return 0

    raise SystemExit(f"unsupported noto command: {args.noto_command}")


def _format_noto_state(state) -> str:
    available = ", ".join(asset.label for asset in state.available_assets) or "none"
    missing = ", ".join(asset.label for asset in state.missing_assets) or "none"
    return (
        f"Noto cache: {state.cache_dir}\n"
        f"Text fallback: {state.text_style}\n"
        f"Available: {available}\n"
        f"Missing: {missing}"
    )


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
