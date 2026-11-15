"""Exercise the real source/cache shell flow with isolated platform-tool fixtures."""

import json
import os
import plistlib
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE_TOOL = r"""#!/usr/bin/env python3
import json, os, plistlib, shlex, shutil, sys, time
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
if name == 'uname':
    print(os.environ.get('FIXTURE_OS', 'Darwin'))
    sys.exit(0)
with open(os.environ['FIXTURE_TRACE'], 'a') as stream:
    stream.write(json.dumps([name, args]) + '\n')
if os.environ.get('FIXTURE_FAIL') == name:
    print('fixture failure: ' + name, file=sys.stderr)
    sys.exit(19)
if os.environ.get('FIXTURE_BLOCK') == name:
    time.sleep(30)
def option(key):
    return args[args.index(key) + 1]
if name == 'jlink':
    dest = Path(option('--output'))
    (dest / 'bin').mkdir(parents=True)
    (dest / 'lib').mkdir()
    java = dest / 'bin/java'
    java.write_text('fixture linked Java\n')
    java.chmod(0o755)
    jdk = Path(sys.argv[0]).resolve().parents[1]
    module = jdk / 'jmods/java.desktop.jmod'
    (dest / 'lib/modules').write_bytes((module if module.exists() else jdk / 'lib/modules').read_bytes())
elif name == 'jpackage':
    app = Path(option('--dest')) / 'Emberwood Kotlin.app'
    for folder in ['app', 'Resources', 'MacOS', 'runtime/Contents']:
        (app / 'Contents' / folder).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(option('--input')) / 'emberwood-kotlin.jar', app / 'Contents/app/emberwood-kotlin.jar')
    shutil.copytree(option('--runtime-image'), app / 'Contents/runtime/Contents/Home')
    java_options = [part for i, arg in enumerate(args) if arg == '--java-options'
                    for part in shlex.split(args[i + 1])]
    if os.environ.get('FIXTURE_OMIT_APPLICATION_NAME'):
        java_options = [value for value in java_options if not value.startswith('-Dapple.awt.application.name=')]
    (app / 'Contents/app/Emberwood Kotlin.cfg').write_text(
        '[Application]\napp.mainclass=' + option('--main-class') + '\n[JavaOptions]\n' +
        ''.join('java-options=' + value + '\n' for value in java_options))
    (app / 'Contents/MacOS/Emberwood Kotlin').write_text('fixture native launcher')
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundleVersion': option('--app-version'),
        'CFBundleShortVersionString': option('--app-version'),
        'LSApplicationCategoryType': 'public.app-category.' + option('--mac-app-category'),
    }))
elif name == 'sips':
    shutil.copyfile(args[3], option('--out'))
elif name == 'iconutil':
    Path(option('-o')).write_bytes(b'fixture icon')
elif name == 'codesign':
    app = Path(args[-1])
    if '--force' in args and '--entitlements' in args:
        shutil.copyfile(option('--entitlements'), app / '.policy')
    elif '--verbose=4' in args:
        print('CodeDirectory flags=0x10002(adhoc,runtime)')
    elif '--entitlements' in args:
        sys.stdout.buffer.write((app / '.policy').read_bytes())
elif name == 'plutil':
    Path(option('-o')).write_bytes(plistlib.dumps(plistlib.loads(Path(args[-1]).read_bytes())))
elif name == 'PlistBuddy':
    action = option('-c').split()
    path = Path(args[-1])
    data = plistlib.loads(path.read_bytes())
    key = action[1].lstrip(':')
    if action[0] == 'Set' and key not in data:
        sys.exit(1)
    data[key] = action[-1]
    path.write_bytes(plistlib.dumps(data))
elif name == 'java':
    if args and args[0].endswith('LauncherDesktopProbe.java'):
        sys.exit(int(os.environ.get('FIXTURE_PROBE_STATUS', '0')))
    if '--version' in args:
        print('Emberwood Kotlin fixture version')
    elif '--invalid' in args or os.environ.get('FIXTURE_PROBE_STATUS') == '3':
        print('Existing CLI reports its error', file=sys.stderr)
        sys.exit(2)
elif name == 'open':
    if args == ['-h']:
        print('--stdout --stderr')
    else:
        Path(option('--stdout')).write_text('native output\n')
        Path(option('--stderr')).write_text(os.environ.get('FIXTURE_NATIVE_STDERR', ''))
"""


class SourceMacAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="source launcher spaces ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project with spaces"
        self.root.mkdir()
        for name in [
            "emberwood-kotlin",
            "tools/link_runtime.sh",
            "tools/build_mac_app.sh",
            "tools/sign_mac_app.sh",
            "tools/mac_runtime_entitlements.plist",
            "tools/source_mac_app.sh",
            "tools/cache_lock.sh",
            "tools/LauncherDesktopProbe.java",
            "tools/ensure_linux_desktop.sh",
        ]:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
            target.chmod(0o755)
        for name in [
            "VERSION",
            "build.gradle.kts",
            "settings.gradle.kts",
            "gradle.properties",
            "src/main/resources/assets/app/emberwood.png",
        ]:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("0.1.0\n" if name == "VERSION" else "fixture input")
        self.jar = self.root / "build/libs/emberwood-kotlin.jar"
        self.jar.parent.mkdir(parents=True)
        self.jar.write_bytes(b"original game")
        os.utime(self.jar, (time.time() + 30, time.time() + 30))
        self.jdk = self.root / "private JDK"
        self.commands = self.root / "platform tools"
        for folder in [
            self.commands,
            self.jdk / "bin",
            self.jdk / "jmods",
            self.jdk / "lib",
        ]:
            folder.mkdir(parents=True)
        for name in ["java.desktop.jmod", "java.base.jmod"]:
            (self.jdk / "jmods" / name).write_bytes(name.encode())
        (self.jdk / "lib/modules").write_bytes(b"tool runtime")
        (self.jdk / "release").write_bytes(b"JAVA_VERSION=25.0.5")
        for name in [
            "java",
            "jlink",
            "jpackage",
            "uname",
            "sips",
            "iconutil",
            "PlistBuddy",
            "codesign",
            "plutil",
            "open",
        ]:
            tool = (
                self.jdk / "bin"
                if name in {"java", "jlink", "jpackage"}
                else self.commands
            ) / name
            tool.write_text(FAKE_TOOL)
            tool.chmod(0o755)
        bootstrap = self.root / "tools/bootstrap.sh"
        bootstrap.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$FIXTURE_JDK"\n')
        bootstrap.chmod(0o755)
        gradle = self.root / "gradlew"
        gradle.write_text(
            '#!/usr/bin/env bash\nprintf "%s\\n" called >> "$FIXTURE_GRADLE"\n'
        )
        gradle.chmod(0o755)
        self.cache = self.root / "cache with spaces"
        self.trace = self.root / "trace.jsonl"
        self.environment = {
            **os.environ,
            "PATH": str(self.commands) + os.pathsep + os.environ["PATH"],
            "EMBERWOOD_CACHE_DIR": str(self.cache),
            "FIXTURE_TRACE": str(self.trace),
            "FIXTURE_JDK": str(self.jdk),
            "FIXTURE_GRADLE": str(self.root / "gradle-called"),
        }

    def run_cache(self, **environment):
        return subprocess.run(
            [self.root / "tools/source_mac_app.sh", self.jdk, self.jar],
            check=False,
            cwd=self.root,
            env={**self.environment, **environment},
            capture_output=True,
            text=True,
            timeout=20,
        )

    def run_launcher(self, *args, **environment):
        return subprocess.run(
            [self.root / "emberwood-kotlin", *args],
            check=False,
            cwd=self.root,
            env={**self.environment, **environment},
            capture_output=True,
            text=True,
            timeout=20,
        )

    def calls(self, name):
        rows = (
            [json.loads(line) for line in self.trace.read_text().splitlines()]
            if self.trace.exists()
            else []
        )
        return [args for tool, args in rows if tool == name]

    def app(self):
        result = self.run_cache()
        self.assertEqual(result.returncode, 0, result.stderr)
        return Path(result.stdout.strip())

    def test_build_reuse_and_actual_jar_and_module_invalidation(self):
        first = self.app()
        metadata = plistlib.loads((first / "Contents/Info.plist").read_bytes())
        self.assertEqual(
            metadata["LSApplicationCategoryType"],
            "public.app-category.adventure-games",
        )
        self.assertEqual(metadata["CFBundleShortVersionString"], "0.1.0")
        self.assertEqual(metadata["CFBundleVersion"], "1.1.0")
        self.assertEqual(self.app(), first)
        self.assertEqual(len(self.calls("jlink")), 1)
        self.assertEqual(len(self.calls("jpackage")), 1)
        self.jar.write_bytes(b"changed game")
        second = self.app()
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.calls("jlink")), 1)
        (self.jdk / "jmods/java.desktop.jmod").write_bytes(b"changed runtime module")
        third = self.app()
        self.assertNotEqual(second, third)
        self.assertEqual(len(self.calls("jlink")), 2)
        self.assertEqual(
            (third / "Contents/app/emberwood-kotlin.jar").read_bytes(), b"changed game"
        )

    def test_corrupt_cached_jar_and_runtime_are_rebuilt(self):
        first = self.app()
        (first / "Contents/app/emberwood-kotlin.jar").write_bytes(b"damaged cache")
        self.assertEqual(self.app(), first)
        self.assertEqual(
            (first / "Contents/app/emberwood-kotlin.jar").read_bytes(), b"original game"
        )
        runtime = next(
            (self.cache / "source-apps/runtimes").glob("*/runtime/lib/modules")
        )
        runtime.write_bytes(b"damaged runtime")
        self.app()
        self.assertEqual(len(self.calls("jlink")), 2)
        self.assertEqual(runtime.read_bytes(), b"java.desktop.jmod")

    def test_signer_and_policy_changes_invalidate_only_the_app(self):
        first = self.app()
        signer = self.root / "tools/sign_mac_app.sh"
        signer.write_text(signer.read_text() + "\n# Changed signing implementation\n")
        second = self.app()
        self.assertNotEqual(first, second)
        policy = self.root / "tools/mac_runtime_entitlements.plist"
        policy.write_text(policy.read_text() + "\n")
        third = self.app()
        self.assertNotEqual(second, third)
        self.assertEqual(len(self.calls("jlink")), 1)
        self.assertEqual(len(self.calls("jpackage")), 3)

    def test_source_cache_and_release_builder_preserve_complete_application_name(self):
        cached = self.app()
        config = "Contents/app/Emberwood Kotlin.cfg"
        expected = "java-options=-Dapple.awt.application.name=Emberwood Kotlin"
        self.assertEqual((cached / config).read_text().splitlines().count(expected), 1)
        self.assertNotIn("Xdock:", (cached / config).read_text())
        runtime = next((self.cache / "source-apps/runtimes").glob("*/runtime"))
        stage = self.root / "release stage"
        built = subprocess.run(
            [
                self.root / "tools/build_mac_app.sh",
                self.jdk,
                self.jar,
                runtime,
                stage,
                "0.1.0",
            ],
            check=False,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(built.returncode, 0, built.stderr)
        release = Path(built.stdout.strip())
        self.assertEqual(
            (release / config).read_bytes(), (cached / config).read_bytes()
        )
        builder = self.root / "tools/build_mac_app.sh"
        builder.write_text(builder.read_text() + "\n# Changed app recipe\n")
        rebuilt = self.app()
        self.assertNotEqual(rebuilt, cached)
        self.assertEqual(
            (rebuilt / config).read_bytes(), (cached / config).read_bytes()
        )
        self.assertEqual(len(self.calls("jlink")), 1)
        self.assertEqual(len(self.calls("jpackage")), 3)

    def test_missing_generated_application_name_cannot_publish_cached_app(self):
        result = self.run_cache(FIXTURE_OMIT_APPLICATION_NAME="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lost the complete application name", result.stderr)
        self.assertEqual(list((self.cache / "source-apps/apps").iterdir()), [])

    def test_pinned_java25_linkable_runtime_needs_no_jmods_directory(self):
        shutil.rmtree(self.jdk / "jmods")
        first = self.app()
        self.assertEqual(self.app(), first)
        (self.jdk / "lib/modules").write_bytes(b"changed linkable runtime")
        second = self.app()
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.calls("jlink")), 2)

    def test_failed_and_interrupted_construction_never_publish_an_app(self):
        failed = self.run_cache(FIXTURE_FAIL="jpackage")
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(list((self.cache / "source-apps/apps").iterdir()), [])
        process = subprocess.Popen(
            [self.root / "tools/source_mac_app.sh", self.jdk, self.jar],
            cwd=self.root,
            env={**self.environment, "FIXTURE_BLOCK": "jpackage"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 10
            while len(self.calls("jpackage")) < 2 and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual(len(self.calls("jpackage")), 2)
            os.killpg(process.pid, signal.SIGTERM)
            self.assertNotEqual(process.wait(timeout=5), 0)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        self.assertFalse((self.cache / "source-apps/build.lock").exists())
        self.assertEqual(list((self.cache / "source-apps").glob(".app.*")), [])
        self.assertTrue(self.app().is_dir())

    def test_concurrent_launchers_share_one_complete_app(self):
        command = [self.root / "tools/source_mac_app.sh", self.jdk, self.jar]
        processes = [
            subprocess.Popen(
                command,
                cwd=self.root,
                env=self.environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        results = [process.communicate(timeout=20) for process in processes]
        self.assertEqual([p.returncode for p in processes], [0, 0], results)
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(len(self.calls("jpackage")), 1)

    def test_mac_launch_is_native_and_relative_data_directory_is_preserved(self):
        result = self.run_launcher("--data-dir", "my saves")
        self.assertEqual(result.returncode, 0, result.stderr)
        invocation = self.calls("open")[-1]
        self.assertEqual(
            invocation[-3:], ["--args", "--data-dir", str(self.root / "my saves")]
        )
        self.assertIn("-W", invocation)
        self.assertIn("-n", invocation)
        self.assertIn("native output", result.stdout)
        again = self.run_launcher("--offline")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(len(self.calls("jpackage")), 1)
        self.assertFalse((self.root / "gradle-called").exists())

    def test_cli_headless_and_invalid_jvm_options_do_not_construct_or_open_apps(self):
        self.assertEqual(self.run_launcher("--help").returncode, 0)
        self.assertEqual(self.run_launcher("--version").returncode, 0)
        self.assertEqual(self.run_launcher("--invalid").returncode, 2)
        self.assertEqual(self.run_launcher(FIXTURE_PROBE_STATUS="3").returncode, 2)
        self.assertEqual(self.run_launcher(FIXTURE_PROBE_STATUS="9").returncode, 9)
        self.assertEqual(self.calls("jpackage"), [])
        self.assertEqual(self.calls("open"), [])

    def test_linux_keeps_the_direct_java_command(self):
        result = self.run_launcher(
            "--data-dir", "relative save", FIXTURE_OS="Linux", DISPLAY=""
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("open"), [])
        self.assertEqual(self.calls("jlink"), [])
        self.assertEqual(
            self.calls("java")[-1],
            [
                "-Xms32m",
                "-Xmx256m",
                "--enable-native-access=ALL-UNNAMED",
                "-jar",
                "build/libs/emberwood-kotlin.jar",
                "--data-dir",
                "relative save",
            ],
        )

    def test_build_only_prepares_native_app_without_launch(self):
        result = self.run_launcher("--build")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls("jpackage")), 1)
        self.assertTrue((self.root / "gradle-called").exists())
        self.assertEqual(self.calls("open"), [])


if __name__ == "__main__":
    unittest.main()
