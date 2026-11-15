"""Acknowledge only the game's deliberately induced native-access startup error.

An isolated app copy keeps the production JAR/runtime and signing policy. The
only launcher change denies unnamed-module native access. Read-only kqueue
receipts establish the actual app exit status; open -W is not that status.
"""

import argparse
import ctypes
import hashlib
import json
import os
import platform
import plistlib
import select
import subprocess
import tempfile
import time
from pathlib import Path

from linux_game_smoke import stop_owned
from mac_app_profile import app_pid
from mac_application_menu import MenuReader
from mac_bundle_smoke import cleanup_app
from mac_game_window import GameWindow, NativeWindowMissing
from mac_profile_observer import NativeStatus
from package_integrity import tree_digest
from physical_key import CODES, NativeKeys

ROOT = Path(__file__).resolve().parents[1]
ERROR_TITLE = "Emberwood Kotlin could not start"
ERROR_MESSAGE = (
    "Emberwood Kotlin could not finish starting. "
    "Close this message and try launching the app again."
)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def deny_native_access(app):
    configs = list((app / "Contents/app").glob("*.cfg"))
    if len(configs) != 1:
        raise RuntimeError("Expected exactly one native launcher configuration")
    path = configs[0]
    lines = path.read_text().splitlines()
    grant = "java-options=--enable-native-access=ALL-UNNAMED"
    if (
        lines.count("app.mainclass=emberwood.MainKt") != 1
        or lines.count("[JavaOptions]") != 1
        or lines.count(grant) != 1
        or any("native-access" in line and line != grant for line in lines)
        or any("native-audit.jar" in line for line in lines)
    ):
        raise RuntimeError("Expected the unchanged production native-access policy")
    before = path.read_bytes()
    lines.remove(grant)
    lines.insert(
        lines.index("[JavaOptions]") + 1, "java-options=--illegal-native-access=deny"
    )
    path.write_text("\n".join(lines) + "\n")
    return {
        "path": path.name,
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "removed": grant,
        "added": "java-options=--illegal-native-access=deny",
    }


class ExitStatus:
    """Observe one owned PID; registration cannot signal or change the process."""

    def __init__(self, pid, *, api=select):
        if type(pid) is not int or pid <= 0:
            raise ValueError("Expected the exact positive app PID")
        if not hasattr(api, "kqueue") or not hasattr(api, "kevent"):
            raise RuntimeError(
                "Native kqueue exit status is unavailable; acknowledgement remains unverified"
            )
        self.pid, self.api = pid, api
        self.observations = []
        # Apple's public sys/event.h: allowed for a child or same-user process
        # we may signal. Python does not expose NOTE_EXITSTATUS on every build.
        self.exit_status = getattr(api, "KQ_NOTE_EXITSTATUS", 0x04000000)
        self.queue = api.kqueue()
        try:
            event = api.kevent(
                pid,
                filter=api.KQ_FILTER_PROC,
                flags=api.KQ_EV_ADD
                | api.KQ_EV_ENABLE
                | api.KQ_EV_ONESHOT
                | getattr(api, "KQ_EV_RECEIPT", 0x0040),
                fflags=api.KQ_NOTE_EXIT | self.exit_status,
            )
            receipt = self.queue.control([event], 1, 0)
            if (
                len(receipt) != 1
                or receipt[0].ident != pid
                or receipt[0].filter != api.KQ_FILTER_PROC
                or not receipt[0].flags & api.KQ_EV_ERROR
                or receipt[0].data != 0
            ):
                raise RuntimeError(
                    "Could not register exact-PID kernel exit-status observation"
                )
            self.registration = self.describe(receipt[0])
        except BaseException:
            self.queue.close()
            raise

    @staticmethod
    def describe(event):
        return {
            name: getattr(event, name)
            for name in ("ident", "filter", "flags", "fflags", "data")
        }

    def wait(self, timeout=10):
        events = self.queue.control([], 1, timeout)
        if len(events) != 1:
            raise RuntimeError(
                "No actual app exit status arrived; exit remains unverified"
            )
        event = events[0]
        record = self.describe(event)
        self.observations.append(record)
        if (
            event.ident != self.pid
            or event.filter != self.api.KQ_FILTER_PROC
            or event.flags & self.api.KQ_EV_ERROR
            or event.fflags & (self.api.KQ_NOTE_EXIT | self.exit_status)
            != self.api.KQ_NOTE_EXIT | self.exit_status
        ):
            raise RuntimeError(f"Incomplete/wrong-PID native exit receipt: {record}")
        record["normal_exit"] = os.WIFEXITED(event.data)
        record["exit_code"] = (
            os.WEXITSTATUS(event.data) if record["normal_exit"] else None
        )
        if not record["normal_exit"] or record["exit_code"] != 1:
            raise RuntimeError(f"Expected actual app exit1 without a signal: {record}")
        return record

    def close(self):
        self.queue.close()


class ErrorDialogReader(MenuReader):
    """Reuse CF/AX decoding only; no application-menu lookup or activation occurs."""

    def snapshot(self):
        app = self.ax.AXUIElementCreateApplication(self.pid)
        if not app:
            raise RuntimeError("Owned error-dialog application is unavailable")
        try:
            owner = ctypes.c_int()
            if (
                self.ax.AXUIElementGetPid(app, ctypes.byref(owner))
                or owner.value != self.pid
            ):
                raise RuntimeError("Error dialog belongs to another process")
            if self.ax.AXUIElementSetMessagingTimeout(app, 1.0):
                raise RuntimeError("Could not bound error-dialog reads")
            with self.attribute(app, "AXFocusedWindow") as window:
                state = {
                    "pid": self.pid,
                    "frontmost": self.scalar(app, "AXFrontmost", "bool"),
                    "role": self.scalar(window, "AXRole", "text"),
                    "subrole": self.scalar(window, "AXSubrole", "text"),
                    "title": self.scalar(window, "AXTitle", "text"),
                    "modal": self.scalar(window, "AXModal", "bool"),
                    "texts": [],
                    "buttons": [],
                    "nodes": 0,
                }
                self.read_nodes(window, state, 0)
                return state
        finally:
            self.cf.CFRelease(app)

    def read_nodes(self, element, state, depth):
        state["nodes"] += 1
        if depth > 10 or state["nodes"] > 100:
            raise RuntimeError("Unexpectedly large startup-error accessibility tree")
        role = self.scalar(element, "AXRole", "text")
        if role == "AXStaticText":
            value = self.scalar(element, "AXValue", "text", optional=True)
            title = self.scalar(element, "AXTitle", "text", optional=True)
            state["texts"].extend(value for value in (value, title) if value)
            return
        if role == "AXButton":
            state["buttons"].append(
                {
                    "title": self.scalar(element, "AXTitle", "text", optional=True),
                    # JDK's ButtonAccessibility exposes accessibilityLabel, whose
                    # public AX attribute is AXDescription, rather than AXTitle.
                    "description": self.scalar(
                        element, "AXDescription", "text", optional=True
                    ),
                    "subrole": self.scalar(element, "AXSubrole", "text", optional=True),
                    "enabled": self.scalar(element, "AXEnabled", "bool"),
                }
            )
            return
        with self.attribute(element, "AXChildren", optional=True) as array:
            if array is None:
                return
            if self.cf.CFGetTypeID(array) != self.cf.CFArrayGetTypeID():
                raise RuntimeError("Unexpected error-dialog children type")
            count = self.cf.CFArrayGetCount(array)
            if not 0 <= count <= 64:
                raise RuntimeError("Unexpectedly large error-dialog child list")
            for index in range(count):
                self.read_nodes(
                    self.cf.CFArrayGetValueAtIndex(array, index), state, depth + 1
                )


def validate_dialog(state):
    texts = [" ".join(text.split()) for text in state["texts"]]
    chrome = {"AXCloseButton", "AXZoomButton", "AXMinimizeButton"}
    content_buttons = [
        button for button in state["buttons"] if button.get("subrole") not in chrome
    ]
    labels = (
        {
            value
            for key in ("title", "description")
            if (value := content_buttons[0].get(key))
        }
        if len(content_buttons) == 1
        else set()
    )
    if (
        state["frontmost"] is not True
        or state["role"] != "AXWindow"
        or state["title"] != ERROR_TITLE
        or ERROR_MESSAGE not in texts
        or len(content_buttons) != 1
        or labels != {"OK"}
        or content_buttons[0]["enabled"] is not True
    ):
        raise RuntimeError(
            "Not the exact owned startup-error message/OK dialog; no acknowledgement sent"
        )


def validate_denial(log):
    required = (
        "Unable to prepare the application menu",
        "java.lang.IllegalCallerException: Illegal native access from an unnamed module",
        "emberwood.CocoaMenuApi",
    )
    if not all(text in log for text in required):
        raise RuntimeError(
            "The error log does not prove the induced native-menu access denial"
        )


def await_error(windows, reader, pid, executable, launcher, output):
    deadline = time.monotonic() + 30
    observations = []
    try:
        while time.monotonic() < deadline:
            row = {"monotonic": time.monotonic(), "pid": pid}
            observations.append(row)
            if launcher.poll() is not None:
                raise RuntimeError(
                    "App exited before its expected startup-error dialog"
                )
            if windows.executable(pid) != executable:
                raise RuntimeError("Startup-error PID changed executable")
            row["facilities"] = windows.facilities()
            try:
                window = windows.find(pid)
            except NativeWindowMissing:
                row["result"] = "WAIT missing owned window"
                time.sleep(0.1)
                continue
            row["window"] = window
            if window["title"] != ERROR_TITLE:
                raise RuntimeError(
                    "Unexpected owned window; no error acknowledgement sent"
                )
            row["dialog"] = reader.snapshot()
            try:
                validate_dialog(row["dialog"])
                validate_denial((output / "app-stderr.log").read_text())
            except RuntimeError as error:
                row.update(result="FAIL before acknowledgement", error=str(error))
                raise
            row["result"] = "PASS exact induced error"
            return window, row["dialog"]
        raise RuntimeError("Expected startup-error dialog did not appear")
    finally:
        write_json(output / "error-observations.json", observations)


def acknowledge_error(windows, reader, pid, executable, window_id, status, receipt):
    if windows.executable(pid) != executable:
        raise RuntimeError("Startup-error PID changed executable before Return")
    windows.facilities()
    window = windows.find(pid, title=ERROR_TITLE)
    if window["id"] != window_id:
        raise RuntimeError("The exact startup-error window changed")
    dialog = reader.snapshot()
    receipt.update(dialog_before_Return=dialog, down_started=None)
    validate_dialog(dialog)
    keyboard = NativeKeys()
    try:
        if keyboard.core.CGEventSourceKeyState(0, CODES["return"][1]):
            raise RuntimeError("Return is already held; no acknowledgement sent")
        receipt["down_started"] = time.monotonic()
        keyboard.send([("return", "down")])
        time.sleep(0.08)
    finally:
        keyboard.close(release=True)
        receipt["up_observed"] = not keyboard.core.CGEventSourceKeyState(
            0, CODES["return"][1]
        )
        receipt["release_finished"] = time.monotonic()
    if not receipt["up_observed"]:
        raise RuntimeError("Physical Return release was not observed")
    receipt["app_exit"] = status.wait()
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build/startup-failure-native-app"
    )
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run this native failure probe on macOS")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    arch = {"arm64": "aarch64"}.get(platform.machine(), platform.machine())
    version = (ROOT / "VERSION").read_text().strip()
    original = (
        args.app
        or ROOT / f"dist/emberwood-kotlin-{version}-macos-{arch}/Emberwood Kotlin.app"
    ).resolve()
    original_hash = tree_digest(original)
    runtime_hash = tree_digest(original / "Contents/runtime")
    jar_hash = hashlib.sha256(
        (original / "Contents/app/emberwood-kotlin.jar").read_bytes()
    ).hexdigest()
    report = {
        "result": "FAIL",
        "visual_review": "UNVERIFIED",
        "original_app": str(original),
        "original_app_tree_sha256": original_hash,
        "runtime_sha256": runtime_hash,
        "production_sha256": jar_hash,
        "physical_acknowledgement": "UNVERIFIED",
        "actual_app_exit": "UNVERIFIED",
        "scope": "Isolated native-access denial; no production test hook or permission acknowledgement",
    }
    with tempfile.TemporaryDirectory(prefix="emberwood startup failure ") as temporary:
        app = Path(temporary).resolve() / "Emberwood Kotlin.app"
        pid, launcher, status = None, None, None
        windows = GameWindow()
        baseline = windows.visible_registry()
        executable = None
        try:
            subprocess.run(["ditto", original, app], check=True, timeout=90)
            report["configuration"] = deny_native_access(app)
            with (app / "Contents/Info.plist").open("rb") as stream:
                executable = (
                    app / "Contents/MacOS" / plistlib.load(stream)["CFBundleExecutable"]
                )
            with (output / "signing.log").open("w") as log:
                subprocess.run(
                    [ROOT / "tools/sign_mac_app.sh", app],
                    check=True,
                    timeout=90,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            if (
                tree_digest(app / "Contents/runtime") != runtime_hash
                or hashlib.sha256(
                    (app / "Contents/app/emberwood-kotlin.jar").read_bytes()
                ).hexdigest()
                != jar_hash
            ):
                raise RuntimeError("Native failure setup changed runtime or game bytes")
            report["copied_app_tree_sha256"] = tree_digest(app)
            native = NativeStatus()
            if app_pid(native, app) is not None:
                raise RuntimeError("The isolated native app is already running")
            command = [
                "open",
                "-W",
                "-n",
                "--stdout",
                str(output / "app-stdout.log"),
                "--stderr",
                str(output / "app-stderr.log"),
                str(app),
                "--args",
                "--data-dir",
                str(Path(temporary) / "save"),
            ]
            report["launcher_argv"] = command
            launcher = subprocess.Popen(command)
            deadline = time.monotonic() + 30
            while pid is None and time.monotonic() < deadline:
                if launcher.poll() is not None:
                    raise RuntimeError(
                        "Native app launcher exited before owned PID observation"
                    )
                pid = app_pid(native, app)
                time.sleep(0.1)
            if pid is None or windows.executable(pid) != executable:
                raise RuntimeError(
                    "The exact isolated native app PID was not established"
                )
            report["pid"] = pid
            status = ExitStatus(pid)
            report["exit_status_registration"] = status.registration
            reader = ErrorDialogReader(pid)
            window, report["dialog"] = await_error(
                windows, reader, pid, executable, launcher, output
            )
            subprocess.run(
                ["screencapture", "-x", output / "startup-error-desktop.png"],
                check=True,
                timeout=5,
            )
            report["acknowledgement"] = {}
            acknowledge_error(
                windows,
                reader,
                pid,
                executable,
                window["id"],
                status,
                report["acknowledgement"],
            )
            report["physical_acknowledgement"] = "PASS Return and release"
            report["actual_app_exit"] = report["acknowledgement"]["app_exit"]
            launcher.wait(timeout=10)
            report["launchservices_exit_code"] = launcher.returncode
            # Kernel exit1 is the app result; LaunchServices success is recorded separately.
            if launcher.returncode != 0:
                raise RuntimeError(
                    "LaunchServices itself failed after app acknowledgement"
                )
            report["result"] = (
                "PASS physical error acknowledgement and actual app exit1; visual review pending"
            )
        except Exception as error:
            report["error"] = str(error)
            try:
                subprocess.run(
                    ["screencapture", "-x", output / "failure-desktop.png"],
                    check=True,
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError) as capture_error:
                report["capture_error"] = str(capture_error)
            raise
        finally:
            try:
                try:
                    if status is not None:
                        report["exit_observations"] = status.observations
                        status.close()
                finally:
                    if executable is not None:
                        cleanup_app(pid, executable, windows, baseline, output)
                        report["cleanup"] = json.loads(
                            (output / "cleanup.json").read_text()
                        )
                        if report["result"].startswith("PASS") and (
                            report["cleanup"]["signals"]
                            or report["cleanup"]["new_windows_remaining"]
                        ):
                            raise RuntimeError(
                                "Error acknowledgement needed fallback signals or left windows"
                            )
            except Exception as error:
                report.update(result="FAIL", cleanup_error=str(error))
                raise
            finally:
                if launcher is not None:
                    stop_owned(launcher)
                report["original_app_tree_sha256_after"] = tree_digest(original)
                if report["original_app_tree_sha256_after"] != original_hash:
                    report.update(
                        result="FAIL", provenance_error="Original native app changed"
                    )
                if "copied_app_tree_sha256" in report:
                    report["copied_app_tree_sha256_after"] = tree_digest(app)
                    if (
                        report["copied_app_tree_sha256_after"]
                        != report["copied_app_tree_sha256"]
                    ):
                        report.update(
                            result="FAIL",
                            provenance_error="Isolated native app changed during the probe",
                        )
                report["frames"] = [
                    {
                        "path": path.name,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                    for path in sorted(output.glob("*.png"))
                ]
                write_json(output / "result.json", report)
        if not report["result"].startswith("PASS"):
            raise RuntimeError(
                report.get("provenance_error", "Native failure proof is incomplete")
            )


if __name__ == "__main__":
    main()
