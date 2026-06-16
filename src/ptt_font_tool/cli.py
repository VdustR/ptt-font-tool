from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .patch import default_output_path, patch_font


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

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

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
