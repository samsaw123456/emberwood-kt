"""Verify bounded input scheduling and external evidence rejection without macOS."""

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mac_main_movement import (
    inspect_held_stream,
    observed_fox,
    owned_window,
    run_hold,
    timed_hold,
    validate_motion,
)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Keyboard:
    def __init__(self, clock, acknowledge=True, fail_down=False, delayed_down=0):
        self.clock, self.acknowledge = clock, acknowledge
        self.fail_down, self.delayed_down = fail_down, delayed_down
        self.down, self.events, self.held = False, [], set()
        self.core = SimpleNamespace(
            CGEventSourceKeyState=lambda *_: self.down if self.acknowledge else False
        )

    def post_mac(self, events):
        self.events.append((self.clock(), events))
        self.down = events[-1][1] == "down"
        if self.down:
            self.clock.now += self.delayed_down
            if self.fail_down:
                raise RuntimeError("Posted down before native error")
        return {"events": events}


class MainMovementTests(unittest.TestCase):
    def test_stalled_preflight_cannot_release_a_key_before_go(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("worker", 3), 0]
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("mac_main_movement.subprocess.Popen", return_value=process),
            patch("mac_main_movement.select.select", return_value=([], [], [])),
            patch("mac_main_movement.NativeKeys") as keys,
            self.assertRaisesRegex(RuntimeError, "did not become ready"),
        ):
            run_hold(Path(directory), 42, Path("/owned"), 7, "left", 0.35, "left")
        process.stdin.write.assert_not_called()
        keys.assert_not_called()

    def test_held_evidence_requires_fresh_pixels_inside_physical_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "capture-trace").mkdir()
            movements = [
                {
                    "before": [300, 511],
                    "input": {
                        "key": "left",
                        "down_post_started": 100.0,
                        "down_post_finished": 100.001,
                        "down_epoch_ns": 1700000100000000000,
                        "up_post_started": 100.35,
                    },
                }
            ]
            row = {
                "image": "frame.png",
                "presentation_seconds": 100.2,
                "receipt_host_seconds": 100.21,
                "receipt_unix_seconds": 1700000100.21,
            }
            path = output / "capture-trace/frames.jsonl"
            for pts, position, passes in (
                (99.9, [250, 511], False),
                (100.5, [250, 511], False),
                (100.2, [300, 511], False),
                (100.2, [250, 511], True),
            ):
                row["presentation_seconds"] = pts
                path.write_text(json.dumps(row) + "\n")
                with patch("mac_main_movement.observed_fox", return_value=position):
                    if passes:
                        self.assertTrue(
                            inspect_held_stream(output, movements)[0][
                                "held_motion_seen"
                            ]
                        )
                    else:
                        with self.assertRaisesRegex(RuntimeError, "Held movement"):
                            inspect_held_stream(output, movements)
            row["receipt_host_seconds"] += 5
            path.write_text(json.dumps(row) + "\n")
            with self.assertRaisesRegex(RuntimeError, "common origin"):
                inspect_held_stream(output, movements)

    def test_release_is_not_extended_by_missing_down_acknowledgment(self):
        clock = Clock()
        keyboard = Keyboard(clock, acknowledge=False)
        record = {}
        with self.assertRaisesRegex(RuntimeError, "physical key states"):
            timed_hold(keyboard, "left", 0.35, record, clock=clock, sleep=clock.sleep)
        self.assertAlmostEqual(keyboard.events[-1][0], 100.35)
        self.assertEqual(keyboard.events[-1][1], [("left", "up")])
        self.assertFalse(keyboard.held)

    def test_native_post_failure_still_releases_attempted_key(self):
        clock = Clock()
        keyboard = Keyboard(clock, fail_down=True)
        with self.assertRaisesRegex(RuntimeError, "native error"):
            timed_hold(keyboard, "a", 0.35, {}, clock=clock, sleep=clock.sleep)
        self.assertEqual(keyboard.events[-1][1], [("a", "up")])
        self.assertFalse(keyboard.down)

    def test_native_post_overrun_is_a_failure_not_a_longer_accepted_hold(self):
        clock, record = Clock(), {}
        keyboard = Keyboard(clock, delayed_down=0.6)
        with self.assertRaises(RuntimeError):
            timed_hold(keyboard, "left", 0.35, record, clock=clock, sleep=clock.sleep)
        self.assertAlmostEqual(record["up_post_started"], 100.6)
        self.assertGreater(record["release_lateness_seconds"], 0.2)

    def test_capture_can_block_longer_than_the_independent_process_hold(self):
        real_popen = subprocess.Popen
        child = (
            "import json,sys,time\n"
            "from pathlib import Path\n"
            "spec=json.loads(sys.argv[1]);print('READY',flush=True)\n"
            "assert sys.stdin.readline().strip()=='GO'\n"
            "down=time.monotonic();time.sleep(spec['seconds']);up=time.monotonic()\n"
            "Path(spec['output']).write_text(json.dumps({'result':'PASS bounded physical hold','down':down,'up':up}))\n"
        )

        def spawn(command, **kwargs):
            return real_popen([sys.executable, "-c", child, command[-1]], **kwargs)

        with (
            tempfile.TemporaryDirectory(prefix="main probe spaces ") as directory,
            patch("mac_main_movement.subprocess.Popen", side_effect=spawn),
        ):
            receipt = run_hold(
                Path(directory),
                42,
                Path("/owned app/game"),
                7,
                "left",
                0.35,
                "left",
                lambda: time.sleep(0.9),
            )
        self.assertLess(receipt["up"] - receipt["down"], 0.45)

    def test_wrong_process_window_and_geometry_refuse_input(self):
        for executable, window in (
            (Path("/other"), {"id": 7, "bounds": [0, 0, 1152, 676]}),
            (Path("/owned"), {"id": 8, "bounds": [0, 0, 1152, 676]}),
            (Path("/owned"), {"id": 7, "bounds": [0, 0, 1024, 676]}),
        ):
            windows = SimpleNamespace(
                executable=lambda _, executable=executable: executable,
                facilities=lambda: None,
                find=lambda *_, window=window, **__: window,
            )
            with (
                self.assertRaises(RuntimeError),
                patch("mac_main_movement.require_game_window") as focus,
            ):
                owned_window(windows, 42, Path("/owned"), 7)
            focus.assert_not_called()

    def test_stale_wall_drift_and_changed_ground_are_rejected(self):
        validate_motion([300, 515], [215, 515], [213, 515])
        for before, released, rested in (
            ([300, 515], [300, 515], [300, 515]),
            ([100, 515], [11, 515], [11, 515]),
            ([300, 515], [215, 515], [202, 515]),
            ([300, 515], [215, 490], [213, 515]),
        ):
            with self.assertRaises(RuntimeError):
                validate_motion(before, released, rested)

    def test_original_opaque_crop_is_recognized_but_translucent_or_resized_is_not(self):
        from PIL import Image

        fixtures = Path(__file__).parent / "fixtures/linux-game-smoke"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            for filename, accepted in (
                ("rested-opaque.png", True),
                ("released-translucent.png", False),
            ):
                canvas = Image.new("RGB", (1152, 676))
                with Image.open(fixtures / filename) as crop:
                    canvas.paste(crop, (180, 508))
                canvas.save(path)
                if accepted:
                    self.assertTrue(180 < observed_fox(path)[0] < 260)
                else:
                    with self.assertRaisesRegex(RuntimeError, "opaque"):
                        observed_fox(path)
            Image.new("RGB", (1024, 676)).save(path)
            with self.assertRaisesRegex(RuntimeError, "changed size"):
                observed_fox(path)


if __name__ == "__main__":
    unittest.main()
