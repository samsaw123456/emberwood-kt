"""Exercise native-app cleanup policy with owned child processes and fake windows."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mac_bundle_smoke import cleanup_app


class Windows:
    def __init__(self, process, executable):
        self.process, self.path = process, executable

    def executable(self, pid):
        assert pid == self.process.pid
        if self.process.poll() is not None:
            raise RuntimeError("Owned process has exited")
        if self.path is None:
            raise RuntimeError("Cannot identify live process")
        return self.path

    def visible_registry(self):
        return set()


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.executable = Path(sys.executable).resolve()
        self.process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"]
        )

        def stop():
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=5)

        self.addCleanup(stop)
        self.windows = Windows(self.process, self.executable)

    def clean(self):
        with patch("mac_bundle_smoke.subprocess.run"):
            cleanup_app(
                self.process.pid, self.executable, self.windows, set(), self.output
            )

    def test_waits_for_actual_owned_process_exit(self):
        self.clean()
        self.assertIsNotNone(self.process.poll())
        result = json.loads((self.output / "cleanup.json").read_text())
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["signals"], ["SIGTERM"])

    def test_different_executable_is_never_signaled(self):
        self.windows.path = Path("/different/executable")
        self.clean()
        self.assertIsNone(self.process.poll())
        self.assertEqual(
            json.loads((self.output / "cleanup.json").read_text())["signals"], []
        )

    def test_live_unidentified_process_fails_closed(self):
        self.windows.path = None
        with self.assertRaisesRegex(RuntimeError, "Cannot identify"):
            self.clean()
        self.assertIsNone(self.process.poll())
        result = json.loads((self.output / "cleanup.json").read_text())
        self.assertEqual(result["result"], "UNVERIFIED")
        self.assertEqual(result["signals"], [])

    def test_leftover_window_prevents_clean_receipt(self):
        self.process.terminate()
        self.process.wait(timeout=5)
        self.windows.visible_registry = lambda: {(99, 123)}
        with (
            patch("mac_bundle_smoke.time.monotonic", side_effect=[0, 6]),
            self.assertRaisesRegex(RuntimeError, "later probes must not run"),
        ):
            self.clean()
        result = json.loads((self.output / "cleanup.json").read_text())
        self.assertEqual(result["result"], "UNVERIFIED")
        self.assertEqual(result["new_windows_remaining"], [[99, 123]])


if __name__ == "__main__":
    unittest.main()
