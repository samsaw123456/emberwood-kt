"""Exercise native-key ownership and the shared quit sequence with fake OS calls."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mac_bundle_smoke import ImmediateMacKeys, physical_command_quit


class NativeQuitTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.created = []

        def create(_source, code, down):
            event = {"code": code, "down": down}
            self.created.append(event)
            return event

        def flags(event, value):
            event["flags"] = value

        def post(_tap, event):
            self.events.append(dict(event))

        self.core = SimpleNamespace(
            CGEventCreateKeyboardEvent=Mock(side_effect=create),
            CGEventSetFlags=Mock(side_effect=flags),
            CGEventPost=Mock(side_effect=post),
            CGEventSourceFlagsState=Mock(return_value=0),
        )
        self.foundation = SimpleNamespace(CFRelease=Mock())
        self.keyboard = ImmediateMacKeys(self.core, self.foundation)

    def test_existing_quit_sequence_flags_timing_and_release_receipt(self):
        with patch("mac_bundle_smoke.time.sleep") as sleep:
            receipt = physical_command_quit(self.core, self.keyboard.key)
        self.assertEqual(
            self.events,
            [
                {"code": 55, "down": True, "flags": 1 << 20},
                {"code": 12, "down": True, "flags": 1 << 20},
                {"code": 12, "down": False, "flags": 1 << 20},
                {"code": 55, "down": False, "flags": 0},
            ],
        )
        self.assertEqual([call.args for call in sleep.call_args_list], [(0.1,), (0.2,)])
        self.assertEqual(
            receipt, {"phase": "after-Command-Q", "command_modifier_released": True}
        )
        self.assertEqual(self.keyboard.held, set())
        self.assertEqual(self.foundation.CFRelease.call_count, 4)
        self.keyboard.close()
        self.assertEqual(self.core.CGEventPost.call_count, 4)

    def test_failed_chord_press_releases_only_attempted_keys(self):
        original = self.core.CGEventPost.side_effect

        def post(tap, event):
            original(tap, event)
            if event["code"] == 55 and event["down"]:
                raise RuntimeError("attempted Command post failed")

        self.core.CGEventPost.side_effect = post
        with self.assertRaisesRegex(RuntimeError, "attempted Command post failed"):
            physical_command_quit(self.core, self.keyboard.key)
        self.assertEqual(
            [(row["code"], row["down"]) for row in self.events],
            [(55, True), (55, False)],
        )
        self.assertEqual(self.keyboard.held, set())
        self.assertEqual(self.foundation.CFRelease.call_count, 2)

    def test_failed_allocation_is_retained_for_keyup_cleanup(self):
        self.core.CGEventCreateKeyboardEvent.return_value = None
        create = self.core.CGEventCreateKeyboardEvent.side_effect
        self.core.CGEventCreateKeyboardEvent.side_effect = None
        with self.assertRaises(RuntimeError):
            self.keyboard.key(2, True)
        self.assertEqual(self.keyboard.held, {2})
        self.core.CGEventCreateKeyboardEvent.side_effect = create
        self.keyboard.close()
        self.assertEqual(self.events, [{"code": 2, "down": False, "flags": 0}])
        self.assertEqual(self.keyboard.held, set())

    def test_cleanup_attempts_every_owned_key_and_preserves_failed_release(self):
        self.keyboard.key(2, True)
        self.keyboard.key(49, True)
        post = self.core.CGEventPost.side_effect

        def fail_one(tap, event):
            if event["code"] == 2 and not event["down"]:
                raise RuntimeError("release failed")
            post(tap, event)

        self.core.CGEventPost.side_effect = fail_one
        with self.assertRaisesRegex(RuntimeError, "Native key cleanup failed"):
            self.keyboard.close()
        self.assertEqual(self.keyboard.held, {2})
        self.assertIn({"code": 49, "down": False, "flags": 0}, self.events)
        self.core.CGEventPost.side_effect = post
        self.keyboard.close()
        self.assertEqual(self.keyboard.held, set())
        self.assertEqual(self.foundation.CFRelease.call_count, 5)

    def test_unreleased_os_modifier_is_never_reported_released(self):
        self.core.CGEventSourceFlagsState.return_value = 1 << 20
        with patch("mac_bundle_smoke.time.sleep"):
            receipt = physical_command_quit(self.core, self.keyboard.key)
        self.assertFalse(receipt["command_modifier_released"])


if __name__ == "__main__":
    unittest.main()
