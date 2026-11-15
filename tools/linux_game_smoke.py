"""Exercise the real game and physical Alt+F4 on a fresh Xvfb/Openbox display.

This is a short launch/lifecycle check, not the exhaustive control inventory.
Python Xlib and Pillow are needed only when running the actual Linux check.
"""

import argparse
import hashlib
import json
import logging
import platform
import signal
import subprocess
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def wait_for(label, action, timeout=10):
    deadline = time.monotonic() + timeout
    while True:
        value = action()
        if value:
            return value
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for {label}")
        time.sleep(0.025)


def stop_owned(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


class Desktop:
    def __init__(self, output):
        from Xlib import XK, X, display
        from Xlib.ext import xtest

        self.x, self.xk, self.xtest = X, XK, xtest
        self.display = display.Display()
        self.root = self.display.screen().root
        self.output = output
        self.window = None
        self.pid = None
        self.held = set()
        self.receipts = []

    def property(self, window, name):
        value = window.get_full_property(
            self.display.intern_atom(name), self.x.AnyPropertyType
        )
        return list(value.value) if value is not None else []

    def clients(self):
        return [
            self.display.create_resource_object("window", int(number))
            for number in self.property(self.root, "_NET_CLIENT_LIST")
        ]

    def require_empty(self):
        if not self.property(self.root, "_NET_SUPPORTING_WM_CHECK"):
            raise RuntimeError("A private window manager is required")
        if self.clients():
            raise RuntimeError("Use a fresh isolated display with no existing apps")

    def find_game(self, process):
        if process.poll() is not None:
            raise RuntimeError("Game exited before its window appeared")
        windows = [
            w
            for w in self.clients()
            if self.property(w, "_NET_WM_PID") == [process.pid]
            and w.get_wm_name() == "Emberwood Kotlin"
            and w.get_attributes().map_state == self.x.IsViewable
        ]
        if len(windows) > 1:
            raise RuntimeError("More than one window belongs to the game")
        if windows:
            self.window, self.pid = windows[0], process.pid
            return True
        return False

    def require_focus(self):
        if self.window is None or self.pid is None:
            raise RuntimeError("No owned game window")
        if self.property(self.window, "_NET_WM_PID") != [self.pid]:
            raise RuntimeError("Window identity changed")
        if self.property(self.root, "_NET_ACTIVE_WINDOW") != [self.window.id]:
            raise RuntimeError("The owned game is not the active window")

    def focus(self):
        self.window.set_input_focus(self.x.RevertToParent, self.x.CurrentTime)
        # A blank-area click gives the Swing panel focus without activating a menu.
        origin = self.root.translate_coords(self.window, 20, 100)
        self.xtest.fake_input(self.display, self.x.MotionNotify, x=origin.x, y=origin.y)
        self.xtest.fake_input(self.display, self.x.ButtonPress, 1)
        self.xtest.fake_input(self.display, self.x.ButtonRelease, 1)
        self.display.sync()
        wait_for(
            "owned active window",
            lambda: self.property(self.root, "_NET_ACTIVE_WINDOW") == [self.window.id],
        )

    def key(self, name, down):
        if down:
            self.require_focus()
        code = self.display.keysym_to_keycode(self.xk.string_to_keysym(name))
        if not code:
            raise RuntimeError(f"No X11 keycode for {name}")
        if down:
            # A failed reply can follow a delivered down; cleanup still owns it.
            self.held.add(name)
        self.xtest.fake_input(
            self.display, self.x.KeyPress if down else self.x.KeyRelease, code
        )
        self.display.sync()
        wait_for(
            f"physical {name} {'down' if down else 'up'}",
            lambda: (
                bool(self.display.query_keymap()[code // 8] & (1 << (code % 8))) == down
            ),
            1,
        )
        self.receipts.append(
            {"key": name, "down": down, "code": code, "time": time.monotonic()}
        )
        if not down:
            self.held.discard(name)

    def tap(self, name):
        self.key(name, True)
        try:
            time.sleep(0.04)
        finally:
            self.key(name, False)

    def capture(self, desktop=False):
        from PIL import Image

        window = self.root if desktop else self.window
        if not desktop:
            self.require_focus()
        size = window.get_geometry()
        if size.depth != 24:
            raise RuntimeError("Smoke capture requires the documented 24-bit Xvfb")
        pixels = window.get_image(
            0, 0, size.width, size.height, self.x.ZPixmap, 0xFFFFFFFF
        )
        if len(pixels.data) != size.width * size.height * 4:
            raise RuntimeError("Unexpected X11 pixel layout")
        return Image.frombytes(
            "RGB", (size.width, size.height), pixels.data, "raw", "BGRX"
        )

    def close(self):
        failures = []
        try:
            for name in sorted(self.held):
                try:
                    self.key(name, False)
                except Exception as error:
                    LOGGER.exception("Failed to release an owned physical key")
                    failures.append(f"{name}: {error}")
        finally:
            self.display.close()
            (self.output / "physical-input.json").write_text(
                json.dumps(self.receipts, indent=2) + "\n"
            )
        if failures:
            raise RuntimeError(f"Held-key cleanup failed: {failures}")


def color_mask(image, color):
    from PIL import ImageChops

    masks = [
        channel.point([255 if abs(i - wanted) <= 1 else 0 for i in range(256)])
        for channel, wanted in zip(image.split(), color)
    ]
    return ImageChops.multiply(ImageChops.multiply(masks[0], masks[1]), masks[2])


def fox_center(image):
    # Original asset colors establish screen movement independently of game state.
    mask = color_mask(image, (181, 66, 45))
    box = mask.getbbox()
    if box is None or mask.histogram()[255] < 10:
        return None
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def resting_center(released, current):
    before, after = fox_center(released), fox_center(current)
    if before is None or after is None or abs(after[0] - before[0]) > 6:
        return None
    return after


def title_visible(image, paused=False):
    if paused and fox_center(image) is not None:
        return False
    width, height = image.size
    area = (400, 45, 750, 85) if paused else (280, 115, 880, 160)
    scaled = tuple(
        round(value * (width / 1152 if index % 2 == 0 else height / 648))
        for index, value in enumerate(area)
    )
    return color_mask(image.crop(scaled), (243, 235, 205)).histogram()[255] > 100


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", required=True, type=Path)
    parser.add_argument("--jar", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").unlink(missing_ok=True)
    result = {"result": "FAIL", "visual_review": "UNVERIFIED", "frames": []}
    desktop = None
    process = None
    frames = {}
    previous = {}

    def interrupted(signum, _frame):
        raise RuntimeError(f"Interrupted by signal {signum}")

    def observe(label, predicate):
        def attempt():
            if process.poll() is not None:
                raise RuntimeError(f"Game exited while waiting for {label}")
            frame = desktop.capture()
            frames[f"{label}-last"] = frame
            return frame if predicate(frame) else None

        frame = wait_for(label, attempt, 10)
        frames[label] = frame
        frames.pop(f"{label}-last")
        return frame

    try:
        if platform.system() != "Linux":
            raise RuntimeError("This smoke check requires Linux")
        java, jar = args.java.resolve(strict=True), args.jar.resolve(strict=True)
        result.update(
            java=str(java),
            jar=str(jar),
            production_sha256=hashlib.sha256(jar.read_bytes()).hexdigest(),
            java_sha256=hashlib.sha256(java.read_bytes()).hexdigest(),
            libjvm_sha256=hashlib.sha256(
                (java.parent.parent / "lib/server/libjvm.so").read_bytes()
            ).hexdigest(),
            helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            architecture=platform.machine(),
            entry_point="emberwood.MainKt",
        )
        desktop = Desktop(output)
        desktop.require_empty()
        previous = {
            kind: signal.signal(kind, interrupted)
            for kind in (signal.SIGINT, signal.SIGTERM)
        }
        with (
            tempfile.TemporaryDirectory(prefix="emberwood-main-smoke-") as data,
            (output / "app.log").open("w") as log,
            ExitStack() as owned,
        ):
            command = [
                str(java),
                "--enable-native-access=ALL-UNNAMED",
                "-Xms32m",
                "-Xmx256m",
                "-cp",
                str(jar),
                "emberwood.MainKt",
                "--data-dir",
                data,
            ]
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            owned.callback(stop_owned, process)
            result.update(pid=process.pid, command=command)
            wait_for("game window", lambda: desktop.find_game(process), 20)
            if Path(f"/proc/{process.pid}/exe").resolve() != java:
                raise RuntimeError("The running JVM differs from the requested one")
            desktop.focus()
            observe("title", title_visible)
            desktop.tap("Return")
            start = observe("started", lambda frame: fox_center(frame) is not None)
            origin = fox_center(start)
            desktop.key("d", True)
            try:
                moved = observe(
                    "moved-right",
                    lambda frame: (fox_center(frame) or (-1, 0))[0] > origin[0] + 60,
                )
            finally:
                desktop.key("d", False)
            time.sleep(0.2)
            # Startup protection alternates opaque and translucent sprite frames.
            # Observe two identifiable frames instead of treating that effect as
            # a missing player or loosening the original-asset color detector.
            settled = observe(
                "movement-released", lambda frame: fox_center(frame) is not None
            )
            time.sleep(0.12)
            rested = observe(
                "movement-rested",
                lambda frame: resting_center(settled, frame) is not None,
            )
            ground = resting_center(settled, rested)
            desktop.key("space", True)
            try:
                airborne = observe(
                    "jump-airborne",
                    lambda frame: (fox_center(frame) or (0, 9999))[1] < ground[1] - 35,
                )
            finally:
                desktop.key("space", False)
            observe(
                "landed",
                lambda frame: (fox_center(frame) or (0, 0))[1] >= ground[1] - 5,
            )
            desktop.tap("Escape")
            observe("paused", lambda frame: title_visible(frame, paused=True))
            result["observed_centers"] = {
                "started": origin,
                "moved_right": fox_center(moved),
                "rested": ground,
                "airborne": fox_center(airborne),
            }
            desktop.key("Alt_L", True)
            try:
                desktop.tap("F4")
            finally:
                desktop.key("Alt_L", False)
            result["java_exit_code"] = process.wait(timeout=10)
            if result["java_exit_code"] != 0:
                raise RuntimeError("Physical close did not produce a clean Java exit")
            wait_for("window removal", lambda: not desktop.clients())
            frames["window-closed"] = desktop.capture(desktop=True)
            result.update(
                result="PASS",
                close="physical Alt+F4 through XTest and Openbox",
                remaining_windows=0,
            )
    except Exception as error:
        LOGGER.exception("Real-game smoke check failed")
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        if desktop is not None:
            try:
                desktop.close()
            except Exception as error:
                LOGGER.exception("Real-game smoke cleanup failed")
                result.update(result="FAIL", cleanup_error=str(error))
        if process is not None:
            stop_owned(process)
            result["final_process_exit_code"] = process.returncode
        for kind, handler in previous.items():
            signal.signal(kind, handler)
        for name, frame in frames.items():
            path = output / f"{name}.png"
            frame.save(path)
            result["frames"].append(
                {
                    "path": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
