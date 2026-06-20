from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import ssl
from typing import Any, Callable, Literal, Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen


NotoTextStyle = Literal["sans", "serif"]

GOOGLE_FONTS_RAW_BASE_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl"
APP_CACHE_DIR_NAME = "ptt-font-tool"
NOTO_CACHE_DIR_NAME = "noto"


@dataclass(frozen=True)
class NotoAsset:
    key: str
    label: str
    filename: str
    url: str
    is_font: bool = True


@dataclass(frozen=True)
class NotoCacheState:
    cache_dir: Path
    text_style: NotoTextStyle
    assets: Sequence[NotoAsset]
    available_assets: Sequence[NotoAsset]
    missing_assets: Sequence[NotoAsset]

    @property
    def complete(self) -> bool:
        return not self.missing_assets

    @property
    def has_cached_files(self) -> bool:
        return any((self.cache_dir / asset.filename).exists() for asset in ALL_NOTO_ASSETS)

    @property
    def fallback_paths(self) -> list[Path]:
        return [
            self.cache_dir / asset.filename
            for asset in self.assets
            if asset.is_font and (self.cache_dir / asset.filename).exists()
        ]


SYMBOLS_ASSET = NotoAsset(
    key="symbols",
    label="Noto Sans Symbols 2",
    filename="NotoSansSymbols2-Regular.ttf",
    url=f"{GOOGLE_FONTS_RAW_BASE_URL}/notosanssymbols2/NotoSansSymbols2-Regular.ttf",
)
SANS_TC_ASSET = NotoAsset(
    key="sans-tc",
    label="Noto Sans TC",
    filename="NotoSansTC-VariableFont_wght.ttf",
    url=f"{GOOGLE_FONTS_RAW_BASE_URL}/notosanstc/NotoSansTC%5Bwght%5D.ttf",
)
SERIF_TC_ASSET = NotoAsset(
    key="serif-tc",
    label="Noto Serif TC",
    filename="NotoSerifTC-VariableFont_wght.ttf",
    url=f"{GOOGLE_FONTS_RAW_BASE_URL}/notoseriftc/NotoSerifTC%5Bwght%5D.ttf",
)
LICENSE_ASSET = NotoAsset(
    key="ofl",
    label="SIL Open Font License 1.1",
    filename="OFL.txt",
    url=f"{GOOGLE_FONTS_RAW_BASE_URL}/notosanstc/OFL.txt",
    is_font=False,
)
ALL_NOTO_ASSETS = (
    SYMBOLS_ASSET,
    SANS_TC_ASSET,
    SERIF_TC_ASSET,
    LICENSE_ASSET,
)


class NotoCacheError(RuntimeError):
    pass


def _certifi_ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()

    return ssl.create_default_context(cafile=certifi.where())


def default_noto_cache_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "PTT Font Tool" / NOTO_CACHE_DIR_NAME
        return Path.home() / "AppData" / "Local" / "PTT Font Tool" / NOTO_CACHE_DIR_NAME

    if sys_platform() == "darwin":
        return Path.home() / "Library" / "Caches" / "PTT Font Tool" / NOTO_CACHE_DIR_NAME

    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        return Path(base) / APP_CACHE_DIR_NAME / NOTO_CACHE_DIR_NAME
    return Path.home() / ".cache" / APP_CACHE_DIR_NAME / NOTO_CACHE_DIR_NAME


def sys_platform() -> str:
    import sys

    return sys.platform


def selected_noto_assets(text_style: NotoTextStyle) -> tuple[NotoAsset, NotoAsset, NotoAsset]:
    return (
        SYMBOLS_ASSET,
        _text_asset(text_style),
        LICENSE_ASSET,
    )


def noto_cache_state(
    text_style: NotoTextStyle,
    *,
    cache_dir: Path | None = None,
) -> NotoCacheState:
    active_cache_dir = cache_dir or default_noto_cache_dir()
    assets = selected_noto_assets(text_style)
    available = [
        asset for asset in assets
        if (active_cache_dir / asset.filename).exists()
    ]
    missing = [
        asset for asset in assets
        if not (active_cache_dir / asset.filename).exists()
    ]
    return NotoCacheState(
        cache_dir=active_cache_dir,
        text_style=text_style,
        assets=assets,
        available_assets=available,
        missing_assets=missing,
    )


def download_noto_assets(
    text_style: NotoTextStyle,
    *,
    cache_dir: Path | None = None,
    force: bool = False,
    opener: Callable[..., Any] = urlopen,
    ssl_context_factory: Callable[[], ssl.SSLContext] = _certifi_ssl_context,
    timeout: int = 30,
) -> NotoCacheState:
    active_cache_dir = cache_dir or default_noto_cache_dir()
    active_cache_dir.mkdir(parents=True, exist_ok=True)

    for asset in selected_noto_assets(text_style):
        destination = active_cache_dir / asset.filename
        if destination.exists() and not force:
            continue
        _download_asset(
            asset,
            destination,
            opener=opener,
            ssl_context_factory=ssl_context_factory,
            timeout=timeout,
        )

    return noto_cache_state(text_style, cache_dir=active_cache_dir)


def clear_noto_cache(*, cache_dir: Path | None = None) -> None:
    active_cache_dir = cache_dir or default_noto_cache_dir()
    active_cache_dir.mkdir(parents=True, exist_ok=True)
    for asset in ALL_NOTO_ASSETS:
        (active_cache_dir / asset.filename).unlink(missing_ok=True)
        (active_cache_dir / f"{asset.filename}.download").unlink(missing_ok=True)


def _download_asset(
    asset: NotoAsset,
    destination: Path,
    *,
    opener: Callable[..., Any],
    ssl_context_factory: Callable[[], ssl.SSLContext],
    timeout: int,
) -> None:
    request = Request(
        asset.url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "ptt-font-tool",
        },
    )
    temporary_path = destination.with_name(f"{destination.name}.download")
    try:
        with opener(request, timeout=timeout, context=ssl_context_factory()) as response:
            with temporary_path.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
        temporary_path.replace(destination)
    except Exception as error:
        temporary_path.unlink(missing_ok=True)
        if _contains_ssl_certificate_error(error):
            raise NotoCacheError(
                "Could not verify the TLS certificate while downloading Noto fonts."
            ) from error
        raise NotoCacheError(f"Could not download {asset.label}: {error}") from error


def _contains_ssl_certificate_error(error: BaseException) -> bool:
    seen: set[int] = set()
    pending: list[BaseException] = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        if isinstance(current, URLError) and isinstance(current.reason, BaseException):
            pending.append(current.reason)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)

    return False


def _text_asset(text_style: NotoTextStyle) -> NotoAsset:
    if text_style == "sans":
        return SANS_TC_ASSET
    if text_style == "serif":
        return SERIF_TC_ASSET
    raise ValueError(f"unsupported Noto text fallback style: {text_style}")
