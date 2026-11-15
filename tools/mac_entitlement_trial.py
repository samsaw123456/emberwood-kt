"""Fresh-run output-only entitlement trial in a disposable native app copy."""

import argparse
import hashlib
import json
import os
import platform
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

from diagnose_mac_output import record_signing
from mac_app_profile import app_pid, configure_app
from mac_bundle_smoke import cleanup_app
from mac_game_window import GameWindow
from mac_profile_observer import NativeStatus
from package_integrity import tree_digest

ROOT = Path(__file__).resolve().parents[1]


def identity(app):
    return {
        "runtime": tree_digest(app / "Contents/runtime"),
        "game_jar": hashlib.sha256(
            (app / "Contents/app/emberwood-kotlin.jar").read_bytes()
        ).hexdigest(),
    }


def sign_without_input(app, entitlements, output, expected):
    subprocess.run(
        ["codesign", "--force", "--sign", "-", "--entitlements", entitlements, app],
        check=True,
        timeout=30,
    )
    subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", app], check=True, timeout=30
    )
    with (output / "entitlement-check.log").open("w") as log:
        receipt = subprocess.run(
            ["codesign", "--display", "--entitlements", ":-", app],
            check=True,
            stdout=subprocess.PIPE,
            stderr=log,
            timeout=15,
        )
    actual = plistlib.loads(receipt.stdout)
    (output / "actual-entitlements.plist").write_bytes(plistlib.dumps(actual))
    if actual.get("com.apple.security.device.audio-input") is not False:
        raise RuntimeError(
            "The diagnostic native app did not retain the explicit input denial"
        )
    if identity(app) != expected:
        raise RuntimeError(
            "Diagnostic signing changed production runtime or game bytes"
        )


def run_owned_check(app, command, output, timeout):
    output.mkdir(parents=True, exist_ok=True)
    native, windows = NativeStatus(), GameWindow()
    baseline = windows.visible_registry()
    metadata = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    executable = app / "Contents/MacOS" / metadata["CFBundleExecutable"]
    try:
        with (output / "driver.log").open("w") as log:
            subprocess.run(
                command,
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
    finally:
        cleanup_app(app_pid(native, app), executable, windows, baseline, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build/mac-entitlement-trial"
    )
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run this native app diagnostic on macOS")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
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
    expected = identity(original)
    evidence = {
        "result": "INCOMPLETE",
        "diagnostic_only": True,
        "audio_input_entitlement": False,
        "production": expected,
        "permission_changes": False,
    }
    with tempfile.TemporaryDirectory(
        prefix="emberwood input-denied trial "
    ) as directory:
        app = Path(directory).resolve() / "Emberwood Kotlin.app"
        subprocess.run(["ditto", original, app], check=True, timeout=60)
        entitlements = output / "diagnostic-entitlements.plist"
        entitlements.write_bytes(
            plistlib.dumps({"com.apple.security.device.audio-input": False})
        )
        try:
            for label in ("original-signing", "startup", "native-pcm"):
                (output / label).mkdir(exist_ok=True)
            source_java = Path(os.environ["JAVA_HOME"]) / "bin/java"
            record_signing(app, source_java, output / "original-signing")
            sign_without_input(app, entitlements, output / "startup", expected)
            record_signing(app, source_java, output / "startup")
            run_owned_check(
                app,
                [
                    sys.executable,
                    ROOT / "tools/mac_bundle_smoke.py",
                    app,
                    "--startup-only",
                    "--output",
                    output / "startup",
                ],
                output / "startup-cleanup",
                180,
            )
            evidence["startup"] = "PASS"
            # Same signed app identity and exact production bytes; only the test entry changes.
            configure_app(
                app,
                ROOT / "build/classes/kotlin/test",
                output / "native-pcm",
                30,
                None,
                "audio",
            )
            sign_without_input(app, entitlements, output / "native-pcm", expected)
            record_signing(app, source_java, output / "native-pcm")
            run_owned_check(
                app,
                [
                    sys.executable,
                    ROOT / "tools/mac_audio_audit.py",
                    "--app",
                    app,
                    "--output",
                    output / "native-pcm",
                ],
                output / "pcm-cleanup",
                900,
            )
            evidence["native_app_pcm"] = "PASS"
            evidence["unchanged_game_and_runtime"] = identity(app) == expected
            evidence["result"] = "PASS"
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            evidence.update(result="FAIL", error=str(error))
            raise
        finally:
            (output / "result.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
