"""External native test controller; the game app's children perform IPC only."""

import argparse
import json
import platform
import select
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from mac_game_focus import require_game_window
from mac_game_window import GameWindow
from mac_pointer import NativePointer
from physical_key import NativeKeys, parse_events

ROOT = Path(__file__).resolve().parents[1]
AUXILIARY_TITLES = {"Emberwood audit focus", "Emberwood mouse focus audit"}


class Controller:
    def __init__(
        self,
        output,
        executable,
        guard=require_game_window,
        windows=None,
        keys_factory=NativeKeys,
        pointer_factory=NativePointer,
        auxiliary_guard=None,
        auxiliary_timeout=2.0,
    ):
        self.output, self.executable = output.resolve(), executable.resolve()
        self.guard, self.windows, self.keys_factory = (
            guard,
            windows or GameWindow(),
            keys_factory,
        )
        self.pid = None
        self.pointer_factory = pointer_factory
        self.auxiliary_guard = auxiliary_guard or require_game_window
        self.auxiliary_timeout = auxiliary_timeout
        self.auxiliary_windows = {}
        self.guarded = False
        self.lock = threading.Lock()
        self.keyboard = threading.Lock()
        self.pointer = threading.Lock()
        self.capture_lock = threading.Lock()
        self.connections = set()
        self.sessions = set()
        self.cleanup_errors = []
        self.closed = False
        self.capture_process = None
        self.capture_log = None
        self.capture_helper = self.output / "mac-window-capture"
        with (self.output / "capture-helper-compile.log").open("w") as log:
            subprocess.run(
                [
                    "xcrun",
                    "swiftc",
                    "-swift-version",
                    "5",
                    "-parse-as-library",
                    "-warnings-as-errors",
                    "-O",
                    "-target",
                    f"{platform.machine()}-apple-macosx15.0",
                    ROOT / "tools/mac_window_capture.swift",
                    "-o",
                    self.capture_helper,
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=90,
            )
        self.temporary = tempfile.TemporaryDirectory(
            prefix="emberwood-input-", dir="/tmp"
        )
        self.path = Path(self.temporary.name) / "events.sock"
        owner = self

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                owner.handle(self)

        self.server = Server(str(self.path), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, name="native-test-controller", daemon=True
        )
        self.thread.start()

    def identify(self, pid):
        if self.windows.executable(pid) != self.executable:
            raise RuntimeError("Requested PID is not the exact private app executable")
        with self.lock:
            if self.pid is not None and self.pid != pid:
                raise RuntimeError("The private game's native PID changed")
            self.pid = pid

    def receive_capture(self):
        process = self.capture_process
        if not select.select([process.stdout], [], [], 5)[0]:
            raise TimeoutError(
                "External native capture did not respond within five seconds"
            )
        result = process.stdout.readline().strip()
        if result not in {"READY", "OK"}:
            raise RuntimeError(f"External native capture failed: {result}")
        return result

    def capture(self, pid, rectangle, path):
        request_started = time.monotonic()
        request_epoch_ns = time.time_ns()
        self.identify(pid)
        path = Path(path).resolve()
        if not path.is_relative_to(self.output) or path.suffix != ".png":
            raise RuntimeError(
                "Capture output must be a PNG inside this audit's output directory"
            )
        self.windows.facilities()
        window = self.windows.find(pid, title="Emberwood Kotlin")
        if rectangle is not None:
            if len(rectangle) != 4 or any(
                type(value) is not int for value in rectangle
            ):
                raise ValueError("Capture rectangle must contain four integers")
            x, y, width, height = rectangle
            left, top, full_width, full_height = window["bounds"]
            if (
                width <= 0
                or height <= 0
                or x < left
                or y < top
                or x + width > left + full_width
                or y + height > top + full_height
            ):
                raise ValueError(
                    "Requested capture rectangle extends outside the exact game window"
                )
        preflight_finished = time.monotonic()
        with self.capture_lock:
            started = time.monotonic()
            self.capture_image(pid, window, rectangle, path)
            with (self.output / "external-capture.jsonl").open("a") as log:
                log.write(
                    json.dumps(
                        {
                            "pid": pid,
                            "window": window,
                            "rectangle": rectangle,
                            "path": str(path),
                            "milliseconds": (time.monotonic() - started) * 1000,
                            "request_epoch_ns": request_epoch_ns,
                            "preflight_milliseconds": (
                                preflight_finished - request_started
                            )
                            * 1000,
                            "lock_wait_milliseconds": (started - preflight_finished)
                            * 1000,
                            "total_milliseconds": (time.monotonic() - request_started)
                            * 1000,
                        }
                    )
                    + "\n"
                )

    def capture_image(self, pid, window, rectangle, path):
        if self.capture_process is None:
            self.capture_log = (self.output / "capture-helper.log").open("w")
            self.capture_process = subprocess.Popen(
                [self.capture_helper, str(pid)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.capture_log,
                text=True,
                bufsize=1,
            )
            if self.receive_capture() != "READY":
                raise RuntimeError("External capture helper did not become ready")
        self.capture_process.stdin.write(
            json.dumps(
                {"window": window["id"], "rectangle": rectangle, "path": str(path)}
            )
            + "\n"
        )
        self.capture_process.stdin.flush()
        if self.receive_capture() != "OK":
            raise RuntimeError("External capture did not complete")

    def verify_window(self, pid, startup=False):
        self.identify(pid)
        record = {"pid": pid, "result": "UNVERIFIED", "startup": startup}
        try:
            record["facilities"] = self.windows.facilities()
            if startup:
                self.capture(pid, None, self.output / "native-startup-window.png")
            record["window"] = self.guard(pid)
            record["result"] = "PASS"
            self.guarded = True
            return record
        except Exception as error:
            record["reason"] = str(error)
            raise
        finally:
            with (
                self.lock,
                (self.output / "external-input-gate.jsonl").open("a") as log,
            ):
                log.write(json.dumps(record) + "\n")

    def handle(self, handler):
        native, pointer, mode, pid = None, None, None, None
        owns_keyboard = False
        owns_pointer = False
        done = threading.Event()
        with self.lock:
            self.connections.add(handler.request)
            self.sessions.add(done)
        try:
            handler.request.settimeout(10)
            request = json.loads(handler.rfile.readline(4096))
            mode, pid = request["mode"], request["pid"]
            if type(pid) is not int or mode not in {
                "guard",
                "keys",
                "capture",
                "capture-serve",
                "pointer-serve",
            }:
                raise ValueError("Invalid test-controller request")
            self.identify(pid)
            if mode == "guard":
                record = self.verify_window(pid, startup=True)
                handler.wfile.write(json.dumps(record).encode() + b"\n")
                return
            if mode == "keys":
                owns_keyboard = self.keyboard.acquire(blocking=False)
                if not owns_keyboard:
                    raise RuntimeError(
                        "A native keyboard test connection is already active"
                    )
                native = self.keys_factory()
                native.trace = str(self.output / "external-physical-key-delivery.jsonl")
            if mode == "pointer-serve":
                owns_pointer = self.pointer.acquire(blocking=False)
                if not owns_pointer:
                    raise RuntimeError(
                        "A native pointer test connection is already active"
                    )

                def receipt(row):
                    with (self.output / "external-pointer-delivery.jsonl").open(
                        "a"
                    ) as log:
                        log.write(json.dumps({"pid": pid, **row}) + "\n")

                pointer = self.pointer_factory(receipt=receipt)
            if mode == "capture":
                requests = [request["capture"]]
            else:
                handler.wfile.write(b"READY\n")
                handler.request.settimeout(
                    1900 if mode in {"capture-serve", "pointer-serve"} else 120
                )
                requests = iter(lambda: handler.rfile.readline(4096), b"")
            for line in requests:
                if mode == "keys":
                    events = parse_events(line.decode().split())
                    if any(action == "down" for _, action in events):
                        if not self.guarded:
                            raise RuntimeError(
                                "The game has not passed its native startup guard"
                            )
                        self.verify_window(pid)
                    native.send(events)
                elif mode == "pointer-serve":
                    self.pointer_request(pid, pointer, json.loads(line))
                else:
                    if not self.guarded:
                        raise RuntimeError(
                            "Capture requires the same PID's successful startup guard"
                        )
                    values = json.loads(line) if isinstance(line, bytes) else line
                    if (
                        len(values) != 5
                        or any(type(value) is not int for value in values[:4])
                        or not isinstance(values[4], str)
                    ):
                        raise ValueError("Capture requires x,y,width,height,path")
                    self.capture(pid, values[:4], values[4])
                handler.wfile.write(b"OK\n")
        except (
            OSError,
            RuntimeError,
            ValueError,
            KeyError,
            TypeError,
            subprocess.SubprocessError,
        ) as error:
            reason = f"{type(error).__name__}: {error}".replace("\n", " ")
            result = {"pid": pid, "result": "UNVERIFIED", "reason": reason}
            reply = json.dumps(result) if mode == "guard" else f"ERROR {reason}"
            try:
                handler.wfile.write(reply.encode() + b"\n")
            except OSError:
                pass  # Disconnected clients still reach native key cleanup.
        finally:
            try:
                if native:
                    native.close(release=True)
                if pointer:
                    pointer.close(release=True)
            except (OSError, RuntimeError) as error:
                self.cleanup_errors.append(str(error))
            finally:
                if owns_keyboard:
                    self.keyboard.release()
                if owns_pointer:
                    self.auxiliary_windows.clear()
                    self.pointer.release()
                with self.lock:
                    self.connections.discard(handler.request)
                    self.sessions.discard(done)
                done.set()

    def pointer_request(self, pid, pointer, request):
        if not self.guarded:
            raise RuntimeError("Pointer input requires the same PID's startup guard")
        self.identify(pid)
        if not isinstance(request, list) or not request:
            raise ValueError("Pointer request must be a non-empty JSON array")
        command = request[0]
        if not isinstance(command, str):
            raise TypeError("Pointer operation name must be text")
        if command in {"register-aux", "unregister-aux"}:
            if (
                len(request) != 2
                or not isinstance(request[1], str)
                or request[1] not in AUXILIARY_TITLES
            ):
                raise ValueError("Unsupported auxiliary audit window")
            title = request[1]
            if command == "unregister-aux":
                if title not in self.auxiliary_windows:
                    raise RuntimeError("Auxiliary audit window was not registered")
                del self.auxiliary_windows[title]
            else:
                self.register_auxiliary(pid, title)
            return
        if (
            command == "move"
            and len(request) == 3
            and all(type(v) is int for v in request[1:])
        ):
            self.pointer_focus(pid, allow_auxiliary=True)
            self.require_point_in_game(pid, request[1:])
            pointer.move(*request[1:])
        elif (
            command == "button"
            and len(request) == 3
            and isinstance(request[1], str)
            and request[1] in {"left", "middle", "right"}
            and type(request[2]) is bool
        ):
            if request[2]:
                self.verify_window(pid)
                self.require_point_in_game(pid, pointer.position())
            elif request[1] not in pointer.held:
                raise RuntimeError(
                    "Cannot release a pointer button this test session did not press"
                )
            # Releases are cleanup, never a new activation; allow them even if focus changes unexpectedly.
            pointer.button(request[1], request[2])
        elif (
            command == "wheel"
            and len(request) == 2
            and type(request[1]) is int
            and 0 < abs(request[1]) <= 20
        ):
            self.verify_window(pid)
            self.require_point_in_game(pid, pointer.position())
            pointer.wheel(request[1])
        else:
            raise ValueError("Invalid native pointer operation")

    def register_auxiliary(self, pid, title):
        # AX focus can become visible before CGWindowList publishes a new AWT
        # window. Observe both independently; this wait never emits input.
        started = time.monotonic()
        record = {"pid": pid, "title": title, "result": "UNVERIFIED", "attempts": []}
        try:
            while True:
                attempt = {"milliseconds": (time.monotonic() - started) * 1000}
                record["attempts"].append(attempt)
                try:
                    self.identify(pid)
                    attempt["focus"] = self.auxiliary_guard(pid, title)
                    window = self.windows.find(pid, title=title)
                    self.auxiliary_windows[title] = window["id"]
                    record.update(result="PASS", window=window)
                    return
                except RuntimeError as error:
                    attempt["reason"] = str(error)
                    remaining = self.auxiliary_timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        raise RuntimeError(
                            f"Auxiliary window {title!r} did not become focused and "
                            f"visible within {self.auxiliary_timeout:g} seconds: {error}"
                        ) from error
                    time.sleep(min(0.025, remaining))
        finally:
            record["milliseconds"] = (time.monotonic() - started) * 1000
            with (self.output / "external-auxiliary-registration.jsonl").open(
                "a"
            ) as log:
                log.write(json.dumps(record) + "\n")

    def require_point_in_game(self, pid, position):
        x, y = position
        left, top, width, height = self.windows.find(pid, title="Emberwood Kotlin")[
            "bounds"
        ]
        if not (left <= x < left + width and top <= y < top + height):
            raise RuntimeError("Pointer position lies outside the exact game window")

    def pointer_focus(self, pid, allow_auxiliary=False):
        try:
            self.guard(pid)
            return
        except RuntimeError as original:
            if allow_auxiliary:
                for title, identifier in self.auxiliary_windows.items():
                    try:
                        self.auxiliary_guard(pid, title)
                        if self.windows.find(pid, title=title)["id"] == identifier:
                            return
                    except RuntimeError:
                        continue
            raise RuntimeError(
                "Pointer move has no verified main or registered auxiliary focus"
            ) from original

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.server.shutdown()
        with self.lock:
            connections, sessions = list(self.connections), list(self.sessions)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # A completed client needs no additional shutdown.
        for done in sessions:
            if not done.wait(5):
                self.cleanup_errors.append(
                    "Native test session did not release within five seconds"
                )
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.capture_process:
            try:
                self.capture_process.stdin.close()
            except BrokenPipeError:
                self.cleanup_errors.append(
                    "Native capture helper closed its input unexpectedly"
                )
            try:
                self.capture_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.capture_process.kill()
                self.capture_process.wait(timeout=5)
                self.cleanup_errors.append(
                    "Native capture helper did not close after EOF"
                )
            if self.capture_process.returncode:
                self.cleanup_errors.append(
                    f"Native capture exited with {self.capture_process.returncode}"
                )
            self.capture_process.stdout.close()
        if self.capture_log:
            self.capture_log.close()
        self.temporary.cleanup()
        if self.cleanup_errors:
            raise RuntimeError("; ".join(self.cleanup_errors))

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        self.close()


def proxy(mode, path, pid, capture=None):
    """Child proxies never call AX, capture APIs or native event posting."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(10)
        connection.connect(str(path))
        with connection.makefile("rb") as stream:
            request = {"mode": mode, "pid": pid}
            if capture is not None:
                request["capture"] = capture
            connection.sendall(json.dumps(request).encode() + b"\n")
            reply = stream.readline(65536).decode().strip()
            if mode == "guard":
                record = json.loads(reply)
                print(json.dumps(record), flush=True)
                if record.get("result") != "PASS" or record.get("pid") != pid:
                    raise RuntimeError("External game-window verification failed")
                return
            if mode == "capture":
                if reply != "OK":
                    raise RuntimeError(reply)
                print("OK", flush=True)
                return
            if reply != "READY":
                raise RuntimeError(f"External native controller unavailable: {reply}")
            print("READY", flush=True)
            for line in sys.stdin:
                connection.sendall(line.encode())
                reply = stream.readline(65536).decode().strip()
                if not reply:
                    raise RuntimeError("External native controller connection closed")
                print(reply, flush=True)
                if reply != "OK":
                    raise RuntimeError(reply)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("guard", "keys", "capture", "capture-serve", "pointer-serve")
    )
    parser.add_argument("socket", type=Path)
    parser.add_argument("pid", type=int)
    parser.add_argument("capture", nargs="*")
    args = parser.parse_args()
    values = None
    if args.mode == "capture":
        if len(args.capture) != 5:
            parser.error("Capture requires X Y WIDTH HEIGHT OUTPUT.png")
        values = [*map(int, args.capture[:4]), args.capture[4]]
    elif args.capture:
        parser.error("Unexpected extra arguments")
    proxy(args.mode, args.socket, args.pid, values)


if __name__ == "__main__":
    main()
