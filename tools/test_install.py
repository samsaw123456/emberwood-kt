"""Exercise the shipped installer against isolated homes and real desktop-file parsing."""

import os
import platform
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(platform.system() == "Linux", "Linux desktop registration tests")
class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="emberwood installer ")
        self.work = Path(self.temporary.name)
        self.home = self.work / 'home with spaces $and%percent "quote" `tick` \\slash'
        self.home.mkdir()
        self.data = self.home / "data"
        self.bundle = self.work / "release"
        self.bundle.mkdir()
        self.app = self.bundle / "Emberwood Kotlin"
        (self.app / "bin").mkdir(parents=True)
        (self.app / ".emberwood-kotlin-managed").write_text("fixture\n")
        (self.app / "icon.png").write_bytes(b"fixture icon")
        self.launcher = self.app / "bin/emberwood-kotlin"
        self.launcher.write_text(
            '#!/bin/sh\nprintf "%s\\n" "launched" > "$HOME/launched.txt"\n'
        )
        self.launcher.chmod(0o755)
        self.installer = self.bundle / "Install Emberwood Kotlin.command"
        shutil.copy2(ROOT / "tools/install.sh", self.installer)
        self.env = dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.data))
        self.destination = self.data / "emberwood-kotlin/app"
        self.desktop = self.data / "applications/org.emberwood.kotlin.desktop"

    def tearDown(self):
        self.temporary.cleanup()

    def run_installer(self, *arguments, success=True):
        result = subprocess.run(
            check=False,
            args=[str(self.installer), *arguments],
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_install_upgrade_registration_and_remove(self):
        self.run_installer()
        self.assertTrue((self.destination / "bin/emberwood-kotlin").is_file())
        subprocess.run(["desktop-file-validate", str(self.desktop)], check=True)
        # Gio parses Exec quoting itself, including spaces, dollars and percent signs.
        result = subprocess.run(
            check=False,
            args=["gio", "launch", str(self.desktop)],
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        import time

        for _ in range(100):
            if (self.home / "launched.txt").exists():
                break
            time.sleep(0.02)
        self.assertEqual((self.home / "launched.txt").read_text(), "launched\n")
        (self.destination / "obsolete.txt").write_text("old release")
        self.launcher.write_text("#!/bin/sh\nexit 0\n")
        self.run_installer()
        self.assertFalse((self.destination / "obsolete.txt").exists())
        self.assertEqual(
            (self.destination / "bin/emberwood-kotlin").read_text(),
            self.launcher.read_text(),
        )
        self.run_installer("--uninstall")
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.desktop.exists())
        self.run_installer("--uninstall")

    def test_unmarked_installation_is_preserved(self):
        self.destination.mkdir(parents=True)
        sentinel = self.destination / "personal-file"
        sentinel.write_text("keep")
        self.run_installer(success=False)
        self.run_installer("--uninstall", success=False)
        self.assertEqual(sentinel.read_text(), "keep")

    def test_incomplete_package_and_invalid_option(self):
        (self.app / ".emberwood-kotlin-managed").unlink()
        self.run_installer(success=False)
        self.assertFalse(self.destination.exists())
        self.run_installer("--unknown", success=False)
        self.run_installer("--uninstall", "unexpected", success=False)

    def test_interrupted_replacement_restores_previous_app(self):
        self.run_installer()
        sentinel = self.destination / "previous-release.txt"
        sentinel.write_text("preserved")
        wrappers = self.work / "wrappers"
        wrappers.mkdir()
        wrapper = wrappers / "mv"
        wrapper.write_text(
            '#!/bin/bash\nset -eu\n/bin/mv "$@"\n'
            'if [[ "${2:-}" == "$EMBERWOOD_TEST_TARGET" && "${3:-}" == */previous '
            '&& ! -e "$EMBERWOOD_FAIL_ONCE" ]]; then\n'
            ' touch "$EMBERWOOD_FAIL_ONCE"\n kill -TERM "$PPID"\nfi\n',
        )
        wrapper.chmod(0o755)
        self.env.update(
            PATH=str(wrappers) + os.pathsep + os.environ["PATH"],
            EMBERWOOD_TEST_TARGET=str(self.destination),
            EMBERWOOD_FAIL_ONCE=str(self.work / "interrupted"),
        )
        self.run_installer(success=False)
        self.assertEqual(sentinel.read_text(), "preserved")
        self.assertTrue((self.destination / "bin/emberwood-kotlin").is_file())
        self.run_installer()
        self.assertFalse(sentinel.exists())

    def test_bad_download_checksum_installs_nothing(self):
        wrappers = self.work / "bad-download"
        wrappers.mkdir()
        downloader = wrappers / "curl"
        downloader.write_text(
            '#!/bin/sh\nwhile [ "$#" -gt 0 ]; do\n'
            ' if [ "$1" = --output ]; then shift; printf tampered > "$1"; exit 0; fi\n'
            " shift\ndone\nexit 1\n",
        )
        downloader.chmod(0o755)
        cache = self.work / "checksum-cache"
        environment = dict(
            self.env,
            EMBERWOOD_CACHE_DIR=str(cache),
            PATH=str(wrappers) + os.pathsep + os.environ["PATH"],
        )
        environment.pop("EMBERWOOD_JAVA_HOME", None)
        result = subprocess.run(
            [ROOT / "tools/bootstrap.sh"],
            env=environment,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"checksum did not match", result.stderr)
        self.assertFalse(list(cache.glob("*/jdk")))
        self.assertFalse(list(cache.glob("*/install.lock")))
        self.assertFalse(list(cache.glob("*/download.*")))

    def test_missing_offline_jdk_and_invalid_override(self):
        environment = dict(self.env, EMBERWOOD_CACHE_DIR=str(self.work / "empty-cache"))
        environment.pop("EMBERWOOD_JAVA_HOME", None)
        result = subprocess.run(
            check=False,
            args=[ROOT / "tools/bootstrap.sh", "--offline"],
            env=environment,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"not cached", result.stderr)
        environment["EMBERWOOD_JAVA_HOME"] = str(self.work / "not-a-jdk")
        result = subprocess.run(
            check=False,
            args=[ROOT / "tools/bootstrap.sh"],
            env=environment,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"complete JDK 25", result.stderr)


if __name__ == "__main__":
    unittest.main()
