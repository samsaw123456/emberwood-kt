"""Guard input ownership and cleanup without requiring a desktop or image library."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from linux_game_smoke import Desktop, fox_center, resting_center, stop_owned


class SmokeOwnershipTests(unittest.TestCase):
    def desktop(self, root_values, window_pid=42):
        desktop = Desktop.__new__(Desktop)
        desktop.root = SimpleNamespace(id=1)
        desktop.window = SimpleNamespace(id=17)
        desktop.pid = 42
        desktop.property = lambda window, name: (
            [window_pid] if window is desktop.window else root_values.get(name, [])
        )
        desktop.display = Mock()
        desktop.xtest = Mock()
        return desktop

    def test_refuses_an_existing_desktop_or_missing_window_manager(self):
        desktop = self.desktop({})
        desktop.clients = list
        with self.assertRaisesRegex(RuntimeError, "window manager"):
            desktop.require_empty()
        desktop = self.desktop({"_NET_SUPPORTING_WM_CHECK": [2]})
        desktop.clients = lambda: [SimpleNamespace(id=99)]
        with self.assertRaisesRegex(RuntimeError, "isolated display"):
            desktop.require_empty()
        desktop.xtest.fake_input.assert_not_called()

    def test_wrong_pid_or_focus_prevents_every_new_key_down(self):
        for desktop in [
            self.desktop({"_NET_ACTIVE_WINDOW": [17]}, window_pid=99),
            self.desktop({"_NET_ACTIVE_WINDOW": [99]}),
        ]:
            with self.assertRaises(RuntimeError):
                desktop.key("Alt_L", True)
            desktop.xtest.fake_input.assert_not_called()

    def test_failed_down_is_still_released_after_focus_changes(self):
        desktop = self.desktop({"_NET_ACTIVE_WINDOW": [17]})
        desktop.held = set()
        desktop.receipts = []
        desktop.x = SimpleNamespace(KeyPress=2, KeyRelease=3)
        desktop.xk = SimpleNamespace(string_to_keysym=lambda name: name)
        desktop.display.keysym_to_keycode.return_value = 64
        desktop.display.sync.side_effect = [RuntimeError("lost reply"), None]
        desktop.display.query_keymap.return_value = [0] * 32
        with self.assertRaisesRegex(RuntimeError, "lost reply"):
            desktop.key("Alt_L", True)
        self.assertEqual(desktop.held, {"Alt_L"})
        desktop.require_focus = Mock(side_effect=RuntimeError("other app focused"))
        with tempfile.TemporaryDirectory() as directory:
            desktop.output = Path(directory)
            desktop.close()
            receipt = json.loads((desktop.output / "physical-input.json").read_text())
            self.assertEqual(
                [(r["key"], r["down"]) for r in receipt], [("Alt_L", False)]
            )
        self.assertFalse(desktop.held)
        desktop.require_focus.assert_not_called()
        desktop.display.close.assert_called_once()

    def test_cleanup_attempts_all_releases_and_reports_failures(self):
        desktop = Desktop.__new__(Desktop)
        desktop.held = {"Alt_L", "F4"}
        desktop.receipts = []
        desktop.display = Mock()
        desktop.key = Mock(side_effect=[RuntimeError("failed Alt release"), None])
        with tempfile.TemporaryDirectory() as directory:
            desktop.output = Path(directory)
            with (
                self.assertLogs("linux_game_smoke", level="ERROR"),
                self.assertRaisesRegex(RuntimeError, "failed Alt release"),
            ):
                desktop.close()
        self.assertEqual(desktop.key.call_count, 2)
        desktop.display.close.assert_called_once()

    def test_failure_cleanup_stops_only_the_owned_process(self):
        owned = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        witness = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"]
        )
        try:
            stop_owned(owned)
            self.assertIsNotNone(owned.poll())
            self.assertIsNone(witness.poll())
        finally:
            stop_owned(owned)
            stop_owned(witness)


@unittest.skipUnless(
    importlib.util.find_spec("PIL"), "Pillow is used by Linux image checks"
)
class SmokeImageTests(unittest.TestCase):
    def test_release_observation_skips_protection_flash_without_missing_player(self):
        from PIL import Image

        fixtures = Path(__file__).parent / "fixtures/linux-game-smoke"
        with (
            Image.open(fixtures / "released-translucent.png") as translucent,
            Image.open(fixtures / "rested-opaque.png") as opaque,
        ):
            self.assertIsNone(fox_center(translucent))
            self.assertIsNotNone(fox_center(opaque))
            self.assertIsNone(resting_center(translucent, opaque))
            self.assertIsNone(resting_center(opaque, translucent))
            self.assertEqual(resting_center(opaque, opaque), fox_center(opaque))
            displaced = Image.new("RGB", opaque.size)
            displaced.paste(opaque, (9, 0))
            self.assertIsNone(resting_center(opaque, displaced))


if __name__ == "__main__":
    unittest.main()
