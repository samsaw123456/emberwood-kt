"""Real child-process protocol/cleanup checks; these do not claim native Mac coverage."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mac_audio_contexts as contexts


class WindowFixture:
    def __init__(self, remaining=False):
        self.calls = 0
        self.remaining = remaining

    def visible_registry(self):
        self.calls += 1
        return {(123, 456)} if self.remaining and self.calls > 1 else set()


class ContextProtocolTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="context protocol ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.events = self.root / "events.jsonl"
        self.marker = self.root / "window-captured"
        self.java = self.root / "fake-java"
        self.java.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            "from pathlib import Path\n"
            f"events = Path({str(self.events)!r})\n"
            f"marker = Path({str(self.marker)!r})\n"
            "mode = sys.argv[-1]\n"
            "started = mode in ('worker-only', 'concurrent')\n"
            "print('READY', flush=True)\n"
            "for line in sys.stdin:\n"
            "    command = line.strip()\n"
            "    with events.open('a') as log: log.write(json.dumps(command) + '\\n')\n"
            "    if command == 'quit': break\n"
            "    if command == 'start':\n"
            "        assert mode == 'gui-first' and marker.exists(), 'No prior window capture'\n"
            "        started = True\n"
            "    print(json.dumps(dict(mode=mode, phase='window-visible', audio='ready' if started else 'not-requested', ready=started, unavailable=None, window_created=mode != 'worker-only', setup_error=None)), flush=True)\n"
        )
        self.java.chmod(0o755)

    def observe(self, mode, *, reject_window=False, remaining=False):
        def snapshot(_windows, _pid, _directory, label, require_window=False):
            if require_window:
                if reject_window:
                    raise RuntimeError("No actual empty JFrame could be captured")
                self.marker.touch()

        with (
            patch.object(contexts, "take_snapshot", side_effect=snapshot),
            patch.object(contexts, "capture_initialization_stacks") as stacks,
            patch.object(contexts.subprocess, "run"),
            patch.object(contexts.time, "sleep"),
        ):
            result = contexts.observe_mode(
                mode, self.java, self.root, WindowFixture(remaining)
            )
        self.assertTrue(stacks.called)
        self.assertEqual(result["cleanup"]["exit_code"], 0)
        with self.assertRaises(ProcessLookupError):
            os.kill(result["pid"], 0)
        return result, [
            json.loads(line) for line in self.events.read_text().splitlines()
        ]

    def test_gui_first_starts_only_after_actual_window_receipt(self):
        result, commands = self.observe("gui-first")
        self.assertEqual(result["result"], "CAPTURED")
        self.assertTrue(result["observed_status"]["ready"])
        self.assertEqual(commands, ["status", "start", "status", "quit"])
        self.assertTrue(result["cleanup_safe"])

    def test_empty_gui_never_requests_audio(self):
        result, commands = self.observe("gui-only")
        self.assertEqual(result["result"], "CAPTURED")
        self.assertEqual(result["observed_status"]["audio"], "not-requested")
        self.assertNotIn("start", commands)

    def test_missing_window_prevents_audio_start_and_cleans_child(self):
        result, commands = self.observe("gui-first", reject_window=True)
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(result["cleanup_safe"])
        self.assertNotIn("start", commands)

    def test_leftover_window_blocks_further_contexts(self):
        result, _ = self.observe("worker-only", remaining=True)
        self.assertEqual(result["result"], "FAIL")
        self.assertFalse(result["cleanup_safe"])
        self.assertEqual(result["cleanup"]["new_windows_remaining"], [(123, 456)])


if __name__ == "__main__":
    unittest.main()
