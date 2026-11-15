"""Audit an isolated LaunchServices app copy with its exact shipped JVM and game."""

import argparse
import ctypes
import hashlib
import json
import os
import platform
import plistlib
import signal
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import ExitStack
from pathlib import Path

from diagnose_mac_output import default_output
from mac_profile_observer import NativeStatus
from mac_test_bridge import Controller
from package_integrity import tree_digest

ROOT = Path(__file__).resolve().parents[1]
TARGETED_CONTROLS_FILTER = r"^PLAYING/(A|D|Left|Right|←|→)$|/M$|/left-shift facing |/right-shift facing |/Release .* while unfocused$"
TARGETED_CONTROLS_CASES = (
    26  # 4 direction + 6 mute + 4 dash + 11 focus/release + lifecycle.
)


def configure_app(app, tests, output, seconds, input_socket, audit="performance"):
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
                f"-Dperformance.output={output}",
                f"-Dperformance.soakSeconds={seconds}",
            ]
        )
    elif audit in {"controls", "controls-targeted"}:
        main_class = "emberwood.NativeAuditKt"
        options.append(f"-Daudit.output={output}")
        if audit == "controls-targeted":
            options.append(f"-Daudit.filter={TARGETED_CONTROLS_FILTER}")
    elif audit == "audio":
        main_class = "emberwood.AudioStateFixture"
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
        # An exited child has no proc_pidpath. A live unidentified PID is never killed.
        try:
            os.kill(candidate, 0)
        except ProcessLookupError:
            return None
        raise
    return candidate if executable == controller.executable else None


def validate_completion(result, audit, seconds):
    if not isinstance(result, dict) or result.get("result") != "PASS":
        raise RuntimeError("Native audit failed; inspect completion.json")
    required = {"result", "exception"}
    if audit in {"controls", "controls-targeted"}:
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
    if audit in {"controls", "controls-targeted"}:
        targeted = audit == "controls-targeted"
        if (
            result.get("cases") != (TARGETED_CONTROLS_CASES if targeted else 280)
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
                    controller.identify(pid)
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
        if process.returncode:
            raise RuntimeError(f"LaunchServices exited with {process.returncode}")
        completion = output / "completion.json"
        if not completion.is_file():
            raise RuntimeError("Native audit ended without its completion record")
        result = json.loads(completion.read_text())
        validate_completion(result, audit, seconds)
        if not pid:
            raise RuntimeError(
                "Audit reported success but no native app PID was observed"
            )
        return result
    finally:
        for kind, handler in previous.items():
            signal.signal(kind, handler)
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
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit",
        choices=("performance", "controls", "controls-targeted"),
        default="performance",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--soak-seconds", type=int, default=30)
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run this diagnostic on macOS")
    if not 30 <= args.soak_seconds <= 1800:
        parser.error("Soak duration must be between 30 and 1800 seconds")
    output = (args.output or ROOT / "build" / f"{args.audit}-native-app").resolve()
    if "\n" in str(output) or "\r" in str(output):
        parser.error("Output path cannot contain a line break")
    output.mkdir(parents=True, exist_ok=True)
    (output / "completion.json").unlink(missing_ok=True)
    version = (ROOT / "VERSION").read_text().strip()
    arch = {"arm64": "aarch64"}.get(platform.machine(), platform.machine())
    original = ROOT / "dist" / f"emberwood-kotlin-{version}-macos-{arch}"
    original /= "Emberwood Kotlin.app"
    tests = ROOT / "build/classes/kotlin/test"
    if (
        not original.is_dir()
        or not (
            tests
            / "emberwood"
            / (
                "PerformanceAudit.class"
                if args.audit == "performance"
                else "NativeAuditKt.class"
            )
        ).is_file()
    ):
        parser.error("Build the native package and performance test classes first")
    selected = default_output()
    runtime_digest = tree_digest(original / "Contents/runtime")
    jar_digest = hashlib.sha256(
        (original / "Contents/app/emberwood-kotlin.jar").read_bytes()
    ).hexdigest()
    evidence = {
        "launch_method": "LaunchServices open -W -n",
        "audit": args.audit,
        "game_jar_sha256": jar_digest,
        "original_runtime_sha256": runtime_digest,
        "selected_output": selected,
        "jfr": "Not enabled: the unchanged shipped runtime has no jdk.jfr module",
        "result": "INCOMPLETE",
    }
    if args.audit == "controls-targeted":
        evidence.update(
            controls_filter=TARGETED_CONTROLS_FILTER,
            expected_filtered_cases=TARGETED_CONTROLS_CASES,
            full_inventory_verified=False,
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
        controller = controllers.enter_context(Controller(output, executable))
        configure_app(
            app, tests, output, args.soak_seconds, controller.path, args.audit
        )
        # Re-sign only the enclosing app: its already signed runtime stays identical.
        subprocess.run(["codesign", "--force", "--sign", "-", app], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", app], check=True)
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
            evidence["audit_completion"] = launch_profile(
                app,
                output,
                args.soak_seconds + 360
                if args.audit == "performance"
                else 600
                if args.audit == "controls-targeted"
                else 2700,
                controller,
                args.audit,
                args.soak_seconds,
            )
            controller.close()
            evidence["external_controller_cleanup"] = "PASS"
            evidence["result"] = (
                "PARTIAL_PASS" if args.audit == "controls-targeted" else "PASS"
            )
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            evidence["result"] = "FAIL"
            evidence["error"] = str(error)
            raise
        finally:
            record.write_text(json.dumps(evidence, indent=2) + "\n")
    if args.audit == "controls-targeted":
        print(
            f"PARTIAL PASS: {TARGETED_CONTROLS_CASES} filtered rows; full inventory remains unverified"
        )
    else:
        print(f"PASS: copied native app completed the {args.audit} audit")


if __name__ == "__main__":
    main()
