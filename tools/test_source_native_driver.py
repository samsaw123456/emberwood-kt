"""Check native-source evidence refusal paths without pretending to run a Mac."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_source_mac_native as driver


class SourceNativeDriverTests(unittest.TestCase):
    def test_cli_checks_actual_exit_and_output_and_retains_failure_receipts(self):
        with tempfile.TemporaryDirectory(prefix="source check ") as directory:
            output = Path(directory)
            with patch.object(driver, "ROOT", output):
                value = driver.run_cli(
                    output,
                    "valid",
                    [sys.executable, "-c", "print('ready')"],
                    os.environ,
                    contains="ready",
                )
                self.assertEqual(value, "ready")
                with self.assertRaisesRegex(RuntimeError, "expected exit"):
                    driver.run_cli(
                        output,
                        "bad-exit",
                        [sys.executable, "-c", "raise SystemExit(3)"],
                        os.environ,
                    )
                with self.assertRaisesRegex(RuntimeError, "was absent"):
                    driver.run_cli(
                        output,
                        "bad-output",
                        [sys.executable, "-c", "print('wrong')"],
                        os.environ,
                        contains="ready",
                    )
            self.assertEqual(
                json.loads((output / "valid.json").read_text())["result"], "PASS"
            )
            for label in ["bad-exit", "bad-output"]:
                self.assertEqual(
                    json.loads((output / f"{label}.json").read_text())["result"], "FAIL"
                )

    def test_failed_preparation_clears_stale_pass_and_cached_app_identity(self):
        with tempfile.TemporaryDirectory(prefix="source stale ") as directory:
            root = Path(directory)
            output = root / "build/evidence"
            output.mkdir(parents=True)
            for name in ["completion.json", "provenance.json"]:
                (output / name).write_text('{"result":"PASS"}')
            (output / "app-path.txt").write_text("/old/app")
            with (
                patch.object(driver, "ROOT", root),
                self.assertRaises(FileNotFoundError),
            ):
                driver.verify_native_source(output)
            self.assertEqual(
                json.loads((output / "completion.json").read_text())["result"], "FAIL"
            )
            self.assertFalse((output / "app-path.txt").exists())
            self.assertFalse((output / "provenance.json").exists())

    def test_snapshot_catches_changed_bytes_and_replaced_identical_files(self):
        with tempfile.TemporaryDirectory(prefix="source snapshot ") as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "populated"):
                driver.snapshot(root)
            file = root / "module bytes"
            file.write_bytes(b"initial")
            first = driver.snapshot(root)
            timestamp = file.stat().st_mtime_ns + 1_000_000
            os.utime(file, ns=(timestamp, timestamp))
            second = driver.snapshot(root)
            self.assertEqual(first["tree_sha256"], second["tree_sha256"])
            self.assertNotEqual(first["mtime_sha256"], second["mtime_sha256"])
            file.write_bytes(b"changed")
            self.assertNotEqual(
                second["tree_sha256"], driver.snapshot(root)["tree_sha256"]
            )


if __name__ == "__main__":
    unittest.main()
