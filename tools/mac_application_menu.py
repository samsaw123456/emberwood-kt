"""Physically inspect the known game's application menu after movement testing.

Accessibility is read-only here: it supplies the exact app-menu geometry and
observed menu contents. Quartz clicks and Escape perform every interaction.
"""

import ctypes
import hashlib
import json
import math
import subprocess
import time
from contextlib import contextmanager

from mac_game_focus import require_game_window
from mac_pointer import NativePointer, Point
from physical_key import CODES, NativeKeys

APP_NAME = "Emberwood Kotlin"


class MenuReader:
    """Read only the explicitly owned application's menu; never activate AX items."""

    def __init__(self, pid):
        self.pid = pid
        self.ax = ctypes.CDLL(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        self.cf = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        signatures = {
            "AXIsProcessTrusted": ([], ctypes.c_bool),
            "AXUIElementCreateApplication": ([ctypes.c_int], ctypes.c_void_p),
            "AXUIElementGetPid": (
                [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)],
                ctypes.c_int,
            ),
            "AXUIElementCopyAttributeValue": (
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
                ctypes.c_int,
            ),
            "AXUIElementSetMessagingTimeout": (
                [ctypes.c_void_p, ctypes.c_float],
                ctypes.c_int,
            ),
            "AXValueGetTypeID": ([], ctypes.c_ulong),
            "AXValueGetValue": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p],
                ctypes.c_bool,
            ),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.ax, name)
            function.argtypes, function.restype = arguments, result
        signatures = {
            "CFStringCreateWithCString": (
                [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32],
                ctypes.c_void_p,
            ),
            "CFStringGetCString": (
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, ctypes.c_uint32],
                ctypes.c_bool,
            ),
            "CFGetTypeID": ([ctypes.c_void_p], ctypes.c_ulong),
            "CFBooleanGetValue": ([ctypes.c_void_p], ctypes.c_bool),
            "CFArrayGetCount": ([ctypes.c_void_p], ctypes.c_long),
            "CFArrayGetValueAtIndex": (
                [ctypes.c_void_p, ctypes.c_long],
                ctypes.c_void_p,
            ),
            "CFRelease": ([ctypes.c_void_p], None),
        }
        for name in ("CFStringGetTypeID", "CFBooleanGetTypeID", "CFArrayGetTypeID"):
            signatures[name] = ([], ctypes.c_ulong)
        for name, (arguments, result) in signatures.items():
            function = getattr(self.cf, name)
            function.argtypes, function.restype = arguments, result
        if not self.ax.AXIsProcessTrusted():
            raise RuntimeError("Existing accessibility read access is unavailable")

    @contextmanager
    def attribute(self, element, name, *, optional=False):
        key = self.cf.CFStringCreateWithCString(None, name.encode(), 0x08000100)
        if not key:
            raise RuntimeError("Could not create the menu attribute name")
        value = ctypes.c_void_p()
        try:
            error = self.ax.AXUIElementCopyAttributeValue(
                element, key, ctypes.byref(value)
            )
        finally:
            self.cf.CFRelease(key)
        try:
            if optional and error in (-25205, -25212):
                yield None
            elif error or not value.value:
                raise RuntimeError(f"Could not read menu {name}: AX error {error}")
            else:
                yield value
        finally:
            if value.value:
                self.cf.CFRelease(value)

    def scalar(self, element, name, kind, *, optional=False):
        with self.attribute(element, name, optional=optional) as value:
            if value is None:
                return None
            expected = {
                "text": self.cf.CFStringGetTypeID,
                "bool": self.cf.CFBooleanGetTypeID,
                "point": self.ax.AXValueGetTypeID,
                "size": self.ax.AXValueGetTypeID,
            }[kind]()
            if self.cf.CFGetTypeID(value) != expected:
                raise RuntimeError(f"Unexpected native type for menu {name}")
            if kind == "bool":
                return bool(self.cf.CFBooleanGetValue(value))
            if kind in ("point", "size"):
                # CGPoint and CGSize each contain two CGFloat doubles on both Macs.
                point = Point()
                if not self.ax.AXValueGetValue(
                    value, 1 if kind == "point" else 2, ctypes.byref(point)
                ):
                    raise RuntimeError(f"Could not decode menu {name}")
                return [point.x, point.y]
            buffer = ctypes.create_string_buffer(2048)
            if not self.cf.CFStringGetCString(value, buffer, len(buffer), 0x08000100):
                raise RuntimeError(f"Could not decode menu {name}")
            return buffer.value.decode("utf-8")

    @contextmanager
    def children(self, element):
        with self.attribute(element, "AXChildren") as array:
            if self.cf.CFGetTypeID(array) != self.cf.CFArrayGetTypeID():
                raise RuntimeError("Menu children are not a native array")
            count = self.cf.CFArrayGetCount(array)
            if not 0 <= count <= 64:
                raise RuntimeError("Unexpectedly large application menu")
            # Borrowed references remain valid until the owning array is released.
            yield [self.cf.CFArrayGetValueAtIndex(array, i) for i in range(count)]

    def snapshot(self):
        app = self.ax.AXUIElementCreateApplication(self.pid)
        if not app:
            raise RuntimeError("The owned application's AX menu is unavailable")
        try:
            owner = ctypes.c_int()
            if (
                self.ax.AXUIElementGetPid(app, ctypes.byref(owner))
                or owner.value != self.pid
            ):
                raise RuntimeError("Application menu belongs to a different PID")
            if self.ax.AXUIElementSetMessagingTimeout(app, 1.0):
                raise RuntimeError("Could not bound application menu reads")
            if not self.scalar(app, "AXFrontmost", "bool"):
                raise RuntimeError("The exact game is not frontmost")
            with self.attribute(app, "AXMenuBar") as bar, self.children(bar) as items:
                matches = [
                    item
                    for item in items
                    if self.scalar(item, "AXTitle", "text") == APP_NAME
                    and self.scalar(item, "AXRole", "text") == "AXMenuBarItem"
                ]
                if len(matches) != 1:
                    raise RuntimeError(
                        "The exact application menu title is missing or ambiguous"
                    )
                item = matches[0]
                result = {
                    "pid": self.pid,
                    "title": APP_NAME,
                    "position": self.scalar(item, "AXPosition", "point"),
                    "size": self.scalar(item, "AXSize", "size"),
                    "selected": self.scalar(item, "AXSelected", "bool"),
                    "items": [],
                }
                menu_center(result)  # Reject malformed native geometry before input.
                if result["selected"]:
                    with self.children(item) as menus:
                        if (
                            len(menus) != 1
                            or self.scalar(menus[0], "AXRole", "text") != "AXMenu"
                        ):
                            raise RuntimeError(
                                "The selected app item has no unique native menu"
                            )
                        with self.children(menus[0]) as entries:
                            for entry in entries:
                                result["items"].append(
                                    {
                                        "role": self.scalar(entry, "AXRole", "text"),
                                        "title": self.scalar(
                                            entry, "AXTitle", "text", optional=True
                                        )
                                        or "",
                                        "enabled": self.scalar(
                                            entry, "AXEnabled", "bool"
                                        ),
                                    }
                                )
                return result
        finally:
            self.cf.CFRelease(app)


def menu_center(state):
    x, y = state["position"]
    width, height = state["size"]
    if (
        not all(
            type(v) in (int, float) and math.isfinite(v) for v in (x, y, width, height)
        )
        or not 1 <= width <= 600
        or not 1 <= height <= 100
    ):
        raise RuntimeError("Invalid native application-menu geometry")
    return x + width / 2, y + height / 2


def validate_contents(state):
    if not state["selected"]:
        raise RuntimeError("The physical application menu is not open")
    titles = [item["title"] for item in state["items"]]
    if "Services" in titles:
        raise RuntimeError("Services remains in the actual application menu")
    for title in (f"About {APP_NAME}", f"Hide {APP_NAME}", f"Quit {APP_NAME}"):
        matches = [item for item in state["items"] if item["title"] == title]
        if len(matches) != 1 or matches[0] != {
            "role": "AXMenuItem",
            "title": title,
            "enabled": True,
        }:
            raise RuntimeError(
                f"The actual enabled menu item is missing or ambiguous: {title}"
            )


def inspect_application_menu(output, pid, executable, windows, window_id):
    """Call only after first-arrow proof; return after physical Escape and recovery."""
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "result": "FAIL",
        "visual_review": "UNVERIFIED",
        "pid": pid,
        "executable": str(executable),
        "window_id": window_id,
        "observations": [],
        "input": [],
        "frames": [],
        "scope": "Read-only own-app AX geometry/contents; physical click and Escape only",
    }
    pointer, keyboard, reader = None, None, None
    clicked = False

    def guard(*, ordinary=False):
        if windows.executable(pid) != executable:
            raise RuntimeError("Application-menu PID changed executable")
        windows.facilities()
        window = windows.find(pid, title=APP_NAME)
        if window["id"] != window_id:
            raise RuntimeError("Application-menu game window changed")
        if ordinary:
            return require_game_window(pid)
        return window

    def observe(label):
        guard()
        state = reader.snapshot()
        report["observations"].append(
            {
                "phase": label,
                "monotonic": time.monotonic(),
                "epoch_ns": time.time_ns(),
                **state,
            }
        )
        return state

    def wait_selected(selected, label):
        deadline = time.monotonic() + 3
        while True:
            state = observe(label)
            if state["selected"] == selected:
                return state
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Application menu did not become selected={selected}"
                )
            time.sleep(0.05)

    def capture(label):
        path = output / f"{label}.png"
        subprocess.run(["screencapture", "-x", str(path)], check=True, timeout=5)
        report["frames"].append(
            {
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    def escape():
        guard()
        if not observe("before-Escape")["selected"]:
            raise RuntimeError(
                "Refusing Escape because the owned menu is no longer open"
            )
        try:
            report["input"].append(
                {"action": "Escape down", "monotonic": time.monotonic()}
            )
            keyboard.send([("escape", "down")])
            time.sleep(0.08)
        finally:
            # Only this controller's attempted down can cause this key-up.
            if "escape" in keyboard.held:
                keyboard.send([("escape", "up")])
            report["input"].append(
                {"action": "Escape released", "monotonic": time.monotonic()}
            )
        wait_selected(False, "after-Escape")

    try:
        report["focus_before"] = guard(ordinary=True)
        reader = MenuReader(pid)
        initial = observe("before-click")
        if initial["selected"]:
            raise RuntimeError("The application menu was already open before this test")
        pointer = NativePointer(receipt=report["input"].append)
        keyboard = NativeKeys()
        if keyboard.core.CGEventSourceKeyState(0, CODES["escape"][1]) or any(
            pointer.core.CGEventSourceButtonState(0, number) for number in (0, 1, 2)
        ):
            raise RuntimeError(
                "The physical Escape key or pointer button was already held"
            )
        original_pointer = pointer.position()
        capture("before-menu")
        pointer.move(*menu_center(initial))
        guard(ordinary=True)
        current = observe("before-physical-click")
        if current["selected"] or menu_center(current) != menu_center(initial):
            raise RuntimeError(
                "The application-menu state/geometry changed before input"
            )
        clicked = True  # A failed post/ack can still have opened the owned menu.
        try:
            pointer.button("left", True)
            time.sleep(0.08)
        finally:
            if "left" in pointer.held:
                pointer.button("left", False)
        opened = wait_selected(True, "after-click")
        capture("menu-open")
        validate_contents(opened)
        escape()
        report["focus_after"] = guard(ordinary=True)
        pointer.move(*original_pointer)
        report["released"] = {
            "Escape": not keyboard.core.CGEventSourceKeyState(0, CODES["escape"][1]),
            "pointer_buttons": not any(
                pointer.core.CGEventSourceButtonState(0, i) for i in (0, 1, 2)
            ),
        }
        if not all(report["released"].values()):
            raise RuntimeError("Menu input did not recover to its released state")
        capture("menu-closed")
        report["result"] = "PASS physical menu assertions; visual review pending"
    except Exception as error:
        report["error"] = str(error)
        if clicked and reader is not None and keyboard is not None:
            try:
                if observe("failure-cleanup")["selected"]:
                    escape()
            except Exception as cleanup_error:  # noqa: BLE001 - preserve the original failure and cleanup receipt
                report["menu_cleanup_error"] = str(cleanup_error)
        raise
    finally:
        failures = []
        for name, controller in (("pointer", pointer), ("keyboard", keyboard)):
            if controller is not None:
                try:
                    controller.close(release=True)
                except Exception as error:  # noqa: BLE001 - attempt both controllers' owned releases
                    failures.append(f"{name}: {error}")
        if failures:
            report.update(result="FAIL", input_cleanup_errors=failures)
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        if failures:
            raise RuntimeError("Menu input cleanup failed: " + "; ".join(failures))
    return report
