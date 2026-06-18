# Desktop MVP

## Goal

Build a cross-platform desktop app for adapting local fonts to PTT terminal cell metrics.

The MVP should run on macOS, Windows, and Linux. Users should be able to open a local font file, preview it in a PTT-like terminal grid, choose a patch strategy, and export a patched font without installing Python or runtime dependencies manually.

## Primary Workflow

1. Open a local font file.
2. Inspect the font metadata and audit summary.
3. Preview the original font in a PTT cell grid.
4. Choose a patch strategy.
5. Preview the patched result.
6. Choose an output path and family name.
7. Export the patched font.
8. Verify the exported font.

## Layout

```text
+------------------------------------------------------------------+
| PTT Font Tool                                      Open Font...   |
+------------------------------+-----------------------------------+
| Font                          | Preview Text                      |
| Family: Lithue 1.1            | [A漢A ㄅㄆㄇ PTT 文章列表 │─█]    |
| Format: OTF / CFF             |                                   |
| Units per em: 1000            | Preview                           |
| Glyphs checked: 18,432        | +-------------------------------+ |
|                              | | PTT-like terminal cell grid     | |
| Audit                         | | rendered with loaded font       | |
| Missing: 0                    | | and patched preview font        | |
| Mismatched: 324               | +-------------------------------+ |
|                              |                                   |
| Strategy                      | Output                            |
| (x) Center                    | Family: [Lithue 1.1 PTT       ]  |
| ( ) Fit                       | Path:   [lithue-1.1-ptt.otf  ]  |
|                              |                         Export   |
+------------------------------+-----------------------------------+
```

## Preview Requirements

The preview must use the font selected by the user.

For the original font preview:

- Load the selected local font into the application font database.
- Apply that loaded family to the preview widget.
- Do not require system-wide font installation.

For the patched preview:

- Patch the font into a temporary file.
- Load the temporary patched font into the application font database.
- Render the preview with the patched family.
- Remove stale temporary application fonts when the selected file, strategy, or family name changes.

The preview should show evidence of PTT cell behavior:

- Half-width characters occupying one cell.
- CJK, full-width, wide, and ambiguous-width characters occupying two cells.
- A visible cell grid or ruler.
- At least one mixed-width sample line.
- Editable preview text.

The preview does not need to perfectly match Chrome or term.ptt.cc rendering. It should make width and alignment problems visible before export.

## Strategy Behavior

`center`:

- Preserve glyph shape and size.
- Set the expected PTT advance width.
- Center the glyph inside its target cell width.
- Allow visual overflow or overlap.

`fit`:

- Set the expected PTT advance width.
- Horizontally shrink glyphs only when they exceed the target width.
- Center the glyph after scaling.

## Output Behavior

Default output path:

- Same directory as the input font.
- Same base name with `-ptt` appended before the extension.

Default family name:

- Original family name with ` PTT` appended.

Users can edit both the output path and family name before export.

## Error States

The MVP should handle:

- Unsupported or unreadable font files.
- Fonts that can be audited but not outline-patched.
- Output path write failures.
- Empty or duplicate family names.
- Verification failures after export.

Errors should state what failed and what the user can do next.

## Cross-Platform Direction

Use a Python-native desktop UI first, with PySide6 as the leading candidate.

Reasons:

- The core font logic is already Python.
- The GUI can call the library directly.
- Application-local font loading supports previewing local fonts without installing them system-wide.
- The same codebase can be packaged for macOS, Windows, and Linux.

Packaging should be validated per platform. The build process should not assume cross-compilation.

## Milestones

### 1. Local Prototype

- Add a minimal desktop entrypoint.
- Open a font file.
- Load the font into the app-local font database.
- Render editable preview text with that font.
- Run audit and display a summary.

### 2. Patch Preview

- Generate a patched temporary font.
- Load the patched temporary font.
- Toggle original and patched preview.
- Update preview when strategy or family name changes.

### 3. Export Flow

- Add output path and family name controls.
- Export patched font.
- Run verify after export.
- Show success or failure state.

### 4. Platform Packaging

- Package a macOS app locally first.
- Add Windows and Linux packaging in CI or platform-specific runners.
- Attach desktop artifacts and checksums to releases.

## Verification

Desktop changes should be verified with:

- Unit tests for reusable preview or export state logic.
- Manual app launch on the current platform.
- Opening at least one known OTF font.
- Previewing original and patched output.
- Exporting and verifying a patched font.
- A smoke package build before release packaging is considered ready.
