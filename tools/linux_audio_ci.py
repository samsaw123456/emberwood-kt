"""Verify the game's own PCM on a private Linux virtual output, never a microphone."""

import argparse
import hashlib
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

from package_integrity import tree_digest

ROOT = Path(__file__).resolve().parents[1]
SERVER = "emberwood-audio"
SINK = "EmberwoodAuditSink"
# No hardware factories, portals, system-session activation or configuration hooks.
PIPEWIRE_CONFIG = f"""
context.properties = {{ core.daemon = true core.name = {SERVER} }}
context.spa-libs = {{
    audio.convert.* = audioconvert/libspa-audioconvert
    support.* = support/libspa-support
}}
context.modules = [
    {{ name = libpipewire-module-protocol-native }}
    {{ name = libpipewire-module-metadata }}
    {{ name = libpipewire-module-spa-node-factory }}
    {{ name = libpipewire-module-client-node }}
    {{ name = libpipewire-module-client-device }}
    {{ name = libpipewire-module-access }}
    {{ name = libpipewire-module-adapter }}
    {{ name = libpipewire-module-link-factory }}
    {{ name = libpipewire-module-session-manager }}
]
context.objects = [
    {{ factory = spa-node-factory args = {{
        factory.name = support.node.driver node.name = Dummy-Driver
        node.group = pipewire.dummy priority.driver = 20000
    }} }}
    {{ factory = adapter args = {{
        factory.name = support.null-audio-sink node.name = {SINK}
        node.description = "Emberwood isolated virtual output"
        media.class = Audio/Sink audio.position = [ FL FR ]
    }} }}
]
"""
ALSA_CONFIG = f"""
pcm.!default {{
    type pipewire server {SERVER} playback_node {SINK}
    hint {{ show on description "Emberwood isolated playback" ioid Output }}
}}
ctl.!default {{ type pipewire server {SERVER} }}
"""


def policy_command(version):
    match = re.search(r"libwireplumber (\d+)\.(\d+)", version)
    if not match:
        raise RuntimeError("Cannot identify the installed WirePlumber policy API")
    series = tuple(map(int, match.groups()))
    # These upstream profiles contain policy only, without hardware monitors.
    if series >= (0, 5):
        return ["wireplumber", "--profile", "policy"]
    if series == (0, 4):
        return ["wireplumber", "--config-file", "policy.conf"]
    raise RuntimeError(f"Unsupported WirePlumber policy-only profile: {series}")


def stop_owned(process):
    """Stop only a child we created and its own process group, even on timeout."""
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def graph(environment):
    return json.loads(
        subprocess.check_output(["pw-dump"], env=environment, text=True, timeout=5)
    )


def validate_virtual_graph(objects):
    if any(item["type"] == "PipeWire:Interface:Device" for item in objects):
        raise RuntimeError(
            "An unexpected hardware device appeared in the private session"
        )
    nodes = [
        item.get("info", {}).get("props", {})
        for item in objects
        if item["type"] == "PipeWire:Interface:Node"
    ]
    if any(props.get("media.class", "").startswith("Audio/Source") for props in nodes):
        raise RuntimeError("A capture-source node appeared in the output-only session")
    sinks = [props for props in nodes if props.get("media.class") == "Audio/Sink"]
    if len(sinks) != 1 or sinks[0].get("node.name") != SINK:
        raise RuntimeError("The private session must contain exactly its virtual sink")
    if any(props.get("node.name") not in {SINK, "Dummy-Driver"} for props in nodes):
        raise RuntimeError(
            "Unexpected playback/capture nodes remain in the private session"
        )
    return [
        {"name": props.get("node.name"), "media_class": props.get("media.class")}
        for props in nodes
    ]


@contextmanager
def private_audio_session(output):
    """All sockets, ALSA policy and state are private; no user's service is changed."""
    output.mkdir(parents=True, exist_ok=True)
    cleanup = {"result": "FAIL", "owned_processes": []}
    with (
        tempfile.TemporaryDirectory(prefix="emberwood-audio-session-") as directory,
        ExitStack() as stack,
    ):
        private = Path(directory)
        private.chmod(0o700)
        config = private / "pipewire.conf"
        config.write_text(PIPEWIRE_CONFIG)
        alsa = private / "alsa.conf"
        alsa.write_text(ALSA_CONFIG)
        bus_config = private / "dbus.conf"
        bus_config.write_text(
            "<busconfig><type>session</type><auth>EXTERNAL</auth>"
            f"<listen>unix:path={private}/bus</listen>"
            '<policy context="default"><allow send_destination="*"/>'
            '<allow receive_sender="*"/><allow own="*"/></policy></busconfig>'
        )
        environment = {
            **os.environ,
            "XDG_RUNTIME_DIR": str(private),
            "PIPEWIRE_RUNTIME_DIR": str(private),
            "PIPEWIRE_REMOTE": SERVER,
            "ALSA_CONFIG_PATH": str(alsa),
            "XDG_CONFIG_HOME": str(private / "config"),
            "XDG_STATE_HOME": str(private / "state"),
            "DBUS_SYSTEM_BUS_ADDRESS": f"unix:path={private}/no-system-bus",
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={private}/bus",
        }
        for key in [
            "PIPEWIRE_CONFIG_DIR",
            "PIPEWIRE_CONFIG_NAME",
            "PIPEWIRE_CONFIG_PREFIX",
            "WIREPLUMBER_CONFIG_DIR",
            "PIPEWIRE_NODE",
            "PIPEWIRE_ALSA",
        ]:
            environment.pop(key, None)
        versions = {
            name: subprocess.check_output(
                [name, "--version"], env=environment, text=True, timeout=5
            )
            for name in ["pipewire", "wireplumber", "pw-record"]
        }
        (output / "versions.json").write_text(json.dumps(versions, indent=2) + "\n")
        processes = []

        def start(name, command):
            log = stack.enter_context((output / f"{name}.log").open("w"))
            process = subprocess.Popen(
                command,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            processes.append(process)
            return process

        try:
            server = start("pipewire", ["pipewire", "--config", str(config)])
            deadline = time.monotonic() + 10
            while not (private / SERVER).exists():
                if server.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(
                        "The private PipeWire server did not become ready"
                    )
                time.sleep(0.05)
            # No service directories: this bus cannot auto-activate desktop helpers.
            bus = start(
                "dbus", ["dbus-daemon", "--nofork", "--config-file", str(bus_config)]
            )
            deadline = time.monotonic() + 5
            while not (private / "bus").exists():
                if bus.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("The private session bus did not become ready")
                time.sleep(0.05)
            manager = start("policy", policy_command(versions["wireplumber"]))
            deadline = time.monotonic() + 10
            while True:
                objects = graph(environment)
                sink_nodes = [
                    item
                    for item in objects
                    if item.get("info", {}).get("props", {}).get("node.name") == SINK
                ]
                if sink_nodes and any(
                    item["type"] == "PipeWire:Interface:Port" for item in objects
                ):
                    break
                if manager.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(
                        "The isolated output policy did not configure playback ports"
                    )
                time.sleep(0.1)
            record = {
                "runtime_directory": str(private),
                "private_server": SERVER,
                "virtual_nodes": validate_virtual_graph(objects),
                "microphone": False,
                "hardware_devices": False,
                "global_session_modified": False,
                "scope": "Real application PCM through ALSA/PipeWire into an isolated virtual output; no claim of speaker hardware playback.",
            }
            (output / "session.json").write_text(json.dumps(record, indent=2) + "\n")
            yield environment
            validate_virtual_graph(graph(environment))
        finally:
            for process in reversed(processes):
                stop_owned(process)
                cleanup["owned_processes"].append(
                    {"pid": process.pid, "exit_code": process.returncode}
                )
            cleanup["result"] = "PASS"
            (output / "cleanup.json").write_text(json.dumps(cleanup, indent=2) + "\n")


def run_display_check(command, log_path, environment, timeout):
    full_command = [
        "xvfb-run",
        "-a",
        "-s",
        "-screen 0 1440x900x24",
        str(ROOT / "tools/run_x11_audit.sh"),
        *map(str, command),
    ]
    log_path.with_suffix(".argv.json").write_text(
        json.dumps(full_command, indent=2) + "\n"
    )
    with log_path.open("w") as log:
        process = subprocess.Popen(
            full_command,
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            if process.wait(timeout=timeout) != 0:
                raise RuntimeError(f"Native desktop check failed; inspect {log_path}")
        finally:
            stop_owned(process)


def run_audits(java_home, output):
    output.mkdir(parents=True, exist_ok=True)
    completion = output / "completion.json"
    completion.unlink(missing_ok=True)
    report = {"result": "FAIL", "routes": {}}
    try:
        tests = ROOT / "build/classes/kotlin/test"
        jar = ROOT / "build/libs/emberwood-kotlin.jar"
        packages = list(
            (ROOT / "dist").glob("emberwood-kotlin-*/Emberwood Kotlin/runtime/bin/java")
        )
        if len(packages) != 1 or not tests.is_dir() or not jar.is_file():
            raise RuntimeError(
                "Build the game, test classes and one Linux package first"
            )
        smoke = ROOT / "tools/linux_game_smoke.py"
        if not smoke.is_file():
            raise RuntimeError(
                "The real-main Linux launch/close verification helper is missing"
            )
        bundled_java = packages[0]
        bundled_jar = bundled_java.parents[2] / "lib/emberwood-kotlin.jar"
        digest = hashlib.sha256(jar.read_bytes()).hexdigest()
        if hashlib.sha256(bundled_jar.read_bytes()).hexdigest() != digest:
            raise RuntimeError("Source and bundled game bytes differ")
        report.update(
            {"game_jar_sha256": digest, "test_classes_sha256": tree_digest(tests)}
        )
        with private_audio_session(output / "session") as environment:
            for route, java, game in [
                ("source", java_home / "bin/java", jar),
                ("packaged", bundled_java, bundled_jar),
            ]:
                evidence = output / route
                evidence.mkdir(parents=True, exist_ok=True)
                (evidence / "results.json").unlink(missing_ok=True)
                command = [
                    sys.executable,
                    str(ROOT / "tools/audio_audit.py"),
                    "--state-fixture",
                    "--output",
                    str(evidence),
                    "--",
                    str(java),
                    "--enable-native-access=ALL-UNNAMED",
                    "-Xms32m",
                    "-Xmx128m",
                    "-XX:ActiveProcessorCount=2",
                    "-cp",
                    os.pathsep.join([str(game), str(tests)]),
                    "emberwood.AudioStateFixture",
                ]
                run_display_check(command, evidence / "driver.log", environment, 420)
                rows = json.loads((evidence / "results.json").read_text())
                if len(rows) != 14 or any(
                    row.get("result") != "PASS" for row in rows.values()
                ):
                    raise RuntimeError(
                        f"{route} audio inventory is incomplete or failed"
                    )
                report["routes"][route] = {
                    "result": "PASS",
                    "java": str(java),
                    "jar": str(game),
                    "cases": len(rows),
                    "analyzed_windows": sum(
                        1
                        for path in evidence.glob("*.wav")
                        if not path.name.endswith(".capture.wav")
                    ),
                    "complete_original_captures": len(
                        list(evidence.glob("*.capture.wav"))
                    ),
                }
                smoke_output = evidence / "game-smoke"
                smoke_output.mkdir(exist_ok=True)
                run_display_check(
                    [
                        sys.executable,
                        smoke,
                        "--java",
                        java,
                        "--jar",
                        game,
                        "--output",
                        smoke_output,
                    ],
                    smoke_output / "driver.log",
                    environment,
                    120,
                )
                report["routes"][route]["physical_main_launch_close"] = "PASS"
        report["result"] = "PASS"
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        report["error"] = str(error)
        raise
    finally:
        completion.write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=Path, default=os.environ.get("JAVA_HOME"))
    parser.add_argument("--output", type=Path, default=ROOT / "build/audio-linux")
    args = parser.parse_args()
    if platform.system() != "Linux" or args.java_home is None:
        parser.error(
            "Run on Linux with --java-home or JAVA_HOME set to the private JDK"
        )

    def interrupted(signum, _frame):
        raise RuntimeError(f"Interrupted by signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    run_audits(args.java_home.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
