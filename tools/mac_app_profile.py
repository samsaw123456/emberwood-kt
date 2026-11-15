"""Audit an isolated LaunchServices app copy with its exact shipped JVM and game."""

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import plistlib
import signal
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import ExitStack
from pathlib import Path

from diagnose_mac_output import default_output
from mac_process_state import terminal_process_state
from mac_profile_observer import NativeStatus
from mac_test_bridge import Controller
from package_integrity import tree_digest

ROOT = Path(__file__).resolve().parents[1]
TARGETED_CONTROLS_FILTER = r"^PLAYING/(A|D|Left|Right|←|→)$|/M$|/left-shift facing |/right-shift facing |/Release .* while unfocused$"
TARGETED_CONTROLS_CASES = (
    26  # 4 direction + 6 mute + 4 dash + 11 focus/release + lifecycle.
)
CAPTURE_CONTROLS_FILTER = r"^PLAYING/(A|D|Left|Right|←|→)$|^TITLE/Return$"
CAPTURE_CONTROLS_CASES = 6  # First four directions, title activation and lifecycle.
FILTERED_CONTROLS = {
    "controls-targeted": (TARGETED_CONTROLS_FILTER, TARGETED_CONTROLS_CASES),
    "controls-capture": (CAPTURE_CONTROLS_FILTER, CAPTURE_CONTROLS_CASES),
}


def configure_app(
    app, tests, output, seconds, input_socket, audit="performance", *, audio_trace=False
):
    if audio_trace and audit != "audio":
        raise ValueError("Audio tracing is only available for the audio audit")
    configs = list((app / "Contents/app").glob("*.cfg"))
    if len(configs) != 1:
        raise RuntimeError("Expected one native launcher configuration")
    config = configs[0]
    text = config.read_text()
    options = [
        f"-Daudit.root={ROOT}",
        f"-Daudit.python={sys.executable}",
    ]
    if input_socket is not None:
        options.append(f"-Daudit.inputSocket={input_socket}")
    if audit == "performance":
        main_class = "emberwood.PerformanceAudit"
        options.extend(
            [
                "-XX:ActiveProcessorCount=2",
                "-Xlog:gc,safepoint:stderr:time,uptime,level,tags",
                f"-Dperformance.output={output}",
                f"-Dperformance.soakSeconds={seconds}",
            ]
        )
    elif audit == "controls" or audit in FILTERED_CONTROLS:
        main_class = "emberwood.NativeAuditKt"
        options.append(f"-Daudit.output={output}")
        if audit in FILTERED_CONTROLS:
            options.append(f"-Daudit.filter={FILTERED_CONTROLS[audit][0]}")
        if audit == "controls-capture":
            options.append("-Daudit.paintTrace=true")
            options.append("-Xlog:gc,safepoint:stderr:time,uptime,level,tags")
    elif audit == "audio":
        main_class = "emberwood.AudioStateFixture"
        options.append("-Xlog:gc,safepoint:stderr:time,uptime,level,tags")
        if audio_trace:
            options.append(f"-Daudio.trace.directory={output / 'trace'}")
    else:
        raise ValueError("Unknown native audit mode")
    replacements = {
        "app.mainclass=emberwood.MainKt": f"app.mainclass={main_class}",
        "app.classpath=$APPDIR/emberwood-kotlin.jar": (
            "app.classpath=$APPDIR/emberwood-kotlin.jar\n"
            "app.classpath=$APPDIR/native-audit.jar"
        ),
        "[JavaOptions]": "[JavaOptions]\n"
        + "\n".join(f"java-options={value}" for value in options),
    }
    if audit == "performance":
        replacements["java-options=-Xmx256m"] = "java-options=-Xmx128m"
    for original, replacement in replacements.items():
        if text.splitlines().count(original) != 1:
            raise RuntimeError(f"Unexpected native configuration: {original}")
        text = text.replace(original, replacement)
    config.write_text(text)
    with zipfile.ZipFile(
        app / "Contents/app/native-audit.jar", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for path in sorted(tests.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(tests))


def app_pid(native, app):
    """Match the exact temporary bundle URL; retain no other app metadata."""
    pool = native.object(native.cls("NSAutoreleasePool"), native.sel("new"))
    at_index = native.sender(ctypes.c_void_p, ctypes.c_ulong)
    string = native.sender(ctypes.c_char_p)
    try:
        # NSWorkspace's running-app list receives LaunchServices updates here.
        native.pump_events(0.05)
        workspace = native.object(
            native.cls("NSWorkspace"), native.sel("sharedWorkspace")
        )
        applications = native.object(workspace, native.sel("runningApplications"))
        found = []
        for index in range(native.integer(applications, native.sel("count"))):
            running = at_index(applications, native.sel("objectAtIndex:"), index)
            url = native.object(running, native.sel("bundleURL"))
            path = native.object(url, native.sel("path")) if url else None
            value = string(path, native.sel("UTF8String")) if path else None
            if value and Path(value.decode()).resolve() == app:
                found.append(native.integer(running, native.sel("processIdentifier")))
        if len(found) > 1:
            raise RuntimeError("Multiple running instances matched the private app")
        return found[0] if found else None
    finally:
        native.void(pool, native.sel("drain"))


def owned_app_pid(native, app, controller, known_pid):
    """Kernel identity also works before LaunchServices publishes the new app."""
    candidate = known_pid or controller.pid
    if candidate is None:
        candidate = app_pid(native, app)
    if candidate is None:
        return None
    try:
        executable = controller.windows.executable(candidate)
    except RuntimeError:
        # A terminal child has no executable path but can remain an unreaped PID.
        # Liveness alone never permits signaling an unidentified process.
        if terminal_process_state(candidate) is not None:
            return None
        raise
    return candidate if executable == controller.executable else None


def validate_completion(result, audit, seconds):
    if not isinstance(result, dict) or result.get("result") != "PASS":
        raise RuntimeError("Native audit failed; inspect completion.json")
    required = {"result", "exception"}
    if audit == "controls" or audit in FILTERED_CONTROLS:
        required.update(
            {"cases", "expected_cases", "failed_cases", "failure_count", "filtered"}
        )
    elif audit == "performance":
        required.update(
            {"measured_windows", "soak_seconds", "failed_scenes", "failures"}
        )
    else:
        raise RuntimeError("Unknown native audit completion mode")
    if not required.issubset(result):
        raise RuntimeError("Native audit completion is missing required evidence")
    if audit == "controls" or audit in FILTERED_CONTROLS:
        targeted = audit in FILTERED_CONTROLS
        expected = FILTERED_CONTROLS[audit][1] if targeted else 280
        if (
            result.get("cases") != expected
            or result.get("expected_cases") != 280
            or result.get("failed_cases") != []
            or result.get("failure_count") != 0
            or result.get("exception") is not None
            or result.get("filtered") is not targeted
        ):
            raise RuntimeError(
                "Native controls completion does not match the requested coverage"
            )
    elif (
        result.get("measured_windows") != 22
        or result.get("soak_seconds") != seconds
        or result.get("failed_scenes") != []
        or result.get("failures") != []
        or result.get("exception") is not None
    ):
        raise RuntimeError(
            "Native performance completion does not match the requested full measurement"
        )


def launch_profile(app, output, timeout, controller, audit="performance", seconds=30):
    native = NativeStatus()
    process = None
    pid = None
    started = time.monotonic()
    rss_samples = []

    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)

    previous = {
        kind: signal.signal(kind, interrupted)
        for kind in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        process = subprocess.Popen(
            [
                "open",
                "-W",
                "-n",
                "--stdout",
                output / "app-stdout.log",
                "--stderr",
                output / "app-stderr.log",
                app,
            ]
        )
        with (output / "native-process.jsonl").open("w", buffering=1) as log:
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > timeout:
                    raise TimeoutError("Native app profile did not finish in time")
                pid = pid or controller.pid or app_pid(native, app)
                if pid:
                    try:
                        controller.identify(pid)
                    except RuntimeError:
                        terminal = terminal_process_state(pid)
                        if terminal is None:
                            raise
                        log.write(
                            json.dumps(
                                {
                                    "pid": pid,
                                    "terminal_process_state": terminal,
                                    "elapsed_seconds": elapsed,
                                }
                            )
                            + "\n"
                        )
                        # LaunchServices can lag the app's terminal transition.
                        # It must still finish, and completion must still validate.
                        process.wait(timeout=5)
                        break
                    row = native.sample_and_wait(pid)
                    if row.get("resident_set_kib") is not None:
                        rss_samples.append(row["resident_set_kib"])
                    row["elapsed_seconds"] = elapsed
                    log.write(json.dumps(row) + "\n")
                elif elapsed > 30:
                    raise RuntimeError("LaunchServices did not start the private app")
                else:
                    time.sleep(0.2)
            log.write(
                json.dumps(
                    {
                        "pid": pid,
                        "launchservices_exit_code": process.returncode,
                        "rss_sample_count": len(rss_samples),
                        "peak_sampled_resident_set_kib": max(rss_samples, default=None),
                        "rss_method": "Exact-PID one-second samples; not an OS high-water mark",
                    }
                )
                + "\n"
            )
        completion = output / "completion.json"
        if not completion.is_file():
            if process.returncode:
                raise RuntimeError(f"LaunchServices exited with {process.returncode}")
            raise RuntimeError("Native audit ended without its completion record")
        result = json.loads(completion.read_text())
        validate_completion(result, audit, seconds)
        if process.returncode:
            raise RuntimeError(f"LaunchServices exited with {process.returncode}")
        if not pid:
            raise RuntimeError(
                "Audit reported success but no native app PID was observed"
            )
        return result
    finally:
        for kind, handler in previous.items():
            signal.signal(kind, handler)
        try:
            # Only the exact private bundle we launched can be terminated here.
            owned = owned_app_pid(native, app, controller, pid)
            if owned:
                try:
                    os.kill(owned, signal.SIGTERM)
                    deadline = time.monotonic() + 5
                    while (
                        owned_app_pid(native, app, controller, owned) == owned
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.1)
                    if owned_app_pid(native, app, controller, owned) == owned:
                        os.kill(owned, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # The exact private process exited between lookup and signal.
        finally:
            # This Popen child is always ours, even if the game's identity became
            # unavailable. Reap the launcher without touching that unknown PID.
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def run_owned_check(app, command, output, timeout):
    """Finish cleanup of only the copied app, including failed child diagnostics."""
    from mac_bundle_smoke import cleanup_app
    from mac_game_window import GameWindow

    output.mkdir(parents=True, exist_ok=True)
    native, windows = NativeStatus(), GameWindow()
    baseline = windows.visible_registry()
    metadata = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    executable = app / "Contents/MacOS" / metadata["CFBundleExecutable"]
    try:
        with (output / "driver.log").open("w") as log:
            subprocess.run(
                command,
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
    finally:
        cleanup_app(app_pid(native, app), executable, windows, baseline, output)


def validate_audio(output, app, game_digest):
    """Require the entire physical-input PCM inventory and completed cleanup."""
    summary = json.loads((output / "summary.json").read_text())
    cleanup = json.loads((output / "cleanup.json").read_text())
    results = json.loads((output / "results.json").read_text())
    if not isinstance(summary, dict) or not isinstance(cleanup, dict):
        raise TypeError("Native audio summary or cleanup evidence is malformed")
    states = {"TITLE", "PLAYING", "PAUSED", "RESPAWNING", "CHAPTER_COMPLETE", "WON"}
    expected = {(state, "m") for state in states} | {
        (state, binding)
        for state in ("TITLE", "PAUSED")
        for binding in ("Mouse", "Return", "space", "KP_Enter")
    }
    checks = {
        "full cue audible",
        "long reference cue audible",
        "mute stops audible cue",
        "muted cue is silent",
        "physical unmute feedback audible",
        "restored cue audible",
        "state retained and input focused",
    }
    if (
        summary.get("result") != "PASS"
        or summary.get("launch_method") != "LaunchServices native app"
        or summary.get("game_jar_sha256") != game_digest
        or Path(summary.get("game_jar", ""))
        != app / "Contents/app/emberwood-kotlin.jar"
        or Path(summary.get("java_executable", ""))
        != app / "Contents/runtime/Contents/Home/bin/java"
        or summary.get("microphone") is not False
        or summary.get("global_audio_fallback") is not False
        or not isinstance(summary.get("game_pid"), int)
        or cleanup.get("pid") != summary.get("game_pid")
        or cleanup.get("result") != "PASS"
        or cleanup.get("new_windows_remaining") != []
    ):
        raise RuntimeError("Native audio identity, scope or cleanup evidence failed")
    if not isinstance(results, dict) or len(results) != 14:
        raise RuntimeError("Native audio did not complete all 14 physical bindings")
    observed = set()
    recordings = []
    for label, row in results.items():
        if not isinstance(row, dict) or not isinstance(row.get("checks"), dict):
            raise TypeError(f"Native audio row is malformed: {label}")
        state, binding = row.get("state"), row.get("binding")
        if not isinstance(state, str) or not isinstance(binding, str):
            raise TypeError(f"Native audio binding is malformed: {label}")
        observed.add((state, binding))
        if (
            row.get("result") != "PASS"
            or row.get("file_prefix") != label
            or label != (state if binding == "m" else f"{state}-{binding}")
            or set(row.get("checks", {})) != checks
            or any(value is not True for value in row["checks"].values())
        ):
            raise RuntimeError(f"Native audio row is incomplete or failed: {label}")
        for phase in ("full", "long", "cut", "muted", "unmute", "restored"):
            path = output / f"{label}-{phase}.wav"
            if not path.is_file() or path.stat().st_size <= 44:
                raise RuntimeError(f"Native audio is missing captured PCM: {path.name}")
            recordings.append(
                {
                    "path": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    if observed != expected:
        raise RuntimeError("Native audio states or physical bindings are missing")
    return {
        "result": "PASS",
        "cases": 14,
        "expected_cases": 14,
        "exception": None,
        "game_pid": summary["game_pid"],
        "cleanup": "PASS",
        "recordings": recordings,
    }


def launch_audio(app, output, game_digest):
    pcm = output / "pcm"
    pcm.mkdir(parents=True, exist_ok=True)
    # A failed new invocation must not reuse a prior successful receipt.
    for name in ("summary.json", "results.json", "cleanup.json"):
        (pcm / name).unlink(missing_ok=True)
    run_owned_check(
        app,
        [
            sys.executable,
            ROOT / "tools/mac_audio_audit.py",
            "--app",
            app,
            "--output",
            pcm,
        ],
        output / "pcm-cleanup",
        900,
    )
    outer_cleanup = json.loads((output / "pcm-cleanup/cleanup.json").read_text())
    if (
        not isinstance(outer_cleanup, dict)
        or outer_cleanup.get("result") != "PASS"
        or outer_cleanup.get("new_windows_remaining") != []
    ):
        raise RuntimeError("Native audio outer process cleanup failed")
    return validate_audio(pcm, app, game_digest)


def validate_audio_trace(output):
    trace = output / "trace"
    summary_path = trace / "summary.json"
    summary = json.loads(summary_path.read_text())
    if (
        not isinstance(summary, dict)
        or summary.get("result") != "PASS"
        or summary.get("truncated") is not False
        or summary.get("native_queue_disposed") is not True
        or summary.get("errors") != []
        or type(summary.get("event_count")) is not int
        or summary["event_count"] <= 0
        or type(summary.get("pcm_bytes")) is not int
        or summary["pcm_bytes"] < 0
    ):
        raise RuntimeError("Audio trace is incomplete, truncated or failed")
    if (
        not (trace / "events.tsv").is_file()
        or not (trace / "events.tsv").stat().st_size
    ):
        raise RuntimeError("Audio trace has no event journal")
    if (trace / "samples.s16le").stat().st_size != summary["pcm_bytes"]:
        raise RuntimeError("Audio trace PCM size does not match its summary")
    return {
        "result": "PASS",
        "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "event_count": summary["event_count"],
        "pcm_bytes": summary["pcm_bytes"],
    }


def validate_capture_trace(output, pid):
    """Require the bounded own-window recording after its helper has drained."""
    trace = output / "capture-trace"
    summary_path = trace / "summary.json"
    summary = json.loads(summary_path.read_text())
    counts = (
        "record_count",
        "image_count",
        "reserved_images",
        "skipped_images",
        "dropped_records",
    )
    if (
        not isinstance(summary, dict)
        or not {"error", "geometry_change", "mach_timebase"}.issubset(summary)
        or type(pid) is not int
        or pid <= 1
        or summary.get("complete") is not True
        or summary.get("error") is not None
        or summary.get("pid") != pid
        or type(summary.get("window")) is not int
        or summary["window"] <= 0
        or any(type(summary.get(name)) is not int for name in counts)
        or not 0 < summary["record_count"] <= 6000
        or not 0 < summary["image_count"] <= 128
        or summary["image_count"] != summary["reserved_images"]
        or summary["skipped_images"] != 0
        or summary["dropped_records"] != 0
        or summary.get("truncated") is not False
        or summary.get("snapshot_comparator_unchanged") is not True
        or summary.get("captures_audio") is not False
        or summary.get("captures_microphone") is not False
        or summary.get("scope") != "initial-fixed-window-geometry"
    ):
        raise RuntimeError(
            "Native capture trace is incomplete, truncated, unscoped or failed"
        )
    timebase = summary["mach_timebase"]
    if not isinstance(timebase, dict) or any(
        type(timebase.get(name)) is not int or timebase[name] <= 0
        for name in ("numerator", "denominator")
    ):
        raise RuntimeError("Native capture trace has no valid Mach clock scale")
    requests = [
        json.loads(line)
        for line in (output / "external-capture.jsonl").read_text().splitlines()
    ]
    if not requests or any(
        not isinstance(row, dict)
        or row.get("pid") != pid
        or not isinstance(row.get("window"), dict)
        or row["window"].get("id") != summary["window"]
        for row in requests
    ):
        raise RuntimeError(
            "Native capture trace differs from the exact snapshot PID/window"
        )
    frames_path = trace / "frames.jsonl"
    frames = [json.loads(line) for line in frames_path.read_text().splitlines()]
    if len(frames) != summary["record_count"]:
        raise RuntimeError(
            "Native capture trace frame count does not match its journal"
        )
    images = []
    for index, row in enumerate(frames):
        if not isinstance(row, dict) or row.get("sequence") != index:
            raise RuntimeError("Native capture trace frame sequence is incomplete")
        if (
            any(
                type(row.get(name)) not in (float, int) or not math.isfinite(row[name])
                for name in (
                    "receipt_host_seconds",
                    "receipt_host_after_seconds",
                    "receipt_unix_seconds",
                )
            )
            or row["receipt_host_seconds"] > row["receipt_host_after_seconds"]
            or any(
                type(row.get(name)) is not int or row[name] < 0
                for name in ("receipt_mach_ticks", "receipt_mach_after_ticks")
            )
            or row["receipt_mach_ticks"] > row["receipt_mach_after_ticks"]
        ):
            raise RuntimeError("Native capture trace frame clock bracket is invalid")
        if "image" not in row:
            continue
        name = row["image"]
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or not name.startswith("stream-")
            or not name.endswith(".png")
            or row.get("valid") is not True
            or row.get("status") != 0
        ):
            raise RuntimeError(
                "Native capture trace image is not a complete scoped frame"
            )
        path = trace / name
        if path.is_symlink():
            raise RuntimeError("Native capture trace image cannot be a symbolic link")
        data = path.read_bytes()
        if (
            len(data) < 45
            or data[:8] != b"\x89PNG\r\n\x1a\n"
            or data[12:16] != b"IHDR"
            or data[-12:] != b"\x00\x00\x00\x00IEND\xaeB`\x82"
            or struct.unpack(">II", data[16:24])
            != (row.get("width"), row.get("height"))
        ):
            raise RuntimeError(
                "Native capture trace PNG is missing or has different dimensions"
            )
        images.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
    names = {item["path"] for item in images}
    if (
        len(images) != summary["image_count"]
        or len(names) != len(images)
        or names != {path.name for path in trace.glob("*.png")}
    ):
        raise RuntimeError(
            "Native capture trace images do not match the drained summary"
        )
    return {
        "result": "PASS retained diagnostic trace",
        "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "frames_sha256": hashlib.sha256(frames_path.read_bytes()).hexdigest(),
        "pid": pid,
        "window": summary["window"],
        "record_count": len(frames),
        "images": images,
        "scope": summary["scope"],
        "geometry_change": summary.get("geometry_change"),
        "full_inventory_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit",
        choices=("performance", "controls", *FILTERED_CONTROLS, "audio"),
        default="performance",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--app",
        type=Path,
        help="Audit this existing native app instead of the distribution app",
    )
    parser.add_argument("--soak-seconds", type=int, default=30)
    parser.add_argument(
        "--audio-trace",
        action="store_true",
        help="Enable test-only clock and output tracing for --audit audio",
    )
    parser.add_argument(
        "--capture-trace",
        action="store_true",
        help="Record a test-only own-window stream alongside --audit controls-capture",
    )
    args = parser.parse_args()
    if args.audio_trace and args.audit != "audio":
        parser.error("--audio-trace requires --audit audio")
    if args.capture_trace and args.audit != "controls-capture":
        parser.error("--capture-trace requires --audit controls-capture")
    if platform.system() != "Darwin":
        parser.error("Run this diagnostic on macOS")
    if not 30 <= args.soak_seconds <= 1800:
        parser.error("Soak duration must be between 30 and 1800 seconds")
    output = (args.output or ROOT / "build" / f"{args.audit}-native-app").resolve()
    if "\n" in str(output) or "\r" in str(output):
        parser.error("Output path cannot contain a line break")
    output.mkdir(parents=True, exist_ok=True)
    if args.audio_trace:
        trace = output / "trace"
        if trace.exists() and (not trace.is_dir() or any(trace.iterdir())):
            parser.error("Use a fresh output directory for --audio-trace")
    if args.capture_trace:
        trace = output / "capture-trace"
        if trace.exists() and (not trace.is_dir() or any(trace.iterdir())):
            parser.error("Use a fresh output directory for --capture-trace")
    (output / "completion.json").unlink(missing_ok=True)
    version = (ROOT / "VERSION").read_text().strip()
    arch = {"arm64": "aarch64"}.get(platform.machine(), platform.machine())
    original = (
        args.app
        or ROOT
        / "dist"
        / f"emberwood-kotlin-{version}-macos-{arch}"
        / "Emberwood Kotlin.app"
    ).resolve()
    tests = ROOT / "build/classes/kotlin/test"
    entry = {
        "performance": "PerformanceAudit.class",
        "audio": "AudioStateFixture.class",
        "controls": "NativeAuditKt.class",
        "controls-targeted": "NativeAuditKt.class",
        "controls-capture": "NativeAuditKt.class",
    }[args.audit]
    if not original.is_dir() or not (tests / "emberwood" / entry).is_file():
        parser.error("Build the native package and requested audit test classes first")
    selected = default_output()
    original_digest = tree_digest(original)
    runtime_digest = tree_digest(original / "Contents/runtime")
    jar_digest = hashlib.sha256(
        (original / "Contents/app/emberwood-kotlin.jar").read_bytes()
    ).hexdigest()
    evidence = {
        "launch_method": "LaunchServices open -W -n",
        "audit": args.audit,
        "original_app": str(original),
        "original_app_tree_sha256": original_digest,
        "game_jar_sha256": jar_digest,
        "original_runtime_sha256": runtime_digest,
        "selected_output": selected,
        "jfr": "Not enabled: the unchanged shipped runtime has no jdk.jfr module",
        "result": "INCOMPLETE",
    }
    if args.audit in FILTERED_CONTROLS:
        selected_filter, expected_cases = FILTERED_CONTROLS[args.audit]
        evidence.update(
            controls_filter=selected_filter,
            expected_filtered_cases=expected_cases,
            full_inventory_verified=False,
        )
    if args.capture_trace:
        evidence["capture_trace_directory"] = str(output / "capture-trace")
    if args.audit == "audio":
        evidence["audio_trace_directory"] = (
            str(output / "trace") if args.audio_trace else None
        )
    with (
        tempfile.TemporaryDirectory(prefix="emberwood native profile ") as temporary,
        ExitStack() as controllers,
    ):
        app = Path(temporary).resolve() / "Emberwood Kotlin.app"
        subprocess.run(["ditto", original, app], check=True)
        with (app / "Contents/Info.plist").open("rb") as stream:
            evidence["native_launcher"] = plistlib.load(stream)["CFBundleExecutable"]
        executable = app / "Contents/MacOS" / evidence["native_launcher"]
        controller = (
            controllers.enter_context(
                Controller(output, executable, capture_trace=args.capture_trace)
            )
            if args.audit != "audio"
            else None
        )
        configure_app(
            app,
            tests,
            output,
            args.soak_seconds,
            controller.path if controller else None,
            args.audit,
            audio_trace=args.audio_trace,
        )
        # Re-sign only the enclosing app: its already signed runtime stays identical.
        subprocess.run([ROOT / "tools/sign_mac_app.sh", app], check=True, timeout=90)
        if tree_digest(app / "Contents/runtime") != runtime_digest:
            raise RuntimeError("Copied private runtime changed during diagnostic setup")
        if (
            hashlib.sha256(
                (app / "Contents/app/emberwood-kotlin.jar").read_bytes()
            ).hexdigest()
            != jar_digest
        ):
            raise RuntimeError("Production game JAR changed during diagnostic setup")
        evidence["copied_runtime_identical"] = True
        record = output / "native-app.json"
        record.write_text(json.dumps(evidence, indent=2) + "\n")
        try:
            evidence["audit_completion"] = (
                launch_audio(app, output, jar_digest)
                if args.audit == "audio"
                else launch_profile(
                    app,
                    output,
                    args.soak_seconds + 360
                    if args.audit == "performance"
                    else 600
                    if args.audit in FILTERED_CONTROLS
                    else 2700,
                    controller,
                    args.audit,
                    args.soak_seconds,
                )
            )
            if (
                tree_digest(app / "Contents/runtime") != runtime_digest
                or hashlib.sha256(
                    (app / "Contents/app/emberwood-kotlin.jar").read_bytes()
                ).hexdigest()
                != jar_digest
            ):
                raise RuntimeError(
                    "Native audit changed production game or runtime bytes"
                )
            evidence["original_app_tree_sha256_after"] = tree_digest(original)
            if evidence["original_app_tree_sha256_after"] != original_digest:
                raise RuntimeError("Native audit changed original app tree")
            if args.audit == "audio":
                if args.audio_trace:
                    evidence["audio_trace_completion"] = validate_audio_trace(output)
                (output / "completion.json").write_text(
                    json.dumps(evidence["audit_completion"], indent=2) + "\n"
                )
            evidence["result"] = (
                "PARTIAL_PASS" if args.audit in FILTERED_CONTROLS else "PASS"
            )
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            subprocess.SubprocessError,
        ) as error:
            evidence["result"] = "FAIL"
            evidence["error"] = str(error)
            raise
        finally:
            active_error = sys.exc_info()[0] is not None
            cleanup_error = None
            if controller:
                try:
                    # End the helper and drain its trace before accepting evidence.
                    controllers.close()
                    evidence["external_controller_cleanup"] = "PASS"
                    if args.capture_trace:
                        evidence["capture_trace_completion"] = validate_capture_trace(
                            output, controller.pid
                        )
                except (
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                    subprocess.SubprocessError,
                ) as error:
                    cleanup_error = error
                    evidence["result"] = "FAIL"
                    evidence["external_controller_cleanup_error"] = str(error)
                    evidence.setdefault("error", str(error))
            if "original_app_tree_sha256_after" not in evidence:
                evidence["original_app_tree_sha256_after"] = tree_digest(original)
            record.write_text(json.dumps(evidence, indent=2) + "\n")
            if cleanup_error is not None and not active_error:
                raise cleanup_error
    if args.audit in FILTERED_CONTROLS:
        print(
            f"PARTIAL PASS: {FILTERED_CONTROLS[args.audit][1]} filtered rows; full inventory remains unverified"
        )
    else:
        print(f"PASS: copied native app completed the {args.audit} audit")


if __name__ == "__main__":
    main()
