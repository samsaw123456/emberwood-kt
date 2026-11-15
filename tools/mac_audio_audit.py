"""Verify Mac game output with app-only capture and physical keys and mouse clicks."""

import argparse
import ctypes
import hashlib
import json
import os
import platform
import select
import subprocess
import tempfile
import time
from pathlib import Path

from audio_audit import audit_states, read_pcm
from mac_game_focus import NativeFocusUnavailable, require_game_window

ROOT = Path(__file__).resolve().parents[1]


class CaptureUnavailable(RuntimeError):
    pass


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


def capture_initialization_stacks(pid, output):
    """Read only the spawned game's stacks, never properties or environment."""
    commands = {
        "java-threads": [
            Path(os.environ["JAVA_HOME"]) / "bin/jcmd",
            str(pid),
            "Thread.print",
            "-l",
        ],
        "native-sample": [
            "/usr/bin/sample",
            str(pid),
            "1",
            "1",
            "-file",
            output / "native-sample.txt",
        ],
    }
    results = {}
    for label, command in commands.items():
        with (output / f"{label}.log").open("w") as log:
            try:
                result = subprocess.run(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=15,
                )
                results[label] = {"exit_code": result.returncode}
            except (OSError, subprocess.TimeoutExpired) as error:
                results[label] = {"result": "UNVERIFIED", "reason": str(error)}
    (output / "initialization-stack-results.json").write_text(
        json.dumps(results, indent=2) + "\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/audio-audit-macos"))
    parser.add_argument(
        "--java", type=Path, help="Java executable; defaults to JAVA_HOME/bin/java"
    )
    parser.add_argument(
        "--jar", type=Path, default=ROOT / "build/libs/emberwood-kotlin.jar"
    )
    parser.add_argument(
        "--output-mixer",
        help="Diagnostic: exact physical output mixer selected by native output-only discovery",
    )
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run this native output audit on macOS.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    java = (args.java or Path(os.environ["JAVA_HOME"]) / "bin/java").resolve()
    jar = args.jar.resolve()
    classes = ROOT / "build/classes/kotlin/test"
    if not java.is_file() or not jar.is_file() or not classes.is_dir():
        parser.error(
            "Build the requested runtime, game JAR and test classes before auditing audio."
        )
    summary = {
        "method": "ScreenCaptureKit whitelist containing only the launched game PID",
        "microphone": False,
        "global_audio_fallback": False,
        "game_jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        "java_executable": str(java),
        "game_jar": str(jar),
        "diagnostic_output_mixer": args.output_mixer,
        "result": "UNVERIFIED",
        "reason": "Native capture helper has not completed",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    helper = output / "mac-audio-capture"
    command = [
        "xcrun",
        "swiftc",
        "-swift-version",
        "5",
        "-parse-as-library",
        "-warnings-as-errors",
        "-O",
        "-target",
        f"{platform.machine()}-apple-macosx15.0",
        str(ROOT / "tools/mac_audio_capture.swift"),
        "-o",
        str(helper),
    ]
    with (output / "compile.log").open("w") as log:
        result = subprocess.run(
            command, check=False, stdout=log, stderr=subprocess.STDOUT
        )
    if result.returncode:
        summary["reason"] = "Native capture helper did not compile; see compile.log"
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print((output / "compile.log").read_text())
        raise CaptureUnavailable("Native capture helper did not compile")
    core = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    foundation = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    core.CGEventCreateKeyboardEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ushort,
        ctypes.c_bool,
    ]
    core.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    core.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    core.CGEventPost.restype = None
    core.CGEventCreateMouseEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        Point,
        ctypes.c_uint32,
    ]
    core.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    foundation.CFRelease.argtypes = [ctypes.c_void_p]
    foundation.CFRelease.restype = None
    held = set()
    keys = {"m": 46, "Return": 36, "space": 49, "KP_Enter": 76, "Tab": 48}

    def key(name, down):
        if down:
            require_game_window(app.pid)
        event = core.CGEventCreateKeyboardEvent(None, keys[name], down)
        if not event:
            raise RuntimeError("macOS did not create the physical key event")
        try:
            core.CGEventPost(0, event)
            if down:
                held.add(name)
            else:
                held.discard(name)
        finally:
            foundation.CFRelease(event)

    def click(x, y):
        require_game_window(app.pid)
        for kind in (
            5,
            1,
            2,
        ):  # Move, left down, left up at the fixture's screen point.
            event = core.CGEventCreateMouseEvent(None, kind, Point(x, y), 0)
            if not event:
                raise RuntimeError("macOS did not create the physical mouse event")
            try:
                core.CGEventPost(0, event)
            finally:
                foundation.CFRelease(event)
            time.sleep(0.04)

    def record(pid, directory, label, action):
        path = directory / f"{label}.wav"
        with (directory / f"{label}-capture.log").open("w") as capture_log:
            capture = subprocess.Popen(
                [helper, str(pid), path],
                stdout=subprocess.PIPE,
                stderr=capture_log,
                text=True,
                bufsize=1,
            )
            try:
                ready, _, _ = select.select([capture.stdout], [], [], 20)
                if not ready or capture.stdout.readline().strip() != "READY":
                    raise CaptureUnavailable(
                        f"Game-only native capture did not start; see {label}-capture.log"
                    )
                action()
                stdout, _ = capture.communicate(timeout=10)
                capture_log.write(stdout)
                if capture.returncode != 0:
                    raise CaptureUnavailable(
                        f"Native PCM window was incomplete; see {label}-capture.log"
                    )
                return read_pcm(path, capture.returncode)
            finally:
                if capture.poll() is None:
                    capture.terminate()
                    capture.wait(timeout=5)

    with (
        tempfile.TemporaryDirectory(prefix="emberwood-mac-audio-") as data,
        (output / "app.log").open("w") as log,
    ):
        app = subprocess.Popen(
            [
                java,
                "-Xms32m",
                "-Xmx256m",
                "--enable-native-access=ALL-UNNAMED",
                *(
                    [f"-Djavax.sound.sampled.SourceDataLine=#{args.output_mixer}"]
                    if args.output_mixer
                    else []
                ),
                "-cp",
                os.pathsep.join((str(jar), str(classes))),
                "emberwood.AudioStateFixture",
                "--data-dir",
                data,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            bufsize=1,
        )
        summary["game_pid"] = app.pid
        try:
            audit_states(
                app,
                log,
                key,
                app.pid,
                output,
                record_audio=record,
                method="fixture states and original cues; physical macOS keys/mouse; game-only captured PCM",
                click=click,
            )
            summary["result"] = "PASS"
            summary.pop("reason", None)
        except (CaptureUnavailable, NativeFocusUnavailable) as error:
            summary.update(result="UNVERIFIED", reason=str(error))
            raise
        except Exception as error:
            summary.update(result="FAIL", reason=str(error))
            raise
        finally:
            (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            for name in list(held):
                key(name, False)
            if app.poll() is None and "finish initialization" in summary.get(
                "reason", ""
            ):
                capture_initialization_stacks(app.pid, output)
            if app.poll() is None:
                app.stdin.close()
                try:
                    app.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    app.terminate()
                    app.wait(timeout=5)


if __name__ == "__main__":
    main()
