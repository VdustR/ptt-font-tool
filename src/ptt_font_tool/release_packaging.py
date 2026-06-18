from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Optional, Sequence


APP_DISPLAY_NAME = "PTT Font Tool"
SUPPORTED_PLATFORMS = {"linux", "macos", "windows"}


def desktop_release_artifact_name(
    *,
    release: str,
    target_platform: str,
    arch: str,
) -> str:
    suffix = ".tar.gz" if target_platform == "linux" else ".zip"
    return f"{_normalize_release_name(release)}-{target_platform}-{arch}{suffix}"


def desktop_bundle_path(dist_dir: Path, *, target_platform: str) -> Path:
    if target_platform == "macos":
        return dist_dir / f"{APP_DISPLAY_NAME}.app"

    return dist_dir / APP_DISPLAY_NAME


def build_pyinstaller_command(
    *,
    entry_script: Path,
    dist_dir: Path,
    work_dir: Path,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_DISPLAY_NAME,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(work_dir),
        "--collect-data",
        "ptt_font_tool",
        str(entry_script),
    ]


def build_desktop_bundle(
    *,
    entry_script: Path,
    dist_dir: Path,
    work_dir: Path,
) -> None:
    command = build_pyinstaller_command(
        entry_script=entry_script,
        dist_dir=dist_dir,
        work_dir=work_dir,
    )
    subprocess.run(command, check=True)


def package_desktop_bundle(
    *,
    dist_dir: Path,
    output_dir: Path,
    release: str,
    target_platform: str,
    arch: str,
) -> tuple[Path, Path]:
    _validate_target_platform(target_platform)
    bundle_path = desktop_bundle_path(dist_dir, target_platform=target_platform)
    if not bundle_path.exists():
        raise FileNotFoundError(f"Desktop bundle not found: {bundle_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / desktop_release_artifact_name(
        release=release,
        target_platform=target_platform,
        arch=arch,
    )

    if target_platform == "linux":
        _write_tar_gz(bundle_path, artifact_path)
    elif target_platform == "macos" and shutil.which("ditto"):
        _write_macos_zip(bundle_path, artifact_path)
    else:
        _write_zip(bundle_path, artifact_path)

    checksum_path = write_sha256_file(artifact_path)
    return artifact_path, checksum_path


def write_sha256_file(artifact_path: Path) -> Path:
    digest = _sha256_digest(artifact_path)
    checksum_path = artifact_path.with_name(f"{artifact_path.name}.sha256")
    checksum_path.write_text(f"{digest}  {artifact_path.name}\n", encoding="utf-8")
    return checksum_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    _validate_target_platform(args.target_platform)

    repo_root = args.repo_root.resolve()
    entry_script = args.entry_script.resolve()
    dist_dir = args.dist_dir.resolve()
    work_dir = args.work_dir.resolve()
    output_dir = args.output_dir.resolve()

    if args.clean:
        shutil.rmtree(dist_dir, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)

    build_desktop_bundle(
        entry_script=entry_script,
        dist_dir=dist_dir,
        work_dir=work_dir,
    )
    artifact_path, checksum_path = package_desktop_bundle(
        dist_dir=dist_dir,
        output_dir=output_dir,
        release=args.release,
        target_platform=args.target_platform,
        arch=args.arch,
    )

    print(f"Packaged desktop release asset: {artifact_path.relative_to(repo_root)}")
    print(f"Wrote checksum: {checksum_path.relative_to(repo_root)}")
    return 0


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build desktop release artifacts.")
    parser.add_argument("--release", required=True, help="Release version or tag.")
    parser.add_argument(
        "--target-platform",
        required=True,
        choices=sorted(SUPPORTED_PLATFORMS),
        help="Release artifact platform label.",
    )
    parser.add_argument("--arch", required=True, help="Release artifact architecture label.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root used for default paths and status output.",
    )
    parser.add_argument(
        "--entry-script",
        type=Path,
        default=Path.cwd() / "scripts" / "ptt_font_desktop_entry.py",
        help="PyInstaller desktop entry script.",
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=Path.cwd() / "build" / "pyinstaller-dist",
        help="PyInstaller dist directory.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path.cwd() / "build" / "pyinstaller-work",
        help="PyInstaller work and spec directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "build" / "release-assets",
        help="Directory for packaged release assets.",
    )
    parser.add_argument(
        "--no-clean",
        action="store_false",
        dest="clean",
        help="Reuse existing PyInstaller and release asset directories.",
    )
    parser.set_defaults(clean=True)
    return parser.parse_args(argv)


def _normalize_release_name(release: str) -> str:
    if release.startswith("ptt-font-tool-v"):
        return release
    if release.startswith("v"):
        return f"ptt-font-tool-{release}"
    return f"ptt-font-tool-v{release}"


def _validate_target_platform(target_platform: str) -> None:
    if target_platform not in SUPPORTED_PLATFORMS:
        choices = ", ".join(sorted(SUPPORTED_PLATFORMS))
        raise ValueError(f"Unsupported target platform: {target_platform}. Expected: {choices}")


def _sha256_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_tar_gz(source: Path, artifact_path: Path) -> None:
    with tarfile.open(artifact_path, "w:gz") as archive:
        archive.add(source, arcname=source.name)


def _write_macos_zip(source: Path, artifact_path: Path) -> None:
    subprocess.run(
        [
            "ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            str(source),
            str(artifact_path),
        ],
        check=True,
    )


def _write_zip(source: Path, artifact_path: Path) -> None:
    with zipfile.ZipFile(artifact_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            archive.write(path, path.relative_to(source.parent))


if __name__ == "__main__":
    raise SystemExit(main())
