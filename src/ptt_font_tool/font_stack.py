from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

from .desktop_model import (
    FallbackStatus,
    PatchedFontState,
    build_fallback_status,
    export_patched_font,
    inspect_font,
)
from .fallback import PTT_REQUIRED_SYMBOLS
from .noto_cache import (
    NOTO_CACHE_DIR_NAME,
    NotoCacheState,
    NotoTextStyle,
    download_noto_assets,
    noto_cache_state,
)
from .patch import default_output_path


ENV_FONTS_DIR = "PTT_FONT_TOOL_FONTS_DIR"
ENV_FALLBACK_FONTS = "PTT_FONT_TOOL_FALLBACK_FONTS"
ENV_NOTO_STYLE = "PTT_FONT_TOOL_NOTO_STYLE"

NotoMode = Union[NotoTextStyle, None]


@dataclass(frozen=True)
class FontStack:
    paths: tuple[Path, ...]

    @property
    def primary_path(self) -> Path:
        return self.paths[0]

    @property
    def fallback_paths(self) -> tuple[Path, ...]:
        return self.paths[1:]


@dataclass(frozen=True)
class ResolvedFontStack:
    stack: FontStack
    fonts_dir: Optional[Path]
    noto_cache_dir: Optional[Path]
    noto_cache: Optional[NotoCacheState]
    fallback_paths: tuple[Path, ...]


@dataclass(frozen=True)
class FontStackBuildResult:
    output_path: Path
    patch: PatchedFontState
    fallback: FallbackStatus
    resolved_stack: ResolvedFontStack


def resolve_fonts_dir(
    fonts_dir: Optional[Union[str, Path]] = None,
    *,
    env: Mapping[str, str] = os.environ,
) -> Optional[Path]:
    value = str(fonts_dir) if fonts_dir is not None else env.get(ENV_FONTS_DIR)
    if not value:
        return None
    return Path(value).expanduser()


def resolve_noto_cache_dir(
    fonts_dir: Optional[Union[str, Path]] = None,
    *,
    env: Mapping[str, str] = os.environ,
) -> Optional[Path]:
    resolved_fonts_dir = resolve_fonts_dir(fonts_dir, env=env)
    if resolved_fonts_dir is None:
        return None
    return resolved_fonts_dir / NOTO_CACHE_DIR_NAME


def resolve_noto_mode(
    noto: Optional[str] = None,
    *,
    env: Mapping[str, str] = os.environ,
    default: str = "sans",
) -> NotoMode:
    value = (noto or env.get(ENV_NOTO_STYLE) or default).strip().lower()
    if value in {"off", "none", "false", "0"}:
        return None
    if value in {"sans", "serif"}:
        return value
    raise ValueError("noto must be 'sans', 'serif', or 'off'")


def parse_path_list(value: Optional[str]) -> tuple[Path, ...]:
    if not value:
        return ()
    return tuple(
        Path(part).expanduser()
        for part in value.split(os.pathsep)
        if part
    )


def resolve_font_stack(
    font_paths: Sequence[Union[str, Path]],
    *,
    env: Mapping[str, str] = os.environ,
) -> FontStack:
    if not font_paths:
        raise ValueError("at least one font path is required")

    explicit_paths = tuple(Path(path).expanduser() for path in font_paths)
    if len(explicit_paths) > 1:
        return FontStack(paths=explicit_paths)

    env_fallback_paths = parse_path_list(env.get(ENV_FALLBACK_FONTS))
    return FontStack(paths=(*explicit_paths, *env_fallback_paths))


def resolve_stack_for_build(
    font_paths: Sequence[Union[str, Path]],
    *,
    fonts_dir: Optional[Union[str, Path]] = None,
    noto: Optional[str] = None,
    download_noto: bool = False,
    env: Mapping[str, str] = os.environ,
) -> ResolvedFontStack:
    stack = resolve_font_stack(font_paths, env=env)
    active_fonts_dir = resolve_fonts_dir(fonts_dir, env=env)
    noto_mode = resolve_noto_mode(noto, env=env)

    if noto_mode is None:
        return ResolvedFontStack(
            stack=stack,
            fonts_dir=active_fonts_dir,
            noto_cache_dir=None,
            noto_cache=None,
            fallback_paths=stack.fallback_paths,
        )

    noto_cache_dir = resolve_noto_cache_dir(fonts_dir, env=env)
    state = (
        download_noto_assets(noto_mode, cache_dir=noto_cache_dir)
        if download_noto
        else noto_cache_state(noto_mode, cache_dir=noto_cache_dir)
    )
    return ResolvedFontStack(
        stack=stack,
        fonts_dir=active_fonts_dir,
        noto_cache_dir=state.cache_dir,
        noto_cache=state,
        fallback_paths=(*stack.fallback_paths, *state.fallback_paths),
    )


def build_font_stack(
    font_paths: Sequence[Union[str, Path]],
    *,
    output_path: Optional[Union[str, Path]] = None,
    family_name: Optional[str] = None,
    strategy: str = "center",
    sample_text: Optional[str] = None,
    required_fallback_chars: Union[str, Sequence[str]] = PTT_REQUIRED_SYMBOLS,
    fonts_dir: Optional[Union[str, Path]] = None,
    noto: Optional[str] = None,
    download_noto: bool = False,
    env: Mapping[str, str] = os.environ,
) -> FontStackBuildResult:
    resolved = resolve_stack_for_build(
        font_paths,
        fonts_dir=fonts_dir,
        noto=noto,
        download_noto=download_noto,
        env=env,
    )
    output = Path(output_path).expanduser() if output_path is not None else default_output_path(resolved.stack.primary_path)
    fallback = build_fallback_status(
        resolved.stack.primary_path,
        required_chars=required_fallback_chars,
        custom_fallback_paths=resolved.stack.fallback_paths,
        noto_fallback_paths=resolved.noto_cache.fallback_paths if resolved.noto_cache is not None else (),
    )
    active_family_name = (
        family_name
        if family_name is not None
        else f"{inspect_font(resolved.stack.primary_path).family_name} PTT"
    )
    patch = export_patched_font(
        resolved.stack.primary_path,
        output,
        family_name=active_family_name,
        strategy=strategy,
        sample_text=sample_text,
        fallback_paths=resolved.fallback_paths,
        required_fallback_chars=required_fallback_chars,
    )
    return FontStackBuildResult(
        output_path=patch.output_path,
        patch=patch,
        fallback=fallback,
        resolved_stack=resolved,
    )
