"""Capture only this game's output ports and verify real M-key mute/recovery.

Run inside an isolated X11 display, with an existing PipeWire user audio service.
State audits require a window manager; tools/run_x11_audit.sh starts an isolated one.
Pass the actual app command after --. Never captures microphone/system-mix audio.
"""

import argparse
import array
import json
import math
import select
import signal
import subprocess
import tempfile
import time
import wave
from functools import lru_cache
from pathlib import Path


def nodes():
    return json.loads(subprocess.check_output(["pw-dump"], text=True))


def ports(pid=None, name=None, direction="out"):
    objects = nodes()
    clients = {
        item["id"]
        for item in objects
        if item["type"] == "PipeWire:Interface:Client"
        and pid is not None
        and str(item.get("info", {}).get("props", {}).get("application.process.id"))
        == str(pid)
    }
    wanted = {
        item["id"]
        for item in objects
        if item["type"] == "PipeWire:Interface:Node"
        and (
            (
                pid is not None
                and (
                    str(
                        item.get("info", {})
                        .get("props", {})
                        .get("application.process.id")
                    )
                    == str(pid)
                    or item.get("info", {}).get("props", {}).get("client.id") in clients
                )
            )
            or (
                name is not None
                and item.get("info", {}).get("props", {}).get("node.name") == name
            )
        )
    }
    return [
        item["id"]
        for item in objects
        if item["type"] == "PipeWire:Interface:Port"
        and item.get("info", {}).get("props", {}).get("node.id") in wanted
        and item.get("info", {}).get("props", {}).get("port.direction") == direction
    ]


@lru_cache(maxsize=1)
def recorder_has_sample_limit():
    return "--sample-count" in subprocess.check_output(
        ["pw-record", "--help"], text=True, timeout=5
    )


def extract_pcm_window(original, destination):
    """Keep the complete capture and select its first exact two-second window."""
    destination.unlink(missing_ok=True)
    with wave.open(str(original), "rb") as source:
        assert (
            source.getframerate(),
            source.getnchannels(),
            source.getsampwidth(),
        ) == (48000, 1, 2)
        frames = source.getnframes()
        assert frames >= 96000, (
            f"Only {frames} frames captured; the two-second window is incomplete"
        )
        pcm = source.readframes(96000)
        assert len(pcm) == 192000, "Captured PCM is truncated"
    with wave.open(str(destination), "wb") as target:
        target.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        target.writeframes(pcm)
    return frames


def record(source, output, label, action):
    """Link only the identified game's playback port, then capture the action."""
    capture_name = f"EmberwoodAudit-{source}-{time.monotonic_ns()}"
    path = output / f"{label}.wav"
    path.unlink(missing_ok=True)
    limited = recorder_has_sample_limit()
    captured = path if limited else output / f"{label}.capture.wav"
    recording = subprocess.Popen(
        [
            "pw-record",
            "--target",
            "0",
            "--properties",
            f'{{ node.name = "{capture_name}" node.autoconnect = false }}',
            "--rate",
            "48000",
            "--channels",
            "1",
            "--format",
            "s16",
            *(["--sample-count", "96000"] if limited else []),
            str(captured),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        target = []
        for _ in range(80):
            target = ports(name=capture_name, direction="in")
            if target:
                break
            time.sleep(0.025)
        assert target, "Isolated recording port did not appear"
        subprocess.run(["pw-link", str(source), str(target[0])], check=True)
        linked = time.monotonic()
        time.sleep(0.1)
        action()
        if not limited:
            # Ubuntu 24.04's PipeWire 1.0 has no --sample-count. Preserve its full
            # WAV, then select the same first 96000 frames without editing samples.
            time.sleep(max(0, linked + 2.2 - time.monotonic()))
            recording.send_signal(signal.SIGINT)
        _, stderr = recording.communicate(timeout=6)
        # PipeWire 1.6.2 exits 1 on its sample limit without a playback drain.
        # Accept that completion only with a complete PCM file and no error text.
        diagnostic = stderr.decode(errors="replace").strip()
        assert recording.returncode in (0, 1) and diagnostic in ("", str(captured)), (
            diagnostic
        )
        capture_frames = 96000 if limited else extract_pcm_window(captured, path)
        result = read_pcm(path, recording.returncode)
        result["capture"] = {
            "method": "sample-count" if limited else "complete WAV, first 96000 frames",
            "original_file": captured.name,
            "original_frames": capture_frames,
        }
        return result
    finally:
        if recording.poll() is None:
            recording.terminate()
            recording.wait(timeout=5)


def read_pcm(path, recorder_exit_code=0):
    """Measure the same complete mono PCM window from either native capture path."""
    with wave.open(str(path)) as stream:
        assert (
            stream.getframerate(),
            stream.getnchannels(),
            stream.getsampwidth(),
        ) == (48000, 1, 2)
        assert stream.getnframes() == 96000
        samples = array.array("h", stream.readframes(96000))
    energy = sum(s * s for s in samples)
    active = [i for i, sample in enumerate(samples) if abs(sample) > 2]
    return {
        "rms": math.sqrt(energy / len(samples)),
        "peak": max(map(abs, samples)),
        "tail_peak": max(map(abs, samples[-24000:])),
        "energy": energy,
        "active_frames": len(active),
        "first_active_frame": active[0] if active else None,
        "last_active_frame": active[-1] if active else None,
        "frames": len(samples),
        "recorder_exit_code": recorder_exit_code,
    }


def read_fixture(app, log):
    ready, _, _ = select.select([app.stdout], [], [], 10)
    assert ready, "Audio state fixture did not acknowledge within ten seconds"
    line = app.stdout.readline().strip()
    log.write(line + "\n")
    log.flush()
    assert line, "Audio state fixture exited unexpectedly"
    return line


def audit_states(
    app,
    log,
    key,
    source,
    output,
    record_audio=record,
    method="fixture state and original gem/win cues; physical X11 keys/mouse",
    click=None,
):
    assert read_fixture(app, log) == "READY"

    assert click is not None, (
        "A real OS mouse callback is required for complete Sound control coverage"
    )

    def request(text):
        app.stdin.write(text + "\n")
        app.stdin.flush()
        return read_fixture(app, log).split("\t")

    def command(text, require_output=True):
        fields = request(text)
        assert len(fields) == 6 and fields[0] == "OK", fields
        assert fields[2] == fields[3], "Audio and persisted-setting mute state disagree"
        if require_output:
            assert fields[5] == "available", fields[5]
        return {
            "state": fields[1],
            "muted": fields[2] == "true",
            "focused": fields[4] == "true",
            "availability": fields[5],
        }

    def sound_target():
        fields = request("sound-target")
        assert len(fields) == 4 and fields[0] == "SOUND", fields
        return fields[1], (int(fields[2]), int(fields[3]))

    def focus_sound():
        for _ in range(30):
            previous, point = sound_target()
            if previous == "sound":
                return point
            key("Tab", True)
            time.sleep(0.05)
            key("Tab", False)
            deadline = time.monotonic() + 3
            while sound_target()[0] == previous and time.monotonic() < deadline:
                time.sleep(0.005)
            assert sound_target()[0] != previous, (
                "Physical Tab did not change menu focus"
            )
        raise AssertionError("Physical Tab navigation did not reach Sound")

    def mute_to(wanted, binding="m"):
        started = time.monotonic()
        if binding == "Mouse":
            # Recording windows take seconds; resolve the live window position at activation.
            point = sound_target()[1]
            click(*point)
        else:
            key(binding, True)
        try:
            while time.monotonic() - started < 3:
                if command("status")["muted"] == wanted:
                    return (time.monotonic() - started) * 1000
                time.sleep(0.005)
            raise AssertionError(
                f"Physical {binding} did not reach the requested audio state"
            )
        finally:
            if binding != "Mouse":
                key(binding, False)

    deadline = time.monotonic() + 10
    while True:
        initial = command("status", require_output=False)
        if initial["availability"] == "available":
            break
        assert initial["availability"] == "initializing", initial
        assert time.monotonic() < deadline, (
            "Audio output did not finish initialization within ten seconds"
        )
        time.sleep(0.025)

    # Warm real key delivery and restore sound before measuring any state.
    mute_to(True)
    mute_to(False)
    time.sleep(0.4)
    evidence = {}
    failures = []
    states = ["TITLE", "PLAYING", "PAUSED", "RESPAWNING", "CHAPTER_COMPLETE", "WON"]
    cases = [(state, "m") for state in states] + [
        (state, binding)
        for state in ("TITLE", "PAUSED")
        for binding in ("Mouse", "Return", "space", "KP_Enter")
    ]
    for state, binding in cases:
        label = state if binding == "m" else state + "-" + binding
        command("state " + state)
        time.sleep(0.2)
        status = command("status")
        assert status["state"] == state and status["focused"], status
        assert not status["muted"], status
        if binding not in ("m", "Mouse"):
            focus_sound()
        row = {
            "method": method,
            "binding": binding,
            "state": state,
            "file_prefix": label,
            "delivery_ms": {},
        }
        evidence[label] = row
        row["full"] = record_audio(
            source, output, label + "-full", lambda: command("cue")
        )
        row["long"] = record_audio(
            source, output, label + "-long", lambda: command("cue win")
        )

        def cut(result=row, activation=binding):
            command("cue win")
            time.sleep(0.35)
            result["delivery_ms"]["mute"] = mute_to(True, activation)

        row["cut"] = record_audio(source, output, label + "-cut", cut)
        row["muted"] = record_audio(
            source, output, label + "-muted", lambda: command("cue")
        )

        def restore(result=row, activation=binding):
            result["delivery_ms"]["restore"] = mute_to(False, activation)

        # Production unmute emits its own gem cue; no fixture cue is used here.
        row["unmute"] = record_audio(source, output, label + "-unmute", restore)
        row["restored"] = record_audio(
            source, output, label + "-restored", lambda: command("cue")
        )
        final = command("status")
        checks = {
            "full cue audible": row["full"]["rms"] > 20,
            "long reference cue audible": row["long"]["rms"] > 20,
            "mute stops audible cue": row["cut"]["rms"] > 20
            and row["cut"]["active_frames"] < row["long"]["active_frames"] * 0.8
            and row["cut"]["tail_peak"] == 0,
            "muted cue is silent": row["muted"]["peak"] == 0,
            "physical unmute feedback audible": row["unmute"]["rms"] > 20,
            "restored cue audible": row["restored"]["rms"] > 20,
            "state retained and input focused": final["state"] == state
            and final["focused"]
            and not final["muted"],
        }
        row["checks"] = checks
        row["result"] = "PASS" if all(checks.values()) else "FAIL"
        failures.extend(
            f"{label}: {name}" for name, passed in checks.items() if not passed
        )
        (output / "results.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(label, row["result"], checks, flush=True)
    assert not failures, failures
    print(
        "PASS: all 14 physical M and Sound-menu cases stop audible cues, silence output and restore it."
    )


def main():
    from Xlib import XK, X, display, error
    from Xlib.ext import xtest

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="build/audio-audit")
    parser.add_argument(
        "--state-fixture",
        action="store_true",
        help="Cover M in six states and all eight Sound-menu activation bindings",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    assert command, "Pass an app or AudioStateFixture command after --"
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="emberwood-audio-") as data,
        (output / "app.log").open("w") as log,
    ):
        app = subprocess.Popen(
            command + ["--data-dir", data],
            stdin=subprocess.PIPE if args.state_fixture else subprocess.DEVNULL,
            stdout=subprocess.PIPE if args.state_fixture else log,
            stderr=log,
            text=True,
            bufsize=1,
        )
        dpy = display.Display()
        held = set()
        try:
            root = dpy.screen().root
            if args.state_fixture:
                assert (
                    root.get_full_property(
                        dpy.intern_atom("_NET_SUPPORTING_WM_CHECK"), X.AnyPropertyType
                    )
                    is not None
                ), "State audit requires a window manager; use tools/run_x11_audit.sh"
            win = None
            source = []
            for _ in range(120):
                clients = root.get_full_property(
                    dpy.intern_atom("_NET_CLIENT_LIST"), X.AnyPropertyType
                )
                windows = (
                    [
                        dpy.create_resource_object("window", int(w))
                        for w in clients.value
                    ]
                    if clients is not None
                    else root.query_tree().children
                )
                for w in windows:
                    try:
                        if w.get_wm_name() == "Emberwood Kotlin":
                            win = w
                    except error.BadWindow:
                        pass
                source = ports(pid=app.pid)
                if win and source:
                    break
                if app.poll() is not None:
                    raise RuntimeError("App exited before audio audit")
                time.sleep(0.1)
            assert win is not None and source, (
                "Game output port unavailable; audio remains unverified"
            )
            win.set_input_focus(X.RevertToParent, X.CurrentTime)
            # A real click also gives the Swing child keyboard focus under bare Xvfb.
            pos = win.translate_coords(root, 0, 0)
            x, y = (20, 100) if args.state_fixture else (576, 278)
            xtest.fake_input(dpy, X.MotionNotify, x=x - pos.x, y=y - pos.y)
            xtest.fake_input(dpy, X.ButtonPress, 1)
            xtest.fake_input(dpy, X.ButtonRelease, 1)
            dpy.sync()
            time.sleep(0.25)

            def key(name, down):
                xtest.fake_input(
                    dpy,
                    X.KeyPress if down else X.KeyRelease,
                    dpy.keysym_to_keycode(XK.string_to_keysym(name)),
                )
                if down:
                    held.add(name)
                else:
                    held.discard(name)
                dpy.sync()

            def tap(name):
                key(name, True)
                time.sleep(0.05)
                key(name, False)

            def click_sound(x, y):
                xtest.fake_input(dpy, X.MotionNotify, x=x, y=y)
                xtest.fake_input(dpy, X.ButtonPress, 1)
                xtest.fake_input(dpy, X.ButtonRelease, 1)
                dpy.sync()

            if args.state_fixture:
                audit_states(app, log, key, source[0], output, click=click_sound)
            else:
                evidence = {}
                for phase in ["on", "muted", "restored"]:
                    if phase != "on":
                        tap("m")
                        time.sleep(0.25)

                    def jumps():
                        until = time.monotonic() + 1.5
                        while time.monotonic() < until:
                            tap("space")
                            time.sleep(0.24)

                    evidence[phase] = record(source[0], output, phase, jumps)
                (output / "results.json").write_text(
                    json.dumps(evidence, indent=2) + "\n"
                )
                assert (
                    evidence["on"]["rms"] > 20 and evidence["restored"]["rms"] > 20
                ), evidence
                assert evidence["muted"]["peak"] == 0, evidence
                print(
                    "PASS: physical M silences gameplay output and unmute restores it.",
                    evidence,
                )
        finally:
            for name in held:
                xtest.fake_input(
                    dpy, X.KeyRelease, dpy.keysym_to_keycode(XK.string_to_keysym(name))
                )
            dpy.sync()
            dpy.close()
            if app.poll() is None:
                app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
