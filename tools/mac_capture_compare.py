"""Compare default, disabled and restored Swing buffering in isolated native apps."""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

from mac_app_profile import validate_capture_trace, validate_graphics_metadata

ROOT = Path(__file__).resolve().parents[1]
SEQUENCE = (
    ("default", "default"),
    ("no-double-buffer", "no-double-buffer"),
    ("default-repeat", "default"),
)
BACKEND_FIELDS = (
    "configuration_class",
    "device_class",
    "device_id",
    "configuration_bounds",
    "default_transform",
    "display_mode",
    "panel_size",
    "frame_size",
    "panel_double_buffered",
    "repaint_manager_class",
    "maximum_buffer_size",
)
IDENTITY_FIELDS = (
    "original_app_tree_sha256",
    "original_app_tree_sha256_after",
    "original_runtime_sha256",
    "game_jar_sha256",
)


def run_variant(output, variant):
    command = [
        sys.executable,
        str(ROOT / "tools/mac_app_profile.py"),
        "--audit",
        "controls-capture",
        "--capture-trace",
        "--rendering-variant",
        variant,
        "--output",
        str(output),
    ]
    with (output / "driver.log").open("w") as log:
        process = subprocess.Popen(
            command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT
        )
        try:
            return process.wait(timeout=900)
        except subprocess.TimeoutExpired as error:
            # The owned Python driver handles SIGTERM while its app monitor is
            # running. Never start another app after an unverified timeout.
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise RuntimeError(
                "Capture diagnostic timed out; subsequent launches are blocked"
            ) from error


def read_variant(output, variant, exit_code):
    receipt = json.loads((output / "native-app.json").read_text())
    completion = json.loads((output / "completion.json").read_text())
    cleanup = json.loads((output / "window-cleanup/cleanup.json").read_text())
    if (
        receipt.get("audit") != "controls-capture"
        or receipt.get("requested_rendering_variant") != variant
        or receipt.get("full_inventory_verified") is not False
        or receipt.get("external_controller_cleanup") != "PASS"
        or receipt.get("native_window_cleanup") != cleanup
        or cleanup.get("result") != "PASS"
        or cleanup.get("new_windows_remaining") != []
        or "external_controller_cleanup_error" in receipt
        or "capture_postcondition_error" in receipt
        or receipt.get("copied_runtime_identical") is not True
        or any(
            not isinstance(receipt.get(name), str) or len(receipt[name]) != 64
            for name in IDENTITY_FIELDS
        )
        or receipt["original_app_tree_sha256"]
        != receipt["original_app_tree_sha256_after"]
    ):
        raise RuntimeError(
            "Native identity or cleanup is unverified; subsequent launches are blocked"
        )
    trace = validate_capture_trace(output, cleanup.get("pid"))
    graphics = validate_graphics_metadata(output, variant)
    if (
        receipt.get("capture_trace_completion") != trace
        or receipt.get("graphics_metadata") != graphics
    ):
        raise RuntimeError(
            "Native diagnostic metadata differs from its retained receipts"
        )
    if any(name not in graphics for name in BACKEND_FIELDS):
        raise RuntimeError("Graphics backend comparison metadata is incomplete")
    if (
        not isinstance(completion, dict)
        or completion.get("cases") != 6
        or completion.get("expected_cases") != 280
        or completion.get("filtered") is not True
        or type(completion.get("failure_count")) is not int
        or not isinstance(completion.get("failed_cases"), list)
        or completion["failure_count"] != len(completion["failed_cases"])
        or not 0 <= completion["failure_count"] <= 6
    ):
        raise RuntimeError("The diagnostic did not finish its six requested rows")
    failed = completion["failure_count"] > 0
    if (
        completion.get("result") != ("FAIL" if failed else "PASS")
        or receipt.get("result") != ("FAIL" if failed else "PARTIAL_PASS")
        or (failed and (not completion.get("exception") or exit_code != 1))
        or (not failed and (completion.get("exception") is not None or exit_code != 0))
    ):
        raise RuntimeError(
            "Diagnostic process status and authoritative result disagree"
        )
    return {
        "requested_variant": variant,
        "driver_exit_code": exit_code,
        "result": receipt["result"],
        "completion": completion,
        "graphics": graphics,
        "identity": {name: receipt[name] for name in IDENTITY_FIELDS},
        "cleanup": cleanup,
        "trace_records": trace["record_count"],
        "trace_images": len(trace["images"]),
        "native_receipt_sha256": hashlib.sha256(
            (output / "native-app.json").read_bytes()
        ).hexdigest(),
    }


def compare(output):
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Use a fresh output directory for the buffering comparison")
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "result": "INCOMPLETE",
        "full_inventory_verified": False,
        "sequence": [],
        "scope": "Three fresh same-runner native apps; test-only RepaintManager buffering override. Not a full control audit or a causal conclusion.",
    }
    record = output / "comparison.json"
    try:
        for label, variant in SEQUENCE:
            destination = output / label
            destination.mkdir()
            exit_code = run_variant(destination, variant)
            current = read_variant(destination, variant, exit_code)
            current["label"] = label
            if (
                report["sequence"]
                and current["identity"] != report["sequence"][0]["identity"]
            ):
                raise RuntimeError(
                    "Production application/runtime changed between diagnostic launches"
                )
            report["sequence"].append(current)
            record.write_text(json.dumps(report, indent=2) + "\n")
        baseline, disabled, repeat = [row["graphics"] for row in report["sequence"]]
        before = baseline["manager_double_buffering_enabled"]
        after = disabled["manager_double_buffering_enabled"]
        restored = repeat["manager_double_buffering_enabled"]
        differences = [
            {
                "field": name,
                "default": baseline[name],
                "no_double_buffer": disabled[name],
                "default_repeat": repeat[name],
            }
            for name in BACKEND_FIELDS
            if not baseline[name] == disabled[name] == repeat[name]
        ]
        report["observed_buffering"] = {
            "default": before,
            "no_double_buffer": after,
            "default_repeat": restored,
            "effective_contrast": before is True and after is False,
            "default_state_restored": restored is before,
            "interpretation": "Observed enabled-to-disabled contrast"
            if before
            else "No effective contrast: default was already disabled",
        }
        report["graphics_backend_equal"] = not differences
        report["graphics_backend_differences"] = differences
        report["result"] = (
            "DIAGNOSTIC_COMPLETE_WITH_CONTROL_FAILURES"
            if any(row["result"] == "FAIL" for row in report["sequence"])
            else "PARTIAL_PASS"
        )
        return report
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        report["result"] = "FAIL"
        report["error"] = str(error)
        raise
    finally:
        record.write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build/controls-capture-comparison"
    )
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run this diagnostic on macOS")
    report = compare(args.output.resolve())
    print(report["result"] + ": six rows per launch; full inventory remains unverified")
    if report["result"] != "PARTIAL_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
