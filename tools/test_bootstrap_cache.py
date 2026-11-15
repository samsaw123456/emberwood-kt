"""Dogfood first-run Java preparation against a local, checksummed vendor fixture."""

import hashlib
import os
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BootstrapCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Java bootstrap spaces ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tools").mkdir()
        for name in ("bootstrap.sh", "cache_lock.sh"):
            shutil.copyfile(ROOT / "tools" / name, self.root / "tools" / name)
            (self.root / "tools" / name).chmod(0o755)
        jdk = self.root / "vendor/private JDK/bin"
        jdk.mkdir(parents=True)
        (jdk / "java").write_text(
            "#!/usr/bin/env bash\ncase ${1:-} in\n"
            "-version) printf 'openjdk version \"25.0.5\"\\n' >&2 ;;\n"
            '--list-modules) printf "java.base@25.0.5\\njava.desktop@25.0.5\\n" ;;\n'
            "*) exit 2 ;;\nesac\n"
        )
        for name in ("javac", "jlink"):
            (jdk / name).write_text("#!/usr/bin/env bash\nexit 0\n")
        for path in jdk.iterdir():
            path.chmod(0o755)
        self.archive = self.root / "vendor.tar.gz"
        with tarfile.open(self.archive, "w:gz") as archive:
            archive.add(jdk.parent, arcname="vendor-jdk")
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        (self.root / "tools/jdk-downloads.tsv").write_text(
            f"linux\tx64\t{digest}\thttps://invalid.example/fixture-only.tar.gz\n"
        )
        commands = self.root / "commands"
        commands.mkdir()
        (commands / "uname").write_text(
            "#!/usr/bin/env bash\nif [[ $1 == -s ]]; then echo Linux; else echo x86_64; fi\n"
        )
        (commands / "curl").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            'printf "%s\\n" called >> "$FIXTURE_DOWNLOAD_LOG"\n'
            "if [[ ${FIXTURE_BLOCK_DOWNLOAD:-false} == true ]]; then sleep 30; fi\n"
            'while (($#)); do if [[ $1 == --output ]]; then cp "$FIXTURE_ARCHIVE" "$2"; exit 0; fi; shift; done\n'
            "exit 2\n"
        )
        for path in commands.iterdir():
            path.chmod(0o755)
        self.cache = self.root / "cache"
        self.log = self.root / "downloads.log"
        self.environment = {
            key: value
            for key, value in os.environ.items()
            if key != "EMBERWOOD_JAVA_HOME"
        }
        self.environment.update(
            PATH=str(commands) + os.pathsep + os.environ["PATH"],
            EMBERWOOD_CACHE_DIR=str(self.cache),
            FIXTURE_ARCHIVE=str(self.archive),
            FIXTURE_DOWNLOAD_LOG=str(self.log),
        )
        self.bootstrap = self.root / "tools/bootstrap.sh"
        self.install = self.cache / "temurin-25.0.5+8-linux-x64"

    def run_bootstrap(self, *args):
        return subprocess.run(
            [self.bootstrap, *args],
            cwd=self.root,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def concurrent(self):
        processes = [
            subprocess.Popen(
                [self.bootstrap],
                cwd=self.root,
                env=self.environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(3)
        ]
        results = [process.communicate(timeout=20) for process in processes]
        self.assertEqual(
            [process.returncode for process in processes], [0, 0, 0], results
        )
        self.assertEqual(len({stdout for stdout, _ in results}), 1)
        self.assertEqual(self.log.read_text().splitlines(), ["called"])
        self.assertTrue((self.install / "jdk/bin/java").is_file())
        self.assertFalse((self.install / "install-file.lock").exists())

    def test_simultaneous_first_runs_download_once_and_reuse_offline(self):
        self.concurrent()
        result = self.run_bootstrap("--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), ["called"])

    def test_multiple_waiters_recover_a_dead_owner_without_duplicate_download(self):
        self.install.mkdir(parents=True)
        (self.install / "install-file.lock").write_text("2147483647\n")
        self.concurrent()

    def test_lock_disappearing_between_existence_check_and_read_is_retried(self):
        self.install.mkdir(parents=True)
        lock = self.install / "install-file.lock"
        lock.write_text("2147483647\n")
        marker = self.root / "lock-read-race-observed"
        command = self.root / "commands/cat"
        command.write_text(
            "#!/usr/bin/env bash\n"
            'if [[ ${1:-} == "$FIXTURE_LOCK" && ! -e "$FIXTURE_RACE_MARKER" ]]; then\n'
            '  printf "%s\\n" removed > "$FIXTURE_RACE_MARKER"\n'
            '  rm -- "$1"\n'
            "fi\n"
            'exec "$FIXTURE_REAL_CAT" "$@"\n'
        )
        command.chmod(0o755)
        self.environment.update(
            FIXTURE_LOCK=str(lock),
            FIXTURE_RACE_MARKER=str(marker),
            FIXTURE_REAL_CAT=shutil.which("cat"),
        )
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(marker.read_text().splitlines(), ["removed"])
        self.assertEqual(self.log.read_text().splitlines(), ["called"])
        self.assertTrue((self.install / "jdk/bin/java").is_file())
        self.assertFalse(lock.exists())

    def test_interrupted_download_cleans_owned_files_then_recovers(self):
        process = subprocess.Popen(
            [self.bootstrap],
            cwd=self.root,
            env={**self.environment, "FIXTURE_BLOCK_DOWNLOAD": "true"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 10
            while not self.log.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(self.log.exists())
            os.killpg(process.pid, signal.SIGTERM)
            self.assertNotEqual(process.wait(timeout=5), 0)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        self.assertFalse((self.install / "install-file.lock").exists())
        self.assertEqual(list(self.install.glob("download.*")), [])
        self.assertFalse((self.install / "jdk").exists())
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.install / "jdk/bin/java").is_file())

    def test_offline_and_checksum_failure_do_not_publish_a_runtime(self):
        result = self.run_bootstrap("--offline")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())
        self.archive.write_bytes(b"wrong download")
        failed = self.run_bootstrap()
        self.assertEqual(failed.returncode, 2)
        self.assertIn("checksum did not match", failed.stderr)
        self.assertFalse((self.install / "jdk").exists())
        self.assertFalse((self.install / "install-file.lock").exists())


if __name__ == "__main__":
    unittest.main()
