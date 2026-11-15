"""Read-only permission and modal-window guard before automated Mac game input."""

import ctypes


class NativeFocusUnavailable(RuntimeError):
    pass


def require_game_window(pid):
    services = ctypes.CDLL(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    )
    core = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    services.AXIsProcessTrusted.restype = ctypes.c_bool
    if not services.AXIsProcessTrusted():
        raise NativeFocusUnavailable(
            "Accessibility read access is unavailable; no consent prompt or input was sent"
        )
    services.AXUIElementCreateApplication.argtypes = [ctypes.c_int]
    services.AXUIElementCreateApplication.restype = ctypes.c_void_p
    services.AXUIElementGetPid.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int),
    ]
    services.AXUIElementGetPid.restype = ctypes.c_int
    services.AXUIElementCopyAttributeValue.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    services.AXUIElementCopyAttributeValue.restype = ctypes.c_int
    core.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    core.CFStringCreateWithCString.restype = ctypes.c_void_p
    core.CFStringGetCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_long,
        ctypes.c_uint32,
    ]
    core.CFStringGetCString.restype = ctypes.c_bool
    core.CFGetTypeID.argtypes = [ctypes.c_void_p]
    core.CFGetTypeID.restype = ctypes.c_ulong
    for name in ("CFStringGetTypeID", "CFBooleanGetTypeID", "CFArrayGetTypeID"):
        getattr(core, name).restype = ctypes.c_ulong
    core.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
    core.CFBooleanGetValue.restype = ctypes.c_bool
    core.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    core.CFArrayGetCount.restype = ctypes.c_long
    core.CFRelease.argtypes = [ctypes.c_void_p]
    core.CFRelease.restype = None

    def attribute(element, name, optional=False):
        key = core.CFStringCreateWithCString(None, name.encode(), 0x08000100)
        result = ctypes.c_void_p()
        try:
            error = services.AXUIElementCopyAttributeValue(
                element, key, ctypes.byref(result)
            )
        finally:
            core.CFRelease(key)
        if optional and error in (
            -25205,
            -25212,
        ):  # Unsupported/no value for optional sheets.
            return None
        if error or not result.value:
            raise NativeFocusUnavailable(
                f"Could not establish {name}: AX error {error}; no input was sent"
            )
        return result

    def value(element, name, kind, optional=False):
        item = attribute(element, name, optional)
        if item is None:
            return None
        try:
            actual = core.CFGetTypeID(item)
            expected = {
                "text": core.CFStringGetTypeID,
                "bool": core.CFBooleanGetTypeID,
                "array": core.CFArrayGetTypeID,
            }[kind]()
            if actual != expected:
                raise NativeFocusUnavailable(
                    f"Unexpected native type for {name}; no input was sent"
                )
            if kind == "bool":
                return core.CFBooleanGetValue(item)
            if kind == "array":
                return core.CFArrayGetCount(item)
            buffer = ctypes.create_string_buffer(512)
            if not core.CFStringGetCString(item, buffer, len(buffer), 0x08000100):
                raise NativeFocusUnavailable(
                    f"Could not read {name}; no input was sent"
                )
            return buffer.value.decode("utf-8")
        finally:
            core.CFRelease(item)

    # Query only the known game. The system-wide focused-app bridge fails with
    # kAXErrorCannotComplete on hosted Macs even when AX access is already trusted.
    app = services.AXUIElementCreateApplication(pid)
    if not app:
        raise NativeFocusUnavailable(
            "Game application lookup is unavailable; no input was sent"
        )
    window = None
    try:
        focused_pid = ctypes.c_int()
        error = services.AXUIElementGetPid(app, ctypes.byref(focused_pid))
        if error or focused_pid.value != pid:
            raise NativeFocusUnavailable(
                f"Focused application PID {focused_pid.value} is not the game PID {pid}; no input was sent"
            )
        window = attribute(app, "AXFocusedWindow")
        state = {
            "frontmost": value(app, "AXFrontmost", "bool"),
            "role": value(window, "AXRole", "text"),
            "subrole": value(window, "AXSubrole", "text"),
            "title": value(window, "AXTitle", "text"),
            "modal": value(window, "AXModal", "bool"),
            "attached_sheets": value(window, "AXSheets", "array", optional=True) or 0,
        }
        if state != {
            "frontmost": True,
            "role": "AXWindow",
            "subrole": "AXStandardWindow",
            "title": "Emberwood Kotlin",
            "modal": False,
            "attached_sheets": 0,
        }:
            raise NativeFocusUnavailable(
                f"Focused window is not the ordinary game window: {state}; no input was sent"
            )
        return state
    finally:
        if window:
            core.CFRelease(window)
        core.CFRelease(app)
