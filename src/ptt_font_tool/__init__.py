"""Font tools for term.ptt.cc terminal cell metrics."""

from .audit import FontAuditResult, GlyphAudit, audit_font
from .font_stack import (
    ENV_FALLBACK_FONTS,
    ENV_FONTS_DIR,
    ENV_NOTO_STYLE,
    FontStack,
    FontStackBuildResult,
    ResolvedFontStack,
    build_font_stack,
    resolve_font_stack,
    resolve_fonts_dir,
    resolve_noto_cache_dir,
    resolve_noto_mode,
    resolve_stack_for_build,
)
from .patch import (
    PatchFontResult,
    PatchedGlyph,
    SkippedGlyph,
    default_output_path,
    patch_font,
)
from .profile import TermPttProfile

__all__ = [
    "FontAuditResult",
    "ENV_FALLBACK_FONTS",
    "ENV_FONTS_DIR",
    "ENV_NOTO_STYLE",
    "FontStack",
    "FontStackBuildResult",
    "GlyphAudit",
    "PatchFontResult",
    "PatchedGlyph",
    "ResolvedFontStack",
    "SkippedGlyph",
    "TermPttProfile",
    "audit_font",
    "build_font_stack",
    "default_output_path",
    "patch_font",
    "resolve_font_stack",
    "resolve_fonts_dir",
    "resolve_noto_cache_dir",
    "resolve_noto_mode",
    "resolve_stack_for_build",
]
