"""Regression fixtures for Quartz event metadata; actual delivery needs Mac testing."""

import unittest

from physical_key import NativeKeys


class QuartzFixture:
    def __init__(self):
        self.flags = 0
        self.keys = {}
        self.posts = []
        self.fail_after_post = False

    def CGEventCreateKeyboardEvent(self, _source, key, down):
        flags = self.flags
        if key in {123, 124, 125, 126}:
            flags |= 0xA00000
        elif key == 76:
            flags |= 0x200000
        return {"key": key, "down": down, "flags": flags}

    def CGEventGetFlags(self, event):
        return event["flags"]

    def CGEventSetFlags(self, event, flags):
        event["flags"] = flags

    def CGEventSourceFlagsState(self, _source):
        return self.flags

    def CGEventSourceKeyState(self, _source, key):
        return self.keys.get(key, False)

    def CGEventPost(self, _tap, event):
        self.posts.append(dict(event))
        self.flags = event["flags"]
        self.keys[event["key"]] = event["down"]
        if self.fail_after_post:
            self.fail_after_post = False
            raise RuntimeError("Posted, then failed")

    def CFRelease(self, _event):
        pass


class KeyFlagsTests(unittest.TestCase):
    def setUp(self):
        self.core = QuartzFixture()
        self.keyboard = NativeKeys.__new__(NativeKeys)
        self.keyboard.mac = True
        self.keyboard.core = self.core
        self.keyboard.held = set()
        self.keyboard.trace = None

    def test_arrow_metadata_does_not_turn_later_m_into_fn_or_keypad_m(self):
        self.keyboard.send([("left", "down"), ("left", "up")])
        self.assertEqual(self.core.posts[-1]["flags"], 0xA00000)
        self.keyboard.send([("m", "down"), ("m", "up")])
        self.keyboard.send([("m", "down"), ("m", "up")])
        self.assertEqual([e["flags"] for e in self.core.posts[-4:]], [0] * 4)
        self.assertEqual([e["down"] for e in self.core.posts[-4:]], [True, False] * 2)
        self.assertFalse(self.core.keys[46])

    def test_ordinary_commands_clear_inherited_arrow_metadata(self):
        for key in (
            "a",
            "d",
            "w",
            "j",
            "m",
            "p",
            "r",
            "space",
            "return",
            "escape",
            "tab",
        ):
            with self.subTest(key=key):
                self.core.flags = 0xA00000
                self.keyboard.send([(key, "down"), (key, "up")])
                self.assertEqual([e["flags"] for e in self.core.posts[-2:]], [0, 0])

    def test_keypad_enter_keeps_its_identity_without_inheriting_fn(self):
        self.core.flags = 0xA00000
        self.keyboard.send([("keypad-enter", "down"), ("keypad-enter", "up")])
        self.assertEqual([e["flags"] for e in self.core.posts], [0x200000] * 2)
        self.assertEqual([e["key"] for e in self.core.posts], [76, 76])

    def test_actual_fn_and_unowned_modifiers_are_preserved(self):
        self.core.flags = 0xA00000 | 0x100000 | 0x40000
        self.core.keys[63] = True
        self.keyboard.send([("m", "down"), ("m", "up")])
        self.assertEqual([e["flags"] for e in self.core.posts], [0x940000] * 2)
        self.assertTrue(self.core.keys[63])

    def test_both_shift_sides_survive_metadata_cleanup_and_alternate_release(self):
        self.core.flags = 0xA00000
        for key, down, expected in [
            ("left-shift", "down", 0x20002),
            ("right-shift", "down", 0x20006),
            ("left-shift", "up", 0x20004),
            ("m", "down", 0x20004),
            ("m", "up", 0x20004),
            ("right-shift", "up", 0),
        ]:
            self.keyboard.send([(key, down)])
            self.assertEqual(self.core.posts[-1]["flags"], expected)
        self.assertEqual(self.keyboard.held, set())

    def test_failed_post_still_releases_only_the_attempted_key(self):
        self.core.flags = 0xA00000
        self.core.fail_after_post = True
        with self.assertRaisesRegex(RuntimeError, "Posted, then failed"):
            self.keyboard.send([("m", "down")])
        self.keyboard.close(release=True)
        self.assertEqual(
            self.core.posts,
            [
                {"key": 46, "down": True, "flags": 0},
                {"key": 46, "down": False, "flags": 0},
            ],
        )
        self.assertEqual(self.keyboard.held, set())


if __name__ == "__main__":
    unittest.main()
