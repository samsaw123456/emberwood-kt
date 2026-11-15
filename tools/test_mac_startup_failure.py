"""Fail closed on unrelated dialogs, missing kernel status and unsafe cleanup."""

import json
import plistlib
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mac_startup_failure import (
    ERROR_MESSAGE,
    ERROR_TITLE,
    ErrorDialogReader,
    ExitStatus,
    acknowledge_error,
    await_error,
    deny_native_access,
    main,
    validate_denial,
    validate_dialog,
)

CONFIG = """[Application]
app.mainclass=emberwood.MainKt
app.classpath=$APPDIR/emberwood-kotlin.jar
[JavaOptions]
java-options=-Xmx256m
java-options=--enable-native-access=ALL-UNNAMED
"""


def dialog():
    return {
        "pid": 42,
        "frontmost": True,
        "role": "AXWindow",
        "subrole": "AXDialog",
        "title": ERROR_TITLE,
        "modal": True,
        "texts": [ERROR_MESSAGE],
        "buttons": [{"title": "OK", "subrole": None, "enabled": True}],
    }


def event(**values):
    return SimpleNamespace(
        **{
            "ident": 42,
            "filter": -5,
            "flags": 0,
            "fflags": 0x84000000,
            "data": 256,
            **values,
        }
    )


def queue_api(registration=None, completion=None):
    queue = Mock()
    queue.control.side_effect = [
        [event(flags=0x4000, fflags=0, data=0)]
        if registration is None
        else registration,
        [event()] if completion is None else completion,
    ]
    api = SimpleNamespace(
        kqueue=Mock(return_value=queue),
        kevent=Mock(
            side_effect=lambda pid, **values: SimpleNamespace(
                ident=pid, data=0, **values
            )
        ),
        KQ_FILTER_PROC=-5,
        KQ_EV_ADD=1,
        KQ_EV_ENABLE=4,
        KQ_EV_ONESHOT=16,
        KQ_EV_ERROR=0x4000,
        KQ_NOTE_EXIT=0x80000000,
    )
    return api, queue


def app_fixture(path):
    (path / "Contents/app").mkdir(parents=True)
    (path / "Contents/runtime").mkdir()
    (path / "Contents/MacOS").mkdir()
    (path / "Contents/app/game.cfg").write_text(CONFIG)
    (path / "Contents/app/emberwood-kotlin.jar").write_bytes(b"original production jar")
    (path / "Contents/runtime/libjvm").write_bytes(b"private runtime")
    (path / "Contents/MacOS/Emberwood Kotlin").write_bytes(b"native executable")
    (path / "Contents/Info.plist").write_bytes(
        plistlib.dumps({"CFBundleExecutable": "Emberwood Kotlin"})
    )


class StartupFailureTests(unittest.TestCase):
    def test_swing_button_label_is_read_without_accepting_unnamed_or_conflicting_buttons(
        self,
    ):
        # The actual ARM raw tree has an untitled content button plus named
        # chrome subroles. JDK's accessibleLabel must be decoded separately.
        values = {
            "AXRole": "AXButton",
            "AXTitle": None,
            "AXDescription": "OK",
            "AXSubrole": None,
            "AXEnabled": True,
        }
        reader = object.__new__(ErrorDialogReader)
        reader.scalar = lambda _element, name, _kind, **_kwargs: values[name]
        state = dialog()
        state.update(buttons=[], nodes=0)
        reader.read_nodes(17, state, 0)
        self.assertEqual(state["buttons"][0]["description"], "OK")
        self.assertIsNone(state["buttons"][0]["title"])
        state["buttons"].extend(
            {"title": None, "description": name, "subrole": subrole, "enabled": enabled}
            for name, subrole, enabled in (
                ("close", "AXCloseButton", True),
                ("zoom", "AXZoomButton", False),
                ("minimize", "AXMinimizeButton", False),
            )
        )
        validate_dialog(state)
        for changed in (
            {"description": None},
            {"description": "Allow"},
            {"title": "Cancel"},
            {"enabled": False},
        ):
            with self.subTest(changed=changed):
                candidate = {**state, "buttons": [{**state["buttons"][0], **changed}]}
                with self.assertRaises(RuntimeError):
                    validate_dialog(candidate)
        state["buttons"].append({"title": None, "description": None, "enabled": True})
        with self.assertRaises(RuntimeError):
            validate_dialog(state)

    def test_rejected_native_dialog_fields_are_retained_before_any_input(self):
        state = dialog()
        state["texts"] = []
        executable = Path("/owned")
        windows = SimpleNamespace(
            executable=lambda _: executable,
            facilities=lambda: {"access": True},
            find=lambda *_args, **_kwargs: {"id": 7, "title": ERROR_TITLE},
        )
        reader = SimpleNamespace(snapshot=lambda: state)
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("mac_startup_failure.NativeKeys") as keys,
        ):
            output = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "exact owned"):
                await_error(
                    windows, reader, 42, executable, Mock(poll=lambda: None), output
                )
            rows = json.loads((output / "error-observations.json").read_text())
            self.assertEqual(rows[-1]["dialog"], state)
            self.assertEqual(rows[-1]["result"], "FAIL before acknowledgement")
            receipt = {}
            with self.assertRaisesRegex(RuntimeError, "exact owned"):
                acknowledge_error(windows, reader, 42, executable, 7, Mock(), receipt)
            self.assertEqual(receipt["dialog_before_Return"], state)
            self.assertIsNone(receipt["down_started"])
            keys.assert_not_called()

    def test_denial_changes_only_one_launcher_option_and_preserves_original(self):
        with tempfile.TemporaryDirectory(prefix="failure fixture spaces ") as directory:
            original, copied = (
                Path(directory) / "original.app",
                Path(directory) / "copy.app",
            )
            app_fixture(original)
            shutil.copytree(original, copied)
            report = deny_native_access(copied)
            self.assertEqual((original / "Contents/app/game.cfg").read_text(), CONFIG)
            altered = (copied / "Contents/app/game.cfg").read_text()
            self.assertNotIn("--enable-native-access", altered)
            self.assertIn("java-options=--illegal-native-access=deny", altered)
            self.assertIn("app.mainclass=emberwood.MainKt", altered)
            self.assertIn("java-options=-Xmx256m", altered)
            self.assertNotEqual(report["before_sha256"], report["after_sha256"])
            with self.assertRaises(RuntimeError):
                deny_native_access(copied)
            self.assertEqual((copied / "Contents/app/game.cfg").read_text(), altered)

    def test_unknown_access_policy_or_mainclass_is_not_mutated(self):
        for changed in (
            CONFIG + "java-options=--illegal-native-access=warn\n",
            CONFIG.replace("emberwood.MainKt", "emberwood.NativeAuditKt"),
            CONFIG.replace(
                "--enable-native-access=ALL-UNNAMED", "--enable-native-access=other"
            ),
        ):
            with tempfile.TemporaryDirectory() as directory:
                app = Path(directory) / "game.app"
                app_fixture(app)
                config = app / "Contents/app/game.cfg"
                config.write_text(changed)
                with self.assertRaises(RuntimeError):
                    deny_native_access(app)
                self.assertEqual(config.read_text(), changed)

    def test_permission_or_other_dialog_cannot_authorize_acknowledgement(self):
        validate_dialog(dialog())
        for field, value in (
            ("title", "Microphone permission"),
            ("frontmost", False),
            ("texts", ["Allow microphone access?"]),
            ("buttons", [{"title": "Allow", "enabled": True}]),
            ("buttons", [{"title": "OK", "enabled": False}]),
            (
                "buttons",
                [
                    {"title": "OK", "enabled": True},
                    {"title": "Cancel", "enabled": True},
                ],
            ),
        ):
            with self.subTest(field=field, value=value):
                state = dialog()
                state[field] = value
                with self.assertRaises(RuntimeError):
                    validate_dialog(state)
        log = "Unable to prepare the application menu\njava.lang.IllegalCallerException: Illegal native access from an unnamed module\nat emberwood.CocoaMenuApi\n"
        validate_denial(log)
        for removed in ("IllegalCallerException", "CocoaMenuApi", "Unable to prepare"):
            with self.assertRaises(RuntimeError):
                validate_denial(log.replace(removed, "unrelated"))

    def test_exact_pid_exit1_is_decoded_from_kernel_not_launcher(self):
        api, queue = queue_api()
        status = ExitStatus(42, api=api)
        flags = api.kevent.call_args.kwargs
        self.assertEqual(flags["fflags"], 0x84000000)
        self.assertTrue(flags["flags"] & 0x40)
        receipt = status.wait()
        self.assertEqual(receipt["data"], 256)
        self.assertEqual(receipt["exit_code"], 1)
        self.assertTrue(receipt["normal_exit"])
        self.assertEqual(status.observations, [receipt])
        status.close()
        queue.close.assert_called_once()

    def test_wrong_pid_missing_status_signal_or_exit0_never_pass(self):
        for completion in (
            [],
            [event(ident=43)],
            [event(fflags=0x80000000)],
            [event(data=15)],
            [event(data=0)],
            [event(data=512)],
            [event(flags=0x4000)],
        ):
            with self.subTest(completion=completion):
                api, _ = queue_api(completion=completion)
                status = ExitStatus(42, api=api)
                with self.assertRaises(RuntimeError):
                    status.wait()
                status.close()
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            ExitStatus(42, api=SimpleNamespace())
        api, queue = queue_api(registration=[event(flags=0x4000, data=13)])
        with self.assertRaisesRegex(RuntimeError, "register"):
            ExitStatus(42, api=api)
        queue.close.assert_called_once()

    def test_physical_return_releases_attempted_down_and_waits_for_actual_exit(self):
        for fail_down in (False, True):
            events, held = [], set()
            executable = Path("/owned app/game")
            windows = SimpleNamespace(
                executable=lambda _, executable=executable: executable,
                facilities=lambda: None,
                find=lambda *_args, **_kwargs: {"id": 7},
            )
            reader = SimpleNamespace(snapshot=lambda: dialog())
            status, receipt = Mock(), {}

            class Keys:
                def __init__(self, held=held, events=events, fail_down=fail_down):
                    self.held, self.events, self.fail_down = held, events, fail_down
                    self.core = SimpleNamespace(
                        CGEventSourceKeyState=lambda *_: bool(self.held)
                    )

                def send(self, batch):
                    self.held.add("return")
                    self.events.extend(batch)
                    if self.fail_down:
                        raise RuntimeError("down delivered before posting error")

                def close(self, release=True):
                    if self.held:
                        self.held.clear()
                        self.events.append(("return", "up"))

            with (
                patch("mac_startup_failure.NativeKeys", Keys),
                patch("mac_startup_failure.time.sleep"),
            ):
                if fail_down:
                    with self.assertRaisesRegex(RuntimeError, "posting error"):
                        acknowledge_error(
                            windows, reader, 42, executable, 7, status, receipt
                        )
                    status.wait.assert_not_called()
                else:
                    acknowledge_error(
                        windows, reader, 42, executable, 7, status, receipt
                    )
                    status.wait.assert_called_once()
            self.assertEqual(events, [("return", "down"), ("return", "up")])
            self.assertTrue(receipt["up_observed"])
            self.assertIsNotNone(receipt["down_started"])

    def test_wrong_executable_does_not_create_or_post_input(self):
        with patch("mac_startup_failure.NativeKeys") as keys:
            with self.assertRaises(RuntimeError):
                acknowledge_error(
                    SimpleNamespace(executable=lambda _: Path("/other")),
                    Mock(),
                    42,
                    Path("/owned"),
                    7,
                    Mock(),
                    {},
                )
            keys.assert_not_called()

    def test_final_provenance_and_cleanup_errors_override_success(self):
        for outcome in (
            "pass",
            "original changed",
            "copied changed",
            "signal fallback",
            "watch close failed",
        ):
            with (
                self.subTest(outcome=outcome),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                original, output = root / "original.app", root / "output"
                app_fixture(original)
                copied = [None]
                process = Mock(returncode=0)
                process.poll.return_value = None
                status = Mock(registration={"pid": 42}, observations=[{"exit_code": 1}])
                if outcome == "watch close failed":
                    status.close.side_effect = RuntimeError("watch close failed")
                windows = SimpleNamespace(
                    visible_registry=lambda: set(),
                    executable=lambda _, copied=copied: (
                        copied[0] / "Contents/MacOS/Emberwood Kotlin"
                    ),
                )

                def run(command, copied=copied, **_kwargs):
                    if command[0] == "ditto":
                        copied[0] = Path(command[2])
                        shutil.copytree(command[1], command[2])
                    elif command[0] == "screencapture":
                        Path(command[-1]).write_bytes(b"retained desktop fixture")
                    return SimpleNamespace(returncode=0)

                def acknowledge(
                    _windows, _reader, _pid, _executable, _id, _status, receipt
                ):
                    receipt.update(app_exit={"exit_code": 1, "normal_exit": True})

                def cleanup(
                    _pid,
                    _executable,
                    _windows,
                    _baseline,
                    destination,
                    outcome=outcome,
                    original=original,
                    copied=copied,
                ):
                    if outcome == "original changed":
                        (original / "Contents/app/emberwood-kotlin.jar").write_bytes(
                            b"changed"
                        )
                    if outcome == "copied changed":
                        (copied[0] / "Contents/runtime/libjvm").write_bytes(
                            b"changed runtime"
                        )
                    (destination / "cleanup.json").write_text(
                        json.dumps(
                            {
                                "signals": ["SIGTERM"]
                                if outcome == "signal fallback"
                                else [],
                                "new_windows_remaining": [],
                            }
                        )
                    )

                with (
                    patch("mac_startup_failure.platform.system", return_value="Darwin"),
                    patch(
                        "mac_startup_failure.platform.machine", return_value="x86_64"
                    ),
                    patch(
                        "sys.argv",
                        ["probe", "--app", str(original), "--output", str(output)],
                    ),
                    patch("mac_startup_failure.GameWindow", return_value=windows),
                    patch("mac_startup_failure.NativeStatus"),
                    patch("mac_startup_failure.app_pid", side_effect=[None, 42]),
                    patch("mac_startup_failure.subprocess.run", side_effect=run),
                    patch("mac_startup_failure.subprocess.Popen", return_value=process),
                    patch("mac_startup_failure.ExitStatus", return_value=status),
                    patch("mac_startup_failure.ErrorDialogReader"),
                    patch(
                        "mac_startup_failure.await_error",
                        return_value=({"id": 7}, dialog()),
                    ),
                    patch(
                        "mac_startup_failure.acknowledge_error", side_effect=acknowledge
                    ),
                    patch(
                        "mac_startup_failure.cleanup_app", side_effect=cleanup
                    ) as cleanup_mock,
                    patch("mac_startup_failure.stop_owned"),
                    patch("mac_startup_failure.time.sleep"),
                ):
                    if outcome == "pass":
                        main()
                    else:
                        with self.assertRaises(RuntimeError):
                            main()
                cleanup_mock.assert_called_once()
                receipt = json.loads((output / "result.json").read_text())
                self.assertEqual(
                    receipt["result"].startswith("PASS"), outcome == "pass"
                )
                self.assertEqual(receipt["visual_review"], "UNVERIFIED")
                if outcome in ("original changed", "copied changed"):
                    self.assertIn("provenance_error", receipt)


if __name__ == "__main__":
    unittest.main()
