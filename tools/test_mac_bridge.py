"""Real IPC policy/cleanup tests with fake OS backends; not Mac-native evidence."""

import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from mac_test_bridge import Controller


class WindowFixture:
    allowed = True

    def __init__(self, executable):
        # Match GameWindow's proc_pidpath contract, including /var -> /private/var.
        self.path = executable.resolve()

    def executable(self, pid):
        return self.path if pid == 42 else Path("/another/app")

    def facilities(self):
        if not self.allowed:
            raise RuntimeError("Fixture capture/input access unavailable")
        return {
            "screen_capture_previously_allowed": True,
            "event_posting_previously_allowed": True,
        }

    auxiliary_id = 8

    def find(self, _pid, title=None):
        return {
            "id": 7 if title in {None, "Emberwood Kotlin"} else self.auxiliary_id,
            "bounds": [10, 20, 640, 480],
            "title": title,
        }


class KeyFixture:
    def __init__(self):
        self.events, self.held, self.closed = [], set(), False

    def send(self, events):
        self.events.extend(events)
        for key, action in events:
            if action == "down":
                self.held.add(key)
            else:
                self.held.discard(key)

    def close(self, release):
        if release:
            self.send([(key, "up") for key in tuple(self.held)])
        self.closed = True


class PointerFixture:
    def __init__(self, receipt):
        self.receipt = receipt
        self.events, self.held, self.closed = [], set(), False
        self.point = (30, 40)
        self.fail_down = False

    def position(self):
        return self.point

    def move(self, x, y):
        self.point = (x, y)
        self.events.append(("move", x, y))

    def button(self, name, down):
        self.events.append(("button", name, down))
        if down:
            self.held.add(name)
            if self.fail_down:
                raise RuntimeError(
                    "Fixture button was posted but acknowledgement failed"
                )
        else:
            self.held.discard(name)
        self.receipt({"button": name, "down": down})

    def wheel(self, rotation):
        self.events.append(("wheel", rotation))

    def close(self, release):
        if release:
            for name in sorted(self.held):
                self.button(name, False)
        self.closed = True


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        directory = Path(self.temporary.name)
        (directory / "physical").mkdir()
        self.output = directory / "alias"
        # Exercise canonical identity on Linux too, rather than only on macOS.
        self.output.symlink_to(directory / "physical", target_is_directory=True)
        self.executable = self.output / "game"
        self.windows = WindowFixture(self.executable)
        self.keys, self.captures = [], []
        self.focused = True
        self.focused_auxiliary = None
        self.pointers = []

        def guard(pid):
            if not self.focused:
                raise RuntimeError("Fixture game is not focused")
            return {"pid": pid, "modal": False}

        def keys():
            result = KeyFixture()
            self.keys.append(result)
            return result

        def pointer(receipt):
            result = PointerFixture(receipt)
            self.pointers.append(result)
            return result

        def auxiliary_guard(pid, title):
            if pid != 42 or self.focused or self.focused_auxiliary != title:
                raise RuntimeError("Fixture auxiliary window is not focused")
            return {"pid": pid, "title": title, "modal": False}

        with patch("mac_test_bridge.subprocess.run"):
            self.controller = Controller(
                self.output,
                self.executable,
                guard=guard,
                windows=self.windows,
                keys_factory=keys,
                pointer_factory=pointer,
                auxiliary_guard=auxiliary_guard,
            )

        def capture(pid, window, rectangle, path):
            self.captures.append((pid, window, rectangle, path))
            path.write_bytes(b"fixture capture, not real Mac pixels")

        self.controller.capture_image = capture

    def tearDown(self):
        self.controller.close()
        self.temporary.cleanup()

    @contextmanager
    def client(self, mode, pid=42):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            connection.connect(str(self.controller.path))
            with connection.makefile("rwb", buffering=0) as stream:
                stream.write(json.dumps({"mode": mode, "pid": pid}).encode() + b"\n")
                yield stream

    def guard(self):
        with self.client("guard") as stream:
            result = json.loads(stream.readline())
            self.assertEqual(result["result"], "PASS")
            self.assertEqual(result["pid"], 42)

    def wait_closed(self, keys):
        deadline = time.monotonic() + 2
        while not keys.closed and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(keys.closed)

    def test_wrong_pid_cannot_guard_or_post(self):
        with self.client("guard", pid=43) as stream:
            self.assertEqual(json.loads(stream.readline())["result"], "UNVERIFIED")
        self.assertFalse(self.controller.guarded)
        self.assertEqual(self.captures, [])
        self.assertEqual(self.keys, [])

    def test_early_connection_does_not_authorize_key_down(self):
        with self.client("keys") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            stream.write(b"d down\n")
            self.assertTrue(stream.readline().startswith(b"ERROR "))
        self.wait_closed(self.keys[0])
        self.assertEqual(self.keys[0].events, [])

    def test_eof_releases_only_held_session_keys(self):
        self.guard()
        with self.client("keys") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            stream.write(b"d down space down space up\n")
            self.assertEqual(stream.readline(), b"OK\n")
        self.wait_closed(self.keys[0])
        self.assertEqual(
            self.keys[0].events,
            [("d", "down"), ("space", "down"), ("space", "up"), ("d", "up")],
        )

    def test_capture_rejects_outside_game_rectangle(self):
        self.guard()
        with self.client("capture-serve") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            stream.write(
                json.dumps([0, 20, 100, 100, str(self.output / "bad.png")]).encode()
                + b"\n"
            )
            self.assertTrue(stream.readline().startswith(b"ERROR "))
        self.assertEqual(len(self.captures), 1)
        self.assertFalse((self.output / "bad.png").exists())

    def test_concurrent_clients_and_duplicate_keyboard_refusal(self):
        self.guard()
        with self.client("keys") as keys, self.client("capture-serve") as captures:
            self.assertEqual(keys.readline(), b"READY\n")
            self.assertEqual(captures.readline(), b"READY\n")
            with self.client("keys") as duplicate:
                self.assertTrue(duplicate.readline().startswith(b"ERROR "))
            keys.write(b"a down\n")
            self.assertEqual(keys.readline(), b"OK\n")
            captures.write(
                json.dumps([20, 30, 100, 80, str(self.output / "frame.png")]).encode()
                + b"\n"
            )
            self.assertEqual(captures.readline(), b"OK\n")
        self.wait_closed(self.keys[0])
        self.assertEqual(self.keys[0].events, [("a", "down"), ("a", "up")])
        self.assertEqual(len(self.keys), 1)

    def test_unavailable_facility_emits_no_keys_or_capture(self):
        self.windows.allowed = False
        with self.client("guard") as stream:
            self.assertEqual(json.loads(stream.readline())["result"], "UNVERIFIED")
        self.assertEqual(self.captures, [])
        self.assertEqual(self.keys, [])

    def test_focus_loss_capture_is_read_only_and_down_remains_guarded(self):
        self.guard()
        self.focused = False
        with self.client("capture-serve") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            stream.write(
                json.dumps(
                    [20, 30, 100, 80, str(self.output / "unfocused.png")]
                ).encode()
                + b"\n"
            )
            self.assertEqual(stream.readline(), b"OK\n")
        with self.client("keys") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            stream.write(b"d down\n")
            self.assertTrue(stream.readline().startswith(b"ERROR "))
        self.wait_closed(self.keys[0])
        self.assertEqual(self.keys[0].events, [])

    def test_child_proxy_from_unrelated_directory_uses_ipc_only(self):
        script = Path(__file__).with_name("mac_test_bridge.py").resolve()

        def run(mode, data=""):
            return subprocess.run(
                [sys.executable, script, mode, self.controller.path, "42"],
                input=data,
                capture_output=True,
                text=True,
                cwd=self.output,
                check=True,
                timeout=5,
            ).stdout

        self.assertEqual(json.loads(run("guard"))["result"], "PASS")
        self.assertEqual(run("keys", "d down\n"), "READY\nOK\n")
        self.wait_closed(self.keys[0])
        self.assertEqual(self.keys[0].events, [("d", "down"), ("d", "up")])
        request = json.dumps([20, 30, 100, 80, str(self.output / "space image.png")])
        self.assertEqual(run("capture-serve", request + "\n"), "READY\nOK\n")
        self.assertEqual(
            run("pointer-serve", '["button","left",true]\n'), "READY\nOK\n"
        )
        self.wait_closed(self.pointers[0])
        self.assertEqual(
            self.pointers[0].events,
            [("button", "left", True), ("button", "left", False)],
        )

    def pointer_command(self, stream, *operation):
        stream.write(json.dumps(operation).encode() + b"\n")
        return stream.readline()

    def test_pointer_early_ready_posts_no_events(self):
        with self.client("pointer-serve") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            self.assertTrue(
                self.pointer_command(stream, "button", "left", True).startswith(
                    b"ERROR "
                )
            )
        self.wait_closed(self.pointers[0])
        self.assertEqual(self.pointers[0].events, [])

    def test_pointer_buttons_wheel_and_eof_release(self):
        self.guard()
        with self.client("pointer-serve") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            for command in [
                ("move", 50, 60),
                ("wheel", -3),
                ("button", "left", True),
                ("button", "middle", True),
                ("button", "right", True),
            ]:
                self.assertEqual(self.pointer_command(stream, *command), b"OK\n")
        self.wait_closed(self.pointers[0])
        self.assertEqual(self.pointers[0].held, set())
        self.assertEqual(
            self.pointers[0].events[-3:],
            [
                ("button", "left", False),
                ("button", "middle", False),
                ("button", "right", False),
            ],
        )

    def test_pointer_refuses_duplicate_owner_and_outside_coordinates(self):
        self.guard()
        with self.client("pointer-serve") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            with self.client("pointer-serve") as duplicate:
                self.assertTrue(duplicate.readline().startswith(b"ERROR "))
            self.assertTrue(
                self.pointer_command(stream, "move", 0, 0).startswith(b"ERROR ")
            )
        self.wait_closed(self.pointers[0])
        self.assertEqual(self.pointers[0].events, [])
        self.assertEqual(len(self.pointers), 1)

    def test_pointer_failed_ack_releases_attempted_down(self):
        self.guard()
        with self.client("pointer-serve") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            self.pointers[0].fail_down = True
            self.assertTrue(
                self.pointer_command(stream, "button", "left", True).startswith(
                    b"ERROR "
                )
            )
        self.wait_closed(self.pointers[0])
        self.assertEqual(
            self.pointers[0].events,
            [("button", "left", True), ("button", "left", False)],
        )

    def test_registered_auxiliary_allows_move_release_but_no_new_press(self):
        self.guard()
        title = "Emberwood mouse focus audit"
        with self.client("pointer-serve") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            self.assertEqual(
                self.pointer_command(stream, "button", "left", True), b"OK\n"
            )
            self.focused, self.focused_auxiliary = False, title
            self.assertEqual(
                self.pointer_command(stream, "register-aux", title), b"OK\n"
            )
            self.assertEqual(self.pointer_command(stream, "move", 50, 60), b"OK\n")
            self.assertEqual(
                self.pointer_command(stream, "button", "left", False), b"OK\n"
            )
            self.assertTrue(
                self.pointer_command(stream, "button", "right", True).startswith(
                    b"ERROR "
                )
            )
        self.wait_closed(self.pointers[0])
        self.assertEqual(
            self.pointers[0].events,
            [("button", "left", True), ("move", 50, 60), ("button", "left", False)],
        )

    def test_auxiliary_registration_binds_native_window_id(self):
        self.guard()
        title = "Emberwood audit focus"
        with self.client("pointer-serve") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            self.focused, self.focused_auxiliary = False, title
            self.assertEqual(
                self.pointer_command(stream, "register-aux", title), b"OK\n"
            )
            self.windows.auxiliary_id = 9
            self.assertTrue(
                self.pointer_command(stream, "move", 50, 60).startswith(b"ERROR ")
            )
        self.wait_closed(self.pointers[0])
        self.assertEqual(self.pointers[0].events, [])

    def test_controller_close_releases_pointer_with_open_client(self):
        self.guard()
        with self.client("pointer-serve") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            self.assertEqual(
                self.pointer_command(stream, "button", "left", True), b"OK\n"
            )
            self.controller.close()
            self.assertEqual(stream.readline(), b"")
        self.assertEqual(self.pointers[0].held, set())
        self.assertTrue(self.pointers[0].closed)

    def test_pointer_rejects_release_not_owned_by_session(self):
        self.guard()
        with self.client("pointer-serve") as stream:
            self.assertEqual(stream.readline(), b"READY\n")
            self.assertTrue(
                self.pointer_command(stream, "button", "left", False).startswith(
                    b"ERROR "
                )
            )
        self.wait_closed(self.pointers[0])
        self.assertEqual(self.pointers[0].events, [])


if __name__ == "__main__":
    unittest.main()
