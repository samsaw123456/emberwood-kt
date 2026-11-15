"""Identify one native game process and its visible window without changing access."""

import ctypes
from pathlib import Path


class Rectangle(ctypes.Structure):
    _fields_ = [(name, ctypes.c_double) for name in ("x", "y", "width", "height")]


class GameWindow:
    def __init__(self):
        self.core = ctypes.CDLL(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        self.foundation = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        self.proc = ctypes.CDLL("/usr/lib/libproc.dylib")
        self.proc.proc_pidpath.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        self.proc.proc_pidpath.restype = ctypes.c_int
        for name in ("CGPreflightScreenCaptureAccess", "CGPreflightPostEventAccess"):
            getattr(self.core, name).restype = ctypes.c_bool
        self.core.CGWindowListCopyWindowInfo.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
        ]
        self.core.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
        self.core.CGRectMakeWithDictionaryRepresentation.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(Rectangle),
        ]
        self.core.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool
        signatures = {
            "CFStringCreateWithCString": (
                [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32],
                ctypes.c_void_p,
            ),
            "CFDictionaryGetValue": (
                [ctypes.c_void_p, ctypes.c_void_p],
                ctypes.c_void_p,
            ),
            "CFNumberGetValue": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p],
                ctypes.c_bool,
            ),
            "CFArrayGetCount": ([ctypes.c_void_p], ctypes.c_long),
            "CFArrayGetValueAtIndex": (
                [ctypes.c_void_p, ctypes.c_long],
                ctypes.c_void_p,
            ),
            "CFRelease": ([ctypes.c_void_p], None),
            "CFStringGetCString": (
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, ctypes.c_uint32],
                ctypes.c_bool,
            ),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.foundation, name)
            function.argtypes, function.restype = arguments, result

    def executable(self, pid):
        buffer = ctypes.create_string_buffer(4096)
        if self.proc.proc_pidpath(pid, buffer, len(buffer)) <= 0:
            raise RuntimeError("Native executable identity is unavailable")
        return Path(buffer.value.decode()).resolve()

    def facilities(self):
        result = {
            "screen_capture_previously_allowed": bool(
                self.core.CGPreflightScreenCaptureAccess()
            ),
            "event_posting_previously_allowed": bool(
                self.core.CGPreflightPostEventAccess()
            ),
        }
        if not all(result.values()):
            raise RuntimeError(
                f"External test facilities unavailable: {result}; no permission request was made"
            )
        return result

    def find(self, pid, title=None):
        names = (
            "kCGWindowOwnerPID",
            "kCGWindowLayer",
            "kCGWindowNumber",
            "kCGWindowBounds",
            "kCGWindowName",
        )
        keys = {
            name: self.foundation.CFStringCreateWithCString(
                None, name.encode(), 0x08000100
            )
            for name in names
        }
        windows = self.core.CGWindowListCopyWindowInfo(1, 0)
        try:
            if not windows:
                raise RuntimeError("Native window list is unavailable")
            found = []
            for index in range(self.foundation.CFArrayGetCount(windows)):
                window = self.foundation.CFArrayGetValueAtIndex(windows, index)
                numbers = {}
                for name in names[:3]:
                    item = self.foundation.CFDictionaryGetValue(window, keys[name])
                    value = ctypes.c_int64()
                    if item and self.foundation.CFNumberGetValue(
                        item, 4, ctypes.byref(value)
                    ):
                        numbers[name] = value.value
                if numbers.get(names[0]) != pid or numbers.get(names[1]) != 0:
                    continue
                name = self.foundation.CFDictionaryGetValue(window, keys[names[4]])
                text = ctypes.create_string_buffer(1024)
                window_title = (
                    text.value.decode()
                    if name
                    and self.foundation.CFStringGetCString(
                        name, text, len(text), 0x08000100
                    )
                    else None
                )
                if title is not None and window_title != title:
                    continue
                bounds = Rectangle()
                item = self.foundation.CFDictionaryGetValue(window, keys[names[3]])
                if item and self.core.CGRectMakeWithDictionaryRepresentation(
                    item, ctypes.byref(bounds)
                ):
                    found.append(
                        {
                            "id": numbers[names[2]],
                            "bounds": [bounds.x, bounds.y, bounds.width, bounds.height],
                            "title": window_title,
                        }
                    )
            if not found:
                raise RuntimeError("The exact game PID has no visible ordinary window")
            if title is not None and len(found) != 1:
                raise RuntimeError("The exact game window title is ambiguous")
            return max(found, key=lambda item: item["bounds"][2] * item["bounds"][3])
        finally:
            if windows:
                self.foundation.CFRelease(windows)
            for value in keys.values():
                self.foundation.CFRelease(value)

    def visible_registry(self):
        """Visible IDs, owner PIDs and layers, including system-owned consent dialogs."""
        keys = [
            self.foundation.CFStringCreateWithCString(None, name.encode(), 0x08000100)
            for name in ("kCGWindowNumber", "kCGWindowOwnerPID", "kCGWindowLayer")
        ]
        windows = self.core.CGWindowListCopyWindowInfo(1, 0)
        try:
            if not windows:
                raise RuntimeError("Native window registry is unavailable")
            result = set()
            for index in range(self.foundation.CFArrayGetCount(windows)):
                window = self.foundation.CFArrayGetValueAtIndex(windows, index)
                values = []
                for key in keys:
                    number = self.foundation.CFDictionaryGetValue(window, key)
                    value = ctypes.c_int64()
                    if not number or not self.foundation.CFNumberGetValue(
                        number, 4, ctypes.byref(value)
                    ):
                        break
                    values.append(value.value)
                if len(values) == 3:
                    result.add(tuple(values))
            return result
        finally:
            if windows:
                self.foundation.CFRelease(windows)
            for key in keys:
                self.foundation.CFRelease(key)
