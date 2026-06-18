import tempfile
import unittest
from pathlib import Path

from ptt_font_tool.release_packaging import (
    desktop_bundle_path,
    desktop_release_artifact_name,
    package_desktop_bundle,
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


if __name__ == "__main__":
    unittest.main()
