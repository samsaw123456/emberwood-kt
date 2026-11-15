"""Exercise real comparison control flow without requesting native facilities."""

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import mac_profile_compare as profile


def completion(result="PASS"):
    return {
        "result": result,
        "measured_windows": 22,
        "soak_seconds": 180,
        "failed_scenes": [] if result == "PASS" else ["active-soak"],
        "failures": [] if result == "PASS" else ["Low frame rate"],
        "exception": None,
    }


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="launcher comparison ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.java = self.root / "private JDK/bin/java"
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b"fixture Java")
        self.jar = self.root / "build/libs/emberwood-kotlin.jar"
        self.jar.parent.mkdir(parents=True)
        self.jar.write_bytes(b"unchanged game")
        self.tests = self.root / "build/classes/kotlin/test"
        (self.tests / "emberwood").mkdir(parents=True)
        (self.tests / "emberwood/PerformanceAudit.class").write_bytes(b"audit fixture")
        self.output = self.root / "measurement output"
        self.output.mkdir()
        self.controller = MagicMock()
        self.controller.path = self.root / "controller.sock"
        self.controller.windows.visible_registry.return_value = {(1, 2)}
        self.process = MagicMock()
        self.process.pid = 12345
        self.process.returncode = 0
        self.process.poll.side_effect = [None, 0, 0]
        self.process.wait.return_value = 0

    def raw_run(self, marker, code=0):
        self.process.returncode = code
        self.process.wait.return_value = code

        def launch(*_args, **_kwargs):
            self.assertFalse((self.output / "completion.json").exists())
            if marker is not None:
                (self.output / "completion.json").write_text(json.dumps(marker))
            return self.process

        with (
            patch.object(profile, "ROOT", self.root),
            patch.object(profile.subprocess, "Popen", side_effect=launch),
            patch.object(profile, "NativeStatus") as native,
            patch.object(profile, "cleanup_app") as cleanup,
        ):
            native.return_value.sample_and_wait.return_value = {
                "pid": 12345,
                "resident_set_kib": 123456,
                "is_frontmost": True,
            }
            result = profile.run_raw(
                self.java, self.jar, self.tests, self.output, 180, self.controller
            )
        self.controller.identify.assert_called_once_with(12345)
        self.controller.close.assert_called_once()
        cleanup.assert_called_once_with(
            12345, self.java, self.controller.windows, {(1, 2)}, self.output
        )
        return result

    def test_raw_success_uses_guarded_input_and_preserves_paths_and_limits(self):
        result = self.raw_run(completion())
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["rss_sample_count"], 1)
        self.assertEqual(result["peak_sampled_resident_set_kib"], 123456)
        command = result["command"]
        self.assertEqual(command[0], str(self.java))
        self.assertIn("-Xmx128m", command)
        self.assertIn("-XX:ActiveProcessorCount=2", command)
        self.assertIn(f"-Daudit.inputSocket={self.controller.path}", command)
        self.assertEqual(command[-2], f"{self.jar}:{self.tests}")
        self.assertFalse(any("FlightRecording" in value for value in command))

    def test_stale_pass_missing_completion_cannot_pass(self):
        (self.output / "completion.json").write_text(json.dumps(completion()))
        result = self.raw_run(marker=None)
        self.assertEqual(result["result"], "FAIL")
        self.assertNotIn("audit_completion", result)
        self.assertEqual(result["external_controller_cleanup"], "PASS")

    def test_failed_raw_thresholds_remain_failed_even_after_clean_exit(self):
        result = self.raw_run(marker=completion("FAIL"), code=1)
        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["audit_completion"]["failed_scenes"], ["active-soak"])
        self.assertEqual(result["external_controller_cleanup"], "PASS")

    def test_cleanup_attempts_windows_after_controller_failure_and_kills_hung_child(
        self,
    ):
        self.process.poll.side_effect = None
        self.process.poll.return_value = None
        self.process.wait.side_effect = [subprocess.TimeoutExpired("java", 5), -9]
        self.controller.close.side_effect = RuntimeError("held input failed to release")
        with (
            patch.object(profile, "cleanup_app") as cleanup,
            self.assertRaisesRegex(RuntimeError, "held input"),
        ):
            profile.cleanup_raw(
                self.process, self.java, self.controller, {(1, 2)}, self.output
            )
        self.process.terminate.assert_called_once()
        self.process.kill.assert_called_once()
        cleanup.assert_called_once()

    def comparison_run(
        self, raw_result="PASS", native_hash=None, cleanup_failure=False
    ):
        raw = {"result": raw_result, "external_controller_cleanup": "PASS"}
        native = {
            "result": "PASS",
            "game_jar_sha256": native_hash
            or hashlib.sha256(self.jar.read_bytes()).hexdigest(),
            "external_controller_cleanup": "PASS",
            "audit_completion": completion(),
        }

        def native_launch(command, **_kwargs):
            path = Path(command[command.index("--output") + 1])
            (path / "native-app.json").write_text(json.dumps(native))
            return subprocess.CompletedProcess(command, 0)

        with (
            patch.object(profile, "ROOT", self.root),
            patch.object(profile, "Controller"),
            patch.object(profile, "run_raw", return_value=raw) as run,
            patch.object(
                profile.subprocess, "run", side_effect=native_launch
            ) as launch,
        ):
            if cleanup_failure:
                run.side_effect = RuntimeError("cleanup failed")
            error = None
            try:
                profile.compare(self.java.parent.parent, self.output, 180)
            except RuntimeError as caught:
                error = caught
            return (
                json.loads((self.output / "comparison.json").read_text()),
                error,
                launch.call_count,
            )

    def test_comparison_preserves_raw_failure_and_still_measures_clean_native_path(
        self,
    ):
        record, error, launches = self.comparison_run(raw_result="FAIL")
        self.assertEqual(record["result"], "FAIL")
        self.assertEqual(record["native_app"]["result"], "PASS")
        self.assertIsNotNone(error)
        self.assertEqual(launches, 1)

    def test_comparison_requires_identical_game_bytes(self):
        record, error, launches = self.comparison_run(native_hash="different game")
        self.assertEqual(record["result"], "FAIL")
        self.assertIn("different production JARs", str(error))
        self.assertEqual(launches, 1)

    def test_uncertain_cleanup_prevents_native_launch_and_removes_old_pass(self):
        native = self.output / "native-app"
        native.mkdir()
        (native / "native-app.json").write_text('{"result":"PASS"}')
        (native / "completion.json").write_text(json.dumps(completion()))
        record, error, launches = self.comparison_run(cleanup_failure=True)
        self.assertEqual(record["result"], "FAIL")
        self.assertIsNotNone(error)
        self.assertEqual(launches, 0)
        self.assertFalse((native / "native-app.json").exists())
        self.assertFalse((native / "completion.json").exists())

    def test_both_successful_completions_pass(self):
        record, error, launches = self.comparison_run()
        self.assertEqual(record["result"], "PASS")
        self.assertIsNone(error)
        self.assertEqual(launches, 1)


if __name__ == "__main__":
    unittest.main()
