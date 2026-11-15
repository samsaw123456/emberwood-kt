"""Observe bounded movement in the unchanged native MainKt app, without fixtures.

This diagnostic is deliberately limited to the Intel runner's observed standard
1152x676 window. It neither paints nor reads the Java model. A separate process
posts each key-up on a fixed deadline; screen capture cannot extend a key hold.
"""

import argparse
import hashlib
import json
import platform
import plistlib
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from linux_game_smoke import fox_center, stop_owned, title_visible
from mac_app_profile import app_pid, validate_capture_trace
from mac_application_menu import inspect_application_menu
from mac_audio_audit import capture_initialization_stacks
from mac_bundle_smoke import ImmediateMacKeys, cleanup_app, physical_command_quit
from mac_game_focus import require_game_window
from mac_game_window import GameWindow, NativeWindowMissing
from mac_profile_observer import NativeStatus
from mac_test_bridge import Controller
from package_integrity import tree_digest
from physical_key import CODES, NativeKeys

ROOT = Path(__file__).resolve().parents[1]
WINDOW_SIZE = (1152, 676)
CLIENT = (0, 28, 1152, 676)
ALLOWED_KEYS = {"return", "d", "a", "left"}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def owned_window(windows, pid, executable, window_id=None):
    if windows.executable(pid) != executable:
        raise RuntimeError("Input PID does not have the exact game executable")
    windows.facilities()
    window = windows.find(pid, title="Emberwood Kotlin")
    if window_id is not None and window["id"] != window_id:
        raise RuntimeError("The exact game window changed")
    if tuple(window["bounds"][2:]) != WINDOW_SIZE:
        raise RuntimeError(
            "This diagnostic requires the observed 1152x676 Intel window"
        )
    require_game_window(pid)
    return window


def await_owned_window(
    windows,
    pid,
    executable,
    launcher,
    output,
    *,
    timeout=30,
    clock=time.monotonic,
    sleep=time.sleep,
):
    """Only a missing window is transient; identity/access/modal errors abort."""
    deadline = clock() + timeout
    with (output / "startup-window-observations.jsonl").open("w") as log:
        while clock() < deadline:
            row = {"pid": pid, "monotonic": clock(), "epoch_ns": time.time_ns()}
            try:
                if launcher.poll() is not None:
                    raise RuntimeError("Native launcher exited before window readiness")
                row["executable"] = str(windows.executable(pid))
                if row["executable"] != str(executable):
                    raise RuntimeError("Startup PID does not have the exact executable")
                row["facilities"] = windows.facilities()
                try:
                    # Unfiltered lookup distinguishes absence from a wrong title.
                    row["candidate_window"] = windows.find(pid)
                except NativeWindowMissing as error:
                    row.update(result="WAIT missing window", error=str(error))
                else:
                    row["window"] = owned_window(windows, pid, executable)
                    row["result"] = "PASS owned ordinary window"
                    return row["window"]
            except Exception as error:
                row.update(result="FAIL", error=str(error))
                raise
            finally:
                log.write(json.dumps(row) + "\n")
                log.flush()
            sleep(min(0.1, max(0, deadline - clock())))
    raise RuntimeError("The exact game window did not become ready within the deadline")


def await_title(output, capture, *, timeout=10, clock=time.monotonic, sleep=time.sleep):
    """Wait for actual title pixels before allowing the first physical Return."""
    from PIL import Image

    deadline = clock() + timeout
    first = True
    with (output / "startup-title-observations.jsonl").open("w") as log:
        while clock() < deadline:
            path = capture("startup-title-latest")
            with Image.open(path) as frame:
                if frame.size != WINDOW_SIZE:
                    raise RuntimeError("Startup title capture changed size")
                visible = title_visible(frame.crop(CLIENT))
            row = {
                "monotonic": clock(),
                "epoch_ns": time.time_ns(),
                "title_visible": visible,
                "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "retention": "First pending and latest captured/accepted images are retained",
            }
            log.write(json.dumps(row) + "\n")
            log.flush()
            if visible:
                destination = output / "title.png"
                path.replace(destination)
                return destination
            if first:
                shutil.copyfile(path, output / "startup-title-first.png")
                first = False
            sleep(min(0.1, max(0, deadline - clock())))
    raise RuntimeError("The actual title pixels did not appear before the deadline")


def timed_hold(native, key, seconds, record, *, clock=time.monotonic, sleep=time.sleep):
    """No capture, filesystem work or blocking down-ack occurs inside the hold."""
    if key not in ALLOWED_KEYS or not 0.04 <= seconds <= 0.75:
        raise ValueError("Unsupported diagnostic hold")
    state = lambda: bool(native.core.CGEventSourceKeyState(0, CODES[key][1]))
    if state():
        raise RuntimeError("The requested key was already held")
    record.update(key=key, requested_seconds=seconds, down_observed=None)
    native.held.add(key)  # A posting failure can still follow a delivered down.
    began = clock()
    record["down_post_started"] = began
    record["down_epoch_ns"] = time.time_ns()
    deadline = began + seconds
    record["release_deadline"] = deadline
    try:
        record["down_post"] = native.post_mac([(key, "down")])
        record["down_post_finished"] = clock()
        while clock() < deadline:
            if record["down_observed"] is None and state():
                record["down_observed"] = clock()
            sleep(min(0.005, max(0, deadline - clock())))
    finally:
        record["up_post_started"] = clock()
        record["up_epoch_ns"] = time.time_ns()
        record["up_post"] = native.post_mac([(key, "up")])
        record["up_post_finished"] = clock()
        acknowledge_until = clock() + 1
        while state() and clock() < acknowledge_until:
            sleep(0.005)
        record["up_observed"] = clock() if not state() else None
        if record["up_observed"] is not None:
            native.held.discard(key)
        record["release_lateness_seconds"] = record["up_post_started"] - deadline
    if record["down_observed"] is None or record["up_observed"] is None:
        raise RuntimeError("Both physical key states were not observed")
    if not -0.002 <= record["release_lateness_seconds"] <= 0.05:
        raise RuntimeError("The fixed key-release deadline was missed")
    if record["up_observed"] - deadline > 0.05:
        raise RuntimeError("macOS acknowledged release after the bounded deadline")


def input_worker(raw):
    spec = json.loads(raw)
    record = {"result": "FAIL", "pid": spec["pid"], "window": spec["window"]}
    native = None

    def interrupted(_number, _frame):
        raise RuntimeError("Owned input worker was interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        owned_window(
            GameWindow(), spec["pid"], Path(spec["executable"]), spec["window"]
        )
        native = NativeKeys()
        print("READY", flush=True)
        if sys.stdin.readline().strip() != "GO":
            raise RuntimeError("No explicit start for the owned key hold")
        timed_hold(native, spec["key"], spec["seconds"], record)
        record["result"] = "PASS bounded physical hold"
    except Exception as error:
        record["error"] = str(error)
        raise
    finally:
        try:
            if native is not None:
                native.close(release=True)
        finally:
            write_json(Path(spec["output"]), record)


def run_hold(
    output, pid, executable, window, key, seconds, label, during=None, before_go=None
):
    destination = output / f"input-{label}.json"
    spec = {
        "pid": pid,
        "executable": str(executable),
        "window": window,
        "key": key,
        "seconds": seconds,
        "output": str(destination),
    }
    with (output / f"input-{label}.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--input-worker",
                json.dumps(spec),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
        )
        go_attempted = False
        try:
            if (
                not select.select([process.stdout], [], [], 10)[0]
                or process.stdout.readline().strip() != "READY"
            ):
                raise RuntimeError("Owned input worker did not become ready")
            if before_go is not None:
                before_go()  # Arm observation only after the worker's AX guard.
            go_attempted = True  # A failed flush can still follow delivered GO.
            process.stdin.write("GO\n")
            process.stdin.flush()
            if during is not None:
                time.sleep(0.12)
                during()  # Independent worker releases even if this capture stalls.
            process.wait(timeout=3)
            receipt = json.loads(destination.read_text())
            if (
                process.returncode
                or receipt.get("result") != "PASS bounded physical hold"
            ):
                raise RuntimeError(
                    f"Bounded physical {key} failed; inspect {destination.name}"
                )
            return receipt
        finally:
            # Do not kill a worker while it may own a down: its maximum hold and
            # acknowledgment budget is <2s. A stalled native call is a hard fail.
            if process.poll() is None:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        stop_owned(process)
                    finally:
                        if go_attempted:
                            emergency = NativeKeys()
                            try:
                                emergency.send([(key, "up")])
                            finally:
                                emergency.close()
            process.stdin.close()
            process.stdout.close()


def held_capture_callback(mode, capture, key):
    if mode == "snapshot":
        return lambda: capture(f"{key}-held-snapshot")
    if mode == "stream-only":
        return None  # Independent SCStream still records pixels during the hold.
    raise ValueError("Unknown held-capture mode")


class LiveSample:
    """Bounded native stack observation of the exact already-owned game PID."""

    def __init__(self, output, windows, pid, executable):
        self.output, self.windows = output, windows
        self.pid, self.executable = pid, executable
        self.process, self.log = None, None
        self.record = {
            "result": "NOT_STARTED",
            "pid": pid,
            "executable": str(executable),
            "scope": "Native sample only; adds observation overhead, not a performance measurement",
        }

    def start(self):
        if self.process is not None:
            raise RuntimeError("The owned native sample was already started")
        if self.windows.executable(self.pid) != self.executable:
            raise RuntimeError("Native sample PID does not have the exact executable")
        command = [
            "/usr/bin/sample",
            str(self.pid),
            "3",
            "1",
            "-file",
            str(self.output / "live-sample.txt"),
        ]
        self.record.update(
            result="RUNNING",
            argv=command,
            start_monotonic=time.monotonic(),
            start_epoch_ns=time.time_ns(),
        )
        try:
            self.log = (self.output / "live-sample.log").open("w")
            self.process = subprocess.Popen(
                command, stdout=self.log, stderr=subprocess.STDOUT
            )
            self.record["launched_monotonic"] = time.monotonic()
            self.record["sampler_pid"] = self.process.pid
        except Exception as error:
            self.record.update(result="FAIL", error=str(error))
            if self.log is not None:
                self.log.close()
            raise
        finally:
            write_json(self.output / "live-sample.json", self.record)

    def finish(self):
        if self.process is None or self.record["result"] != "RUNNING":
            return
        try:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.record["forced_sampler_cleanup"] = True
                stop_owned(self.process)
                raise RuntimeError("Owned native sample exceeded its bounded duration")
            self.record["returncode"] = self.process.returncode
            path = self.output / "live-sample.txt"
            if (
                self.process.returncode != 0
                or not path.is_file()
                or not path.stat().st_size
            ):
                raise RuntimeError(
                    "Owned native sample did not produce a successful trace"
                )
            self.record.update(
                result="PASS native sample captured",
                trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        except Exception as error:
            self.record.update(result="FAIL", error=str(error))
            raise
        finally:
            self.record.update(
                returncode=self.process.returncode,
                completion_observed_monotonic=time.monotonic(),
                completion_observed_epoch_ns=time.time_ns(),
            )
            self.log.close()
            write_json(self.output / "live-sample.json", self.record)


def observed_fox(path):
    from PIL import Image

    with Image.open(path) as original:
        if original.size != WINDOW_SIZE:
            raise RuntimeError(
                "Native capture changed size; no inferred rescaling is allowed"
            )
        client = original.convert("RGB").crop(CLIENT)
        # Grounded movement only. Exclude the chrome, HUD, footer and title fox.
        point = fox_center(client.crop((0, 170, 1152, 570)))
    if point is None:
        raise RuntimeError(
            "No opaque original-palette fox in the gameplay ground region"
        )
    return [point[0], point[1] + 170]


def validate_motion(before, released, rested):
    if not all(50 < point[0] < 450 for point in (before, released, rested)):
        raise RuntimeError("Movement reached an unsafe boundary or unexpected spawn")
    if before[0] - rested[0] < 50:
        raise RuntimeError("No independently visible screen-left travel")
    if abs(released[0] - rested[0]) > 6:
        raise RuntimeError("The fox did not recover to rest after key-up")
    if (
        max(point[1] for point in (before, released, rested))
        - min(point[1] for point in (before, released, rested))
        > 6
    ):
        raise RuntimeError(
            "Ground position changed; damage, jump or respawn cannot count as movement proof"
        )


def observe_recovery(mode, key, capture, *, sleep=time.sleep):
    released = None
    if mode == "snapshot":
        sleep(0.3)
        released = observed_fox(capture(f"{key}-released"))
        sleep(0.3 if key == "a" else 3.5)
    elif mode == "stream-only":
        # Keep AX/snapshot queries out of the complete held and early-recovery
        # interval; derive release pixels by PTS after the stream is drained.
        sleep(0.6 if key == "a" else 3.5)
    else:
        raise ValueError("Unknown held-capture mode")
    return released, observed_fox(capture(f"{key}-rested"))


def inspect_held_stream(output, movements):
    records = [
        json.loads(line)
        for line in (output / "capture-trace/frames.jsonl").read_text().splitlines()
    ]
    proof = []
    for movement in movements:
        receipt = movement["input"]
        # CPython's Mac monotonic clock and CM host time normally share Mach's
        # clock. Verify their epoch anchors instead of silently assuming that.
        nearest = min(
            records,
            key=lambda row: abs(
                row["receipt_unix_seconds"] - receipt["down_epoch_ns"] / 1e9
            ),
        )
        offset = nearest["receipt_host_seconds"] - nearest["receipt_unix_seconds"]
        difference = (
            receipt["down_epoch_ns"] / 1e9 + offset - receipt["down_post_started"]
        )
        if abs(difference) > 0.02:
            raise RuntimeError(
                "Input and stream clocks do not have a verified common origin"
            )
        low, high = receipt["down_post_finished"], receipt["up_post_started"]
        eligible = [
            row
            for row in records
            if row.get("image")
            and row.get("presentation_seconds") is not None
            and low <= row["presentation_seconds"] <= high
        ]
        observed = []
        for row in eligible:
            point = observed_fox(output / "capture-trace" / row["image"])
            observed.append(
                {
                    "frame": row["image"],
                    "pts": row["presentation_seconds"],
                    "fox": point,
                }
            )
        valid = [
            row
            for row in observed
            if 20 < movement["before"][0] - row["fox"][0] < 115
            and abs(row["fox"][1] - movement["before"][1]) <= 6
        ]
        proof.append(
            {
                "key": receipt["key"],
                "clock_anchor_difference_seconds": difference,
                "samples": observed,
                "held_motion_seen": bool(valid),
            }
        )
    write_json(output / "held-stream-proof.json", proof)
    if not all(row["held_motion_seen"] for row in proof):
        raise RuntimeError(
            "Held movement was not presented during every fixed input interval"
        )
    return proof


def inspect_released_stream(output, movements):
    """Require presented recovery pixels while the controller avoids AX polling."""
    records = [
        json.loads(line)
        for line in (output / "capture-trace/frames.jsonl").read_text().splitlines()
    ]
    proof = []
    for movement in movements:
        receipt = movement["input"]
        low, high = receipt["up_observed"] + 0.2, receipt["up_observed"] + 0.5
        observed = [
            {
                "frame": row["image"],
                "pts": row["presentation_seconds"],
                "fox": observed_fox(output / "capture-trace" / row["image"]),
            }
            for row in records
            if row.get("image")
            and row.get("presentation_seconds") is not None
            and low <= row["presentation_seconds"] <= high
        ]
        row = {"key": receipt["key"], "interval": [low, high], "samples": observed}
        proof.append(row)
        write_json(output / "released-stream-proof.json", proof)
        if not observed:
            raise RuntimeError(
                "No presented stream image in the early-release interval"
            )
        for sample in observed:
            validate_motion(movement["before"], sample["fox"], movement["rested"])
        movement["released"] = observed[0]["fox"]
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build/main-movement-native-app"
    )
    parser.add_argument(
        "--held-capture", choices=("snapshot", "stream-only"), default="snapshot"
    )
    parser.add_argument(
        "--live-sample",
        action="store_true",
        help="Start a bounded own-PID native sample immediately before Left GO",
    )
    parser.add_argument(
        "--inspect-app-menu",
        action="store_true",
        help="Physically inspect the application menu only after movement proof",
    )
    parser.add_argument("--input-worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run this native diagnostic on macOS")
    if args.input_worker:
        input_worker(args.input_worker)
        return
    from PIL import Image  # Fail before launch if the test-only dependency is absent.

    del Image
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Use a fresh output directory")
    output.mkdir(parents=True, exist_ok=True)
    arch = {"arm64": "aarch64"}.get(platform.machine(), platform.machine())
    version = (ROOT / "VERSION").read_text().strip()
    app = (
        args.app
        or ROOT / f"dist/emberwood-kotlin-{version}-macos-{arch}/Emberwood Kotlin.app"
    ).resolve()
    with (app / "Contents/Info.plist").open("rb") as stream:
        executable = (
            app / "Contents/MacOS" / plistlib.load(stream)["CFBundleExecutable"]
        )
    configs = list((app / "Contents/app").glob("*.cfg"))
    if (
        len(configs) != 1
        or configs[0].read_text().splitlines().count("app.mainclass=emberwood.MainKt")
        != 1
        or "native-audit.jar" in configs[0].read_text()
    ):
        parser.error("Expected the unchanged production MainKt launcher")
    original_hash = tree_digest(app)
    report = {
        "result": "FAIL",
        "full_inventory_verified": False,
        "visual_review": "UNVERIFIED",
        "app": str(app),
        "original_app_tree_sha256": original_hash,
        "production_sha256": hashlib.sha256(
            (app / "Contents/app/emberwood-kotlin.jar").read_bytes()
        ).hexdigest(),
        "client_crop": CLIENT,
        "window_size": WINDOW_SIZE,
        "movements": [],
        "held_capture": args.held_capture,
        "live_sample_requested": args.live_sample,
        "application_menu_requested": args.inspect_app_menu,
        "scope": "Bounded real MainKt observation; no nonce, fixture, Java agent, forced painting or rendering override. A pass cannot exclude an intermittent stall.",
    }
    windows, native = GameWindow(), NativeStatus()
    baseline = windows.visible_registry()
    if app_pid(native, app) is not None:
        raise RuntimeError(
            "The exact app is already running; it is not owned by this diagnostic"
        )
    pid, launcher, controller, sampler = None, None, None, None
    try:
        controller = Controller(
            output, executable, capture_trace=True, capture_image_interval=0.1
        )
        with tempfile.TemporaryDirectory(prefix="emberwood-main-save-") as data:
            command = ["open", "-W", "-n", str(app), "--args", "--data-dir", data]
            report["launcher_argv"] = command
            launcher = subprocess.Popen(command)
            deadline = time.monotonic() + 30
            while pid is None and time.monotonic() < deadline:
                pid = app_pid(native, app)
                if launcher.poll() is not None:
                    raise RuntimeError("Native launcher exited before startup")
                time.sleep(0.1)
            if pid is None:
                raise RuntimeError("The exact native app did not appear")
            report["pid"] = pid
            if args.live_sample:
                sampler = LiveSample(output, windows, pid, executable)
                report["live_sample"] = sampler.record
            window = await_owned_window(windows, pid, executable, launcher, output)
            report["window"] = window

            def ordinary_capture(label):
                owned_window(windows, pid, executable, window["id"])
                path = output / f"{label}.png"
                subprocess.run(
                    ["screencapture", "-x", "-o", "-l", str(window["id"]), str(path)],
                    check=True,
                    timeout=5,
                )
                return path

            await_title(output, ordinary_capture)
            run_hold(output, pid, executable, window["id"], "return", 0.08, "start")
            time.sleep(1.0)  # Initial invulnerability opacity ends without input.
            start = observed_fox(ordinary_capture("entry"))
            if not 120 < start[0] < 160 or not 490 < start[1] < 536:
                raise RuntimeError("Original entry ground/camp position is not visible")
            run_hold(output, pid, executable, window["id"], "d", 0.65, "prepare")
            time.sleep(0.3)
            before = observed_fox(ordinary_capture("prepared"))
            if not 270 < before[0] < 350 or abs(before[1] - start[1]) > 6:
                raise RuntimeError("D did not reach the original safe clearing")

            trace_started = time.monotonic()

            def capture(label):
                if time.monotonic() - trace_started > 10:
                    raise RuntimeError("Bounded active stream exceeded ten seconds")
                owned_window(windows, pid, executable, window["id"])
                path = output / f"{label}.png"
                controller.capture(pid, None, path)
                if time.monotonic() - trace_started > 10:
                    raise RuntimeError(
                        "Capture exceeded the bounded ten-second stream segment"
                    )
                return path

            before = observed_fox(capture("a-before"))
            for key in ("a", "left"):
                if time.monotonic() - trace_started > (4.5 if key == "left" else 1.5):
                    raise RuntimeError(
                        "Insufficient bounded stream time for the next command"
                    )
                receipt = run_hold(
                    output,
                    pid,
                    executable,
                    window["id"],
                    key,
                    0.35,
                    key,
                    held_capture_callback(args.held_capture, capture, key),
                    sampler.start if key == "left" and sampler is not None else None,
                )
                released, rested = observe_recovery(args.held_capture, key, capture)
                if released is not None:
                    validate_motion(before, released, rested)
                report["movements"].append(
                    {
                        "input": receipt,
                        "before": before,
                        "released": released,
                        "rested": rested,
                    }
                )
                before = rested
            controller.close()  # Drain the bounded stream before physical Quit.
            controller = None
            report["trace"] = validate_capture_trace(output, pid)
            summary = json.loads((output / "capture-trace/summary.json").read_text())
            if (
                summary.get("image_interval_seconds") != 0.1
                or summary.get("geometry_change") is not None
            ):
                raise RuntimeError("The fixed-window100ms stream scope changed")
            report["held_stream"] = inspect_held_stream(output, report["movements"])
            if args.held_capture == "stream-only":
                report["released_stream"] = inspect_released_stream(
                    output, report["movements"]
                )
            if sampler is not None:
                sampler.finish()
            if args.inspect_app_menu:
                report["application_menu"] = inspect_application_menu(
                    output / "application-menu", pid, executable, windows, window["id"]
                )
            owned_window(windows, pid, executable, window["id"])
            keyboard = NativeKeys()
            poster = ImmediateMacKeys(keyboard.core, keyboard.core)
            try:
                report["physical_quit"] = physical_command_quit(
                    keyboard.core, poster.key
                )
            finally:
                poster.close()
                keyboard.close()
            if not report["physical_quit"]["command_modifier_released"]:
                raise RuntimeError("Physical Command release was not observed")
            launcher.wait(timeout=10)
            report["launcher_returncode"] = launcher.returncode
            if launcher.returncode != 0:
                raise RuntimeError(
                    "The native launcher failed after physical Command+Q"
                )
            report["result"] = "PARTIAL_PASS awaiting visual review"
    except Exception as error:
        report["error"] = str(error)
        try:
            subprocess.run(
                ["screencapture", "-x", str(output / "failure-desktop.png")],
                check=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as capture_error:
            report["failure_capture_error"] = str(capture_error)
        try:
            if pid is not None and windows.executable(pid) == executable:
                capture_initialization_stacks(pid, output)
        except (OSError, RuntimeError, KeyError) as stack_error:
            report["failure_stack_error"] = str(stack_error)
        raise
    finally:
        try:
            if controller is not None:
                controller.close()
        except Exception as error:
            report["result"] = "FAIL"
            report["capture_cleanup_error"] = str(error)
            raise
        finally:
            try:
                if sampler is not None:
                    try:
                        sampler.finish()
                    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                        report["result"] = "FAIL"
                        report["live_sample_error"] = str(error)
                cleanup_app(pid, executable, windows, baseline, output)
                report["cleanup"] = json.loads((output / "cleanup.json").read_text())
                if report["result"] == "PARTIAL_PASS awaiting visual review" and (
                    report["cleanup"].get("signals") != []
                    or report["cleanup"].get("new_windows_remaining") != []
                ):
                    raise RuntimeError(
                        "Physical Quit needed fallback cleanup or left native windows"
                    )
            except Exception as error:
                report["result"] = "FAIL"
                report["native_cleanup_error"] = str(error)
                raise
            finally:
                if launcher is not None:
                    stop_owned(launcher)
                report["original_app_tree_sha256_after"] = tree_digest(app)
                if report["original_app_tree_sha256_after"] != original_hash:
                    report["result"] = "FAIL"
                    report["provenance_error"] = "Original app changed"
                report["frames"] = [
                    {
                        "path": path.relative_to(output).as_posix(),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                    for path in sorted(output.rglob("*.png"))
                ]
                write_json(output / "result.json", report)
        if report["result"] != "PARTIAL_PASS awaiting visual review":
            raise RuntimeError(
                report.get(
                    "error", report.get("provenance_error", "Native Main probe failed")
                )
            )


if __name__ == "__main__":
    main()
