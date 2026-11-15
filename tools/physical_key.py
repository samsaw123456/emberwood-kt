#!/usr/bin/env python3
"""Send native keys in one batch without calling Emberwood's input handlers."""

import ctypes
import sys
import time

CODES = {
    # name: X11 keysym, macOS hardware keycode
    "right-shift": (0xFFE2, 60),
    "left-shift": (0xFFE1, 56),
    "keypad-enter": (0xFF8D, 76),
    "space": (0x20, 49),
    "w": (0x77, 13),
    "a": (0x61, 0),
    "d": (0x64, 2),
    "j": (0x6A, 38),
    "left": (0xFF51, 123),
    "right": (0xFF53, 124),
    "up": (0xFF52, 126),
    "tab": (0xFF09, 48),
}
if len(sys.argv) < 3 or len(sys.argv) % 2 != 1:
    raise SystemExit("Usage: physical_key.py KEY down|up [KEY down|up ...]")
events = list(zip(sys.argv[1::2], sys.argv[2::2]))
if any(key not in CODES or action not in ("down", "up") for key, action in events):
    raise SystemExit("Unsupported key or action")
if sys.platform == "darwin":
    core = ctypes.CDLL(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    )
    core.CGEventCreateKeyboardEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ushort,
        ctypes.c_bool,
    ]
    core.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    core.CGEventPost.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    core.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    core.CGEventSourceFlagsState.argtypes = [ctypes.c_int]
    core.CGEventSourceFlagsState.restype = ctypes.c_uint64
    core.CGEventSourceKeyState.argtypes = [ctypes.c_int, ctypes.c_ushort]
    core.CGEventSourceKeyState.restype = ctypes.c_bool
    core.CFRelease.argtypes = [ctypes.c_void_p]
    shifts = {
        key: bool(core.CGEventSourceKeyState(0, CODES[key][1]))
        for key in ("left-shift", "right-shift")
    }
    for key, action in events:
        event = core.CGEventCreateKeyboardEvent(None, CODES[key][1], action == "down")
        if not event:
            raise RuntimeError("Cannot create physical keyboard event")
        try:
            if key in shifts:
                shifts[key] = action == "down"
                # Apple IOLLEvent.h: preserve both device-side bits and the
                # aggregate Shift bit when the other physical Shift stays held.
                flags = core.CGEventSourceFlagsState(0) & ~(0x20000 | 0x2 | 0x4)
                if shifts["left-shift"]:
                    flags |= 0x20000 | 0x2
                if shifts["right-shift"]:
                    flags |= 0x20000 | 0x4
                core.CGEventSetFlags(event, flags)
            core.CGEventPost(0, event)
        finally:
            core.CFRelease(event)
    # AWT omits a second-side modifier event when aggregate flags do not change.
    # Verify the physical OS key state independently instead of fabricating AWT events.
    desired = {key: action == "down" for key, action in events}
    deadline = time.monotonic() + 1
    while any(
        core.CGEventSourceKeyState(0, CODES[key][1]) != down
        for key, down in desired.items()
    ):
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "macOS did not acknowledge the injected physical key state"
            )
        time.sleep(0.005)
else:
    x11 = ctypes.CDLL("libX11.so.6")
    xtest = ctypes.CDLL("libXtst.so.6")
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XKeysymToKeycode.restype = ctypes.c_ubyte
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xtest.XTestFakeKeyEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_ulong,
    ]
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError("X11 display unavailable")
    try:
        for key, action in events:
            code = x11.XKeysymToKeycode(display, CODES[key][0])
            if not code or not xtest.XTestFakeKeyEvent(
                display, code, int(action == "down"), 0
            ):
                raise RuntimeError("Physical key injection failed")
        x11.XFlush(display)
    finally:
        x11.XCloseDisplay(display)
