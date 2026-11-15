"""Exercise a real installed macOS app through LaunchServices and native key events."""

import argparse
import ctypes
import json
import platform
import plistlib
import subprocess
import tempfile
import time
from pathlib import Path

from mac_game_focus import NativeFocusUnavailable, require_game_window
from mac_profile_observer import NativeStatus


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument(
        "--startup-only",
        action="store_true",
        help="Capture startup without sending any keyboard or mouse input",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("build/bundle-launch-macos")
    )
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run this check on macOS.")
    app = args.app.resolve()
    with (app / "Contents/Info.plist").open("rb") as stream:
        executable = (
            app / "Contents/MacOS" / plistlib.load(stream)["CFBundleExecutable"]
        )
    args.output.mkdir(parents=True, exist_ok=True)
    core = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    foundation = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    foundation.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    foundation.CFStringCreateWithCString.restype = ctypes.c_void_p
    foundation.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    foundation.CFDictionaryGetValue.restype = ctypes.c_void_p
    foundation.CFNumberGetValue.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
    ]
    foundation.CFNumberGetValue.restype = ctypes.c_bool
    foundation.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    foundation.CFArrayGetCount.restype = ctypes.c_long
    foundation.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    foundation.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    foundation.CFRelease.argtypes = [ctypes.c_void_p]
    foundation.CFRelease.restype = None
    core.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    core.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    core.CGEventCreateKeyboardEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ushort,
        ctypes.c_bool,
    ]
    core.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    core.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    core.CGEventSetFlags.restype = None
    core.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    core.CGEventPost.restype = None
    core.CGEventSourceFlagsState.argtypes = [ctypes.c_int]
    core.CGEventSourceFlagsState.restype = ctypes.c_uint64
    native = NativeStatus()
    receipts = []
    held = set()
    keys = {
        name: foundation.CFStringCreateWithCString(None, name.encode(), 0x08000100)
        for name in ("kCGWindowOwnerPID", "kCGWindowLayer", "kCGWindowNumber")
    }

    def number(dictionary, name):
        item = foundation.CFDictionaryGetValue(dictionary, keys[name])
        value = ctypes.c_int64()
        if not item or not foundation.CFNumberGetValue(item, 4, ctypes.byref(value)):
            return None
        return value.value

    def window_for(pid):
        windows = core.CGWindowListCopyWindowInfo(1, 0)
        if not windows:
            raise RuntimeError("macOS did not provide its on-screen window list")
        try:
            for index in range(foundation.CFArrayGetCount(windows)):
                window = foundation.CFArrayGetValueAtIndex(windows, index)
                if (
                    number(window, "kCGWindowOwnerPID") == pid
                    and number(window, "kCGWindowLayer") == 0
                ):
                    return number(window, "kCGWindowNumber")
        finally:
            foundation.CFRelease(windows)
        return None

    def key(code, down, flags=0):
        if down:
            held.add(code)
        event = core.CGEventCreateKeyboardEvent(None, code, down)
        if not event:
            raise RuntimeError("macOS did not create the physical key event")
        try:
            core.CGEventSetFlags(event, flags)
            core.CGEventPost(0, event)
            if not down:
                held.discard(code)
        finally:
            foundation.CFRelease(event)

    def tap(code, duration=0.08):
        key(code, True)
        time.sleep(duration)
        key(code, False)
        time.sleep(0.4)

    def require_foreground(pid, phase):
        state = native.sample_and_wait(pid)
        state["phase"] = phase
        state["command_modifier_down"] = bool(
            core.CGEventSourceFlagsState(0) & (1 << 20)
        )
        receipts.append(state)
        (args.output / "native-state.json").write_text(
            json.dumps(receipts, indent=2) + "\n"
        )
        if not state.get("active") or not state["is_frontmost"]:
            raise RuntimeError(
                f"Installed game is not the receiving foreground app at {phase}; inspect desktop and native-state evidence"
            )
        if not args.startup_only:
            try:
                state["accessibility_window"] = require_game_window(pid)
            except NativeFocusUnavailable as error:
                state["input_guard_error"] = str(error)
                raise
            finally:
                (args.output / "native-state.json").write_text(
                    json.dumps(receipts, indent=2) + "\n"
                )

    process = None
    pid = None
    try:
        with tempfile.TemporaryDirectory(prefix="emberwood-bundle-save-") as data:
            process = subprocess.Popen(
                ["open", "-W", "-n", app, "--args", "--data-dir", data]
            )
            window = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                listing = subprocess.check_output(
                    ["ps", "-axo", "pid=,command="], text=True
                )
                for line in listing.splitlines():
                    fields = line.strip().split(None, 1)
                    if (
                        len(fields) == 2
                        and fields[1].startswith(str(executable))
                        and data in fields[1]
                    ):
                        pid = int(fields[0])
                if pid:
                    window = window_for(pid)
                    if window:
                        break
                if process.poll() is not None:
                    raise RuntimeError(
                        "LaunchServices app exited before showing a window"
                    )
                time.sleep(0.2)
            if not window:
                raise RuntimeError("Installed app did not show its native window")
            time.sleep(2)
            subprocess.run(
                [
                    "screencapture",
                    "-x",
                    "-o",
                    "-l",
                    str(window),
                    args.output / "title.png",
                ],
                check=True,
            )
            subprocess.run(
                ["screencapture", "-x", args.output / "desktop-with-dock.png"],
                check=True,
            )
            require_foreground(pid, "before-game-input")
            if args.startup_only:
                (args.output / "result.json").write_text(
                    json.dumps(
                        {
                            "launcher": "LaunchServices open -W -n copied diagnostic .app",
                            "launcher_executable": str(executable),
                            "actions": [],
                            "result": "Startup captured; visual review must confirm no permission dialog. No keyboard or mouse input was sent.",
                        },
                        indent=2,
                    )
                    + "\n"
                )
                print(
                    "Startup captured without input; inspect desktop-with-dock.png for any permission dialog."
                )
                return
            tap(36)  # Return: start from the actual title screen.
            tap(2, 0.35)  # D: move right.
            tap(49)  # Space: jump.
            tap(53)  # Escape: pause.
            subprocess.run(
                [
                    "screencapture",
                    "-x",
                    "-o",
                    "-l",
                    str(window),
                    args.output / "paused.png",
                ],
                check=True,
            )
            require_foreground(pid, "before-Command-Q")
            key(55, True, 1 << 20)  # Physical Command + Q.
            key(12, True, 1 << 20)
            time.sleep(0.1)
            key(12, False, 1 << 20)
            key(55, False)
            time.sleep(0.2)
            command_released = not bool(core.CGEventSourceFlagsState(0) & (1 << 20))
            receipts.append(
                {
                    "phase": "after-Command-Q",
                    "command_modifier_released": command_released,
                }
            )
            (args.output / "native-state.json").write_text(
                json.dumps(receipts, indent=2) + "\n"
            )
            if not command_released:
                raise RuntimeError(
                    "Physical Command release was not reflected by macOS"
                )
            process.wait(timeout=10)
            if window_for(pid) is not None:
                raise RuntimeError("Command+Q did not close the installed app")
            subprocess.run(
                ["screencapture", "-x", args.output / "closed.png"], check=True
            )
            (args.output / "result.json").write_text(
                json.dumps(
                    {
                        "launcher": "LaunchServices open -W -n installed .app",
                        "launcher_executable": str(executable),
                        "runtime": str(app / "Contents/runtime/Contents/Home"),
                        "actions": ["Return", "D", "Space", "Escape", "Command+Q"],
                        "result": "Native launch/close passed; screenshots require visual review",
                    },
                    indent=2,
                )
                + "\n"
            )
            print("PASS: installed .app window launched; native Command+Q closed it.")
    finally:
        for code in list(held):
            key(code, False)
        if pid and window_for(pid) is not None:
            subprocess.run(["kill", "-TERM", str(pid)], check=False)
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        for value in keys.values():
            foundation.CFRelease(value)


if __name__ == "__main__":
    main()
