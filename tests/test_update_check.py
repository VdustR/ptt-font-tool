import io
import json
import unittest

from ptt_font_tool.update_check import (
    check_for_update,
    is_newer_release,
    parse_latest_release,
)


class UpdateCheckTest(unittest.TestCase):
    def test_detects_prefixed_release_tag_as_newer(self):
        self.assertTrue(is_newer_release("ptt-font-tool-v0.4.0", "0.3.0"))
        self.assertFalse(is_newer_release("ptt-font-tool-v0.3.0", "0.3.0"))

    def test_parses_latest_release_payload(self):
        release = parse_latest_release({
            "tag_name": "ptt-font-tool-v0.4.0",
            "name": "ptt-font-tool: v0.4.0",
            "html_url": "https://github.com/VdustR/ptt-font-tool/releases/tag/ptt-font-tool-v0.4.0",
            "draft": False,
            "prerelease": False,
        })

        self.assertEqual(release.version, "0.4.0")
        self.assertEqual(
            release.url,
            "https://github.com/VdustR/ptt-font-tool/releases/tag/ptt-font-tool-v0.4.0",
        )

    def test_check_for_update_reports_available_release(self):
        def opener(request, timeout):
            self.assertEqual(timeout, 8)
            self.assertEqual(request.headers["Accept"], "application/vnd.github+json")
            payload = {
                "tag_name": "ptt-font-tool-v0.4.0",
                "name": "ptt-font-tool: v0.4.0",
                "html_url": "https://github.com/VdustR/ptt-font-tool/releases/tag/ptt-font-tool-v0.4.0",
                "draft": False,
                "prerelease": False,
            }
            return _Response(json.dumps(payload).encode("utf-8"))

        result = check_for_update(current_version="0.3.0", opener=opener)

        self.assertTrue(result.update_available)
        self.assertEqual(result.current_version, "0.3.0")
        self.assertEqual(result.latest.version, "0.4.0")

    def test_check_for_update_reports_current_version(self):
        def opener(_request, timeout):
            payload = {
                "tag_name": "ptt-font-tool-v0.3.0",
                "name": "ptt-font-tool: v0.3.0",
                "html_url": "https://github.com/VdustR/ptt-font-tool/releases/tag/ptt-font-tool-v0.3.0",
                "draft": False,
                "prerelease": False,
            }
            return _Response(json.dumps(payload).encode("utf-8"))

        result = check_for_update(current_version="0.3.0", opener=opener)

        self.assertFalse(result.update_available)
        self.assertEqual(result.latest.version, "0.3.0")


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self._body.read()


if __name__ == "__main__":
    unittest.main()
