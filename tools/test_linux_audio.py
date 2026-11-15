"""Verify output-only session guards and lossless legacy-recorder compatibility."""

import array
import json
import signal
import tempfile
import unittest
import wave
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import audio_audit
import linux_audio_ci


def wav(path, samples):
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        stream.writeframes(samples.tobytes())


class LinuxAudioTests(unittest.TestCase):
    def test_session_shutdown_failure_cannot_leave_a_pass_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "build/libs/emberwood-kotlin.jar"
            bundled = root / "dist/emberwood-kotlin-test/Emberwood Kotlin"
            for path in [
                source,
                bundled / "lib/emberwood-kotlin.jar",
                bundled / "runtime/bin/java",
                root / "tools/linux_game_smoke.py",
            ]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            (root / "build/classes/kotlin/test").mkdir(parents=True)

            @contextmanager
            def session(_output):
                yield {}
                raise RuntimeError("Unexpected node remains after application exit")

            def display_check(_command, log, _environment, _timeout):
                (log.parent / "results.json").write_text(
                    json.dumps({str(i): {"result": "PASS"} for i in range(14)})
                )

            with (
                patch.object(linux_audio_ci, "ROOT", root),
                patch.object(linux_audio_ci, "private_audio_session", session),
                patch.object(linux_audio_ci, "run_display_check", display_check),
                self.assertRaisesRegex(RuntimeError, "Unexpected node"),
            ):
                linux_audio_ci.run_audits(root / "jdk", root / "output")
            report = json.loads((root / "output/completion.json").read_text())
            self.assertEqual(report["result"], "FAIL")
            self.assertEqual(len(report["routes"]), 2)
            self.assertIn("Unexpected node", report["error"])

    def test_missing_build_overwrites_stale_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "completion.json").write_text('{"result":"PASS"}')
            with (
                patch.object(linux_audio_ci, "ROOT", root),
                self.assertRaises(RuntimeError),
            ):
                linux_audio_ci.run_audits(root / "missing-jdk", root)
            self.assertEqual(
                json.loads((root / "completion.json").read_text())["result"], "FAIL"
            )

    def test_old_and_new_policy_profiles_never_start_hardware_monitors(self):
        self.assertEqual(
            linux_audio_ci.policy_command("Linked with libwireplumber 0.4.17"),
            ["wireplumber", "--config-file", "policy.conf"],
        )
        self.assertEqual(
            linux_audio_ci.policy_command("Linked with libwireplumber 0.5.13"),
            ["wireplumber", "--profile", "policy"],
        )
        with self.assertRaises(RuntimeError):
            linux_audio_ci.policy_command("unexpected version")

    def test_output_graph_rejects_hardware_sources_and_extra_sinks(self):
        sink = {
            "type": "PipeWire:Interface:Node",
            "info": {
                "props": {"media.class": "Audio/Sink", "node.name": linux_audio_ci.SINK}
            },
        }
        self.assertEqual(
            linux_audio_ci.validate_virtual_graph([sink])[0]["name"],
            linux_audio_ci.SINK,
        )
        for extra in [
            {"type": "PipeWire:Interface:Device"},
            {
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {"media.class": "Audio/Source", "node.name": "unexpected"}
                },
            },
            {
                "type": "PipeWire:Interface:Node",
                "info": {
                    "props": {"media.class": "Audio/Sink", "node.name": "unexpected"}
                },
            },
        ]:
            with self.subTest(extra=extra), self.assertRaises(RuntimeError):
                linux_audio_ci.validate_virtual_graph([sink, extra])
        with self.assertRaises(RuntimeError):
            linux_audio_ci.validate_virtual_graph([])

    def test_pcm_selection_keeps_exact_prefix_and_original_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            original, selected = (
                Path(directory) / "original.wav",
                Path(directory) / "selected.wav",
            )
            samples = array.array("h", (index % 32767 for index in range(110000)))
            wav(original, samples)
            before = original.read_bytes()
            self.assertEqual(audio_audit.extract_pcm_window(original, selected), 110000)
            self.assertEqual(original.read_bytes(), before)
            with wave.open(str(selected)) as stream:
                self.assertEqual(stream.getnframes(), 96000)
                self.assertEqual(stream.readframes(96000), samples[:96000].tobytes())
            wav(original, samples[:95000])
            with self.assertRaisesRegex(AssertionError, "incomplete"):
                audio_audit.extract_pcm_window(original, selected)
            self.assertFalse(selected.exists())

    def test_both_recorder_protocols_retain_same_window_and_invoke_real_action(self):
        for limited in [True, False]:
            with (
                self.subTest(limited=limited),
                tempfile.TemporaryDirectory() as directory,
            ):
                output = Path(directory)
                commands, signals, actions = [], [], []

                class Recorder:
                    returncode = 0

                    def __init__(
                        self, command, command_log=commands, sample_limit=limited, **_
                    ):
                        command_log.append(command)
                        wav(
                            Path(command[-1]),
                            array.array(
                                "h", [321] * (96000 if sample_limit else 110000)
                            ),
                        )

                    def communicate(self, timeout):
                        return b"", b""

                    def send_signal(self, value, signal_log=signals):
                        signal_log.append(value)

                    def poll(self):
                        return 0

                with (
                    patch.object(
                        audio_audit, "recorder_has_sample_limit", return_value=limited
                    ),
                    patch.object(audio_audit.subprocess, "Popen", Recorder),
                    patch.object(audio_audit.subprocess, "run"),
                    patch.object(audio_audit, "ports", return_value=[456]),
                    patch.object(audio_audit.time, "sleep"),
                ):
                    receipt = audio_audit.record(
                        123,
                        output,
                        "cue",
                        lambda actions=actions: actions.append("cue"),
                    )
                self.assertEqual(actions, ["cue"])
                self.assertEqual(receipt["frames"], 96000)
                self.assertEqual(receipt["peak"], 321)
                self.assertEqual("--sample-count" in commands[0], limited)
                self.assertEqual(signals, [] if limited else [signal.SIGINT])
                self.assertEqual((output / "cue.capture.wav").exists(), not limited)
                json.dumps(receipt)


if __name__ == "__main__":
    unittest.main()
