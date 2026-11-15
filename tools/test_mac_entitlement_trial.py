"""Check entitlement-trial refusal paths without signing or launching a real app."""

import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mac_entitlement_trial import identity, sign_without_input


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
                        command, 0, stdout=plistlib.dumps(actual)
                    )

                with patch("mac_entitlement_trial.subprocess.run", side_effect=run):
                    if value is False and not tamper:
                        sign_without_input(root, entitlements, root, expected)
                    else:
                        with self.assertRaises(RuntimeError):
                            sign_without_input(root, entitlements, root, expected)


if __name__ == "__main__":
    unittest.main()
