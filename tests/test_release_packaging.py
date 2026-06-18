import contextlib
import io
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

from ptt_font_tool.release_packaging import (
    clean_desktop_build_directories,
    desktop_bundle_path,
    desktop_release_artifact_name,
    main,
    package_desktop_bundle,
    _zip_archive_name,
)


class ReleasePackagingTest(unittest.TestCase):
    def test_builds_release_artifact_names_from_release_please_tag(self):
        self.assertEqual(
            desktop_release_artifact_name(
                release="ptt-font-tool-v0.4.0",
                target_platform="macos",
                arch="arm64",
            ),
            "ptt-font-tool-v0.4.0-macos-arm64.zip",
        )
        self.assertEqual(
            desktop_release_artifact_name(
                release="0.4.0",
                target_platform="linux",
                arch="x64",
            ),
            "ptt-font-tool-v0.4.0-linux-x64.tar.gz",
        )

    def test_resolves_platform_specific_pyinstaller_bundle_paths(self):
        dist_dir = Path("/tmp/dist")

        self.assertEqual(
            desktop_bundle_path(dist_dir, target_platform="macos"),
            dist_dir / "PTT Font Tool.app",
        )
        self.assertEqual(
            desktop_bundle_path(dist_dir, target_platform="windows"),
            dist_dir / "PTT Font Tool",
        )
        self.assertEqual(
            desktop_bundle_path(dist_dir, target_platform="linux"),
            dist_dir / "PTT Font Tool",
        )

    def test_packages_bundle_and_writes_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "dist" / "PTT Font Tool"
            nested = bundle / "_internal"
            nested.mkdir(parents=True)
            (nested / "payload.txt").write_text("desktop bundle\n", encoding="utf-8")

            artifact, checksum = package_desktop_bundle(
                dist_dir=root / "dist",
                output_dir=root / "release",
                release="v0.4.0",
                target_platform="linux",
                arch="x64",
            )

            self.assertEqual(artifact.name, "ptt-font-tool-v0.4.0-linux-x64.tar.gz")
            self.assertTrue(artifact.exists())
            self.assertEqual(checksum.name, "ptt-font-tool-v0.4.0-linux-x64.tar.gz.sha256")
            self.assertRegex(
                checksum.read_text(encoding="utf-8"),
                r"^[0-9a-f]{64}  ptt-font-tool-v0\.4\.0-linux-x64\.tar\.gz\n$",
            )

    def test_clean_keeps_existing_release_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist_dir = root / "dist"
            work_dir = root / "work"
            output_dir = root / "release"
            for path in (dist_dir, work_dir, output_dir):
                path.mkdir()
                (path / "artifact.txt").write_text("keep?\n", encoding="utf-8")

            clean_desktop_build_directories(dist_dir=dist_dir, work_dir=work_dir)

            self.assertFalse(dist_dir.exists())
            self.assertFalse(work_dir.exists())
            self.assertTrue((output_dir / "artifact.txt").exists())

    def test_reports_missing_pyinstaller_before_building(self):
        def fake_import(name, *args, **kwargs):
            if name == "PyInstaller":
                raise ModuleNotFoundError(name="PyInstaller")

            return original_import(name, *args, **kwargs)

        original_import = __import__
        stderr = io.StringIO()

        with patch("builtins.__import__", side_effect=fake_import):
            with contextlib.redirect_stderr(stderr):
                exit_code = main([
                    "--release",
                    "v0.4.0",
                    "--target-platform",
                    "linux",
                    "--arch",
                    "x64",
                ])

        self.assertEqual(exit_code, 1)
        self.assertIn("PyInstaller is required", stderr.getvalue())

    def test_help_does_not_require_pyinstaller(self):
        def fake_import(name, *args, **kwargs):
            if name == "PyInstaller":
                raise ModuleNotFoundError(name="PyInstaller")

            return original_import(name, *args, **kwargs)

        original_import = __import__
        stdout = io.StringIO()

        with patch("builtins.__import__", side_effect=fake_import):
            with contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as error:
                    main(["--help"])

        self.assertEqual(error.exception.code, 0)
        self.assertIn("Build desktop release artifacts", stdout.getvalue())

    def test_zip_archive_names_always_use_forward_slashes(self):
        self.assertEqual(
            _zip_archive_name(
                PureWindowsPath(r"C:\dist\PTT Font Tool\_internal\payload.txt"),
                PureWindowsPath(r"C:\dist"),
            ),
            "PTT Font Tool/_internal/payload.txt",
        )


if __name__ == "__main__":
    unittest.main()
