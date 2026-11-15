"""Real SDK buffer/PNG checks without starting capture or requesting permission."""

import json
import platform
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(platform.system() == "Darwin", "Requires the installed Mac SDK")
class NativeStreamDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="emberwood stream fixture ")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.helper = cls.root / "capture"
        subprocess.run(
            [
                "xcrun",
                "swiftc",
                "-swift-version",
                "5",
                "-parse-as-library",
                "-warnings-as-errors",
                "-O",
                "-target",
                f"{platform.machine()}-apple-macosx15.0",
                ROOT / "tools/mac_window_capture.swift",
                ROOT / "tools/mac_stream_diagnostic.swift",
                "-o",
                cls.helper,
            ],
            check=True,
            timeout=90,
        )

    def test_real_buffers_bounds_metadata_and_copy_ownership(self):
        output = self.root / "evidence with spaces"
        result = subprocess.run(
            [self.helper, "--test-stream-diagnostic", output],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        self.assertIn("no capture or permission request", result.stdout)
        summary = json.loads((output / "summary.json").read_text())
        self.assertTrue(summary["complete"])
        self.assertIsNone(summary["error"])
        self.assertFalse(summary["truncated"])
        self.assertEqual(summary["record_count"], 2)
        self.assertEqual(summary["image_count"], 1)
        self.assertEqual(summary["reserved_images"], 1)
        self.assertEqual(summary["skipped_images"], 0)
        self.assertFalse(summary["captures_audio"])
        self.assertFalse(summary["captures_microphone"])
        records = [
            json.loads(line)
            for line in (output / "frames.jsonl").read_text().splitlines()
        ]
        self.assertEqual(records[0]["nonce"], 0x8127)
        self.assertEqual(records[0]["presentation_seconds"], 123)
        self.assertNotIn("image", records[1])
        self.assertNotIn("nonce", records[1])
        for record in records:
            self.assertLessEqual(
                record["receipt_host_seconds"], record["receipt_host_after_seconds"]
            )
            self.assertGreater(record["receipt_unix_seconds"], 1_700_000_000)
        # The native fixture decodes pixels through CoreGraphics and verifies the
        # white-cell count after the original IOSurface was zeroed.
        png = (output / "stream-0000.png").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", png[16:24]), (128, 128))
        stale = subprocess.run(
            [self.helper, "--test-stream-diagnostic", output],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn("must be empty", stale.stderr)


if __name__ == "__main__":
    unittest.main()
