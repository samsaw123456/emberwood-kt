"""Capture only this game's output ports and verify real M-key mute/recovery.

Run inside an isolated X11 display, with an existing PipeWire user audio service.
Pass the actual app command after --. Never captures microphone/system-mix audio.
"""

import argparse
import array
import json
import math
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
    wanted = {
        item["id"]
        for item in objects
        if item["type"] == "PipeWire:Interface:Node"
        and (
            (
                pid is not None
                and str(
                    item.get("info", {}).get("props", {}).get("application.process.id")
                )
                == str(pid)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="build/audio-audit")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    assert command, "Pass an app command after --"
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="emberwood-audio-") as data,
        (output / "app.log").open("w") as log,
    ):
        app = subprocess.Popen(
            command + ["--data-dir", data], stdout=log, stderr=subprocess.STDOUT
        )
        dpy = display.Display()
        held = set()
        try:
            root = dpy.screen().root
            win = None
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
            # Move through the actual Start button before sending physical keys.
            pos = win.translate_coords(root, 0, 0)
            xtest.fake_input(dpy, X.MotionNotify, x=576 - pos.x, y=278 - pos.y)
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

            evidence = {}
            for phase in ["on", "muted", "restored"]:
                if phase != "on":
                    tap("m")
                    time.sleep(0.25)
                capture_name = f"EmberwoodAudit-{app.pid}"
                path = output / f"{phase}.wav"
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
                    for _ in range(80):
                        target = ports(name=capture_name, direction="in")
                        if target:
                            break
                        time.sleep(0.025)
                    assert target, "Isolated recording port did not appear"
                    subprocess.run(
                        ["pw-link", str(source[0]), str(target[0])], check=True
                    )
                    until = time.monotonic() + 2.4
                    while time.monotonic() < until and recording.poll() is None:
                        tap("space")
                        time.sleep(0.24)
                    recording.communicate(timeout=6)
                    with wave.open(str(path)) as stream:
                        assert stream.getnframes() == 96000
                        samples = array.array("h", stream.readframes(96000))[12000:]
                    evidence[phase] = {
                        "rms": math.sqrt(sum(s * s for s in samples) / len(samples)),
                        "peak": max(map(abs, samples)),
                        "frames": 96000,
                    }
                finally:
                    if recording.poll() is None:
                        recording.terminate()
                        recording.wait(timeout=5)
            assert evidence["on"]["rms"] > 20 and evidence["restored"]["rms"] > 20, (
                evidence
            )
            assert evidence["muted"]["peak"] == 0, evidence
            (output / "results.json").write_text(json.dumps(evidence, indent=2) + "\n")
            print(
                "PASS: physical M key silences actual game output and unmute restores it.",
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
