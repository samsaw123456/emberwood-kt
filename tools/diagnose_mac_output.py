"""Test production Mac output without mixer overrides or microphone access."""

import argparse
import ctypes
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PropertyAddress(ctypes.Structure):
    _fields_ = [
        ("selector", ctypes.c_uint32),
        ("scope", ctypes.c_uint32),
        ("element", ctypes.c_uint32),
    ]


def fourcc(value):
    return int.from_bytes(value.encode("ascii"), "big")


def default_output():
    audio = ctypes.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
    foundation = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    audio.AudioObjectGetPropertyData.argtypes = [
        ctypes.c_uint32,
        ctypes.POINTER(PropertyAddress),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    ]
    audio.AudioObjectGetPropertyData.restype = ctypes.c_int32
    foundation.CFStringGetLength.argtypes = [ctypes.c_void_p]
    foundation.CFStringGetLength.restype = ctypes.c_long
    foundation.CFStringGetMaximumSizeForEncoding.argtypes = [
        ctypes.c_long,
        ctypes.c_uint32,
    ]
    foundation.CFStringGetMaximumSizeForEncoding.restype = ctypes.c_long
    foundation.CFStringGetCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_long,
        ctypes.c_uint32,
    ]
    foundation.CFStringGetCString.restype = ctypes.c_bool
    foundation.CFRelease.argtypes = [ctypes.c_void_p]
    foundation.CFRelease.restype = None

    def read(object_id, selector, value):
        address = PropertyAddress(fourcc(selector), fourcc("glob"), 0)
        size = ctypes.c_uint32(ctypes.sizeof(value))
        status = audio.AudioObjectGetPropertyData(
            object_id,
            ctypes.byref(address),
            0,
            None,
            ctypes.byref(size),
            ctypes.byref(value),
        )
        if status or size.value != ctypes.sizeof(value):
            raise RuntimeError(
                f"Output property {selector} unavailable: status={status}, size={size.value}"
            )
        return value

    # kAudioObjectSystemObject=1; dOut is ONLY the default output device.
    device = read(1, "dOut", ctypes.c_uint32()).value
    if not device:
        raise RuntimeError(
            "No native default output device; no alternative was selected"
        )
    # kAudioObjectPropertyName; this does not enumerate/query input devices.
    name_ref = read(device, "lnam", ctypes.c_void_p())
    if not name_ref.value:
        raise RuntimeError("Default output device has no name")
    try:
        utf8 = 0x08000100
        size = (
            foundation.CFStringGetMaximumSizeForEncoding(
                foundation.CFStringGetLength(name_ref), utf8
            )
            + 1
        )
        buffer = ctypes.create_string_buffer(size)
        if not foundation.CFStringGetCString(name_ref, buffer, size, utf8):
            raise RuntimeError("Default output name could not be decoded")
        name = buffer.value.decode("utf-8")
    finally:
        foundation.CFRelease(name_ref)
    if not name or "\n" in name or "\r" in name or len(name.encode("utf-8")) >= 256:
        raise RuntimeError(
            "Default output name cannot be represented exactly in the Java mixer/configuration"
        )
    return {
        "device_id": device,
        "name": name,
        "queried_properties": ["default output (dOut)", "that output's name (lnam)"],
        "input_query": False,
        "permission_changes": False,
    }


def verify_output_backend(java, jar, tests, output, label, sdk_layout):
    command = [
        java,
        "--enable-native-access=ALL-UNNAMED",
        "-cp",
        os.pathsep.join([str(jar), str(tests)]),
        "emberwood.MacAudioOutputProbe",
    ]
    with (output / f"{label}-layout.log").open("w") as log:
        layout = subprocess.run(
            [*command, "--layouts"],
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            check=True,
            timeout=30,
        )
    actual = json.loads(layout.stdout)
    comparison = {
        "sdk": sdk_layout,
        "jvm": actual,
        "result": "PASS" if actual == sdk_layout else "FAIL",
    }
    (output / f"{label}-abi.json").write_text(json.dumps(comparison, indent=2) + "\n")
    if actual != sdk_layout:
        raise RuntimeError(
            f"{label} FFM layout differs from the installed SDK; no playback or input attempted"
        )
    with (output / f"{label}-lifecycle.log").open("w") as log:
        subprocess.run(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=30,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build/mac-output-diagnostic"
    )
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run this diagnostic on macOS")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    layout_helper = output / "mac-audio-layout"
    with (output / "sdk-layout-compile.log").open("w") as log:
        subprocess.run(
            [
                "xcrun",
                "clang",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                ROOT / "tools/mac_audio_layout.c",
                "-framework",
                "AudioToolbox",
                "-o",
                layout_helper,
            ],
            check=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=60,
        )
    sdk_layout = json.loads(
        subprocess.check_output([layout_helper], text=True, timeout=10)
    )
    (output / "sdk-layout.json").write_text(json.dumps(sdk_layout, indent=2) + "\n")
    selected = default_output()
    (output / "output-device.json").write_text(json.dumps(selected, indent=2) + "\n")
    version = (ROOT / "VERSION").read_text().strip()
    arch = {"arm64": "aarch64"}.get(platform.machine(), platform.machine())
    original = (
        ROOT
        / "dist"
        / f"emberwood-kotlin-{version}-macos-{arch}"
        / "Emberwood Kotlin.app"
    )
    if not original.is_dir():
        parser.error("Build the native package first")
    results = {}
    with tempfile.TemporaryDirectory(
        prefix="emberwood output diagnostic "
    ) as temporary:
        app = Path(temporary) / "Emberwood Kotlin.app"
        subprocess.run(["ditto", original, app], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", app], check=True)
        jar = app / "Contents/app/emberwood-kotlin.jar"
        runtime = app / "Contents/runtime/Contents/Home/bin/java"
        selected["game_jar_sha256"] = hashlib.sha256(jar.read_bytes()).hexdigest()
        selected["audio_selection"] = "Unmodified production backend; no mixer override"
        (output / "output-device.json").write_text(
            json.dumps(selected, indent=2) + "\n"
        )
        tests = ROOT / "build/classes/kotlin/test"
        for label, executable, game_jar in (
            (
                "source",
                Path(os.environ["JAVA_HOME"]) / "bin/java",
                ROOT / "build/libs/emberwood-kotlin.jar",
            ),
            ("packaged", runtime, jar),
        ):
            key = f"{label}-abi-lifecycle"
            results[key] = "INCOMPLETE"
            try:
                verify_output_backend(
                    executable, game_jar, tests, output, label, sdk_layout
                )
                results[key] = "PASS"
            except Exception:
                results[key] = "FAIL"
                raise
            finally:
                (output / "results.json").write_text(
                    json.dumps(results, indent=2) + "\n"
                )
        commands = {
            "bundle-foreground": [
                sys.executable,
                ROOT / "tools/mac_bundle_smoke.py",
                app,
                "--startup-only",
                "--output",
                output / "bundle-launch",
            ],
            "source-pcm": [
                sys.executable,
                ROOT / "tools/mac_audio_audit.py",
                "--output",
                output / "audio-source",
            ],
            "packaged-pcm": [
                sys.executable,
                ROOT / "tools/mac_audio_audit.py",
                "--output",
                output / "audio-packaged",
                "--java",
                runtime,
                "--jar",
                jar,
            ],
        }
        for label, command in commands.items():
            with (output / f"{label}.log").open("w") as log:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=600,
                )
            results[label] = "PASS" if result.returncode == 0 else "FAIL"
            print(label, results[label], flush=True)
            (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    if any(value != "PASS" for value in results.values()):
        raise SystemExit(
            "Output-only diagnostic failed; inspect retained logs and screenshots. No microphone permission was granted."
        )


if __name__ == "__main__":
    main()
