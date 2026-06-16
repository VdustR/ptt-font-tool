# PTT Font Tool

Desktop, CLI, and library tools for adapting fonts to term.ptt.cc terminal cell metrics.

## Desktop

The desktop app is planned as the primary user-facing workflow.

Goals:

- Open a local font file.
- Preview whether the font follows term.ptt.cc terminal cell metrics.
- Process the font into a PTT-friendly local output.
- Export patched font files without requiring users to install Python, fontTools, Brotli, or other runtime dependencies.

The desktop build should bundle all required runtime dependencies so users can download and run the app directly.

## CLI

The CLI is planned for repeatable local workflows and automation.

Planned commands:

```bash
ptt-font audit input.otf
ptt-font patch input.otf --output output.otf
ptt-font verify output.otf
```

## Library

The Python library contains the reusable core for the desktop app and CLI.

Current modules:

- `ptt_font_tool.profile`: maps Unicode characters to Term PTT cell widths.
- `ptt_font_tool.audit`: reads a font and reports whether glyph advance widths match the Term PTT profile.
- `ptt_font_tool.patch`: patches glyph advance widths to match the Term PTT profile.

## Font Width Model

term.ptt.cc uses terminal-style 2:1 cell metrics:

- ASCII and halfwidth characters use one cell.
- CJK, fullwidth, wide, and East Asian ambiguous characters use two cells.
- For a 1000 UPEM font, one cell is expected to be 500 font units and two cells are expected to be 1000 font units.
- For a 1200 UPEM font, one cell is expected to be 600 font units and two cells are expected to be 1200 font units.

The default profile uses Python's Unicode East Asian Width data and treats ambiguous-width characters as wide for term.ptt.cc.

## Current Limits

- `patch_font_metrics` changes horizontal advance metrics only.
- Proportional CFF fonts may also need outline fitting so wide Latin outlines do not visually overlap after their advances are compressed to half-width cells.
- CFF outline fitting is currently a local proof of concept and has not been promoted into the library API yet.

## Development

Create an isolated Python environment and install the package:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Run tests:

```bash
python -m unittest discover -s tests
```

## Release Plan

This repository is planned to use Release Please for versioning and release automation.

Release artifacts should eventually include:

- CLI package artifacts.
- Desktop app bundles with runtime dependencies included.
- Checksums for downloadable artifacts.

## License And Font Rights

This project is licensed under MIT.

Input fonts remain under their original licenses. Generated fonts may only be used or distributed according to the input font license. This tool does not grant redistribution rights for third-party fonts.
