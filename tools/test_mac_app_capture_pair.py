"""Exercise the three-run diagnostic barrier without claiming native Mac coverage."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mac_app_profile import (
    configure_app,
    validate_capture_trace,
    validate_graphics_metadata,
)
from mac_capture_compare import compare
from test_mac_app_capture import graphics_fixture, trace_fixture


class BufferingComparisonTests(unittest.TestCase):
    def test_variant_config_is_scoped_to_disposable_capture_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "private.app"
            library = app / "Contents/app"
            library.mkdir(parents=True)
            config = library / "game.cfg"
            config.write_text(
                "[Application]\napp.mainclass=emberwood.MainKt\napp.classpath=$APPDIR/emberwood-kotlin.jar\n[JavaOptions]\njava-options=-Xmx256m\n"
            )
            before = config.read_bytes()
            classes = root / "classes"
            classes.mkdir()
            for audit in ("performance", "controls", "controls-targeted", "audio"):
                with self.subTest(audit=audit), self.assertRaises(ValueError):
                    configure_app(
                        app,
                        classes,
                        root / "output",
                        30,
                        None,
                        audit,
                        rendering_variant="no-double-buffer",
                    )
                self.assertEqual(config.read_bytes(), before)
            configure_app(
                app,
                classes,
                root / "output",
                30,
                None,
                "controls-capture",
                rendering_variant="no-double-buffer",
            )
            configured = config.read_text()
            self.assertIn(
                "java-options=-Daudit.disableDoubleBuffering=true\n", configured
            )
            self.assertIn("java-options=-Daudit.paintTrace=true\n", configured)
            self.assertIn("java-options=-Xmx256m\n", configured)
            self.assertNotIn("sun.java2d.", configured)
            config.write_bytes(before)
            configure_app(
                app,
                classes,
                root / "output",
                30,
                None,
                "controls-capture",
                rendering_variant="scheduled-repaint",
            )
            configured = config.read_text()
            self.assertIn("java-options=-Daudit.scheduledRepaint=true\n", configured)
            self.assertNotIn("audit.disableDoubleBuffering", configured)
            self.assertNotIn("sun.java2d.", configured)

    def fixture_run(
        self,
        output,
        variant,
        *,
        failed=False,
        cleanup_failed=False,
        original_changed=False,
        baseline_disabled=False,
        backend_changed=False,
    ):
        pid = {"default": 12345, "no-double-buffer": 12346, "default-repeat": 12347}[
            output.name
        ]
        trace_fixture(output, pid)
        graphics = graphics_fixture(
            output,
            disabled=variant == "no-double-buffer",
            enabled=False if baseline_disabled else None,
        )
        if backend_changed:
            graphics["configuration_class"] = "different.GraphicsConfiguration"
            (output / "graphics-metadata.json").write_text(json.dumps(graphics))
        cleanup = {
            "pid": pid,
            "result": "FAIL" if cleanup_failed else "PASS",
            "new_windows_remaining": [[37, pid, 0]] if cleanup_failed else [],
        }
        (output / "window-cleanup").mkdir()
        (output / "window-cleanup/cleanup.json").write_text(json.dumps(cleanup))
        completion = {
            "result": "FAIL" if failed else "PASS",
            "cases": 6,
            "expected_cases": 280,
            "filtered": True,
            "failure_count": 1 if failed else 0,
            "failed_cases": ["Left deadline"] if failed else [],
            "exception": "Left deadline" if failed else None,
        }
        (output / "completion.json").write_text(json.dumps(completion))
        identity = "b" * 64 if original_changed else "a" * 64
        receipt = {
            "audit": "controls-capture",
            "requested_rendering_variant": variant,
            "full_inventory_verified": False,
            "external_controller_cleanup": "PASS",
            "native_window_cleanup": cleanup,
            "copied_runtime_identical": True,
            "original_app_tree_sha256": identity,
            "original_app_tree_sha256_after": identity,
            "original_runtime_sha256": "c" * 64,
            "game_jar_sha256": "d" * 64,
            "capture_trace_completion": validate_capture_trace(output, pid),
            "graphics_metadata": validate_graphics_metadata(output, variant),
            "result": "FAIL" if failed else "PARTIAL_PASS",
        }
        (output / "native-app.json").write_text(json.dumps(receipt))
        return 1 if failed else 0

    def test_failed_default_still_runs_variant_and_reversal_after_cleanup(self):
        for baseline_fails in (False, True):
            with (
                self.subTest(failed=baseline_fails),
                tempfile.TemporaryDirectory() as directory,
            ):
                calls = []

                def run(output, variant, calls=calls, baseline_fails=baseline_fails):
                    calls.append((output.name, variant))
                    return self.fixture_run(
                        output, variant, failed=baseline_fails and variant == "default"
                    )

                with patch("mac_capture_compare.run_variant", side_effect=run):
                    report = compare(Path(directory) / "comparison")
                self.assertEqual(
                    calls,
                    [
                        ("default", "default"),
                        ("no-double-buffer", "no-double-buffer"),
                        ("default-repeat", "default"),
                    ],
                )
                self.assertFalse(report["full_inventory_verified"])
                self.assertTrue(report["observed_buffering"]["effective_contrast"])
                self.assertTrue(report["observed_buffering"]["default_state_restored"])
                self.assertTrue(report["graphics_backend_equal"])
                self.assertEqual(
                    report["result"],
                    "DIAGNOSTIC_COMPLETE_WITH_CONTROL_FAILURES"
                    if baseline_fails
                    else "PARTIAL_PASS",
                )

    def test_cleanup_failure_or_changed_game_blocks_subsequent_launches(self):
        for defect in ("cleanup", "identity"):
            with (
                self.subTest(defect=defect),
                tempfile.TemporaryDirectory() as directory,
            ):
                calls = []

                def run(output, variant, calls=calls, defect=defect):
                    calls.append(output.name)
                    return self.fixture_run(
                        output,
                        variant,
                        cleanup_failed=defect == "cleanup",
                        original_changed=defect == "identity" and len(calls) == 2,
                    )

                output = Path(directory) / "comparison"
                with (
                    patch("mac_capture_compare.run_variant", side_effect=run),
                    self.assertRaises(RuntimeError),
                ):
                    compare(output)
                self.assertEqual(
                    calls,
                    ["default"]
                    if defect == "cleanup"
                    else ["default", "no-double-buffer"],
                )
                self.assertEqual(
                    json.loads((output / "comparison.json").read_text())["result"],
                    "FAIL",
                )

    def test_already_disabled_default_and_backend_change_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:

            def run(output, variant):
                return self.fixture_run(
                    output,
                    variant,
                    baseline_disabled=True,
                    backend_changed=variant == "no-double-buffer",
                )

            with patch("mac_capture_compare.run_variant", side_effect=run):
                report = compare(Path(directory) / "comparison")
            self.assertFalse(report["observed_buffering"]["effective_contrast"])
            self.assertIn(
                "already disabled", report["observed_buffering"]["interpretation"]
            )
            self.assertFalse(report["graphics_backend_equal"])
            self.assertEqual(
                report["graphics_backend_differences"][0]["field"],
                "configuration_class",
            )

    def test_existing_output_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "old.json").write_text("prior evidence")
            with (
                patch("mac_capture_compare.run_variant") as run,
                self.assertRaises(ValueError),
            ):
                compare(output)
            run.assert_not_called()
            self.assertEqual((output / "old.json").read_text(), "prior evidence")


if __name__ == "__main__":
    unittest.main()
