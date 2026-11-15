"""Capture only this game's output ports and verify real M-key mute/recovery.

Run inside an isolated X11 display, with an existing PipeWire user audio service.
Pass the actual app command after --. Never captures microphone/system-mix audio.
"""

import argparse
import array
import json
import math
import select
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from Xlib import XK, X, display, error
from Xlib.ext import xtest


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


def record(source, output, label, action):
    """Link only the identified game's playback port, then capture the action."""
    capture_name = f"EmberwoodAudit-{source}-{time.monotonic_ns()}"
    path = output / f"{label}.wav"
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
            "--sample-count",
            "96000",
            str(path),
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
        time.sleep(0.1)
        action()
        _, stderr = recording.communicate(timeout=6)
        # PipeWire 1.6.2 exits 1 on its sample limit without a playback drain.
        # Accept that completion only with a complete PCM file and no error text.
        diagnostic = stderr.decode(errors="replace").strip()
        assert recording.returncode in (0, 1) and diagnostic in ("", str(path)), (
            diagnostic
        )
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
            "energy": energy,
            "active_frames": len(active),
            "first_active_frame": active[0] if active else None,
            "last_active_frame": active[-1] if active else None,
            "frames": len(samples),
            "recorder_exit_code": recording.returncode,
        }
    finally:
        if recording.poll() is None:
            recording.terminate()
            recording.wait(timeout=5)


def read_fixture(app, log):
    ready, _, _ = select.select([app.stdout], [], [], 10)
    assert ready, "Audio state fixture did not acknowledge within ten seconds"
    line = app.stdout.readline().strip()
    log.write(line + "\n")
    log.flush()
    assert line, "Audio state fixture exited unexpectedly"
    return line


def audit_states(app, log, key, source, output):
    assert read_fixture(app, log) == "READY"

    def command(text):
        app.stdin.write(text + "\n")
        app.stdin.flush()
        fields = read_fixture(app, log).split("\t")
        assert len(fields) == 6 and fields[0] == "OK", fields
        assert fields[2] == fields[3], "Audio and persisted-setting mute state disagree"
        assert fields[5] == "available", fields[5]
        return {
            "state": fields[1],
            "muted": fields[2] == "true",
            "focused": fields[4] == "true",
        }

    def mute_to(wanted):
        started = time.monotonic()
        key("m", True)
        try:
            while time.monotonic() - started < 3:
                if command("status")["muted"] == wanted:
                    return (time.monotonic() - started) * 1000
                time.sleep(0.005)
            raise AssertionError("Physical M did not reach the requested audio state")
        finally:
            key("m", False)

    # Warm real key delivery and restore sound before measuring any state.
    mute_to(True)
    mute_to(False)
    time.sleep(0.4)
    evidence = {}
    failures = []
    states = ["TITLE", "PLAYING", "PAUSED", "RESPAWNING", "CHAPTER_COMPLETE", "WON"]
    for state in states:
        command("state " + state)
        time.sleep(0.2)
        status = command("status")
        assert status["state"] == state and status["focused"], status
        assert not status["muted"], status
        row = {
            "method": "fixture state and original gem cue; physical X11 M only",
            "delivery_ms": {},
        }
        evidence[state] = row
        row["full"] = record(source, output, state + "-full", lambda: command("cue"))

        def cut(result=row):
            command("cue")
            time.sleep(0.05)
            result["delivery_ms"]["mute"] = mute_to(True)

        row["cut"] = record(source, output, state + "-cut", cut)
        row["muted"] = record(source, output, state + "-muted", lambda: command("cue"))

        def restore(result=row):
            result["delivery_ms"]["restore"] = mute_to(False)

        # Production unmute emits its own gem cue; no fixture cue is used here.
        row["unmute"] = record(source, output, state + "-unmute", restore)
        row["restored"] = record(
            source, output, state + "-restored", lambda: command("cue")
        )
        final = command("status")
        checks = {
            "full cue audible": row["full"]["rms"] > 20,
            "mute interrupts active cue": row["cut"]["active_frames"]
            < row["full"]["active_frames"] * 0.9,
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
            f"{state}: {name}" for name, passed in checks.items() if not passed
        )
        (output / "results.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(state, row["result"], checks, flush=True)
    assert not failures, failures
    print(
        "PASS: physical M interrupts, silences and restores actual game output in all six states."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="build/audio-audit")
    parser.add_argument(
        "--state-fixture",
        action="store_true",
        help="Use AudioStateFixture to cover all six game states",
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
            win = None
            source = []
            for _ in range(120):
                for w in root.query_tree().children:
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

            if args.state_fixture:
                audit_states(app, log, key, source[0], output)
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
