"""External test-only Quartz pointer input; callers guard the exact game window."""

import ctypes
import math
import sys
import time
from typing import ClassVar


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class NativePointer:
    # Quartz button numbers and down/up/drag event types, independent of Java masks.
    BUTTONS: ClassVar = {
        "left": (0, 1, 2, 6),
        "middle": (2, 25, 26, 27),
        "right": (1, 3, 4, 7),
    }

    def __init__(
        self,
        receipt=None,
        *,
        core=None,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        if core is None:
            if sys.platform != "darwin":
                raise RuntimeError("NativePointer requires macOS")
            core = ctypes.CDLL(
                "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
            )
        self.core, self.receipt, self.clock, self.sleep = core, receipt, clock, sleep
        self.held = set()
        self.closed = False
        declarations = {
            "CGEventCreate": ([ctypes.c_void_p], ctypes.c_void_p),
            "CGEventGetLocation": ([ctypes.c_void_p], Point),
            "CGEventCreateMouseEvent": (
                [ctypes.c_void_p, ctypes.c_uint32, Point, ctypes.c_uint32],
                ctypes.c_void_p,
            ),
            "CGEventCreateScrollWheelEvent2": (
                [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]
                + [ctypes.c_int32] * 3,
                ctypes.c_void_p,
            ),
            "CGEventPost": ([ctypes.c_uint32, ctypes.c_void_p], None),
            "CGEventSourceButtonState": (
                [ctypes.c_int32, ctypes.c_uint32],
                ctypes.c_bool,
            ),
            "CGEventSourceCounterForEventType": (
                [ctypes.c_int32, ctypes.c_uint32],
                ctypes.c_uint32,
            ),
            "CFRelease": ([ctypes.c_void_p], None),
        }
        for name, (arguments, result) in declarations.items():
            function = getattr(core, name)
            function.argtypes, function.restype = arguments, result

    def position(self):
        """Read Quartz screen coordinates; creating this snapshot posts no event."""
        event = self.core.CGEventCreate(None)
        if not event:
            raise RuntimeError("macOS could not snapshot the current pointer")
        try:
            point = self.core.CGEventGetLocation(event)
            if not math.isfinite(point.x) or not math.isfinite(point.y):
                raise RuntimeError("macOS returned an invalid pointer position")
            return point.x, point.y
        finally:
            self.core.CFRelease(event)

    def _post(self, event):
        if not event:
            raise RuntimeError("macOS could not create the requested pointer event")
        try:
            self.core.CGEventPost(0, event)  # kCGHIDEventTap
        finally:
            self.core.CFRelease(event)

    def _perform(self, action, details, post, observe):
        if self.closed:
            raise RuntimeError("Native pointer controller is closed")
        started = self.clock()
        record = {"action": action, **details, "result": "FAIL"}
        try:
            post()
            deadline = self.clock() + 1.0
            while True:
                acknowledged, observation = observe()
                record["observation"] = observation
                if acknowledged:
                    record["result"] = "PASS"
                    return record
                if self.clock() >= deadline:
                    raise RuntimeError(
                        f"macOS did not acknowledge pointer {action}: {observation}"
                    )
                self.sleep(0.005)
        except Exception as error:
            record["error"] = f"{type(error).__name__}: {error}"
            raise
        finally:
            record["milliseconds"] = (self.clock() - started) * 1000
            if self.receipt is not None:
                self.receipt(record)

    def move(self, x, y):
        if any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in (x, y)
        ):
            raise ValueError("Pointer coordinates must be finite numbers")
        # With multiple buttons held, retain a stable primary drag button.
        name = next((name for name in self.BUTTONS if name in self.held), None)
        button, event_type = (
            (self.BUTTONS[name][0], self.BUTTONS[name][3]) if name else (0, 5)
        )

        def observe():
            current = self.position()
            return (
                abs(current[0] - x) <= 0.5 and abs(current[1] - y) <= 0.5,
                {"position": list(current)},
            )

        return self._perform(
            "move",
            {"target": [x, y], "event_type": event_type, "button": button},
            lambda: self._post(
                self.core.CGEventCreateMouseEvent(None, event_type, Point(x, y), button)
            ),
            observe,
        )

    def button(self, name, down):
        if type(name) is not str or name not in self.BUTTONS or type(down) is not bool:
            raise ValueError("Expected left|middle|right and a Boolean button state")
        if self.closed:
            raise RuntimeError("Native pointer controller is closed")
        button, pressed, released, _ = self.BUTTONS[name]
        point = self.position()
        if down:
            # Posting can succeed before observation fails; cleanup must still release it.
            self.held.add(name)

        def observe():
            actual = bool(self.core.CGEventSourceButtonState(0, button))
            if actual == down and not down:
                self.held.discard(name)
            return actual == down, {"button": name, "down": actual}

        return self._perform(
            "button",
            {"button": name, "down": down, "position": list(point)},
            lambda: self._post(
                self.core.CGEventCreateMouseEvent(
                    None, pressed if down else released, Point(*point), button
                )
            ),
            observe,
        )

    def wheel(self, rotation):
        if type(rotation) is not int or not -(2**31) < rotation < 2**31:
            raise ValueError("Wheel rotation must fit a signed 32-bit Quartz delta")
        if rotation == 0:
            raise ValueError("Wheel rotation must be nonzero")
        # Java positive rotation scrolls down. Quartz line deltas use the opposite sign.
        before = self.core.CGEventSourceCounterForEventType(0, 22)

        def observe():
            after = self.core.CGEventSourceCounterForEventType(0, 22)
            return after != before, {"counter_before": before, "counter_after": after}

        return self._perform(
            "wheel",
            {"rotation": rotation, "quartz_delta": -rotation},
            lambda: self._post(
                self.core.CGEventCreateScrollWheelEvent2(None, 1, 1, -rotation, 0, 0)
            ),
            observe,
        )

    def close(self, release=True):
        if self.closed:
            return
        failures = []
        if release:
            for name in sorted(self.held):
                try:
                    self.button(name, False)
                except Exception as error:  # noqa: BLE001 - all releases must be attempted
                    failures.append(f"{name}: {error}")
        if failures:
            # Leave failed attempted buttons retryable; never skip later releases.
            raise RuntimeError("Pointer release failed: " + "; ".join(failures))
        self.closed = True
