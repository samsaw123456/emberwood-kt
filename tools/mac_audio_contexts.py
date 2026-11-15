"""Observe isolated AWT/audio startup contexts without any keyboard or mouse input."""

import argparse
import hashlib
import json
import os
import platform
import queue
import subprocess
import threading
import time
from pathlib import Path

from mac_audio_audit import capture_initialization_stacks
from mac_game_window import GameWindow

ROOT = Path(__file__).resolve().parents[1]
MODES = ("gui-only", "worker-only", "gui-first", "concurrent")


def take_snapshot(windows, pid, directory, label, require_window=False):
    record = {"pid": pid, "label": label}
    try:
        window = windows.find(pid)
        record["window"] = window
        subprocess.run(
            [
                "screencapture",
                "-x",
                "-o",
                "-l",
                str(window["id"]),
                directory / f"{label}-window.png",
            ],
            check=True,
            timeout=5,
        )
    except RuntimeError as error:
        record["window_unavailable"] = str(error)
        if require_window:
            raise
    finally:
        subprocess.run(
            ["screencapture", "-x", directory / f"{label}-desktop.png"],
            check=True,
            timeout=5,
        )
        (directory / f"{label}.json").write_text(json.dumps(record, indent=2) + "\n")


def stop_probe(process):
    """Request normal shutdown, then terminate only this child if it stalls."""
    attempts = []
    if process.poll() is None:
        try:
            process.stdin.write("quit\n")
            process.stdin.flush()
            attempts.append("protocol-quit")
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            process.terminate()
            attempts.append("terminate-owned-process")
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                attempts.append("kill-owned-process")
                process.wait(timeout=3)
    return {"attempts": attempts, "exit_code": process.returncode}


def observe_mode(mode, java, output, windows):
    directory = output / mode
    directory.mkdir(parents=True, exist_ok=True)
    baseline = windows.visible_registry()
    received = queue.Queue()
    result = {
        "mode": mode,
        "method": "No OS input; separate fresh JVM",
        "result": "INCOMPLETE",
    }
    command = [
        java,
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        os.pathsep.join(
            [
                str(ROOT / "build/libs/emberwood-kotlin.jar"),
                str(ROOT / "build/classes/kotlin/test"),
            ]
        ),
        "emberwood.MacAudioContextProbe",
        mode,
    ]
    with (directory / "app.log").open("w") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            bufsize=1,
        )
        result["pid"] = process.pid

        def read():
            for line in process.stdout:
                log.write(line)
                log.flush()
                received.put(line.rstrip("\n"))
            received.put(None)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()

        def receive(timeout=5):
            try:
                line = received.get(timeout=timeout)
            except queue.Empty as error:
                raise TimeoutError("Owned context probe did not respond") from error
            if line is None:
                raise RuntimeError("Owned context probe exited before replying")
            return line

        def request(command):
            process.stdin.write(command + "\n")
            process.stdin.flush()
            status = json.loads(receive())
            with (directory / "status.jsonl").open("a") as statuses:
                statuses.write(json.dumps(status) + "\n")
            if status.get("setup_error"):
                raise RuntimeError(status["setup_error"])
            return status

        try:
            if receive(10) != "READY":
                raise RuntimeError("Context probe did not become protocol-ready")
            if mode == "gui-first":
                deadline = time.monotonic() + 10
                while request("status").get("phase") != "window-visible":
                    if time.monotonic() > deadline:
                        raise TimeoutError(
                            "Empty JFrame never became visible; no audio start requested"
                        )
                    time.sleep(0.1)
                take_snapshot(
                    windows, process.pid, directory, "before-audio", require_window=True
                )
                request("start")
            deadline = time.monotonic() + 10
            while True:
                status = request("status")
                settled = (
                    status["window_created"]
                    if mode == "gui-only"
                    else status["audio"] in {"ready", "unavailable"}
                )
                if settled or time.monotonic() > deadline:
                    break
                time.sleep(0.1)
            result["observed_status"] = status
            # A native permission sheet may arrive after JFrame/audio readiness.
            time.sleep(3)
            take_snapshot(windows, process.pid, directory, "observed")
            capture_initialization_stacks(process.pid, directory)
            result["result"] = "CAPTURED"
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            result.update(result="FAIL", error=str(error))
            if process.poll() is None:
                try:
                    take_snapshot(windows, process.pid, directory, "failure")
                except (
                    OSError,
                    RuntimeError,
                    subprocess.SubprocessError,
                ) as capture_error:
                    result["failure_capture_error"] = str(capture_error)
                capture_initialization_stacks(process.pid, directory)
        finally:
            try:
                result["cleanup"] = stop_probe(process)
                reader.join(timeout=1)
                process.stdin.close()
                process.stdout.close()
                # Do not mistake a delayed dialog from this context for the next one.
                deadline = time.monotonic() + 3
                while True:
                    remaining = windows.visible_registry() - baseline
                    if not remaining or time.monotonic() >= deadline:
                        break
                    time.sleep(0.1)
                result["cleanup"]["new_windows_remaining"] = sorted(remaining)
                result["cleanup_safe"] = process.poll() is not None and not remaining
                subprocess.run(
                    ["screencapture", "-x", directory / "after-cleanup-desktop.png"],
                    check=True,
                    timeout=5,
                )
                if not result["cleanup_safe"]:
                    result.update(
                        result="FAIL",
                        error="New native windows remain after owned-process cleanup; subsequent contexts were not launched",
                    )
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                result.update(
                    result="FAIL", cleanup_safe=False, cleanup_error=str(error)
                )
            (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run the no-input context observations on macOS")
    java = Path(os.environ["JAVA_HOME"]) / "bin/java"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    windows = GameWindow()
    # Read-only preflight; never request or grant Screen Recording access.
    if not windows.core.CGPreflightScreenCaptureAccess():
        raise RuntimeError(
            "External screenshot access is unavailable; no context launched"
        )
    summary = {
        "order": MODES,
        "game_jar_sha256": hashlib.sha256(
            (ROOT / "build/libs/emberwood-kotlin.jar").read_bytes()
        ).hexdigest(),
        "physical_input": False,
        "permission_changes": False,
        "observations": [],
    }
    for mode in MODES:
        summary["observations"].append(observe_mode(mode, java, output, windows))
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        if not summary["observations"][-1].get("cleanup_safe", False):
            break
    if len(summary["observations"]) != len(MODES) or any(
        item["result"] != "CAPTURED" for item in summary["observations"]
    ):
        raise SystemExit(
            "Context observation failed; inspect retained own-PID stacks and screenshots"
        )


if __name__ == "__main__":
    main()
