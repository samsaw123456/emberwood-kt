"""Bounded stdin/stdout for one exact LaunchServices test app, using private FIFOs."""

import os
import plistlib
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from mac_app_profile import app_pid
from mac_bundle_smoke import cleanup_app
from mac_game_window import GameWindow
from mac_profile_observer import NativeStatus


class NativeAppProcess:
    def __init__(
        self,
        app,
        data,
        output,
        *,
        windows=None,
        native=None,
        discover=app_pid,
        opener=("open",),
    ):
        self.app, self.output = app.resolve(), output.resolve()
        metadata = plistlib.loads((self.app / "Contents/Info.plist").read_bytes())
        self.executable = self.app / "Contents/MacOS" / metadata["CFBundleExecutable"]
        self.windows = windows or GameWindow()
        self.native = native or NativeStatus()
        self.baseline = self.windows.visible_registry()
        self.pid, self.process, self.stdin, self.stdout = None, None, None, None
        self.temporary = tempfile.TemporaryDirectory(prefix="emberwood-app-stdio-")
        directory = Path(self.temporary.name)
        incoming, outgoing = directory / "stdin", directory / "stdout"
        try:
            help_text = subprocess.run(
                [*opener, "-h"], check=False, capture_output=True, text=True, timeout=5
            )
            if any(
                flag not in help_text.stdout + help_text.stderr
                for flag in ("--stdin", "--stdout", "--stderr")
            ):
                raise RuntimeError(
                    "Installed LaunchServices open does not support required stdio redirection"
                )
            for path in (incoming, outgoing):
                os.mkfifo(path, 0o600)
            # Holding both ends avoids FIFO-open deadlock before LaunchServices starts.
            self.stdin = os.fdopen(
                os.open(incoming, os.O_RDWR | os.O_NONBLOCK), "w", buffering=1
            )
            self.stdout = os.fdopen(
                os.open(outgoing, os.O_RDWR | os.O_NONBLOCK), "r", buffering=1
            )
            self.process = subprocess.Popen(
                [
                    *opener,
                    "-W",
                    "-n",
                    "--stdin",
                    incoming,
                    "--stdout",
                    outgoing,
                    "--stderr",
                    self.output / "native-stderr.log",
                    self.app,
                    "--args",
                    "--data-dir",
                    data,
                ]
            )
            deadline = time.monotonic() + 30
            while self.pid is None:
                self.pid = discover(self.native, self.app)
                if self.pid is not None:
                    if self.windows.executable(self.pid) != self.executable:
                        raise RuntimeError(
                            "LaunchServices stdio PID has a different executable"
                        )
                    break
                if self.process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(
                        "LaunchServices stdio app did not register its exact native PID"
                    )
                time.sleep(0.05)
        except BaseException:
            self.close()
            raise

    def poll(self):
        return self.process.poll()

    def wait(self, timeout):
        return self.process.wait(timeout=timeout)

    def terminate(self):
        if self.pid:
            try:
                same = self.windows.executable(self.pid) == self.executable
            except RuntimeError:
                try:
                    os.kill(self.pid, 0)
                except ProcessLookupError:
                    return
                raise
            if same:
                os.kill(self.pid, signal.SIGTERM)

    def close(self):
        try:
            if self.stdin and not self.stdin.closed:
                self.stdin.close()
            cleanup_app(
                self.pid, self.executable, self.windows, self.baseline, self.output
            )
        finally:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            if self.stdout:
                self.stdout.close()
            self.temporary.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        self.close()
