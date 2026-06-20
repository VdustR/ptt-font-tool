import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ptt_font_tool.desktop_model import AuditSummary, FallbackStatus, PatchedFontState
from ptt_font_tool.font_stack import (
    ENV_FALLBACK_FONTS,
    ENV_FONTS_DIR,
    ENV_NOTO_STYLE,
    build_font_stack,
    resolve_font_stack,
    resolve_fonts_dir,
    resolve_noto_cache_dir,
    resolve_noto_mode,
    resolve_stack_for_build,
)


class FontStackTest(unittest.TestCase):
    def test_resolve_font_stack_uses_env_fallbacks_when_only_primary_is_explicit(self):
        primary = Path("primary.ttf")
        fallback_one = Path("fallback-one.ttf")
        fallback_two = Path("fallback-two.ttf")

        stack = resolve_font_stack(
            [primary],
            env={ENV_FALLBACK_FONTS: os.pathsep.join([str(fallback_one), str(fallback_two)])},
        )

        self.assertEqual(stack.primary_path, primary)
        self.assertEqual(stack.fallback_paths, (fallback_one, fallback_two))

    def test_resolve_font_stack_prefers_explicit_fallbacks_over_env_fallbacks(self):
        primary = Path("primary.ttf")
        explicit = Path("explicit.ttf")
        env_fallback = Path("env.ttf")

        stack = resolve_font_stack(
            [primary, explicit],
            env={ENV_FALLBACK_FONTS: str(env_fallback)},
        )

        self.assertEqual(stack.paths, (primary, explicit))

    def test_resolve_fonts_dir_prefers_explicit_value_then_env(self):
        explicit = Path("~/explicit-fonts")
        env_value = "/tmp/env-fonts"

        self.assertEqual(
            resolve_fonts_dir(explicit, env={ENV_FONTS_DIR: env_value}),
            explicit.expanduser(),
        )
        self.assertEqual(
            resolve_fonts_dir(None, env={ENV_FONTS_DIR: env_value}),
            Path(env_value),
        )

    def test_resolve_noto_cache_dir_places_noto_under_fonts_dir(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            self.assertEqual(resolve_noto_cache_dir(root, env={}), root / "noto")

    def test_resolve_noto_mode_prefers_explicit_value_then_env(self):
        self.assertEqual(resolve_noto_mode("sans", env={ENV_NOTO_STYLE: "serif"}), "sans")
        self.assertEqual(resolve_noto_mode(None, env={ENV_NOTO_STYLE: "serif"}), "serif")
        self.assertIsNone(resolve_noto_mode(None, env={ENV_NOTO_STYLE: "off"}))

    def test_resolve_stack_for_build_adds_cached_noto_paths_after_fallbacks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary = root / "primary.ttf"
            fallback = root / "fallback.ttf"
            noto_font = root / "fonts" / "noto" / "NotoSansSymbols2-Regular.ttf"
            noto_font.parent.mkdir(parents=True)
            noto_font.write_bytes(b"cached")

            resolved = resolve_stack_for_build(
                [primary, fallback],
                fonts_dir=root / "fonts",
                noto="sans",
                env={},
            )

        self.assertEqual(resolved.stack.paths, (primary, fallback))
        self.assertEqual(resolved.noto_cache_dir, root / "fonts" / "noto")
        self.assertEqual(resolved.fallback_paths, (fallback, noto_font))

    def test_build_font_stack_requires_a_primary_font(self):
        with self.assertRaisesRegex(ValueError, "at least one font path is required"):
            build_font_stack([], noto="off")

    def test_build_font_stack_forwards_sample_text_to_patch(self):
        fallback = FallbackStatus(
            missing=[],
            custom_resolved=[],
            noto_resolved=[],
            unresolved=[],
            layers=[],
        )
        patched = PatchedFontState(
            output_path=Path("output.ttf"),
            audit=AuditSummary(total=1, ok=1, missing=0, mismatch=0),
            fallback_added=[],
            fallback_unresolved=[],
        )

        with (
            patch("ptt_font_tool.font_stack.build_fallback_status", return_value=fallback),
            patch("ptt_font_tool.font_stack.export_patched_font", return_value=patched) as export,
        ):
            build_font_stack(
                [Path("primary.ttf")],
                output_path=Path("output.ttf"),
                family_name="Primary PTT",
                sample_text="A漢",
                noto="off",
            )

        self.assertEqual(export.call_args.kwargs["sample_text"], "A漢")


if __name__ == "__main__":
    unittest.main()
