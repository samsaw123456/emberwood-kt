"""Check scoped capture receipts and partial-only diagnostic driver behavior."""

import json
import plistlib
import shutil
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from mac_app_profile import CAPTURE_CONTROLS_FILTER, main, validate_capture_trace


def trace_fixture(output, pid=12345):
    """Synthetic PNG/protocol fixture; not actual native capture evidence."""
    trace = output / "capture-trace"
    trace.mkdir(exist_ok=True)

    def chunk(kind, body):
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body))
        )

    image = b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    )
    image += chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b"")
    (trace / "stream-0000.png").write_bytes(image)
    frames = [
        {
            "sequence": 0,
            "valid": True,
            "status": 0,
            "width": 1,
            "height": 1,
            "nonce": 7,
            "image": "stream-0000.png",
        },
        {"sequence": 1, "valid": True, "status": 1},
    ]
    for row in frames:
        row.update(
            receipt_host_seconds=100.0 + row["sequence"],
            receipt_host_after_seconds=100.001 + row["sequence"],
            receipt_unix_seconds=1_700_000_000.0 + row["sequence"],
            receipt_mach_ticks=100_000 + row["sequence"],
            receipt_mach_after_ticks=100_001 + row["sequence"],
        )
    (trace / "frames.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in frames)
    )
    (output / "external-capture.jsonl").write_text(
        json.dumps({"pid": pid, "window": {"id": 37}}) + "\n"
    )
    summary = {
        "complete": True,
        "error": None,
        "pid": pid,
        "window": 37,
        "record_count": 2,
        "image_count": 1,
        "reserved_images": 1,
        "skipped_images": 0,
        "dropped_records": 0,
        "truncated": False,
        "snapshot_comparator_unchanged": True,
        "captures_audio": False,
        "captures_microphone": False,
        "scope": "initial-fixed-window-geometry",
        "geometry_change": None,
        "mach_timebase": {"numerator": 1, "denominator": 1},
    }
    (trace / "summary.json").write_text(json.dumps(summary))
    return summary, frames


class CaptureTraceTests(unittest.TestCase):
    def test_incomplete_unscoped_or_wrong_process_trace_never_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            summary, _frames = trace_fixture(output)
            result = validate_capture_trace(output, 12345)
            self.assertEqual(result["record_count"], 2)
            self.assertFalse(result["full_inventory_verified"])
            for change in (
                {"complete": False},
                {"error": ["writer failed"]},
                {"pid": 12346},
                {"window": 38},
                {"record_count": 3},
                {"record_count": True},
                {"image_count": 2},
                {"reserved_images": 2},
                {"skipped_images": 1},
                {"dropped_records": 1},
                {"truncated": True},
                {"snapshot_comparator_unchanged": False},
                {"captures_audio": True},
                {"captures_microphone": True},
                {"scope": "desktop"},
                {"mach_timebase": {"numerator": 1, "denominator": 0}},
                {"mach_timebase": None},
            ):
                with self.subTest(change=change):
                    (output / "capture-trace/summary.json").write_text(
                        json.dumps({**summary, **change})
                    )
                    with self.assertRaises(RuntimeError):
                        validate_capture_trace(output, 12345)
            for name in ("complete", "error", "geometry_change", "mach_timebase"):
                incomplete = dict(summary)
                del incomplete[name]
                (output / "capture-trace/summary.json").write_text(
                    json.dumps(incomplete)
                )
                with self.subTest(missing=name), self.assertRaises(RuntimeError):
                    validate_capture_trace(output, 12345)

    def test_journal_png_and_snapshot_identity_are_checked(self):
        for failure in (
            "missing",
            "dimensions",
            "sequence",
            "extra",
            "outside",
            "pid",
            "window",
            "clock",
            "mach_clock",
            "missing_clock",
        ):
            with (
                self.subTest(failure=failure),
                tempfile.TemporaryDirectory() as directory,
            ):
                output = Path(directory)
                _summary, frames = trace_fixture(output)
                trace = output / "capture-trace"
                if failure == "missing":
                    (trace / "stream-0000.png").unlink()
                elif failure == "dimensions":
                    frames[0]["width"] = 2
                elif failure == "sequence":
                    frames[1]["sequence"] = 3
                elif failure == "extra":
                    (trace / "unlisted.png").write_bytes(
                        (trace / "stream-0000.png").read_bytes()
                    )
                elif failure == "outside":
                    frames[0]["image"] = "../outside.png"
                elif failure == "clock":
                    frames[0]["receipt_host_after_seconds"] = 0
                elif failure == "mach_clock":
                    frames[0]["receipt_mach_after_ticks"] = 0
                elif failure == "missing_clock":
                    del frames[0]["receipt_unix_seconds"]
                else:
                    request = {"pid": 12345, "window": {"id": 37}}
                    if failure == "pid":
                        request["pid"] = 67890
                    else:
                        request["window"]["id"] = 38
                    (output / "external-capture.jsonl").write_text(
                        json.dumps(request) + "\n"
                    )
                (trace / "frames.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in frames)
                )
                with self.assertRaises((OSError, RuntimeError)):
                    validate_capture_trace(output, 12345)

    def test_trace_flag_refuses_other_modes_before_native_operations(self):
        for mode in ("performance", "controls", "controls-targeted", "audio"):
            with (
                self.subTest(mode=mode),
                patch(
                    "sys.argv",
                    ["mac_app_profile.py", "--audit", mode, "--capture-trace"],
                ),
                patch("mac_app_profile.default_output") as output,
                patch("mac_app_profile.Controller") as controller,
                self.assertRaises(SystemExit) as stopped,
            ):
                main()
            self.assertEqual(stopped.exception.code, 2)
            output.assert_not_called()
            controller.assert_not_called()

    def test_partial_driver_drains_trace_even_when_primary_snapshot_fails(self):
        for primary_failure, incomplete_trace in (
            (False, False),
            (True, False),
            (False, True),
            (True, True),
        ):
            with self.subTest(
                primary_failure=primary_failure, incomplete_trace=incomplete_trace
            ):
                self.exercise_driver(primary_failure, incomplete_trace)

    def exercise_driver(self, primary_failure, incomplete_trace):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "VERSION").write_text("0.1.0\n")
            app = root / "original/Emberwood Kotlin.app"
            library = app / "Contents/app"
            library.mkdir(parents=True)
            (library / "emberwood-kotlin.jar").write_bytes(b"unchanged game")
            (library / "Emberwood Kotlin.cfg").write_text(
                "[Application]\napp.mainclass=emberwood.MainKt\napp.classpath=$APPDIR/emberwood-kotlin.jar\n[JavaOptions]\njava-options=-Xmx256m\n"
            )
            (app / "Contents/Info.plist").write_bytes(
                plistlib.dumps({"CFBundleExecutable": "Emberwood Kotlin"})
            )
            runtime = app / "Contents/runtime/bin/java"
            runtime.parent.mkdir(parents=True)
            runtime.write_bytes(b"unchanged runtime")
            tests = root / "build/classes/kotlin/test/emberwood"
            tests.mkdir(parents=True)
            (tests / "NativeAuditKt.class").write_bytes(b"test fixture")
            output = root / "output"
            closed = []

            class ControllerFixture:
                pid = 12345

                def __init__(self, folder, executable, *, capture_trace=False):
                    self.path = folder / "input.sock"
                    self.trace = capture_trace

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    closed.append(True)
                    summary, _frames = trace_fixture(output)
                    if incomplete_trace:
                        summary["skipped_images"] = 1
                        (output / "capture-trace/summary.json").write_text(
                            json.dumps(summary)
                        )

            def command(argv, **_options):
                if argv[0] == "ditto":
                    shutil.copytree(argv[1], argv[2])
                else:
                    self.assertEqual(argv[0], root / "tools/sign_mac_app.sh")

            def audit(copy, destination, timeout, controller, mode, seconds):
                self.assertTrue(controller.trace)
                self.assertEqual(mode, "controls-capture")
                self.assertFalse(closed)
                self.assertFalse((output / "capture-trace/summary.json").exists())
                self.assertIn(
                    f"java-options=-Daudit.filter={CAPTURE_CONTROLS_FILTER}\n",
                    (copy / "Contents/app/Emberwood Kotlin.cfg").read_text(),
                )
                if primary_failure:
                    raise RuntimeError("primary snapshot failed")
                return {
                    "result": "PASS",
                    "cases": 6,
                    "expected_cases": 280,
                    "filtered": True,
                    "failure_count": 0,
                    "failed_cases": [],
                    "exception": None,
                }

            with (
                patch("mac_app_profile.ROOT", root),
                patch("mac_app_profile.platform.system", return_value="Darwin"),
                patch("mac_app_profile.platform.machine", return_value="x86_64"),
                patch(
                    "sys.argv",
                    [
                        "mac_app_profile.py",
                        "--audit",
                        "controls-capture",
                        "--capture-trace",
                        "--app",
                        str(app),
                        "--output",
                        str(output),
                    ],
                ),
                patch(
                    "mac_app_profile.default_output",
                    return_value={"name": "fixture output"},
                ),
                patch("mac_app_profile.Controller", ControllerFixture),
                patch("mac_app_profile.subprocess.run", side_effect=command),
                patch("mac_app_profile.launch_profile", side_effect=audit),
            ):
                if primary_failure or incomplete_trace:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "primary snapshot failed"
                        if primary_failure
                        else "capture trace",
                    ):
                        main()
                else:
                    main()
            evidence = json.loads((output / "native-app.json").read_text())
            self.assertEqual(
                evidence["result"],
                "FAIL" if primary_failure or incomplete_trace else "PARTIAL_PASS",
            )
            self.assertFalse(evidence["full_inventory_verified"])
            self.assertEqual(closed, [True])
            if not incomplete_trace:
                self.assertEqual(
                    evidence["capture_trace_completion"]["record_count"], 2
                )
            self.assertEqual(runtime.read_bytes(), b"unchanged runtime")
            self.assertEqual(
                (library / "emberwood-kotlin.jar").read_bytes(), b"unchanged game"
            )


if __name__ == "__main__":
    unittest.main()
