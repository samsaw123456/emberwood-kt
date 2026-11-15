"""Verify isolated native-launcher configuration and authoritative result handling."""

import copy
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from mac_app_profile import (
    CAPTURE_CONTROLS_FILTER,
    configure_app,
    tree_digest,
    validate_completion,
)


class NativeAppConfigTests(unittest.TestCase):
    def test_modes_keep_game_and_runtime_bytes_and_select_matching_test_entry(self):
        for mode, main in [
            ("performance", "emberwood.PerformanceAudit"),
            ("controls", "emberwood.NativeAuditKt"),
            ("controls-targeted", "emberwood.NativeAuditKt"),
            ("controls-capture", "emberwood.NativeAuditKt"),
            ("audio", "emberwood.AudioStateFixture"),
        ]:
            with (
                self.subTest(mode=mode),
                tempfile.TemporaryDirectory(prefix="native audit ") as folder,
            ):
                root = Path(folder)
                app = root / "Emberwood Kotlin.app"
                library = app / "Contents/app"
                library.mkdir(parents=True)
                runtime = app / "Contents/runtime/bin"
                runtime.mkdir(parents=True)
                (runtime / "java").write_bytes(b"original runtime fixture")
                game = library / "emberwood-kotlin.jar"
                game.write_bytes(b"unchanged game fixture")
                config = library / "Emberwood Kotlin.cfg"
                config.write_text(
                    "[Application]\napp.mainclass=emberwood.MainKt\napp.classpath=$APPDIR/emberwood-kotlin.jar\n[JavaOptions]\njava-options=-Xms32m\njava-options=-Xmx256m\njava-options=--enable-native-access=ALL-UNNAMED\n"
                )
                classes = root / "test classes/emberwood"
                classes.mkdir(parents=True)
                (classes / "Audit.class").write_bytes(b"test class fixture")
                before = tree_digest(app / "Contents/runtime")
                configure_app(
                    app, classes.parent, root / "output", 180, root / "input.sock", mode
                )
                configured = config.read_text()
                self.assertNotIn("audio.trace.directory", configured)
                self.assertNotIn("audit.disableDoubleBuffering", configured)
                self.assertNotIn("audit.scheduledRepaint", configured)
                self.assertEqual(
                    "java-options=-Daudit.paintTrace=true\n" in configured,
                    mode == "controls-capture",
                )
                self.assertIn(f"app.mainclass={main}\n", configured)
                self.assertIn("app.classpath=$APPDIR/native-audit.jar\n", configured)
                self.assertIn(
                    "java-options=--enable-native-access=ALL-UNNAMED\n", configured
                )
                if mode == "performance":
                    self.assertIn("java-options=-Xmx128m\n", configured)
                    self.assertIn("-Dperformance.soakSeconds=180\n", configured)
                    self.assertIn("-XX:ActiveProcessorCount=2\n", configured)
                    self.assertIn(
                        "java-options=-Xlog:gc,safepoint:stderr:time,uptime,level,tags\n",
                        configured,
                    )
                else:
                    self.assertIn("java-options=-Xmx256m\n", configured)
                    self.assertEqual(
                        "-Xlog:gc,safepoint:stderr:time,uptime,level,tags"
                        in configured,
                        mode in {"audio", "controls-capture"},
                    )
                    if mode.startswith("controls"):
                        self.assertIn("-Daudit.output=", configured)
                    self.assertEqual(
                        "-Daudit.filter=" in configured,
                        mode in {"controls-targeted", "controls-capture"},
                    )
                    self.assertNotIn("performance.", configured)
                self.assertEqual(tree_digest(app / "Contents/runtime"), before)
                self.assertEqual(game.read_bytes(), b"unchanged game fixture")
                with zipfile.ZipFile(library / "native-audit.jar") as archive:
                    self.assertEqual(archive.namelist(), ["emberwood/Audit.class"])

    def test_partial_filtered_or_wrong_duration_results_never_pass(self):
        performance = {
            "result": "PASS",
            "measured_windows": 22,
            "soak_seconds": 180,
            "failed_scenes": [],
            "failures": [],
            "exception": None,
        }
        controls = {
            "result": "PASS",
            "cases": 280,
            "expected_cases": 280,
            "failed_cases": [],
            "failure_count": 0,
            "filtered": False,
            "exception": None,
        }
        for mode, valid, changes in [
            (
                "performance",
                performance,
                [{"measured_windows": 21}, {"soak_seconds": 30}, {"failures": ["lag"]}],
            ),
            (
                "controls",
                controls,
                [
                    {"cases": 279},
                    {"expected_cases": 279},
                    {"filtered": True},
                    {"failure_count": 1},
                    {"failed_cases": ["movement"]},
                ],
            ),
        ]:
            validate_completion(valid, mode, 180)
            for change in [
                *changes,
                {"result": "FAIL"},
                {"exception": "startup failed"},
            ]:
                with (
                    self.subTest(mode=mode, change=change),
                    self.assertRaises(RuntimeError),
                ):
                    validate_completion({**valid, **change}, mode, 180)
            missing = copy.deepcopy(valid)
            del missing["exception"]
            with self.assertRaises(RuntimeError):
                validate_completion(missing, mode, 180)
        for malformed in [None, [], "PASS", {}]:
            with self.assertRaises(RuntimeError):
                validate_completion(malformed, "controls", 180)

    def test_targeted_control_result_can_never_validate_as_full_inventory(self):
        partial = {
            "result": "PASS",
            "cases": 26,
            "expected_cases": 280,
            "failed_cases": [],
            "failure_count": 0,
            "filtered": True,
            "exception": None,
        }
        validate_completion(partial, "controls-targeted", 30)
        with self.assertRaises(RuntimeError):
            validate_completion(partial, "controls", 30)
        for changes in [
            {"cases": 25},
            {"cases": 280},
            {"filtered": False},
            {"failure_count": 1},
            {"exception": "missing input"},
        ]:
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                validate_completion({**partial, **changes}, "controls-targeted", 30)

    def test_capture_mode_preserves_first_direction_order_and_is_partial(self):
        inventory = [
            "PLAYING/A",
            "PLAYING/←",
            "PLAYING/D",
            "PLAYING/→",
            "PLAYING/A with scrolling camera",
            "TITLE/Tab",
            "TITLE/Return",
            "PAUSED/Return",
            "TITLE/Return unavailable",
            "PLAYING/A unavailable",
        ]
        self.assertEqual(
            [row for row in inventory if re.search(CAPTURE_CONTROLS_FILTER, row)],
            ["PLAYING/A", "PLAYING/←", "PLAYING/D", "PLAYING/→", "TITLE/Return"],
        )
        partial = {
            "result": "PASS",
            "cases": 6,
            "expected_cases": 280,
            "failed_cases": [],
            "failure_count": 0,
            "filtered": True,
            "exception": None,
        }
        validate_completion(partial, "controls-capture", 30)
        for mode in ("controls", "controls-targeted"):
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                validate_completion(partial, mode, 30)
        for changes in (
            {"cases": 5},
            {"cases": 280},
            {"filtered": False},
            {"failure_count": 1},
            {"failed_cases": ["left"]},
            {"exception": "missing trace"},
        ):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                validate_completion({**partial, **changes}, "controls-capture", 30)


if __name__ == "__main__":
    unittest.main()
