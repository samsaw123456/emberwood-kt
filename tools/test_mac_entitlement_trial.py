"""Check entitlement-trial refusal paths without signing or launching a real app."""

import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mac_entitlement_trial import identity, requested_entitlements, sign_without_input


class EntitlementTests(unittest.TestCase):
    def test_only_explicit_false_and_unchanged_production_bytes_are_accepted(self):
        for value, tamper in [
            (False, False),
            (True, False),
            (None, False),
            (False, True),
        ]:
            with (
                self.subTest(value=value, tamper=tamper),
                tempfile.TemporaryDirectory() as folder,
            ):
                root = Path(folder)
                (root / "Contents/runtime").mkdir(parents=True)
                runtime = root / "Contents/runtime/java"
                runtime.write_bytes(b"original runtime")
                (root / "Contents/app").mkdir(parents=True)
                (root / "Contents/app/emberwood-kotlin.jar").write_bytes(
                    b"original game"
                )
                expected = identity(root)
                entitlements = root / "requested.plist"
                entitlements.write_bytes(
                    plistlib.dumps({"com.apple.security.device.audio-input": False})
                )

                def run(
                    command, *, tamper=tamper, runtime=runtime, value=value, **_kwargs
                ):
                    if tamper:
                        runtime.write_bytes(b"modified runtime")
                    actual = (
                        {}
                        if value is None
                        else {"com.apple.security.device.audio-input": value}
                    )
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout=plistlib.dumps(actual),
                        stderr=b"CodeDirectory flags=0x2(adhoc)\n",
                    )

                with patch("mac_entitlement_trial.subprocess.run", side_effect=run):
                    if value is False and not tamper:
                        sign_without_input(root, entitlements, root, expected)
                    else:
                        with self.assertRaises(RuntimeError):
                            sign_without_input(root, entitlements, root, expected)

    def test_hardened_requires_observed_flag_exact_exceptions_and_unchanged_bytes(self):
        minimal = requested_entitlements("hardened")
        for actual, flags, tamper in [
            (minimal, "10002", False),
            (minimal, "2", False),
            (minimal, None, False),
            (
                {**minimal, "com.apple.security.device.audio-input": False},
                "10002",
                False,
            ),
            (
                {
                    **minimal,
                    "com.apple.security.cs.allow-unsigned-executable-memory": True,
                },
                "10002",
                False,
            ),
            ({"com.apple.security.cs.allow-jit": True}, "10002", False),
            (minimal, "10002", True),
        ]:
            with (
                self.subTest(actual=actual, flags=flags, tamper=tamper),
                tempfile.TemporaryDirectory() as directory,
            ):
                app = Path(directory)
                (app / "Contents/runtime").mkdir(parents=True)
                (app / "Contents/runtime/java").write_bytes(b"original runtime")
                (app / "Contents/app").mkdir(parents=True)
                jar = app / "Contents/app/emberwood-kotlin.jar"
                jar.write_bytes(b"original game")
                expected = identity(app)
                entitlements = app / "request.plist"
                entitlements.write_bytes(plistlib.dumps(minimal))
                commands = []

                def run(
                    command,
                    *,
                    actual=actual,
                    flags=flags,
                    tamper=tamper,
                    jar=jar,
                    commands=commands,
                    **_kwargs,
                ):
                    commands.append(command)
                    if tamper:
                        jar.write_bytes(b"different game")
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout=plistlib.dumps(actual),
                        stderr=(
                            f"CodeDirectory flags=0x{flags}(runtime)\n"
                            if flags
                            else "missing flags\n"
                        ).encode(),
                    )

                with patch("mac_entitlement_trial.subprocess.run", side_effect=run):
                    if actual == minimal and flags == "10002" and not tamper:
                        sign_without_input(app, entitlements, app, expected, "hardened")
                    else:
                        with self.assertRaises(RuntimeError):
                            sign_without_input(
                                app, entitlements, app, expected, "hardened"
                            )
                self.assertIn("--options", commands[0])
                self.assertIn("runtime", commands[0])
                self.assertNotIn("--deep", commands[0])


if __name__ == "__main__":
    unittest.main()
