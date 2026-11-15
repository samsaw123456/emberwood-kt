#!/usr/bin/env python3
"""Send real native keys in a batch, or serve batches over one OS connection."""

import ctypes
import json
import os
import sys
import time

CODES = {
    # name: X11 keysym, macOS hardware keycode
    "right-shift": (0xFFE2, 60),
    "left-shift": (0xFFE1, 56),
    "keypad-enter": (0xFF8D, 76),
    "return": (0xFF0D, 36),
    "escape": (0xFF1B, 53),
    "space": (0x20, 49),
    "w": (0x77, 13),
    "a": (0x61, 0),
    "d": (0x64, 2),
    "j": (0x6A, 38),
    "m": (0x6D, 46),
    "p": (0x70, 35),
    "r": (0x72, 15),
    "left": (0xFF51, 123),
    "right": (0xFF53, 124),
    "up": (0xFF52, 126),
    "down": (0xFF54, 125),
    "tab": (0xFF09, 48),
}


def parse_events(arguments):
    if not arguments or len(arguments) % 2:
        raise ValueError("Expected KEY down|up [KEY down|up ...]")
    events = list(zip(arguments[::2], arguments[1::2]))
    if any(key not in CODES or action not in ("down", "up") for key, action in events):
        raise ValueError("Unsupported key or action")
    return events


class NativeKeys:
    def __init__(self):
        self.held = set()
        self.trace = os.environ.get("EMBERWOOD_PHYSICAL_TRACE")
        self.mac = sys.platform == "darwin"
        if self.mac:
            self.core = ctypes.CDLL(
                "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
            )
            self.core.CGEventCreateKeyboardEvent.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ushort,
                ctypes.c_bool,
            ]
            self.core.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
            self.core.CGEventPost.argtypes = [ctypes.c_uint, ctypes.c_void_p]
            self.core.CGEventGetFlags.argtypes = [ctypes.c_void_p]
            self.core.CGEventGetFlags.restype = ctypes.c_uint64
            self.core.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
            self.core.CGEventSourceFlagsState.argtypes = [ctypes.c_int]
            self.core.CGEventSourceFlagsState.restype = ctypes.c_uint64
            self.core.CGEventSourceKeyState.argtypes = [ctypes.c_int, ctypes.c_ushort]
            self.core.CGEventSourceKeyState.restype = ctypes.c_bool
            self.core.CFRelease.argtypes = [ctypes.c_void_p]
        else:
            self.x11 = ctypes.CDLL("libX11.so.6")
            self.xtest = ctypes.CDLL("libXtst.so.6")
            self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self.x11.XOpenDisplay.restype = ctypes.c_void_p
            self.x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            self.x11.XKeysymToKeycode.restype = ctypes.c_ubyte
            self.x11.XFlush.argtypes = [ctypes.c_void_p]
            self.x11.XQueryKeymap.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            self.xtest.XTestFakeKeyEvent.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_int,
                ctypes.c_ulong,
            ]
            self.display = self.x11.XOpenDisplay(None)
            if not self.display:
                raise RuntimeError("X11 display unavailable")
            self.keycodes = {
                key: self.x11.XKeysymToKeycode(self.display, codes[0])
                for key, codes in CODES.items()
            }

    def send(self, events):
        began = time.monotonic_ns()
        # An acknowledged failure can follow an actual press: retain attempted downs.
        self.held.update(key for key, action in events if action == "down")
        observation = self.send_mac(events) if self.mac else self.send_x11(events)
        for key, action in events:
            if action == "down":
                self.held.add(key)
            else:
                self.held.discard(key)
        if self.trace:
            with open(self.trace, "a", encoding="utf-8") as output:
                output.write(
                    json.dumps(
                        {
                            "events": events,
                            "batch_milliseconds": (time.monotonic_ns() - began) / 1e6,
                            **observation,
                        }
                    )
                    + "\n"
                )

    def post_mac(self, events):
        """Post without waiting; direct callers must track and release their downs."""
        core = self.core
        shift_masks = {"left-shift": 0x2, "right-shift": 0x4}
        initial_flags = core.CGEventSourceFlagsState(0)
        shifts = {key: bool(initial_flags & mask) for key, mask in shift_masks.items()}
        posted_flags = []
        for key, action in events:
            event = core.CGEventCreateKeyboardEvent(
                None, CODES[key][1], action == "down"
            )
            if not event:
                raise RuntimeError("Cannot create physical keyboard event")
            try:
                flags = core.CGEventGetFlags(event)
                if key in shifts:
                    shifts[key] = action == "down"
                    # Apple IOLLEvent.h: preserve both device-side and aggregate Shift.
                    flags = core.CGEventSourceFlagsState(0) & ~(0x20000 | 0x2 | 0x4)
                    for shift, held in shifts.items():
                        if held:
                            flags |= 0x20000 | shift_masks[shift]
                # A nil-source Quartz event can inherit an earlier arrow's keypad/Fn
                # metadata. Those are not modifiers held for a subsequent letter.
                # Preserve real Fn state, and retain the current arrow/keypad identity.
                fn_down = bool(core.CGEventSourceKeyState(0, 63))
                if key not in {"left", "right", "up", "down", "keypad-enter"}:
                    flags &= ~0x200000
                if key not in {"left", "right", "up", "down"} and not fn_down:
                    flags &= ~0x800000
                core.CGEventSetFlags(event, flags)
                posted_flags.append(
                    {
                        "key": key,
                        "action": action,
                        "flags": flags,
                        "fn_key_down": fn_down,
                    }
                )
                core.CGEventPost(0, event)
            finally:
                core.CFRelease(event)
        return {
            "initial_flags": initial_flags,
            "posted_flags": posted_flags,
            "desired_shifts": shifts,
        }

    def send_mac(self, events):
        posted = self.post_mac(events)
        core = self.core
        shift_masks = {"left-shift": 0x2, "right-shift": 0x4}
        initial_flags = posted["initial_flags"]
        posted_flags = posted["posted_flags"]
        shifts = posted["desired_shifts"]
        desired = {key: action == "down" for key, action in events}
        deadline = time.monotonic() + 1
        while True:
            flags = core.CGEventSourceFlagsState(0)
            keys = {
                key: bool(core.CGEventSourceKeyState(0, CODES[key][1]))
                for key in desired
            }
            # AWT can omit a second-side Shift when aggregate flags do not change.
            # Apple's device-side flags independently acknowledge these physical sides.
            acknowledged = {
                key: bool(flags & shift_masks[key]) if key in shifts else keys[key]
                for key in desired
            }
            if acknowledged == desired and (
                not any(key in shifts for key in desired)
                or bool(flags & 0x20000) == any(shifts.values())
            ):
                return {
                    "initial_flags": initial_flags,
                    "flags": flags,
                    "key_table": keys,
                    "acknowledged": acknowledged,
                    "posted_flags": posted_flags,
                }
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "macOS did not acknowledge the injected physical key state: "
                    f"desired={desired}, flags={flags:#x}, initial_flags={initial_flags:#x}, "
                    f"key_table={keys}, modifier_or_key_state={acknowledged}, "
                    f"hid_flags={core.CGEventSourceFlagsState(1):#x}"
                )
            time.sleep(0.005)

    def send_x11(self, events):
        for key, action in events:
            code = self.keycodes[key]
            if not code or not self.xtest.XTestFakeKeyEvent(
                self.display, code, int(action == "down"), 0
            ):
                raise RuntimeError("Physical key injection failed")
        self.x11.XFlush(self.display)
        desired = {key: action == "down" for key, action in events}
        deadline = time.monotonic() + 1
        state = (ctypes.c_ubyte * 32)()
        while True:
            # This reply comes from the independent X connection, after the fake events.
            self.x11.XQueryKeymap(self.display, state)
            acknowledged = {
                key: bool(
                    state[self.keycodes[key] // 8] & (1 << (self.keycodes[key] % 8))
                )
                for key in desired
            }
            if acknowledged == desired:
                return {"acknowledged": acknowledged}
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "X11 did not acknowledge the injected physical key state: "
                    f"desired={desired}, acknowledged={acknowledged}"
                )
            time.sleep(0.005)

    def close(self, release=False):
        try:
            if release and self.held:
                self.send([(key, "up") for key in sorted(self.held)])
        finally:
            if not self.mac:
                self.x11.XCloseDisplay(self.display)


def main():
    server = sys.argv[1:] == ["--serve"]
    if not server:
        events = parse_events(sys.argv[1:])
    native = NativeKeys()
    try:
        if server:
            print("READY", flush=True)
            for line in sys.stdin:
                try:
                    native.send(parse_events(line.split()))
                except (ValueError, RuntimeError, OSError) as error:
                    message = f"{type(error).__name__}: {error}".replace("\n", " ")
                    print(message, file=sys.stderr, flush=True)
                    print(f"ERROR {message}", flush=True)
                else:
                    print("OK", flush=True)
        else:
            native.send(events)
    finally:
        # Batch CLI preserves its historic press/hold semantics across invocations.
        # Server EOF releases only the keys this process attempted to hold.
        native.close(release=server)


if __name__ == "__main__":
    main()
