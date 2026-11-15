"""Exercise dependency recovery without invoking a host package manager."""

import os
import pty
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DesktopDependenciesTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="emberwood dependencies ")
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "private runtime"
        (self.runtime / "lib/server").mkdir(parents=True)
        (self.runtime / "bin").mkdir()
        for name in ("libawt_xawt.so", "libfontmanager.so", "libjsound.so"):
            (self.runtime / "lib" / name).write_text("native-library fixture")
        self.commands = self.root / "commands"
        self.commands.mkdir()
        for name in ("awk", "sort", "find", "bash", "dirname"):
            (self.commands / name).symlink_to(shutil.which(name))
        self.env = {
            **os.environ,
            "PATH": str(self.commands),
            "DISPLAY": ":fixture",
            "TEST_ROOT": str(self.root),
            "TEST_RUNTIME": str(self.runtime),
            "TEST_MISSING": "libXtst.so.6",
        }
        self.command("uname", "printf 'Linux\\n'\n")
        self.command("id", "printf '%s\\n' \"${TEST_UID:-0}\"\n")
        (self.root / "libfontconfig.so.1").write_text("fontconfig fixture")
        self.command(
            "od", "[[ ${TEST_OD_FAILURE:-} != yes ]] || exit 9\nprintf '62\\n'\n"
        )
        self.command(
            "ldconfig",
            "[[ ${TEST_CACHE_FAILURE:-} != yes ]] || exit 8\n"
            'if [[ ${TEST_FONTCONFIG:-present} == present || -e "$TEST_ROOT/repaired" ]]; then\n'
            ' printf "libfontconfig.so.1 (libc6,x86-64) => %s\\n" "$TEST_ROOT/libfontconfig.so.1"\nfi\n',
        )
        self.command("notify-send", 'printf "%s\\n" "$*" >> "$TEST_ROOT/notice"\n')
        self.command(
            "ldd",
            'printf "%s\\n" "$LD_LIBRARY_PATH" >> "$TEST_ROOT/ldd-paths"\n'
            '[[ "$LD_LIBRARY_PATH" == "$TEST_RUNTIME/lib:$TEST_RUNTIME/lib/server"* ]] || exit 9\n'
            'if [[ ${TEST_LDD_FAILURE:-} == yes ]]; then printf "broken library\\n"; exit 1; fi\n'
            'if [[ ! -e "$TEST_ROOT/repaired" ]]; then\n'
            ' while IFS= read -r name; do [[ -z "$name" ]] || printf "%s => not found\\n" "$name"; done <<< "$TEST_MISSING"\n'
            "fi\n",
        )
        self.command(
            "apt-get",
            'printf "%s\\n" "$@" >> "$TEST_ROOT/package-command"\n'
            'if [[ "${!#}" == update ]]; then\n'
            " [[ ${TEST_UPDATE_FAILURE:-} != yes ]] || exit 100\n"
            ' : > "$TEST_ROOT/metadata-ready"\n exit 0\nfi\n'
            "[[ ${TEST_INSTALL_FAILURE:-} != yes ]] || exit 100\n"
            'if [[ ${TEST_NO_REPAIR:-} != yes ]]; then : > "$TEST_ROOT/repaired"; fi\n',
        )
        self.command(
            "apt-cache",
            'if [[ ${TEST_EMPTY_INDEX:-} == yes && ! -e "$TEST_ROOT/metadata-ready" ]]; then exit 100; fi\n'
            'if [[ "$2" == libasound2t64 || "$2" == libpng16-16t64 ]]; then [[ ${TEST_T64:-yes} == yes ]]; fi\n',
        )
        java = self.runtime / "bin/java"
        java.write_text(
            "#!/bin/bash\n"
            'printf "%s\\n" "$*" >> "$TEST_ROOT/java-calls"\n'
            "[[ ${TEST_VM_FAILURE:-} != yes ]] || exit 7\n"
            'printf "    java.awt.headless = %s\\n" "${TEST_HEADLESS:-false}" >&2\n'
        )
        java.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    def command(self, name, body):
        path = self.commands / name
        path.write_text("#!/bin/bash\nset -eu\n" + body)
        path.chmod(0o755)

    def run_check(self, *options):
        return subprocess.run(
            [
                "/bin/bash",
                ROOT / "tools/ensure_linux_desktop.sh",
                self.runtime,
                *options,
            ],
            check=False,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=10,
        )

    def test_healthy_runtime_does_not_install_or_start_an_extra_jvm(self):
        (self.root / "repaired").touch()
        result = self.run_check("--launch")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "package-command").exists())
        self.assertFalse((self.root / "java-calls").exists())
        self.assertEqual(len((self.root / "ldd-paths").read_text().splitlines()), 4)

    def test_only_missing_packages_are_installed_once_then_rechecked(self):
        self.env["TEST_MISSING"] = "libXtst.so.6\nlibXrender.so.1\nlibXtst.so.6"
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.root / "package-command").read_text().splitlines(),
            [
                "install",
                "--yes",
                "--no-install-recommends",
                "--",
                "libxrender1",
                "libxtst6",
            ],
        )
        self.assertEqual(len((self.root / "ldd-paths").read_text().splitlines()), 8)

    def test_offline_missing_library_never_runs_a_package_manager(self):
        result = self.run_check("--offline")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Offline mode will not download", result.stderr)
        self.assertFalse((self.root / "package-command").exists())

    def test_headless_launches_preserve_existing_game_diagnostic(self):
        self.env["DISPLAY"] = ""
        self.assertEqual(self.run_check("--launch").returncode, 0)
        self.assertFalse((self.root / "ldd-paths").exists())
        self.env.update(DISPLAY=":fixture", TEST_HEADLESS="true")
        self.assertEqual(self.run_check("--launch").returncode, 0)
        self.assertFalse((self.root / "package-command").exists())

    def test_invalid_jvm_options_do_not_trigger_installation(self):
        self.env["TEST_VM_FAILURE"] = "yes"
        self.assertEqual(self.run_check("--launch").returncode, 7)
        self.assertFalse((self.root / "package-command").exists())

    def test_explicit_headless_does_not_require_desktop_inspection_tools(self):
        self.env.update(
            JAVA_TOOL_OPTIONS="-Djava.awt.headless=true", TEST_HEADLESS="true"
        )
        (self.commands / "ldd").unlink()
        self.assertEqual(self.run_check("--launch").returncode, 0)
        self.assertFalse((self.root / "package-command").exists())
        self.assertFalse((self.root / "ldd-paths").exists())

    def test_failed_install_and_unresolved_library_are_errors(self):
        self.env["TEST_INSTALL_FAILURE"] = "yes"
        failed = self.run_check()
        self.assertEqual(failed.returncode, 2)
        self.assertIn("system installer did not finish", failed.stderr)
        self.env.pop("TEST_INSTALL_FAILURE")
        self.env["TEST_NO_REPAIR"] = "yes"
        unresolved = self.run_check()
        self.assertEqual(unresolved.returncode, 2)
        self.assertIn("still missing", unresolved.stderr)

    def test_unknown_library_or_package_manager_does_not_mutate_system(self):
        self.env["TEST_MISSING"] = "libUnknown.so.1"
        unknown = self.run_check()
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("no supported automatic package mapping", unknown.stderr)
        self.env["TEST_MISSING"] = "libXtst.so.6"
        (self.commands / "apt-get").unlink()
        unsupported = self.run_check()
        self.assertEqual(unsupported.returncode, 2)
        self.assertIn("system package manager", unsupported.stderr)
        self.assertFalse((self.root / "package-command").exists())

    def test_normal_graphical_authorization_and_denial(self):
        self.env["TEST_UID"] = "1000"
        self.command(
            "pkexec",
            'printf "%s\\n" "$*" > "$TEST_ROOT/authorization"\n'
            '[[ ${TEST_DENIED:-} != yes ]] || exit 126\nexec "$@"\n',
        )
        self.env["TEST_DENIED"] = "yes"
        self.assertEqual(self.run_check().returncode, 2)
        self.assertFalse((self.root / "package-command").exists())
        self.env.pop("TEST_DENIED")
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "authorization").exists())

    def test_no_authorization_tool_returns_exact_terminal_recovery(self):
        self.env["TEST_UID"] = "1000"
        result = self.run_check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("sudo apt-get install libxtst6", result.stderr)
        self.assertFalse((self.root / "package-command").exists())
        self.assertTrue((self.root / "notice").exists())

    def test_terminal_uses_normal_sudo_authorization(self):
        self.env["TEST_UID"] = "1000"
        self.command("sudo", '[[ "$1" == -- ]]\nshift\nexec "$@"\n')
        master, terminal = pty.openpty()
        try:
            result = subprocess.run(
                ["/bin/bash", ROOT / "tools/ensure_linux_desktop.sh", self.runtime],
                check=False,
                env=self.env,
                stdin=terminal,
                text=True,
                capture_output=True,
                timeout=10,
            )
        finally:
            os.close(terminal)
            os.close(master)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "package-command").exists())

    def test_alsa_package_uses_available_abi_name(self):
        self.env["TEST_MISSING"] = "libasound.so.2"
        self.assertEqual(self.run_check().returncode, 0)
        self.assertIn("libasound2t64", (self.root / "package-command").read_text())
        (self.root / "repaired").unlink()
        (self.root / "package-command").unlink()
        self.env["TEST_T64"] = "no"
        self.assertEqual(self.run_check().returncode, 0)
        self.assertEqual(
            (self.root / "package-command").read_text().splitlines()[-1], "libasound2"
        )

    def test_dynamic_fontconfig_dependency_is_installed_and_rechecked(self):
        self.env.update(TEST_MISSING="", TEST_FONTCONFIG="missing")
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.root / "package-command").read_text().splitlines()[-1],
            "libfontconfig1",
        )

    def test_fontconfig_cache_failure_never_reaches_package_installation(self):
        self.env["TEST_CACHE_FAILURE"] = "yes"
        result = self.run_check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Cannot read the system library cache", result.stderr)
        self.assertFalse((self.root / "package-command").exists())

    def test_empty_package_indexes_refresh_before_choosing_alsa_abi(self):
        self.env.update(TEST_MISSING="libasound.so.2", TEST_EMPTY_INDEX="yes")
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = (self.root / "package-command").read_text().splitlines()
        self.assertIn("update", commands)
        self.assertLess(commands.index("update"), commands.index("install"))
        self.assertEqual(commands[-1], "libasound2t64")
        self.assertNotIn("libasound2", commands)

    def test_failed_index_refresh_does_not_attempt_package_install(self):
        self.env.update(TEST_EMPTY_INDEX="yes", TEST_UPDATE_FAILURE="yes")
        result = self.run_check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Could not refresh package information", result.stderr)
        self.assertNotIn(
            "install", (self.root / "package-command").read_text().splitlines()
        )

    def test_architecture_probe_failure_never_reaches_package_installation(self):
        self.env["TEST_OD_FAILURE"] = "yes"
        result = self.run_check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Cannot inspect the private Java executable", result.stderr)
        self.assertFalse((self.root / "package-command").exists())

    def test_broken_runtime_and_failed_linker_probe_are_not_success(self):
        self.env["TEST_LDD_FAILURE"] = "yes"
        self.assertEqual(self.run_check().returncode, 2)
        self.env.pop("TEST_LDD_FAILURE")
        (self.runtime / "lib/libawt_xawt.so").unlink()
        self.assertEqual(self.run_check().returncode, 2)
        self.assertFalse((self.root / "package-command").exists())

    def source_launcher(self):
        project = self.root / "source"
        (project / "tools").mkdir(parents=True)
        (project / "src/main").mkdir(parents=True)
        (project / "build/libs").mkdir(parents=True)
        for name in (
            "build.gradle.kts",
            "settings.gradle.kts",
            "gradle.properties",
            "VERSION",
        ):
            (project / name).write_text("fixture")
        shutil.copy2(ROOT / "emberwood-kotlin", project / "emberwood-kotlin")
        shutil.copy2(
            ROOT / "tools/ensure_linux_desktop.sh",
            project / "tools/ensure_linux_desktop.sh",
        )
        bootstrap = project / "tools/bootstrap.sh"
        bootstrap.write_text('#!/bin/bash\nprintf "%s\\n" "$TEST_RUNTIME"\n')
        bootstrap.chmod(0o755)
        gradle = project / "gradlew"
        gradle.write_text('#!/bin/bash\n: > "$TEST_ROOT/build-called"\n')
        gradle.chmod(0o755)
        (project / "build/libs/emberwood-kotlin.jar").write_text("fixture game")
        return project / "emberwood-kotlin"

    def test_source_non_gui_options_never_probe_or_install(self):
        launcher = self.source_launcher()
        for arguments in (["--help"], ["--version"], ["--invalid"], ["--build"]):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    ["/bin/bash", launcher, *arguments],
                    check=False,
                    env=self.env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((self.root / "ldd-paths").exists())
                self.assertFalse((self.root / "package-command").exists())
        self.assertTrue((self.root / "build-called").exists())

    def test_source_gui_uses_shared_offline_and_online_recovery(self):
        launcher = self.source_launcher()
        offline = subprocess.run(
            ["/bin/bash", launcher, "--offline"],
            check=False,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(offline.returncode, 2, offline.stderr)
        self.assertFalse((self.root / "package-command").exists())
        online = subprocess.run(
            ["/bin/bash", launcher],
            check=False,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(online.returncode, 0, online.stderr)
        self.assertTrue((self.root / "package-command").exists())


if __name__ == "__main__":
    unittest.main()
