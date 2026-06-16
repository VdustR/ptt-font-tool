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
-> bundled Noto Sans Symbols 2
-> bundled Noto Sans TC or Noto Serif TC
```

Rules:

- The input font always has highest priority.
- Existing glyphs in the input font are not overwritten.
- User fallback fonts are tried in the order selected by the user.
- Noto fallback fonts are always last and act as a safety net.
- The first fallback font that contains a missing glyph provides that glyph.
- If a glyph is still missing after the full chain, export remains allowed but the UI must keep a warning visible.

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

When bundled Noto glyphs are used:

- Bundle the Noto OFL license with the app.
- Do not name the generated font as a Noto font.
- Keep generated font family names based on the input font, such as `SentyWatermelon PTT`.
- Generate or display license notes that mention the input font, user fallbacks, and bundled Noto fallbacks.

Custom fallback fonts have unknown license terms. The app should warn users that generated fonts remain subject to the input font and fallback font licenses.

## Current PoC Limits

The first merge implementation supports TrueType `glyf` fonts only.

Unsupported cases should fail clearly:

- CFF-based OTF target fonts.
- CFF-based OTF fallback fonts.
- Variable or color font behavior that has not been compatibility tested.

The desktop UI should present unsupported fallback merge as a warning, not silently produce a broken font.
