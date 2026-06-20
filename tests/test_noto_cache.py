import io
import tempfile
import unittest
from pathlib import Path

from ptt_font_tool.noto_cache import (
    LICENSE_ASSET,
    SANS_TC_ASSET,
    SERIF_TC_ASSET,
    SYMBOLS_ASSET,
    clear_noto_cache,
    download_noto_assets,
    noto_cache_state,
    selected_noto_assets,
)


class NotoCacheTest(unittest.TestCase):
    def test_selected_assets_include_symbols_license_and_selected_text_fallback(self):
        self.assertEqual(
            selected_noto_assets("sans"),
            (SYMBOLS_ASSET, SANS_TC_ASSET, LICENSE_ASSET),
        )
        self.assertEqual(
            selected_noto_assets("serif"),
            (SYMBOLS_ASSET, SERIF_TC_ASSET, LICENSE_ASSET),
        )

    def test_cache_state_reports_available_and_missing_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            (cache_dir / SYMBOLS_ASSET.filename).write_bytes(b"symbols")

            state = noto_cache_state("sans", cache_dir=cache_dir)

            self.assertFalse(state.complete)
            self.assertEqual(state.available_assets, [SYMBOLS_ASSET])
            self.assertEqual(state.missing_assets, [SANS_TC_ASSET, LICENSE_ASSET])
            self.assertEqual(state.fallback_paths, [cache_dir / SYMBOLS_ASSET.filename])

    def test_download_writes_missing_assets_and_skips_existing_files(self):
        calls = []

        def opener(request, timeout, context):
            calls.append(request.full_url)
            return _Response(f"downloaded:{request.full_url}".encode("utf-8"))

        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            (cache_dir / SYMBOLS_ASSET.filename).write_bytes(b"existing")

            state = download_noto_assets(
                "sans",
                cache_dir=cache_dir,
                opener=opener,
                ssl_context_factory=lambda: object(),
            )

            self.assertEqual((cache_dir / SYMBOLS_ASSET.filename).read_bytes(), b"existing")
            self.assertEqual(
                (cache_dir / SANS_TC_ASSET.filename).read_bytes(),
                f"downloaded:{SANS_TC_ASSET.url}".encode("utf-8"),
            )
            self.assertEqual(
                (cache_dir / LICENSE_ASSET.filename).read_bytes(),
                f"downloaded:{LICENSE_ASSET.url}".encode("utf-8"),
            )

        self.assertEqual(calls, [SANS_TC_ASSET.url, LICENSE_ASSET.url])
        self.assertTrue(state.complete)

    def test_force_download_replaces_existing_files(self):
        calls = []

        def opener(request, timeout, context):
            calls.append(request.full_url)
            return _Response(b"fresh")

        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            for asset in selected_noto_assets("serif"):
                (cache_dir / asset.filename).write_bytes(b"stale")

            state = download_noto_assets(
                "serif",
                cache_dir=cache_dir,
                force=True,
                opener=opener,
                ssl_context_factory=lambda: object(),
            )

            for asset in selected_noto_assets("serif"):
                self.assertEqual((cache_dir / asset.filename).read_bytes(), b"fresh")

        self.assertEqual(calls, [asset.url for asset in selected_noto_assets("serif")])
        self.assertTrue(state.complete)

    def test_clear_removes_known_assets_and_partial_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            for asset in selected_noto_assets("sans"):
                (cache_dir / asset.filename).write_bytes(b"cached")
                (cache_dir / f"{asset.filename}.download").write_bytes(b"partial")
            unrelated = cache_dir / "custom.ttf"
            unrelated.write_bytes(b"keep")

            clear_noto_cache(cache_dir=cache_dir)

            for asset in selected_noto_assets("sans"):
                self.assertFalse((cache_dir / asset.filename).exists())
                self.assertFalse((cache_dir / f"{asset.filename}.download").exists())
            self.assertTrue(unrelated.exists())


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size=-1) -> bytes:
        return self._body.read(size)


if __name__ == "__main__":
    unittest.main()
