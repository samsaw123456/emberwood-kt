"""Fresh-run output-only entitlement trial in a disposable native app copy."""

import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from diagnose_mac_output import record_signing
from mac_app_profile import configure_app, run_owned_check
from package_integrity import tree_digest

ROOT = Path(__file__).resolve().parents[1]


def requested_entitlements(mode):
    if mode == "false-only":
        return {"com.apple.security.device.audio-input": False}
    if mode == "hardened":
        # Pinned HotSpot executable mappings use MAP_JIT; FFM upcalls use CodeCache.
        # See docs/MAC_SIGNING_TRIAL.md. No input, debugger, dyld or unsigned-memory grant.
        return {
            "com.apple.security.cs.allow-jit": True,
            "com.apple.security.cs.disable-library-validation": True,
        }
    raise ValueError(f"Unknown diagnostic signing mode: {mode}")


def identity(app):
    return {
        "runtime": tree_digest(app / "Contents/runtime"),
        "game_jar": hashlib.sha256(
            (app / "Contents/app/emberwood-kotlin.jar").read_bytes()
        ).hexdigest(),
    }


def sign_without_input(app, entitlements, output, expected, mode="false-only"):
    subprocess.run(
        [
            "codesign",
            "--force",
            "--sign",
            "-",
            *(["--options", "runtime"] if mode == "hardened" else []),
            "--entitlements",
            entitlements,
            app,
        ],
        check=True,
        timeout=30,
    )
    subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", app], check=True, timeout=30
    )
    receipt = subprocess.run(
        ["codesign", "--display", "--verbose=4", "--entitlements", ":-", app],
        check=True,
        capture_output=True,
        timeout=15,
    )
    description = receipt.stderr.decode()
    (output / "entitlement-check.log").write_text(description)
    actual = plistlib.loads(receipt.stdout)
    (output / "actual-entitlements.plist").write_bytes(plistlib.dumps(actual))
    requested = requested_entitlements(mode)
    if actual != requested or any(type(value) is not bool for value in actual.values()):
        raise RuntimeError(
            "The diagnostic native app did not retain exactly the requested entitlements"
        )
    flags = re.search(r"\bflags=0x([0-9a-fA-F]+)", description)
    if not flags or bool(int(flags.group(1), 16) & 0x10000) != (mode == "hardened"):
        raise RuntimeError(
            "The observed native signature runtime flag does not match the trial"
        )
    (output / "signature-policy.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "flags": "0x" + flags.group(1),
                "hardened_runtime": mode == "hardened",
                "entitlements": actual,
            },
            indent=2,
        )
        + "\n"
    )
    if identity(app) != expected:
        raise RuntimeError(
            "Diagnostic signing changed production runtime or game bytes"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build/mac-entitlement-trial"
    )
    parser.add_argument(
        "--mode", choices=("false-only", "hardened"), default="false-only"
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
        "signing_mode": args.mode,
        "requested_entitlements": requested_entitlements(args.mode),
        "production": expected,
        "permission_changes": False,
    }
    with tempfile.TemporaryDirectory(
        prefix="emberwood input-denied trial "
    ) as directory:
        app = Path(directory).resolve() / "Emberwood Kotlin.app"
        subprocess.run(["ditto", original, app], check=True, timeout=60)
        entitlements = output / "diagnostic-entitlements.plist"
        entitlements.write_bytes(plistlib.dumps(requested_entitlements(args.mode)))
        try:
            for label in ("original-signing", "startup", "native-pcm"):
                (output / label).mkdir(exist_ok=True)
            source_java = Path(os.environ["JAVA_HOME"]) / "bin/java"
            record_signing(app, source_java, output / "original-signing")
            sign_without_input(
                app, entitlements, output / "startup", expected, args.mode
            )
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
            sign_without_input(
                app, entitlements, output / "native-pcm", expected, args.mode
            )
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
            if not evidence["unchanged_game_and_runtime"]:
                raise RuntimeError(
                    "Diagnostic execution changed production runtime or game bytes"
                )
            evidence["result"] = "PASS"
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            evidence.update(result="FAIL", error=str(error))
            raise
        finally:
            (output / "result.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
