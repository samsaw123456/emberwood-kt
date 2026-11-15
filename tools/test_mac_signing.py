"""Exercise production signing refusal paths with isolated platform-tool fixtures."""

import json
import os
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE_TOOL = r"""#!/usr/bin/env python3
import json, os, plistlib, shutil, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
if name == 'uname':
    print('Darwin')
elif name == 'plutil':
    data = plistlib.loads(Path(args[-1]).read_bytes())
    Path(args[args.index('-o') + 1]).write_bytes(plistlib.dumps(data))
elif name == 'codesign':
    with open(os.environ['SIGN_TRACE'], 'a') as stream:
        stream.write(json.dumps(args) + '\n')
    app = Path(args[-1])
    if '--force' in args:
        assert '--deep' not in args
        shutil.copyfile(args[args.index('--entitlements') + 1], app / '.policy')
    elif '--verify' in args:
        if os.environ.get('SIGN_FAIL') == 'verify':
            sys.exit(1)
    elif '--verbose=4' in args:
        print('CodeDirectory flags=0x' + ('2(adhoc)' if os.environ.get('SIGN_FAIL') == 'runtime' else '10002(adhoc,runtime)'))
    elif '--entitlements' in args:
        data = plistlib.loads((app / '.policy').read_bytes())
        failure = os.environ.get('SIGN_FAIL')
        if failure == 'extra': data['com.apple.security.device.audio-input'] = True
        if failure == 'type': data['com.apple.security.cs.allow-jit'] = 'true'
        if failure == 'false': data['com.apple.security.cs.allow-jit'] = False
        sys.stdout.buffer.write(plistlib.dumps(data))
"""


class MacSigningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mac signing fixtures ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        tools = self.root / "tools"
        tools.mkdir()
        for name in ["sign_mac_app.sh", "mac_runtime_entitlements.plist"]:
            shutil.copyfile(ROOT / "tools" / name, tools / name)
        (tools / "sign_mac_app.sh").chmod(0o755)
        commands = self.root / "platform tools"
        commands.mkdir()
        for name in ["uname", "codesign", "plutil"]:
            command = commands / name
            command.write_text(FAKE_TOOL)
            command.chmod(0o755)
        self.app = self.root / "Emberwood Kotlin.app"
        (self.app / "Contents/MacOS").mkdir(parents=True)
        (self.app / "Contents/Info.plist").write_bytes(plistlib.dumps({}))
        self.inner = self.app / "Contents/runtime/Contents/Home/lib/modules"
        self.inner.parent.mkdir(parents=True)
        self.inner.write_bytes(b"unchanged private runtime")
        self.trace = self.root / "trace.jsonl"
        self.env = {
            **os.environ,
            "PATH": str(commands) + os.pathsep + os.environ["PATH"],
            "SIGN_TRACE": str(self.trace),
        }

    def run_signer(self, failure=""):
        return subprocess.run(
            [self.root / "tools/sign_mac_app.sh", self.app],
            check=False,
            env={**self.env, "SIGN_FAIL": failure},
            text=True,
            capture_output=True,
            timeout=10,
        )

    def test_outer_only_signing_preserves_runtime_and_checks_exact_policy(self):
        result = self.run_signer()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.trace.read_text().splitlines()]
        self.assertNotIn("--deep", calls[0])
        self.assertEqual(calls[0][calls[0].index("--options") + 1], "runtime")
        self.assertIn(["--verify", "--deep", "--strict", str(self.app)], calls)
        policy = plistlib.loads((self.app / ".policy").read_bytes())
        self.assertEqual(
            policy,
            {
                "com.apple.security.cs.allow-jit": True,
                "com.apple.security.cs.disable-library-validation": True,
            },
        )
        self.assertTrue(all(type(value) is bool for value in policy.values()))
        self.assertEqual(self.inner.read_bytes(), b"unchanged private runtime")

    def test_unverified_or_unhardened_signature_is_rejected(self):
        for failure in ["verify", "runtime"]:
            with self.subTest(failure=failure):
                self.assertNotEqual(self.run_signer(failure).returncode, 0)

    def test_added_entitlement_or_wrong_boolean_value_is_rejected(self):
        for failure in ["extra", "type", "false"]:
            with self.subTest(failure=failure):
                result = self.run_signer(failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("entitlements differ", result.stderr)


if __name__ == "__main__":
    unittest.main()
