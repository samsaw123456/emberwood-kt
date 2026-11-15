"""Exercise physical menu selection, scoped guards and release recovery."""

import copy
import ctypes
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mac_application_menu import (
    MenuReader,
    inspect_application_menu,
    menu_center,
    validate_contents,
)


def menu_state(*, selected=False):
    return {
        "pid": 123,
        "title": "Emberwood Kotlin",
        "position": [137.0, 27.0],
        "size": [162.0, 23.0],
        "selected": selected,
        "items": [
            {"role": "AXMenuItem", "title": title, "enabled": True}
            for title in (
                "About Emberwood Kotlin",
                "Hide Emberwood Kotlin",
                "Hide Others",
                "Quit Emberwood Kotlin",
            )
        ]
        if selected
        else [],
    }


class MenuTests(unittest.TestCase):
    def test_geometry_and_actual_required_contents_are_independent(self):
        state = menu_state(selected=True)
        self.assertEqual(menu_center(state), (218.0, 38.5))
        validate_contents(state)
        for change in ("services", "missing", "disabled", "duplicate", "closed"):
            with self.subTest(change=change):
                altered = copy.deepcopy(state)
                if change == "services":
                    altered["items"].append(
                        {"role": "AXMenuItem", "title": "Services", "enabled": True}
                    )
                elif change == "missing":
                    altered["items"].pop(0)
                elif change == "disabled":
                    altered["items"][-1]["enabled"] = False
                elif change == "duplicate":
                    altered["items"].append(copy.deepcopy(altered["items"][0]))
                else:
                    altered["selected"] = False
                with self.assertRaises(RuntimeError):
                    validate_contents(altered)
        for geometry in ([math.nan, 27, 162, 23], [137, 27, 0, 23], [137, 27, 162, -1]):
            with self.subTest(geometry=geometry):
                state["position"], state["size"] = geometry[:2], geometry[2:]
                with self.assertRaises(RuntimeError):
                    menu_center(state)

    def exercise(
        self,
        *,
        services=False,
        wrong_pid=False,
        fail_open_capture=False,
        preheld=False,
        changed_geometry=False,
        release_error=False,
    ):
        events, selected, buttons = [], [False], set()
        escape_down = [preheld]
        executable = Path(
            "/Applications/Emberwood Kotlin.app/Contents/MacOS/Emberwood Kotlin"
        )
        windows = SimpleNamespace(
            executable=Mock(return_value=Path("/other") if wrong_pid else executable),
            facilities=Mock(return_value={"access": True}),
            find=Mock(return_value={"id": 77}),
        )
        observations = [0]

        def snapshot():
            observations[0] += 1
            state = menu_state(selected=selected[0])
            if services and selected[0]:
                state["items"].append(
                    {"role": "AXMenuItem", "title": "Services", "enabled": True}
                )
            if changed_geometry and observations[0] > 1:
                state["position"][0] += 20
            return state

        class Pointer:
            def __init__(self, receipt):
                self.receipt, self.held = receipt, set()
                self.core = SimpleNamespace(
                    CGEventSourceButtonState=lambda _source, button: button in buttons
                )

            def position(self):
                return 421.5, 321.5

            def move(self, *position):
                events.append(("move", position))
                self.receipt({"action": "move", "position": position})

            def button(self, name, down):
                events.append((name, down))
                if down:
                    self.held.add(name)
                    buttons.add(0)
                    selected[0] = True
                else:
                    self.held.discard(name)
                    buttons.discard(0)
                self.receipt({"action": "button", "down": down})

            def close(self, release=True):
                events.append(("pointer cleanup", release))
                for name in list(self.held):
                    self.button(name, False)
                if release_error:
                    raise RuntimeError("pointer cleanup error")

        class Keys:
            def __init__(self):
                self.held = set()
                self.core = SimpleNamespace(
                    CGEventSourceKeyState=lambda *_: escape_down[0]
                )

            def send(self, batch):
                events.append(("keys", batch))
                escape_down[0] = batch[-1][1] == "down"
                if escape_down[0]:
                    self.held.add("escape")
                    selected[0] = False
                else:
                    self.held.discard("escape")

            def close(self, release=True):
                events.append(("keyboard cleanup", release))
                if self.held:
                    self.send([("escape", "up")])

        def capture(command, **_kwargs):
            events.append(("capture", Path(command[-1]).name))
            if fail_open_capture and command[-1].endswith("menu-open.png"):
                raise RuntimeError("capture failed")
            Path(command[-1]).write_bytes(b"retained image fixture")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "menu"
            with (
                patch(
                    "mac_application_menu.MenuReader",
                    return_value=SimpleNamespace(snapshot=snapshot),
                ),
                patch("mac_application_menu.NativePointer", Pointer),
                patch("mac_application_menu.NativeKeys", Keys),
                patch(
                    "mac_application_menu.require_game_window",
                    return_value={"ordinary": True},
                ),
                patch("mac_application_menu.subprocess.run", side_effect=capture),
                patch("mac_application_menu.time.sleep"),
            ):
                if any(
                    (
                        services,
                        wrong_pid,
                        fail_open_capture,
                        preheld,
                        changed_geometry,
                        release_error,
                    )
                ):
                    with self.assertRaises(RuntimeError):
                        inspect_application_menu(output, 123, executable, windows, 77)
                else:
                    inspect_application_menu(output, 123, executable, windows, 77)
            report = json.loads((output / "result.json").read_text())
        return events, report, selected[0], escape_down[0], buttons

    def test_physical_click_uses_native_geometry_then_escape_restores_focus(self):
        events, report, selected, escape, buttons = self.exercise()
        self.assertEqual(
            report["result"], "PASS physical menu assertions; visual review pending"
        )
        self.assertEqual(report["visual_review"], "UNVERIFIED")
        self.assertIn(("move", (218.0, 38.5)), events)
        self.assertLess(
            events.index(("left", True)), events.index(("capture", "menu-open.png"))
        )
        self.assertLess(
            events.index(("capture", "menu-open.png")),
            events.index(("keys", [("escape", "down")])),
        )
        self.assertIn(("keys", [("escape", "up")]), events)
        self.assertEqual(report["released"], {"Escape": True, "pointer_buttons": True})
        self.assertFalse(selected or escape or buttons)
        self.assertEqual(
            [row["path"] for row in report["frames"]],
            ["before-menu.png", "menu-open.png", "menu-closed.png"],
        )
        self.assertEqual(report["focus_after"], {"ordinary": True})

    def test_services_or_failed_open_capture_remains_failure_and_closes_owned_menu(
        self,
    ):
        for argument in ("services", "fail_open_capture"):
            with self.subTest(argument=argument):
                events, report, selected, escape, buttons = self.exercise(
                    **{argument: True}
                )
                self.assertEqual(report["result"], "FAIL")
                self.assertIn(("keys", [("escape", "down")]), events)
                self.assertFalse(selected or escape or buttons)
                self.assertTrue(report["error"])

    def test_wrong_identity_or_preheld_key_does_not_send_input(self):
        for argument in ("wrong_pid", "preheld"):
            with self.subTest(argument=argument):
                events, report, _selected, _escape, _buttons = self.exercise(
                    **{argument: True}
                )
                self.assertEqual(report["result"], "FAIL")
                self.assertFalse(
                    any(row[0] in ("move", "left", "keys") for row in events)
                )

    def test_geometry_change_prevents_click_and_does_not_escape_into_game(self):
        events, report, selected, escape, buttons = self.exercise(changed_geometry=True)
        self.assertEqual(report["result"], "FAIL")
        self.assertFalse(any(row[0] in ("left", "keys") for row in events))
        self.assertFalse(selected or escape or buttons)

    def test_cleanup_failure_never_keeps_pass_and_attempts_keyboard_cleanup(self):
        events, report, *_ = self.exercise(release_error=True)
        self.assertEqual(report["result"], "FAIL")
        self.assertIn(("keyboard cleanup", True), events)
        self.assertEqual(
            report["input_cleanup_errors"], ["pointer: pointer cleanup error"]
        )

    def test_native_geometry_decoding_type_error_and_release_ownership(self):
        reader = object.__new__(MenuReader)
        releases = []

        def copy_attribute(_element, _key, destination):
            ctypes.cast(destination, ctypes.POINTER(ctypes.c_void_p))[0] = 55
            return 0

        def decode(_value, kind, destination):
            values = ctypes.cast(destination, ctypes.POINTER(ctypes.c_double))
            values[0], values[1] = (137.0, 27.0) if kind == 1 else (162.0, 23.0)
            return True

        reader.ax = SimpleNamespace(
            AXUIElementCopyAttributeValue=copy_attribute,
            AXValueGetTypeID=lambda: 99,
            AXValueGetValue=Mock(side_effect=decode),
        )
        reader.cf = SimpleNamespace(
            CFStringCreateWithCString=lambda *_: 44,
            CFRelease=lambda value: releases.append(
                value.value if isinstance(value, ctypes.c_void_p) else value
            ),
            CFGetTypeID=lambda _: 99,
            CFStringGetTypeID=lambda: 1,
            CFBooleanGetTypeID=lambda: 2,
        )
        self.assertEqual(reader.scalar(1, "AXPosition", "point"), [137.0, 27.0])
        self.assertEqual(reader.scalar(1, "AXSize", "size"), [162.0, 23.0])
        self.assertEqual(
            [call.args[1] for call in reader.ax.AXValueGetValue.call_args_list], [1, 2]
        )
        reader.cf.CFGetTypeID = lambda _: 777
        with self.assertRaisesRegex(RuntimeError, "Unexpected native type"):
            reader.scalar(1, "AXPosition", "point")
        self.assertEqual(releases, [44, 55, 44, 55, 44, 55])


if __name__ == "__main__":
    unittest.main()
