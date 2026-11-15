"""Run control or native Mac audio checks using only the packaged game JAR/runtime."""

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audio",
        action="store_true",
        help="Run the native Mac PCM audit with the bundled runtime",
    )
    args = parser.parse_args()
    system = platform.system()
    if system == "Darwin":
        subprocess.run(
            [
                sys.executable,
                ROOT / "tools/mac_app_profile.py",
                "--audit",
                "audio" if args.audio else "controls",
                "--output",
                ROOT
                / "build"
                / ("audio-audit-macos-packaged" if args.audio else "audit-packaged"),
            ],
            cwd=ROOT,
            check=True,
        )
        return
    if args.audio:
        parser.error("The bundled native PCM capture uses macOS ScreenCaptureKit.")
    version = (ROOT / "VERSION").read_text().strip()
    arch = {"arm64": "aarch64", "amd64": "x86_64"}.get(
        platform.machine(), platform.machine()
    )
    package = ROOT / "dist" / f"emberwood-kotlin-{version}-linux-{arch}"
    app = package / "Emberwood Kotlin"
    java = app / "runtime/bin/java"
    jar = app / "lib/emberwood-kotlin.jar"
    tests = ROOT / "build/classes/kotlin/test"
    if not java.is_file() or not jar.is_file() or not tests.is_dir():
        raise SystemExit(
            "Build test classes and the native package before auditing it."
        )
    output = ROOT / "build/audit-packaged"
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(java),
            "-Xms32m",
            "-Xmx256m",
            "--enable-native-access=ALL-UNNAMED",
            f"-Daudit.output={output}",
            "-Djava.awt.headless=false",
            "-cp",
            os.pathsep.join([str(jar), str(tests)]),
            "emberwood.NativeAuditKt",
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
