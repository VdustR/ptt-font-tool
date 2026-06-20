from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
import json
import re
import ssl
from typing import Any, Callable, Optional
from urllib.request import Request, urlopen


LATEST_RELEASE_API_URL = "https://api.github.com/repos/VdustR/ptt-font-tool/releases/latest"
PACKAGE_NAME = "ptt-font-tool"


@dataclass(frozen=True)
class ReleaseInfo:
    tag_name: str
    version: str
    name: str
    url: str


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest: ReleaseInfo
    update_available: bool


class UpdateCheckError(RuntimeError):
    pass


def current_package_version() -> str:
    try:
        return importlib.metadata.version(PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError as error:
        raise UpdateCheckError("Could not determine the installed PTT Font Tool version.") from error


def _certifi_ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()

    return ssl.create_default_context(cafile=certifi.where())


def check_for_update(
    *,
    current_version: Optional[str] = None,
    opener: Callable[..., Any] = urlopen,
    ssl_context_factory: Callable[[], ssl.SSLContext] = _certifi_ssl_context,
    timeout: int = 8,
    api_url: str = LATEST_RELEASE_API_URL,
) -> UpdateCheckResult:
    active_version = current_version or current_package_version()
    request = Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"ptt-font-tool/{active_version}",
        },
    )

    try:
        with opener(request, timeout=timeout, context=ssl_context_factory()) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except ssl.SSLCertVerificationError as error:
        raise UpdateCheckError(
            "Could not verify GitHub's TLS certificate while checking for updates. "
            "Please download updates from GitHub Releases and report this issue if it persists."
        ) from error
    except Exception as error:
        raise UpdateCheckError(f"Could not check for updates: {error}") from error

    latest = parse_latest_release(payload)
    return UpdateCheckResult(
        current_version=active_version,
        latest=latest,
        update_available=is_newer_release(latest.tag_name, active_version),
    )


def parse_latest_release(payload: dict[str, Any]) -> ReleaseInfo:
    if payload.get("draft") or payload.get("prerelease"):
        raise UpdateCheckError("Latest release is not a stable published release.")

    tag_name = _required_string(payload, "tag_name")
    url = _required_string(payload, "html_url")
    version = _release_version(tag_name)
    if version is None:
        raise UpdateCheckError(f"Could not parse release version from tag: {tag_name}")

    name = payload.get("name")
    return ReleaseInfo(
        tag_name=tag_name,
        version=version,
        name=name if isinstance(name, str) and name else tag_name,
        url=url,
    )


def is_newer_release(release_tag: str, current_version: str) -> bool:
    release_version = _release_version(release_tag)
    current = _version_parts(current_version)
    if release_version is None or current is None:
        return False

    latest = _version_parts(release_version)
    return latest is not None and latest > current


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise UpdateCheckError(f"GitHub release payload is missing `{key}`.")

    return value


def _release_version(tag_name: str) -> Optional[str]:
    match = re.fullmatch(r"(?:ptt-font-tool-)?v?(\d+(?:\.\d+){0,2})(?:[+-].*)?", tag_name)
    if match is None:
        return None

    return match.group(1)


def _version_parts(version: str) -> Optional[tuple[int, int, int]]:
    match = re.fullmatch(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[+-].*)?", version)
    if match is None:
        return None

    return tuple(int(part or "0") for part in match.groups())
