"""Compare guarded source-JVM and native-app performance on the same Mac runner."""

import argparse
import hashlib
import json
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

from mac_app_profile import validate_completion
from mac_bundle_smoke import cleanup_app
from mac_profile_observer import NativeStatus
from mac_test_bridge import Controller
from package_integrity import tree_digest

ROOT = Path(__file__).resolve().parents[1]


def cleanup_raw(process, java, controller, baseline, output):
    errors = []
    try:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        errors.append(f"Child termination: {error}")
    try:
        controller.close()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        errors.append(f"Input/capture cleanup: {error}")
    try:
        cleanup_app(
            process.pid if process else None,
            java,
            controller.windows,
            baseline,
            output,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        errors.append(f"Native window cleanup: {error}")
    if errors:
        raise RuntimeError("; ".join(errors))


def raw_command(java, jar, tests, output, seconds, socket):
    return [
        str(java),
        "-Xms32m",
        "-Xmx128m",
        "-XX:ActiveProcessorCount=2",
        "--enable-native-access=ALL-UNNAMED",
        f"-Daudit.root={ROOT}",
        f"-Daudit.python={sys.executable}",
        f"-Daudit.inputSocket={socket}",
        f"-Dperformance.output={output}",
        f"-Dperformance.soakSeconds={seconds}",
        "-cp",
        f"{jar}:{tests}",
        "emberwood.PerformanceAudit",
    ]


def run_raw(java, jar, tests, output, seconds, controller):
    """Keep failed measurements, but never continue after uncertain cleanup."""
    (output / "completion.json").unlink(missing_ok=True)
    command = raw_command(java, jar, tests, output, seconds, controller.path)
    evidence = {
        "launch_method": "Direct private-JDK java process, as used by the source launcher",
        "command": command,
        "game_jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        "result": "INCOMPLETE",
        "limits": "128 MiB heap, two visible processors; unchanged audit thresholds",
        "jfr": "Not enabled; neither comparison path has recording overhead",
    }
    baseline = controller.windows.visible_registry()
    process = None
    rss_samples = []
    started = time.monotonic()

    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)

    previous = {
        kind: signal.signal(kind, interrupted)
        for kind in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        native = NativeStatus()
        with (
            (output / "app-stdout.log").open("w") as stdout,
            (output / "app-stderr.log").open("w") as stderr,
            (output / "native-process.jsonl").open("w", buffering=1) as log,
        ):
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            evidence["pid"] = process.pid
            controller.identify(process.pid)
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > seconds + 360:
                    raise TimeoutError("Raw-JVM profile did not finish in time")
                row = native.sample_and_wait(process.pid)
                row["elapsed_seconds"] = elapsed
                if row.get("resident_set_kib") is not None:
                    rss_samples.append(row["resident_set_kib"])
                log.write(json.dumps(row) + "\n")
            evidence["child_exit_code"] = process.wait()
            evidence["rss_sample_count"] = len(rss_samples)
            evidence["peak_sampled_resident_set_kib"] = max(rss_samples, default=None)
            evidence["rss_method"] = (
                "Exact-PID one-second samples; not an OS high-water mark"
            )
            log.write(
                json.dumps(
                    {
                        key: evidence[key]
                        for key in (
                            "pid",
                            "child_exit_code",
                            "rss_sample_count",
                            "peak_sampled_resident_set_kib",
                            "rss_method",
                        )
                    }
                )
                + "\n"
            )
        completion = output / "completion.json"
        if completion.is_file():
            evidence["audit_completion"] = json.loads(completion.read_text())
        if process.returncode:
            raise RuntimeError(f"Raw-JVM audit exited with {process.returncode}")
        validate_completion(evidence.get("audit_completion"), "performance", seconds)
        evidence["result"] = "PASS"
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        evidence["result"] = "FAIL"
        evidence["error"] = str(error)
    finally:
        for kind, handler in previous.items():
            signal.signal(kind, handler)
        try:
            cleanup_raw(process, java, controller, baseline, output)
            evidence["external_controller_cleanup"] = "PASS"
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            evidence["result"] = "FAIL"
            evidence["cleanup_error"] = str(error)
            raise RuntimeError(
                "Raw-JVM cleanup failed; native app must not launch"
            ) from error
        finally:
            (output / "raw-jvm.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def compare(java_home, output, seconds):
    output.mkdir(parents=True, exist_ok=True)
    record = output / "comparison.json"
    record.unlink(missing_ok=True)
    for name in ("raw-jvm", "native-app"):
        for marker in ("completion.json", f"{name}.json"):
            (output / name / marker).unlink(missing_ok=True)
    java = (java_home / "bin/java").resolve()
    jar = ROOT / "build/libs/emberwood-kotlin.jar"
    tests = ROOT / "build/classes/kotlin/test"
    if (
        not java.is_file()
        or not jar.is_file()
        or not (tests / "emberwood/PerformanceAudit.class").is_file()
    ):
        raise RuntimeError(
            "Build the game/test classes and prepare the private Java runtime first"
        )
    game_hash = hashlib.sha256(jar.read_bytes()).hexdigest()
    classes_hash = tree_digest(tests)
    evidence = {
        "result": "INCOMPLETE",
        "soak_seconds": seconds,
        "game_jar_sha256": game_hash,
        "test_classes_sha256": classes_hash,
        "source_java": str(java),
        "source_launcher": str(ROOT / "emberwood-kotlin"),
        "scope": "Same-runner launch-context comparison, not an uninstrumented campaign or all hardware",
    }
    try:
        raw_output = output / "raw-jvm"
        raw_output.mkdir(exist_ok=True)
        with Controller(raw_output, java) as controller:
            evidence["raw_jvm"] = run_raw(
                java, jar, tests, raw_output, seconds, controller
            )
        # run_raw only returns after owned-process and new-window cleanup pass.
        native_output = output / "native-app"
        native_output.mkdir(exist_ok=True)
        native_record = native_output / "native-app.json"
        native_record.unlink(missing_ok=True)
        with (native_output / "driver.log").open("w") as log:
            completed = subprocess.run(
                [
                    sys.executable,
                    ROOT / "tools/mac_app_profile.py",
                    "--output",
                    native_output,
                    "--soak-seconds",
                    str(seconds),
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        evidence["native_driver_exit_code"] = completed.returncode
        if not native_record.is_file():
            raise RuntimeError(
                "Native app comparison did not produce its provenance record"
            )
        native = json.loads(native_record.read_text())
        if not isinstance(native, dict):
            raise TypeError("Native app provenance must be an object")
        evidence["native_app"] = native
        if native.get("game_jar_sha256") != game_hash:
            raise RuntimeError("Source and native app used different production JARs")
        if (
            tree_digest(tests) != classes_hash
            or hashlib.sha256(jar.read_bytes()).hexdigest() != game_hash
        ):
            raise RuntimeError("Game or audit classes changed during the comparison")
        if completed.returncode or native.get("external_controller_cleanup") != "PASS":
            raise RuntimeError("Native app comparison or cleanup failed")
        validate_completion(native.get("audit_completion"), "performance", seconds)
        if evidence["raw_jvm"]["result"] != "PASS":
            raise RuntimeError(
                "Raw-JVM audit failed; its measurements remain authoritative"
            )
        evidence["result"] = "PASS"
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        evidence["result"] = "FAIL"
        evidence["error"] = str(error)
        raise
    finally:
        record.write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build/performance-launcher-comparison"
    )
    parser.add_argument("--soak-seconds", type=int, choices=(30, 180), default=180)
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run this diagnostic on macOS")
    compare(args.java_home.resolve(), args.output.resolve(), args.soak_seconds)
    print("PASS: source-JVM and native-app measurements both passed on this runner")


if __name__ == "__main__":
    main()
