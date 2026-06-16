# Product

## Register

product

## Users

PTT users, theme authors, font tinkerers, and maintainers who want to adapt local font files for PTT terminal rendering without hand-editing font metrics or installing a Python toolchain.

Users are usually working on their own machine with local font files. They need to inspect whether a font fits PTT's cell model, choose a conversion strategy, preview the result, and export a usable font file.

## Product Purpose

PTT Font Tool adapts existing font files to PTT terminal cell metrics through a desktop app, CLI, and Python library.

The desktop app is the primary user-facing workflow. It should let users open a local font file, preview that font in a PTT-like terminal grid, choose a patch strategy, set the output name, and export a patched font without requiring Python, fontTools, Brotli, or other runtime dependencies to be installed separately.

Success means a user can evaluate and export a PTT-ready font confidently from macOS, Windows, or Linux.

## Brand Personality

Professional, retro terminal, and low-distraction.

The product should feel like a focused utility for people who care about terminal typography. It can carry PTT and terminal flavor, but the UI should stay practical and calm while the font preview carries most of the personality.

## Anti-references

Avoid generic SaaS dashboard styling, decorative terminal gimmicks, marketing-page composition, and over-designed controls that slow down file conversion.

Avoid making the preview feel fake. The preview should use the user's loaded font file whenever possible, not a static screenshot or unrelated fallback font.

## Design Principles

- Make the loaded font the center of the workflow.
- Keep conversion controls direct and reversible.
- Prefer visible evidence over explanation: audit results and preview samples should make issues obvious.
- Design for repeatable local work: opening files, changing strategy, and exporting should stay fast.
- Keep platform behavior familiar across macOS, Windows, and Linux.

## Accessibility & Inclusion

Use clear contrast, keyboard-accessible controls, visible focus states, and reduced-motion-safe interactions.

The app should not rely on color alone to communicate audit status or conversion success. Preview text should be editable so users can test their own language and symbols.
