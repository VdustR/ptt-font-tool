# Fallback Glyphs

## Goal

Some fonts do not include PTT-heavy symbols such as arrows, circles, box drawing characters, or block elements. When those glyphs are missing, the browser or terminal renderer falls back to another system font. The result can look visually inconsistent even when the main font metrics are correct.

Fallback glyph support should let PTT Font Tool copy missing glyphs from an ordered fallback chain into the output font.

## Ordered Fallback Chain

The fallback chain is ordered:

```text
input font
-> user fallback 1
-> user fallback 2
-> ...
-> downloaded Noto Sans Symbols 2
-> downloaded Noto Sans TC or Noto Serif TC
```

Rules:

- The input font always has highest priority.
- Existing glyphs in the input font are not overwritten.
- User fallback fonts are tried in the order selected by the user.
- Downloaded Noto fallback fonts are always last and act as a safety net.
- The first fallback font that contains a missing glyph provides that glyph.
- If a glyph is still missing after the full chain, export remains allowed but the UI must keep a warning visible.
- If Noto has not been downloaded yet, the fallback ledger should show the missing Noto layer inline instead of opening a modal.

## Noto Cache Management

The desktop app downloads Noto fallback fonts into an app-managed cache directory. It does not install fonts system-wide.

The UI should support:

- Downloading the selected Noto fallback set.
- Re-downloading the selected set.
- Clearing downloaded Noto files.
- Opening the cache directory.
- Choosing `Noto Sans TC` or `Noto Serif TC` as the text fallback.

The shared library resolves configuration in this order:

```text
explicit API / CLI arguments
-> environment variables
-> OS-specific defaults
```

When `fonts_dir` is provided, Noto files are stored under `fonts_dir/noto`. When `fonts_dir` is omitted, the existing OS-specific Noto cache directory is used.

Environment variables:

- `PTT_FONT_TOOL_FONTS_DIR`
- `PTT_FONT_TOOL_NOTO_STYLE`
- `PTT_FONT_TOOL_FALLBACK_FONTS`

## Default Noto Choices

Symbols:

- `Noto Sans Symbols 2`

Text fallback:

- `Noto Sans TC`
- `Noto Serif TC`

Symbols do not have a serif-specific default. The Sans / Serif choice affects text fallback, not symbol fallback.

## Required PTT Glyph Set

The initial required set should include:

```text
←→↑↓◎○●◆◇★☆│─█▁▂▃▄▅▆▇【】
```

This list is intentionally small for the first implementation. It should grow from real PTT screenshots and user reports.

## Merge Pipeline

Recommended export pipeline:

```text
input font
-> merge missing glyphs from fallback chain
-> patch PTT metrics and outlines
-> verify output
```

Merging before patching lets newly copied fallback glyphs go through the same PTT cell fitting logic as the original glyphs.

## License Requirements

Noto fonts are licensed under the SIL Open Font License 1.1.

When downloaded Noto glyphs are used:

- Download the Noto OFL license into the app cache with the selected fonts.
- Do not name the generated font as a Noto font.
- Keep generated font family names based on the input font, such as `SentyWatermelon PTT`.
- Generate or display license notes that mention the input font, user fallbacks, and downloaded Noto fallbacks.

Custom fallback fonts have unknown license terms. The app should warn users that generated fonts remain subject to the input font and fallback font licenses.

## Current PoC Limits

The first merge implementation supports TrueType `glyf` fonts only.

Unsupported cases should fail clearly:

- CFF-based OTF target fonts.
- CFF-based OTF fallback fonts.
- Variable or color font behavior that has not been compatibility tested.

The desktop UI should present unsupported fallback merge as a warning, not silently produce a broken font.
