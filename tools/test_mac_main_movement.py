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

from mac_game_window import NativeWindowMissing
from mac_main_movement import (
    LiveSample,
    await_owned_window,
    await_title,
    held_capture_callback,
    inspect_held_stream,
    inspect_released_stream,
    observe_recovery,
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
    def test_stream_mode_queries_no_snapshot_until_after_early_recovery(self):
        for key, delay in (("a", 0.6), ("left", 3.5)):
            for mode in ("snapshot", "stream-only"):
                with self.subTest(key=key, mode=mode):
                    clock, captures = Clock(), []

                    def capture(label, captures=captures, clock=clock):
                        captures.append((label, clock()))
                        return Path(label)

                    during = held_capture_callback(mode, capture, key)
                    if during is not None:
                        during()
                    with patch(
                        "mac_main_movement.observed_fox", return_value=[215, 511]
                    ):
                        released, rested = observe_recovery(
                            mode, key, capture, sleep=clock.sleep
                        )
                    self.assertEqual(rested, [215, 511])
                    if mode == "stream-only":
                        self.assertIsNone(during)
                        self.assertIsNone(released)
                        self.assertEqual(captures, [(f"{key}-rested", 100 + delay)])
                    else:
                        self.assertEqual(released, [215, 511])
                        self.assertEqual(
                            [r[0] for r in captures],
                            [
                                f"{key}-held-snapshot",
                                f"{key}-released",
                                f"{key}-rested",
                            ],
                        )
                        self.assertAlmostEqual(captures[1][1], 100.3)
                        self.assertAlmostEqual(
                            captures[2][1], 100.6 if key == "a" else 103.8
                        )

    def test_stream_release_requires_early_presented_interior_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "capture-trace").mkdir()
            movement = {
                "input": {"key": "left", "up_observed": 100.35},
                "before": [300, 511],
                "rested": [215, 511],
            }
            for pts, point, accepted in (
                (100.4, [215, 511], False),  # Too early to prove recovery.
                (103.6, [215, 511], False),  # A late fresh frame cannot fill a gap.
                (100.65, [300, 511], False),  # Stale scene despite in-range PTS.
                (100.65, [11, 511], False),  # Wall stopping is not braking.
                (100.65, [223, 511], False),  # More than 6px drift after release.
                (100.65, [215, 490], False),  # Changed ground cannot be accepted.
                (100.65, [215, 511], True),
            ):
                row = {"image": "sample.png", "presentation_seconds": pts}
                (output / "capture-trace/frames.jsonl").write_text(
                    json.dumps(row) + "\n"
                )
                with patch("mac_main_movement.observed_fox", return_value=point):
                    if accepted:
                        proof = inspect_released_stream(output, [movement])
                        self.assertEqual(proof[0]["samples"][0]["fox"], point)
                        self.assertEqual(movement["released"], point)
                    else:
                        with self.assertRaises(RuntimeError):
                            inspect_released_stream(output, [movement])
            rows = [
                {"image": f"{i}.png", "presentation_seconds": pts}
                for i, pts in enumerate((100.65, 100.75))
            ]
            (output / "capture-trace/frames.jsonl").write_text(
                "\n".join(map(json.dumps, rows))
            )
            with (
                patch(
                    "mac_main_movement.observed_fox",
                    side_effect=[[215, 511], [240, 511]],
                ),
                self.assertRaisesRegex(RuntimeError, "recover to rest"),
            ):
                inspect_released_stream(output, [movement])

    def test_native_sample_is_exact_pid_nonblocking_and_records_completed_trace(self):
        with tempfile.TemporaryDirectory(prefix="sample path spaces ") as directory:
            output = Path(directory)
            process = Mock(pid=123, returncode=0)
            windows = SimpleNamespace(
                executable=Mock(return_value=Path("/owned app/game"))
            )
            sample = LiveSample(output, windows, 42, Path("/owned app/game"))
            with patch(
                "mac_main_movement.subprocess.Popen", return_value=process
            ) as popen:
                sample.start()
            process.wait.assert_not_called()
            self.assertEqual(
                popen.call_args.args[0],
                [
                    "/usr/bin/sample",
                    "42",
                    "3",
                    "1",
                    "-file",
                    str(output / "live-sample.txt"),
                ],
            )
            (output / "live-sample.txt").write_text("native owned sample\n")
            sample.finish()
            sample.finish()  # Cleanup is safe after the normal completion path.
            process.wait.assert_called_once_with(timeout=5)
            self.assertTrue(sample.log.closed)
            receipt = json.loads((output / "live-sample.json").read_text())
            self.assertEqual(receipt["result"], "PASS native sample captured")
            self.assertEqual(receipt["returncode"], 0)
            self.assertEqual(len(receipt["trace_sha256"]), 64)

    def test_native_sample_rejects_wrong_identity_and_cleans_only_its_sampler(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            windows = SimpleNamespace(executable=Mock(return_value=Path("/other")))
            sample = LiveSample(output, windows, 42, Path("/owned"))
            with (
                patch("mac_main_movement.subprocess.Popen") as popen,
                self.assertRaisesRegex(RuntimeError, "exact executable"),
            ):
                sample.start()
            popen.assert_not_called()
            windows.executable.return_value = Path("/owned")
            process = Mock(pid=123, returncode=-15)
            process.wait.side_effect = subprocess.TimeoutExpired("sample", 5)
            with patch("mac_main_movement.subprocess.Popen", return_value=process):
                sample.start()
            with (
                patch("mac_main_movement.stop_owned") as stop,
                self.assertRaisesRegex(RuntimeError, "bounded duration"),
            ):
                sample.finish()
            stop.assert_called_once_with(process)
            self.assertTrue(sample.log.closed)
            receipt = json.loads((output / "live-sample.json").read_text())
            self.assertEqual(receipt["result"], "FAIL")
            self.assertTrue(receipt["forced_sampler_cleanup"])

    def test_sample_is_armed_after_worker_ready_and_before_go(self):
        real_popen = subprocess.Popen
        child = (
            "import json,sys,time\nfrom pathlib import Path\n"
            "spec=json.loads(sys.argv[1]);out=Path(spec['output']).parent\n"
            "ready=time.monotonic();(out/'ready').write_text(str(ready));print('READY',flush=True)\n"
            "assert sys.stdin.readline().strip()=='GO'\n"
            "go=time.monotonic();armed=json.loads((out/'armed').read_text())\n"
            "Path(spec['output']).write_text(json.dumps({'result':'PASS bounded physical hold','ready':ready,'armed':armed,'go':go}))\n"
        )

        def spawn(command, **kwargs):
            return real_popen([sys.executable, "-c", child, command[-1]], **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)

            def arm():
                began = time.monotonic()
                self.assertLessEqual(float((output / "ready").read_text()), began)
                (output / "armed").write_text(
                    json.dumps({"began": began, "finished": time.monotonic()})
                )

            with patch("mac_main_movement.subprocess.Popen", side_effect=spawn):
                receipt = run_hold(
                    output, 42, Path("/owned"), 7, "left", 0.35, "left", before_go=arm
                )
            # This IPC fixture proves ordering, not the host's sleep precision.
            # timed_hold's clock/release tests independently enforce its budget.
            self.assertLessEqual(receipt["ready"], receipt["armed"]["began"])
            self.assertLessEqual(
                receipt["armed"]["began"], receipt["armed"]["finished"]
            )
            self.assertLessEqual(receipt["armed"]["finished"], receipt["go"])

    def test_sample_missing_output_or_failure_cannot_pass(self):
        for code, contents in ((0, None), (0, ""), (1, "partial sample")):
            with (
                self.subTest(code=code, contents=contents),
                tempfile.TemporaryDirectory() as directory,
            ):
                output = Path(directory)
                sample = LiveSample(
                    output,
                    SimpleNamespace(executable=lambda _: Path("/owned")),
                    42,
                    Path("/owned"),
                )
                with patch(
                    "mac_main_movement.subprocess.Popen",
                    return_value=Mock(pid=123, returncode=code),
                ):
                    sample.start()
                if contents is not None:
                    (output / "live-sample.txt").write_text(contents)
                with self.assertRaisesRegex(RuntimeError, "successful trace"):
                    sample.finish()
                self.assertTrue(sample.log.closed)
                self.assertEqual(
                    json.loads((output / "live-sample.json").read_text())["result"],
                    "FAIL",
                )

    def test_failed_observation_arming_sends_no_go_or_emergency_key(self):
        process = Mock()
        process.stdout.readline.return_value = "READY\n"
        process.poll.return_value = 0
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("mac_main_movement.subprocess.Popen", return_value=process),
            patch(
                "mac_main_movement.select.select",
                return_value=([process.stdout], [], []),
            ),
            patch("mac_main_movement.NativeKeys") as keys,
            self.assertRaisesRegex(RuntimeError, "cannot sample"),
        ):
            run_hold(
                Path(directory),
                42,
                Path("/owned"),
                7,
                "left",
                0.35,
                "left",
                before_go=Mock(side_effect=RuntimeError("cannot sample")),
            )
        process.stdin.write.assert_not_called()
        keys.assert_not_called()

    def test_late_owned_window_is_observed_before_readiness(self):
        clock = Clock()
        window = {"id": 7, "bounds": [0, 0, 1152, 676]}
        windows = SimpleNamespace(
            executable=Mock(return_value=Path("/owned")),
            facilities=Mock(return_value={"permitted": True}),
            find=Mock(
                side_effect=[
                    NativeWindowMissing("not yet created"),
                    NativeWindowMissing("not yet visible"),
                    window,
                    window,
                ]
            ),
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("mac_main_movement.require_game_window") as focus,
        ):
            output = Path(directory)
            actual = await_owned_window(
                windows,
                42,
                Path("/owned"),
                SimpleNamespace(poll=lambda: None),
                output,
                clock=clock,
                sleep=clock.sleep,
            )
            rows = [
                json.loads(line)
                for line in (output / "startup-window-observations.jsonl")
                .read_text()
                .splitlines()
            ]
        self.assertEqual(actual, window)
        self.assertAlmostEqual(clock(), 100.2)
        self.assertEqual([row["pid"] for row in rows], [42, 42, 42])
        self.assertEqual(
            [row["result"] for row in rows],
            [
                "WAIT missing window",
                "WAIT missing window",
                "PASS owned ordinary window",
            ],
        )
        focus.assert_called_once_with(42)

    def test_startup_identity_access_title_and_modal_errors_are_not_retried(self):
        window = {"id": 7, "bounds": [0, 0, 1152, 676]}
        for failure in ("identity", "permission", "title", "modal"):
            with self.subTest(failure=failure):
                clock = Clock()
                windows = SimpleNamespace(
                    executable=Mock(
                        return_value=Path(
                            "/other" if failure == "identity" else "/owned"
                        )
                    ),
                    facilities=Mock(
                        side_effect=RuntimeError("no permission")
                        if failure == "permission"
                        else None,
                        return_value={},
                    ),
                    find=Mock(
                        side_effect=[
                            window,
                            NativeWindowMissing("different owned title"),
                        ]
                        if failure == "title"
                        else None,
                        return_value=window,
                    ),
                )
                with (
                    tempfile.TemporaryDirectory() as directory,
                    patch(
                        "mac_main_movement.require_game_window",
                        side_effect=RuntimeError("modal")
                        if failure == "modal"
                        else None,
                    ),
                    self.assertRaises(RuntimeError),
                ):
                    await_owned_window(
                        windows,
                        42,
                        Path("/owned"),
                        SimpleNamespace(poll=lambda: None),
                        Path(directory),
                        clock=clock,
                        sleep=clock.sleep,
                    )
                self.assertEqual(clock(), 100.0)

    def test_missing_window_timeout_keeps_observations_and_sends_no_input(self):
        clock = Clock()
        windows = SimpleNamespace(
            executable=lambda _: Path("/owned"),
            facilities=dict,
            find=Mock(side_effect=NativeWindowMissing("absent")),
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("mac_main_movement.NativeKeys") as keys,
            patch("mac_main_movement.require_game_window") as focus,
        ):
            output = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "deadline"):
                await_owned_window(
                    windows,
                    42,
                    Path("/owned"),
                    SimpleNamespace(poll=lambda: None),
                    output,
                    timeout=0.25,
                    clock=clock,
                    sleep=clock.sleep,
                )
            rows = (
                (output / "startup-window-observations.jsonl").read_text().splitlines()
            )
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(json.loads(row)["error"] == "absent" for row in rows))
        self.assertAlmostEqual(clock(), 100.25)
        keys.assert_not_called()
        focus.assert_not_called()

    def test_title_wait_uses_client_pixels_and_retains_pending_and_accepted_images(
        self,
    ):
        from PIL import Image

        clock = Clock()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)

            def capture(label):
                path = output / f"{label}.png"
                Image.new("RGB", (1152, 676)).save(path)
                return path

            with patch(
                "mac_main_movement.title_visible", side_effect=[False, True]
            ) as visible:
                path = await_title(output, capture, clock=clock, sleep=clock.sleep)
            self.assertEqual(path, output / "title.png")
            self.assertTrue((output / "startup-title-first.png").exists())
            self.assertEqual(visible.call_count, 2)
            self.assertTrue(
                all(call.args[0].size == (1152, 648) for call in visible.call_args_list)
            )
            self.assertAlmostEqual(clock(), 100.1)
            with self.assertRaisesRegex(RuntimeError, "title pixels"):
                await_title(
                    output, capture, timeout=0.2, clock=clock, sleep=clock.sleep
                )

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

    def test_child_releases_while_parent_capture_remains_blocked(self):
        real_popen = subprocess.Popen
        child = (
            "import json,sys,time\n"
            "from pathlib import Path\n"
            "spec=json.loads(sys.argv[1]);print('READY',flush=True)\n"
            "assert sys.stdin.readline().strip()=='GO'\n"
            "out=Path(spec['output']);down=time.monotonic();deadline=down+3\n"
            "while not (out.parent/'capture-started').exists():\n"
            " assert time.monotonic()<deadline,'parent capture never started'\n"
            " time.sleep(.005)\n"
            "time.sleep(spec['seconds']);up=time.monotonic()\n"
            "Path(spec['output']).write_text(json.dumps({'result':'PASS bounded physical hold','down':down,'up':up}))\n"
        )

        def spawn(command, **kwargs):
            return real_popen([sys.executable, "-c", child, command[-1]], **kwargs)

        with (
            tempfile.TemporaryDirectory(prefix="main probe spaces ") as directory,
            patch("mac_main_movement.subprocess.Popen", side_effect=spawn),
        ):
            output, captured = Path(directory), {}

            def blocked_capture():
                captured["began"] = time.monotonic()
                (output / "capture-started").write_text("started")
                deadline = time.monotonic() + 3
                while not (output / "input-left.json").exists():
                    if time.monotonic() >= deadline:
                        self.fail(
                            "Child release waited for the blocked capture to finish"
                        )
                    time.sleep(0.005)
                captured["finished"] = time.monotonic()

            receipt = run_hold(
                output,
                42,
                Path("/owned app/game"),
                7,
                "left",
                0.35,
                "left",
                blocked_capture,
            )
        self.assertLess(receipt["down"], receipt["up"])
        self.assertLess(captured["began"], receipt["up"])
        self.assertLess(receipt["up"], captured["finished"])

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
