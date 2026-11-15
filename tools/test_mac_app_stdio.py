"""Real FIFO/process protocol fixtures; no claim of native LaunchServices coverage."""

import os
import plistlib
import select
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mac_app_stdio import NativeAppProcess


class WindowFixture:
    def __init__(self, executable):
        self.path = executable.resolve()

    def executable(self, pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError as error:
            raise RuntimeError("Owned process exited") from error
        return self.path

    def visible_registry(self):
        return set()


class NativeStdioTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="native stdio ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.app = self.root / "Emberwood Kotlin.app"
        (self.app / "Contents/MacOS").mkdir(parents=True)
        self.executable = self.app / "Contents/MacOS/Emberwood Kotlin"
        self.executable.write_text("fixture identity only")
        (self.app / "Contents/Info.plist").write_bytes(
            plistlib.dumps({"CFBundleExecutable": self.executable.name})
        )
        self.pid_file = self.root / "pid"
        self.opener = self.root / "fake-open.py"
        self.opener.write_text(
            "import os,sys\nfrom pathlib import Path\n"
            "if '-h' in sys.argv:\n    print('--stdin --stdout --stderr'); raise SystemExit\n"
            f"Path({str(self.pid_file)!r}).write_text(str(os.getpid()))\n"
            "with open(sys.argv[sys.argv.index('--stdin')+1]) as incoming, open(sys.argv[sys.argv.index('--stdout')+1], 'w', buffering=1) as outgoing:\n"
            "    outgoing.write('READY\\n')\n"
            "    for line in incoming: outgoing.write('ECHO '+line)\n"
        )
        original_run = subprocess.run

        def run(command, *args, **kwargs):
            if command[0] == "screencapture":
                return subprocess.CompletedProcess(command, 0)
            return original_run(command, *args, **kwargs)

        self.addCleanup(patch.stopall)
        patch("mac_bundle_smoke.subprocess.run", side_effect=run).start()

    def discover(self, *_args):
        text = self.pid_file.read_text().strip() if self.pid_file.exists() else ""
        return int(text) if text.isdigit() else None

    def start(self, executable=None):
        return NativeAppProcess(
            self.app,
            self.root,
            self.root,
            windows=WindowFixture(executable or self.executable),
            native=object(),
            discover=self.discover,
            opener=(sys.executable, self.opener),
        )

    def read(self, process):
        self.assertTrue(select.select([process.stdout], [], [], 5)[0])
        return process.stdout.readline().strip()

    def test_private_fifos_transfer_commands_and_close_on_eof(self):
        with self.start() as process:
            self.assertEqual(self.read(process), "READY")
            pipes = Path(process.temporary.name)
            for path in pipes.iterdir():
                self.assertTrue(stat.S_ISFIFO(path.stat().st_mode))
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            for command in ("status", 'quoted "path" and fox 🦊'):
                process.stdin.write(command + "\n")
                process.stdin.flush()
                self.assertEqual(self.read(process), "ECHO " + command)
            process.stdin.close()
            self.assertEqual(process.wait(timeout=5), 0)
            pid = process.pid
        self.assertFalse(pipes.exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_wrong_native_identity_is_rejected_and_owned_opener_is_reaped(self):
        with self.assertRaisesRegex(RuntimeError, "different executable"):
            self.start(Path("/different/application"))
        with self.assertRaises(ProcessLookupError):
            os.kill(int(self.pid_file.read_text()), 0)


if __name__ == "__main__":
    unittest.main()
