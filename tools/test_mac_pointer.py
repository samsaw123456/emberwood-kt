"""Quartz pointer delivery/cleanup fixtures; these do not claim native Mac proof."""

import ctypes
import math
import unittest
from unittest.mock import Mock

from mac_pointer import NativePointer, Point


class Clock:
    now = 0.0

    def read(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class QuartzFixture:
    def __init__(self, clock):
        self.clock = clock
        self.point = (40.0, 60.0)
        self.buttons = set()
        self.events = {}
        self.posted, self.released, self.pending = [], [], []
        self.ignored = set()
        self.throw_after_post = set()
        self.delay = 0.015
        self.counter = 0
        self.fail_creation = False
        self.CGEventCreate = Mock(side_effect=self.snapshot)
        self.CGEventGetLocation = Mock(
            side_effect=lambda ref: Point(*self.events[ref]["point"])
        )
        self.CGEventCreateMouseEvent = Mock(side_effect=self.mouse)
        self.CGEventCreateScrollWheelEvent2 = Mock(side_effect=self.wheel)
        self.CGEventPost = Mock(side_effect=self.post)
        self.CGEventSourceButtonState = Mock(side_effect=self.button_state)
        self.CGEventSourceCounterForEventType = Mock(side_effect=self.event_counter)
        self.CFRelease = Mock(side_effect=self.release)

    def create(self, values):
        reference = len(self.events) + 1
        self.events[reference] = values
        return reference

    def snapshot(self, source):
        assert source is None
        self.deliver()
        return self.create({"kind": "snapshot", "point": self.point})

    def mouse(self, source, event_type, point, button):
        assert source is None
        if self.fail_creation:
            return None
        return self.create(
            {
                "kind": "mouse",
                "type": event_type,
                "point": (point.x, point.y),
                "button": button,
            }
        )

    def wheel(self, source, units, count, vertical, horizontal, third):
        assert source is None
        return self.create(
            {
                "kind": "wheel",
                "type": 22,
                "units": units,
                "count": count,
                "deltas": (vertical, horizontal, third),
            }
        )

    def post(self, tap, reference):
        assert tap == 0
        event = self.events[reference]
        self.posted.append(event)
        if event["type"] not in self.ignored:
            self.pending.append((self.clock.read() + self.delay, event))
        if event["type"] in self.throw_after_post:
            raise RuntimeError("Fixture failure after event was queued")

    def deliver(self):
        while self.pending and self.pending[0][0] <= self.clock.read():
            _, event = self.pending.pop(0)
            if event["kind"] == "wheel":
                self.counter = (self.counter + 1) % 2**32
            else:
                self.point = event["point"]
                if event["type"] in (1, 3, 25):
                    self.buttons.add(event["button"])
                elif event["type"] in (2, 4, 26):
                    self.buttons.discard(event["button"])

    def button_state(self, source, button):
        assert source == 0
        self.deliver()
        return button in self.buttons

    def event_counter(self, source, event_type):
        assert (source, event_type) == (0, 22)
        self.deliver()
        return self.counter

    def release(self, reference):
        assert reference in self.events and reference not in self.released
        self.released.append(reference)


class PointerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.core = QuartzFixture(self.clock)
        self.receipts = []
        self.pointer = NativePointer(
            receipt=self.receipts.append,
            core=self.core,
            clock=self.clock.read,
            sleep=self.clock.sleep,
        )

    def tearDown(self):
        # Every created snapshot/event must be released, including failed posts.
        self.assertEqual(set(self.core.events), set(self.core.released))

    def test_construction_is_passive_and_position_is_a_released_snapshot(self):
        self.assertEqual(self.core.events, {})
        self.assertEqual(self.pointer.position(), (40.0, 60.0))
        self.assertEqual(self.core.posted, [])
        self.assertEqual(self.receipts, [])
        self.assertEqual(ctypes.sizeof(Point), 16)
        self.assertIs(self.core.CGEventGetLocation.restype, Point)
        self.assertIs(self.core.CGEventCreateMouseEvent.argtypes[2], Point)
        self.assertEqual(
            self.core.CGEventCreateScrollWheelEvent2.argtypes[-3:], [ctypes.c_int32] * 3
        )

    def test_move_waits_for_os_coordinates_and_records_elapsed_time(self):
        self.pointer.move(120, 80)
        self.assertEqual(self.core.point, (120.0, 80.0))
        self.assertEqual(self.core.posted[-1]["type"], 5)
        self.assertGreaterEqual(self.receipts[-1]["milliseconds"], 15)
        self.assertEqual(self.receipts[-1]["observation"]["position"], [120.0, 80.0])

    def test_each_physical_button_and_held_drag_has_its_own_quartz_type(self):
        for name, number, down_type, up_type, drag_type in (
            ("left", 0, 1, 2, 6),
            ("middle", 2, 25, 26, 27),
            ("right", 1, 3, 4, 7),
        ):
            with self.subTest(button=name):
                self.pointer.button(name, True)
                self.assertIn(number, self.core.buttons)
                self.pointer.move(100 + number, 120 + number)
                self.pointer.button(name, False)
                self.assertNotIn(number, self.core.buttons)
                self.assertEqual(
                    [e["type"] for e in self.core.posted[-3:]],
                    [down_type, drag_type, up_type],
                )
                self.assertEqual(
                    [e["button"] for e in self.core.posted[-3:]], [number] * 3
                )
        self.assertEqual(self.pointer.held, set())

    def test_scroll_uses_java_direction_and_acknowledges_counter_wrap(self):
        self.core.counter = 2**32 - 1
        self.pointer.wheel(3)
        self.pointer.wheel(-2)
        self.assertEqual(
            [e["deltas"] for e in self.core.posted], [(-3, 0, 0), (2, 0, 0)]
        )
        self.assertTrue(
            all((e["units"], e["count"]) == (1, 1) for e in self.core.posted)
        )
        self.assertEqual(self.receipts[0]["observation"]["counter_after"], 0)

    def test_unacknowledged_post_is_bounded_traced_and_still_released(self):
        self.core.ignored.add(1)
        with self.assertRaisesRegex(RuntimeError, "did not acknowledge"):
            self.pointer.button("left", True)
        self.assertGreaterEqual(self.clock.read(), 1)
        self.assertLess(self.clock.read(), 1.02)
        self.assertEqual(self.pointer.held, {"left"})
        self.assertEqual(self.receipts[-1]["result"], "FAIL")
        self.pointer.close()
        self.assertEqual([e["type"] for e in self.core.posted], [1, 2])

    def test_post_exception_retains_attempted_down_for_cleanup(self):
        self.core.throw_after_post.add(1)
        with self.assertRaisesRegex(RuntimeError, "after event was queued"):
            self.pointer.button("left", True)
        self.assertEqual(self.pointer.held, {"left"})
        self.clock.sleep(0.02)
        self.core.deliver()
        self.assertEqual(self.core.buttons, {0})
        self.pointer.close()
        self.assertEqual(self.core.buttons, set())

    def test_failed_creation_retains_attempt_and_does_not_release_null(self):
        self.core.fail_creation = True
        with self.assertRaisesRegex(RuntimeError, "could not create"):
            self.pointer.button("middle", True)
        self.assertEqual(self.pointer.held, {"middle"})
        self.assertEqual(self.core.posted, [])
        self.core.fail_creation = False
        self.pointer.close()

    def test_cleanup_attempts_all_owned_buttons_and_failed_releases_are_retryable(self):
        self.pointer.button("left", True)
        self.pointer.button("middle", True)
        self.core.buttons.add(
            1
        )  # An unrelated right button is never released by cleanup.
        self.core.ignored.add(2)
        with self.assertRaisesRegex(RuntimeError, "left:"):
            self.pointer.close()
        self.assertEqual(self.pointer.held, {"left"})
        self.assertEqual(self.core.buttons, {0, 1})
        self.assertEqual([e["type"] for e in self.core.posted[-2:]], [2, 26])
        self.core.ignored.clear()
        self.pointer.close()
        self.assertEqual(self.core.buttons, {1})
        count = len(self.core.posted)
        self.pointer.close()
        self.assertEqual(len(self.core.posted), count)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            self.pointer.move(1, 2)

    def test_invalid_arguments_and_nonfinite_snapshot_never_post(self):
        for point in ((math.nan, 0), (0, math.inf), (True, 0), ("1", 0)):
            with self.assertRaises(ValueError):
                self.pointer.move(*point)
        for button, down in (("extra", True), ([], True), ("left", 1)):
            with self.assertRaises(ValueError):
                self.pointer.button(button, down)
        for rotation in (0, 1.5, True, -(2**31), 2**31):
            with self.assertRaises(ValueError):
                self.pointer.wheel(rotation)
        self.core.point = (math.nan, 1)
        with self.assertRaisesRegex(RuntimeError, "invalid pointer"):
            self.pointer.position()
        self.assertEqual(self.core.posted, [])


if __name__ == "__main__":
    unittest.main()
