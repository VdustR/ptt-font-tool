# Packaging Plan

## Desktop

The desktop app should be distributed as a bundled application. Users should not need to install Python, fontTools, Brotli, or other runtime libraries before using it.

Packaging options to evaluate:

- PyInstaller or Briefcase for a Python-native desktop package.
- Tauri with a Python sidecar if the UI needs stronger native app ergonomics.
- Electron only if the desktop UI needs heavier web-platform integration.

The first desktop milestone should package:

- The GUI.
- The Python font processing runtime.
- All Python dependencies.
- A small built-in preview font sample.

## CLI

The CLI can ship as a Python package first, then later add standalone binaries if needed.

Initial CLI scope:

- `ptt-font patch`
- `--strategy center`
- `--strategy fit`
- `--family-name`
- default `-ptt` output path when `--output` is omitted

Expected release artifacts:

- Source distribution.
- Wheel.
- Optional standalone binaries for macOS, Linux, and Windows.

## Release Automation

Release Please should create release PRs from Conventional Commit history.

Published release assets should eventually include:

- Desktop app bundle.
- CLI artifacts.
- Checksums.
