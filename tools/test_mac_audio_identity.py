"""Exercise the real Swift PID/config guard without recording or privacy requests."""

import platform
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(platform.system() == "Darwin", "Requires the installed Mac SDK")
class NativeAudioIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="emberwood capture identity "
        )
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.helper = cls.root / "capture"
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
                ROOT / "tools/mac_audio_capture.swift",
                "-o",
                cls.helper,
            ],
            check=True,
            timeout=90,
        )

    def test_exact_native_identity_and_malformed_targets(self):
        app = self.root / "Emberwood Kotlin.app"
        executable = app / "Contents/MacOS/Emberwood Kotlin"
        executable.parent.mkdir(parents=True)
        shutil.copy2("/bin/sleep", executable)
        config = app / "Contents/app/Emberwood Kotlin.cfg"
        config.parent.mkdir()
        metadata = app / "Contents/Info.plist"
        info = {
            "CFBundleIdentifier": "org.emberwood.kotlin",
            "CFBundleExecutable": "Emberwood Kotlin",
        }
        metadata.write_bytes(plistlib.dumps(info))
        valid = (
            "[Application]\napp.mainclass=emberwood.AudioStateFixture\n[JavaOptions]\n"
        )
        config.write_text(valid)
        process = subprocess.Popen([executable, "60"])
        unrelated = subprocess.Popen(["/bin/sleep", "60"])
        try:

            def check(pid):
                return subprocess.run(
                    [self.helper, "--verify-native-fixture", str(pid), app],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            accepted = check(process.pid)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertIn("no capture or permission request", accepted.stdout)
            self.assertIn("exact launched executable", check(unrelated.pid).stderr)
            for invalid in (
                valid.replace("AudioStateFixture", "MainKt"),
                valid.replace("[Application]", "[JavaOptions]"),
                valid.replace(
                    "[JavaOptions]", "app.mainclass=emberwood.AudioStateFixture"
                ),
            ):
                with self.subTest(configuration=invalid):
                    config.write_text(invalid)
                    rejected = check(process.pid)
                    self.assertEqual(rejected.returncode, 77)
                    self.assertIn(
                        "not configured as the audio fixture", rejected.stderr
                    )
            config.write_text(valid)
            metadata.write_bytes(
                plistlib.dumps({**info, "CFBundleIdentifier": "other"})
            )
            self.assertIn("not the isolated Emberwood app", check(process.pid).stderr)
        finally:
            for child in (process, unrelated):
                child.terminate()
                child.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
