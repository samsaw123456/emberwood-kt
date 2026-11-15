"""Run the same physical-input audit with main classes loaded only from a packaged JAR/runtime."""

import os
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    version = (ROOT / "VERSION").read_text().strip()
    system = platform.system()
    target = "macos" if system == "Darwin" else "linux"
    arch = {"arm64": "aarch64", "amd64": "x86_64"}.get(
        platform.machine(), platform.machine()
    )
    package = ROOT / "dist" / f"emberwood-kotlin-{version}-{target}-{arch}"
    app = package / (
        "Emberwood Kotlin.app" if system == "Darwin" else "Emberwood Kotlin"
    )
    content = app / "Contents" if system == "Darwin" else app
    java = content / (
        "runtime/Contents/Home/bin/java" if system == "Darwin" else "runtime/bin/java"
    )
    jar = content / (
        "app/emberwood-kotlin.jar" if system == "Darwin" else "lib/emberwood-kotlin.jar"
    )
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
