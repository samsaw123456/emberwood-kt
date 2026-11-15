"""Package audits must use the native Mac launcher, with no raw-JVM fallback."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audit_package import main


class PackageAuditRoutingTests(unittest.TestCase):
    def test_mac_modes_delegate_once_to_the_native_app_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for audio in (False, True):
                with (
                    self.subTest(audio=audio),
                    patch("audit_package.ROOT", root),
                    patch("audit_package.platform.system", return_value="Darwin"),
                    patch(
                        "audit_package.sys.argv",
                        ["audit"] + (["--audio"] if audio else []),
                    ),
                    patch("audit_package.subprocess.run") as run,
                ):
                    main()
                    run.assert_called_once()
                    command = run.call_args.args[0]
                    self.assertEqual(command[1], root / "tools/mac_app_profile.py")
                    self.assertEqual(
                        command[2:4], ["--audit", "audio" if audio else "controls"]
                    )
                    self.assertNotIn("--java", command)
                    self.assertTrue(run.call_args.kwargs["check"])

    def test_linux_keeps_the_actual_packaged_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "VERSION").write_text("0.1.0\n")
            app = root / "dist/emberwood-kotlin-0.1.0-linux-x86_64/Emberwood Kotlin"
            java, jar = app / "runtime/bin/java", app / "lib/emberwood-kotlin.jar"
            for path in (java, jar):
                path.parent.mkdir(parents=True)
                path.touch()
            (root / "build/classes/kotlin/test").mkdir(parents=True)
            with (
                patch("audit_package.ROOT", root),
                patch("audit_package.platform.system", return_value="Linux"),
                patch("audit_package.platform.machine", return_value="x86_64"),
                patch("audit_package.sys.argv", ["audit"]),
                patch("audit_package.subprocess.run") as run,
            ):
                main()
                command = run.call_args.args[0]
                self.assertEqual(command[0], str(java))
                self.assertIn(str(jar), command[command.index("-cp") + 1])
                self.assertEqual(command[-1], "emberwood.NativeAuditKt")


if __name__ == "__main__":
    unittest.main()
