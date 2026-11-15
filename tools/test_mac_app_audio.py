"""Refuse partial/stale PCM evidence and preserve native launch/cleanup contracts."""

import json
import plistlib
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

from mac_app_profile import (
    launch_audio,
    main,
    run_owned_check,
    tree_digest,
    validate_audio,
    validate_audio_trace,
)


def trace_fixture(output):
    trace = output / "trace"
    trace.mkdir()
    (trace / "events.tsv").write_text("kind\tpcm_offset\nwrite\t0\n")
    (trace / "samples.s16le").write_bytes(b"\x01\x00")
    summary = {
        "result": "PASS",
        "truncated": False,
        "native_queue_disposed": True,
        "errors": [],
        "event_count": 1,
        "pcm_bytes": 2,
    }
    (trace / "summary.json").write_text(json.dumps(summary))
    return summary


def fixture(output, app):
    """Structural reports and silent WAV fixtures, never a real audio PASS claim."""
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "result": "PASS",
        "launch_method": "LaunchServices native app",
        "game_jar_sha256": "fixture-sha",
        "game_jar": str(app / "Contents/app/emberwood-kotlin.jar"),
        "java_executable": str(app / "Contents/runtime/Contents/Home/bin/java"),
        "microphone": False,
        "global_audio_fallback": False,
        "game_pid": 12345,
    }
    cleanup = {"result": "PASS", "pid": 12345, "new_windows_remaining": []}
    checks = {
        "full cue audible": True,
        "long reference cue audible": True,
        "mute stops audible cue": True,
        "muted cue is silent": True,
        "physical unmute feedback audible": True,
        "restored cue audible": True,
        "state retained and input focused": True,
    }
    rows = {}
    for state in (
        "TITLE",
        "PLAYING",
        "PAUSED",
        "RESPAWNING",
        "CHAPTER_COMPLETE",
        "WON",
    ):
        bindings = (
            ("m", "Mouse", "Return", "space", "KP_Enter")
            if state in ("TITLE", "PAUSED")
            else ("m",)
        )
        for binding in bindings:
            label = state if binding == "m" else f"{state}-{binding}"
            rows[label] = {
                "result": "PASS",
                "state": state,
                "binding": binding,
                "file_prefix": label,
                "checks": dict(checks),
            }
            for phase in ("full", "long", "cut", "muted", "unmute", "restored"):
                with wave.open(str(output / f"{label}-{phase}.wav"), "wb") as stream:
                    stream.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                    stream.writeframes(b"\0\0" * 10)
    for name, value in [("summary", summary), ("cleanup", cleanup), ("results", rows)]:
        (output / f"{name}.json").write_text(json.dumps(value))
    return summary, cleanup, rows


class NativeAudioDriverTests(unittest.TestCase):
    def test_audio_mode_uses_selected_app_shared_signer_and_after_run_identity(self):
        for tamper, audio_trace in (
            (False, False),
            (False, True),
            ("copied-runtime", True),
            ("original-config", False),
        ):
            with (
                self.subTest(tamper=tamper, audio_trace=audio_trace),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory).resolve()
                (root / "VERSION").write_text("0.1.0\n")
                app = root / "source cache/Emberwood Kotlin.app"
                library = app / "Contents/app"
                library.mkdir(parents=True)
                (library / "emberwood-kotlin.jar").write_bytes(b"game fixture")
                config = library / "Emberwood Kotlin.cfg"
                config.write_text(
                    "[Application]\napp.mainclass=emberwood.MainKt\napp.classpath=$APPDIR/emberwood-kotlin.jar\n[JavaOptions]\njava-options=-Xmx256m\n"
                )
                runtime = app / "Contents/runtime/Contents/Home/bin/java"
                runtime.parent.mkdir(parents=True)
                runtime.write_bytes(b"private runtime fixture")
                (app / "Contents/Info.plist").write_bytes(
                    plistlib.dumps({"CFBundleExecutable": "Emberwood Kotlin"})
                )
                tests = root / "build/classes/kotlin/test/emberwood"
                tests.mkdir(parents=True)
                (tests / "AudioStateFixture.class").write_bytes(b"class fixture")
                output = root / "audio evidence"
                commands = []
                original_digest = tree_digest(app)

                def native_command(
                    command, *, commands=commands, app=app, root=root, **_options
                ):
                    commands.append(command)
                    if command[0] == "ditto":
                        self.assertEqual(command[1], app.resolve())
                        shutil.copytree(command[1], command[2])
                    else:
                        self.assertEqual(command[0], root / "tools/sign_mac_app.sh")
                        self.assertEqual(len(command), 2)

                def audited(
                    copy,
                    target,
                    _digest,
                    *,
                    app=app,
                    output=output,
                    tamper=tamper,
                    audio_trace=audio_trace,
                ):
                    self.assertNotEqual(copy, app)
                    self.assertEqual(target, output)
                    text = (copy / "Contents/app/Emberwood Kotlin.cfg").read_text()
                    self.assertIn("app.mainclass=emberwood.AudioStateFixture", text)
                    self.assertNotIn("audit.inputSocket", text)
                    if audio_trace:
                        self.assertIn(
                            f"java-options=-Daudio.trace.directory={output / 'trace'}\n",
                            text,
                        )
                        trace_fixture(output)
                    else:
                        self.assertNotIn("audio.trace.directory", text)
                    if tamper == "copied-runtime":
                        (copy / "Contents/runtime/Contents/Home/bin/java").write_bytes(
                            b"changed"
                        )
                    elif tamper == "original-config":
                        (app / "Contents/app/Emberwood Kotlin.cfg").write_text(
                            "changed launcher configuration"
                        )
                    return {"result": "PASS", "cases": 14}

                with (
                    patch("mac_app_profile.ROOT", root),
                    patch("mac_app_profile.platform.system", return_value="Darwin"),
                    patch("mac_app_profile.platform.machine", return_value="arm64"),
                    patch(
                        "mac_app_profile.sys.argv",
                        [
                            "audit",
                            "--audit",
                            "audio",
                            "--app",
                            str(app),
                            "--output",
                            str(output),
                        ]
                        + (["--audio-trace"] if audio_trace else []),
                    ),
                    patch(
                        "mac_app_profile.default_output", return_value={"fixture": True}
                    ),
                    patch("mac_app_profile.Controller") as controller,
                    patch("mac_app_profile.subprocess.run", side_effect=native_command),
                    patch("mac_app_profile.launch_audio", side_effect=audited),
                ):
                    if tamper:
                        message = (
                            "changed original app tree"
                            if tamper == "original-config"
                            else "changed production"
                        )
                        with self.assertRaisesRegex(RuntimeError, message):
                            main()
                    else:
                        main()
                    controller.assert_not_called()
                evidence = json.loads((output / "native-app.json").read_text())
                self.assertEqual(evidence["result"], "FAIL" if tamper else "PASS")
                self.assertEqual(evidence["original_app"], str(app.resolve()))
                self.assertEqual(evidence["original_app_tree_sha256"], original_digest)
                self.assertEqual(
                    evidence["original_app_tree_sha256_after"], tree_digest(app)
                )
                self.assertEqual(
                    evidence["original_app_tree_sha256_after"] == original_digest,
                    tamper != "original-config",
                )
                self.assertEqual(
                    evidence["audio_trace_directory"],
                    str(output / "trace") if audio_trace else None,
                )
                self.assertEqual((output / "completion.json").exists(), not tamper)
                self.assertEqual(runtime.read_bytes(), b"private runtime fixture")
                self.assertEqual(len(commands), 2)

    def test_audio_trace_refuses_failed_truncated_unclosed_or_partial_evidence(self):
        mutations = [
            {"result": "FAIL"},
            {"truncated": True},
            {"native_queue_disposed": False},
            {"errors": ["write failed"]},
            {"pcm_bytes": 4},
            {"event_count": 0},
        ]
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            original = trace_fixture(output)
            self.assertEqual(validate_audio_trace(output)["result"], "PASS")
            for mutation in mutations:
                with self.subTest(mutation=mutation):
                    (output / "trace/summary.json").write_text(
                        json.dumps(original | mutation)
                    )
                    with self.assertRaises(RuntimeError):
                        validate_audio_trace(output)
            (output / "trace/summary.json").write_text(json.dumps(original))
            (output / "trace/events.tsv").unlink()
            with self.assertRaisesRegex(RuntimeError, "no event journal"):
                validate_audio_trace(output)

    def test_audio_trace_refuses_other_modes_before_native_access(self):
        for mode in ("performance", "controls", "controls-targeted"):
            with (
                self.subTest(mode=mode),
                patch(
                    "mac_app_profile.sys.argv",
                    ["audit", "--audit", mode, "--audio-trace"],
                ),
                patch("mac_app_profile.default_output") as output,
                patch("mac_app_profile.subprocess.run") as native,
                self.assertRaises(SystemExit) as failure,
            ):
                main()
            self.assertEqual(failure.exception.code, 2)
            output.assert_not_called()
            native.assert_not_called()

    def test_partial_wrong_identity_or_failed_cleanup_never_validate(self):
        mutations = [
            ("summary", lambda x: x.update(launch_method="raw Java executable")),
            ("summary", lambda x: x.update(game_jar_sha256="old-sha")),
            ("summary", lambda x: x.update(java_executable="/global/java")),
            ("summary", lambda x: x.update(microphone=True)),
            ("summary", lambda x: x.update(global_audio_fallback=True)),
            ("cleanup", lambda x: x.update(result="FAIL")),
            ("cleanup", lambda x: x.update(pid=54321)),
            ("cleanup", lambda x: x.update(new_windows_remaining=[9])),
            ("results", lambda x: x.pop("TITLE-Mouse")),
            ("results", lambda x: x["WON"].update(state="TITLE")),
            ("results", lambda x: x["WON"].update(result="FAIL")),
            (
                "results",
                lambda x: x["WON"]["checks"].update({"muted cue is silent": False}),
            ),
            ("results", lambda x: x["WON"]["checks"].pop("restored cue audible")),
        ]
        with tempfile.TemporaryDirectory() as directory:
            output, app = Path(directory) / "pcm", Path(directory) / "app"
            fixture(output, app)
            result = validate_audio(output, app, "fixture-sha")
            self.assertEqual(result["cases"], 14)
            self.assertEqual(len(result["recordings"]), 84)
            for name, mutate in mutations:
                with self.subTest(report=name, mutate=mutate):
                    fixture(output, app)
                    path = output / f"{name}.json"
                    document = json.loads(path.read_text())
                    mutate(document)
                    path.write_text(json.dumps(document))
                    with self.assertRaises(RuntimeError):
                        validate_audio(output, app, "fixture-sha")
            fixture(output, app)
            (output / "PAUSED-Mouse-unmute.wav").unlink()
            with self.assertRaisesRegex(RuntimeError, "missing captured PCM"):
                validate_audio(output, app, "fixture-sha")

    def test_audio_launch_uses_exact_app_and_refuses_stale_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            output, app = Path(directory) / "output", Path(directory) / "native app"
            pcm = output / "pcm"
            fixture(pcm, app)

            def run(owned, command, cleanup_output, timeout):
                self.assertEqual(owned, app)
                self.assertEqual(command[-4:], ["--app", app, "--output", pcm])
                self.assertNotIn("--java", command)
                self.assertEqual(timeout, 900)
                for name in ("summary", "results", "cleanup"):
                    self.assertFalse((pcm / f"{name}.json").exists())
                fixture(pcm, app)
                cleanup_output.mkdir()
                (cleanup_output / "cleanup.json").write_text(
                    json.dumps(
                        {
                            "result": "PASS",
                            "new_windows_remaining": [],
                        }
                    )
                )

            with patch("mac_app_profile.run_owned_check", side_effect=run):
                self.assertEqual(launch_audio(app, output, "fixture-sha")["cases"], 14)
            with (
                patch("mac_app_profile.run_owned_check"),
                self.assertRaises(FileNotFoundError),
            ):
                launch_audio(app, output, "fixture-sha")

    def test_child_timeout_still_checks_only_owned_app_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            app, output = Path(directory) / "copy.app", Path(directory) / "output"
            (app / "Contents").mkdir(parents=True)
            (app / "Contents/Info.plist").write_bytes(
                plistlib.dumps({"CFBundleExecutable": "Emberwood Kotlin"})
            )
            windows = Mock()
            windows.visible_registry.return_value = {7, 8}
            with (
                patch("mac_app_profile.NativeStatus"),
                patch("mac_game_window.GameWindow", return_value=windows),
                patch("mac_app_profile.app_pid", return_value=12345),
                patch("mac_bundle_smoke.cleanup_app") as cleanup,
                patch(
                    "mac_app_profile.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(["fixture"], 1),
                ),
                self.assertRaises(subprocess.TimeoutExpired),
            ):
                run_owned_check(app, ["fixture"], output, 1)
            cleanup.assert_called_once_with(
                12345, app / "Contents/MacOS/Emberwood Kotlin", windows, {7, 8}, output
            )


if __name__ == "__main__":
    unittest.main()
