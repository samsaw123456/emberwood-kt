"""Exercise terminal-process races with real children, without claiming Mac GUI proof."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mac_app_profile import launch_profile, owned_app_pid
from mac_bundle_smoke import cleanup_app
from mac_process_state import terminal_process_state


class NativeExitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="native exit fixture ")
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name).resolve()
        self.executable = self.output / "private.app/Contents/MacOS/game"
        self.executable.parent.mkdir(parents=True)
        self.executable.write_text("identity fixture")

    def child(self, source):
        process = subprocess.Popen([sys.executable, "-c", source])

        def stop():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)

        self.addCleanup(stop)
        return process

    def zombie(self):
        child = self.child("import os; os._exit(0)")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if terminal_process_state(child.pid) == "zombie":
                return child
            time.sleep(0.01)
        self.fail("The owned child did not reach an observable unreaped state")

    def controller(self, process, *, identified=False):
        def executable(pid):
            self.assertEqual(pid, process.pid)
            if not identified or terminal_process_state(pid) is not None:
                raise RuntimeError("Native executable identity is unavailable")
            return self.executable

        def identify(pid):
            if executable(pid) != self.executable:
                raise RuntimeError("Different executable")

        return SimpleNamespace(
            pid=process.pid,
            executable=self.executable,
            windows=SimpleNamespace(
                executable=executable, visible_registry=lambda: set()
            ),
            identify=identify,
        )

    def completion(self, result="PASS"):
        value = {
            "result": result,
            "cases": 280,
            "expected_cases": 280,
            "filtered": False,
            "failure_count": 0 if result == "PASS" else 3,
            "failed_cases": [] if result == "PASS" else ["Left", "Space", "W"],
            "exception": None
            if result == "PASS"
            else "Three input observations failed",
        }
        (self.output / "completion.json").write_text(json.dumps(value))
        return value

    def test_real_unreaped_child_is_terminal_despite_successful_kill_zero(self):
        process = self.zombie()
        os.kill(process.pid, 0)
        self.assertEqual(terminal_process_state(process.pid), "zombie")
        process.wait(timeout=5)
        self.assertEqual(terminal_process_state(process.pid), "gone")

    def launch_after_child_exit(self, completion, *, opener_status=0):
        child = self.zombie()
        controller = self.controller(child)
        release = self.output / "release-owned-launcher"
        opener = self.child(
            "import time\nfrom pathlib import Path\n"
            f"release = Path({str(release)!r})\n"
            "while not release.exists(): time.sleep(0.01)\n"
            f"raise SystemExit({opener_status})\n"
        )
        identify = controller.identify

        def identify_before_launcher_exit(pid):
            try:
                identify(pid)
            finally:
                # The owned opener cannot finish before the monitor observes
                # the app PID, even if a CI worker pauses this test for seconds.
                release.touch()

        controller.identify = identify_before_launcher_exit
        if completion is not None:
            self.completion(completion)
        actual_kill = os.kill
        with (
            patch("mac_app_profile.NativeStatus", return_value=object()),
            patch(
                "mac_app_profile.subprocess",
                SimpleNamespace(
                    Popen=lambda *_args, **_options: opener,
                    TimeoutExpired=subprocess.TimeoutExpired,
                ),
            ),
            patch("mac_process_state.os.kill", wraps=actual_kill) as kill,
        ):
            try:
                return launch_profile(
                    self.executable.parents[2], self.output, 10, controller, "controls"
                )
            finally:
                self.assertTrue(all(call.args[1] == 0 for call in kill.call_args_list))

    def test_monitor_waits_for_launcher_and_validates_success_without_signaling_zombie(
        self,
    ):
        self.assertEqual(self.launch_after_child_exit("PASS")["result"], "PASS")
        rows = [
            json.loads(row)
            for row in (self.output / "native-process.jsonl").read_text().splitlines()
        ]
        self.assertEqual(rows[0]["terminal_process_state"], "zombie")
        self.assertEqual(rows[-1]["launchservices_exit_code"], 0)

    def test_actual_failed_completion_is_not_masked_by_exit_identity_or_launcher_status(
        self,
    ):
        with self.assertRaisesRegex(RuntimeError, "Native audit failed"):
            self.launch_after_child_exit("FAIL", opener_status=1)
        self.assertEqual(
            json.loads((self.output / "completion.json").read_text())["failure_count"],
            3,
        )

    def test_terminal_app_without_completion_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError, "without its completion record"):
            self.launch_after_child_exit(None)

    def test_monitor_reaps_own_launcher_when_game_identity_remains_unknown(self):
        child = self.child("import time; time.sleep(30)")
        opener = self.child("import time; time.sleep(30)")
        controller = self.controller(child)
        actual_kill = os.kill
        with (
            patch("mac_app_profile.NativeStatus", return_value=object()),
            patch(
                "mac_app_profile.subprocess",
                SimpleNamespace(
                    Popen=lambda *_args, **_options: opener,
                    TimeoutExpired=subprocess.TimeoutExpired,
                ),
            ),
            patch("mac_process_state.os.kill", wraps=actual_kill) as kill,
            self.assertRaisesRegex(RuntimeError, "identity is unavailable"),
        ):
            launch_profile(
                self.executable.parents[2], self.output, 10, controller, "controls"
            )
        self.assertIsNone(child.poll())
        self.assertIsNotNone(opener.poll())
        self.assertTrue(
            all(
                call.args[1] == 0
                for call in kill.call_args_list
                if call.args[0] == child.pid
            )
        )

    def test_cleanup_never_signals_a_zombie_or_live_unidentified_process(self):
        for dead in (True, False):
            with self.subTest(dead=dead):
                process = (
                    self.zombie() if dead else self.child("import time; time.sleep(30)")
                )
                controller = self.controller(process)
                actual_kill = os.kill
                with (
                    patch("mac_process_state.os.kill", wraps=actual_kill) as kill,
                    patch(
                        "mac_bundle_smoke.subprocess",
                        SimpleNamespace(
                            run=lambda *_args, **_options: None,
                            SubprocessError=subprocess.SubprocessError,
                        ),
                    ),
                ):
                    if dead:
                        self.assertIsNone(
                            owned_app_pid(
                                object(), Path("/unused"), controller, process.pid
                            )
                        )
                        cleanup_app(
                            process.pid,
                            self.executable,
                            controller.windows,
                            set(),
                            self.output,
                        )
                    else:
                        with self.assertRaisesRegex(
                            RuntimeError, "identity is unavailable"
                        ):
                            owned_app_pid(
                                object(), Path("/unused"), controller, process.pid
                            )
                        with self.assertRaisesRegex(
                            RuntimeError, "identity is unavailable"
                        ):
                            cleanup_app(
                                process.pid,
                                self.executable,
                                controller.windows,
                                set(),
                                self.output,
                            )
                        self.assertIsNone(process.poll())
                    self.assertTrue(
                        all(call.args[1] == 0 for call in kill.call_args_list)
                    )

    def test_failed_empty_or_nonterminal_ps_never_proves_exit(self):
        process = self.child("import time; time.sleep(30)")
        for code, state in [(0, "R"), (0, "SE"), (0, "T"), (0, "U"), (0, ""), (1, "Z")]:
            with (
                self.subTest(code=code, state=state),
                patch(
                    "mac_process_state.subprocess.run",
                    return_value=SimpleNamespace(returncode=code, stdout=state),
                ),
            ):
                self.assertIsNone(terminal_process_state(process.pid))


if __name__ == "__main__":
    unittest.main()
