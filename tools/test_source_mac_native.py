"""Dogfood the real Mac source launcher, private cache and offline native app."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from package_integrity import tree_digest

ROOT = Path(__file__).resolve().parents[1]


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(path):
    """Detect replacement as well as byte changes during an offline cache reuse."""
    files = [
        item for item in sorted(path.rglob("*")) if item.is_file() or item.is_symlink()
    ]
    if not files:
        raise RuntimeError(f"Expected a populated native cache: {path}")
    times = hashlib.sha256()
    for item in files:
        times.update(str(item.relative_to(path)).encode() + b"\0")
        times.update(str(item.lstat().st_mtime_ns).encode() + b"\0")
    return {
        "tree_sha256": tree_digest(path),
        "mtime_sha256": times.hexdigest(),
        "files": len(files),
    }


def run_cli(
    output, label, command, environment, expected=0, contains=None, timeout=120
):
    started = time.monotonic()
    completed = subprocess.run(
        [str(value) for value in command],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    (output / f"{label}.stdout.log").write_text(completed.stdout)
    (output / f"{label}.stderr.log").write_text(completed.stderr)
    receipt = {
        "argv": [str(value) for value in command],
        "exit_code": completed.returncode,
        "seconds": time.monotonic() - started,
        "result": "FAIL",
    }
    try:
        if completed.returncode != expected:
            raise RuntimeError(
                f"{label}: expected exit {expected}, got {completed.returncode}; inspect its logs"
            )
        if contains and contains not in completed.stdout + completed.stderr:
            raise RuntimeError(f"{label}: expected output {contains!r} was absent")
        receipt["result"] = "PASS"
        return completed.stdout.strip()
    finally:
        (output / f"{label}.json").write_text(json.dumps(receipt, indent=2) + "\n")


def verify_native_source(output):
    output.mkdir(parents=True, exist_ok=True)
    completion = output / "completion.json"
    app_path_file = output / "app-path.txt"
    completion.unlink(missing_ok=True)
    app_path_file.unlink(missing_ok=True)
    (output / "provenance.json").unlink(missing_ok=True)
    result = {"result": "FAIL", "visual_review": "PENDING"}
    try:
        # Keep the large JDK/app caches outside retained evidence. Preserve them for
        # the following exact-app profile; the disposable CI workspace owns them.
        cache = Path(
            tempfile.mkdtemp(prefix="native source cache ", dir=ROOT / "build")
        )
        environment = {**os.environ, "EMBERWOOD_CACHE_DIR": str(cache)}
        environment.pop("EMBERWOOD_JAVA_HOME", None)
        environment.pop("JAVA_TOOL_OPTIONS", None)
        launcher = ROOT / "emberwood-kotlin"
        result["cache"] = str(cache)
        source_jar = ROOT / "build/libs/emberwood-kotlin.jar"
        expected_jar = file_digest(source_jar)
        run_cli(
            output,
            "help-cold",
            [launcher, "--help"],
            environment,
            contains="Emberwood Kotlin",
        )
        if list(cache.iterdir()):
            raise RuntimeError("--help unexpectedly prepared dependencies")
        run_cli(
            output,
            "cold-build",
            [launcher, "--build"],
            environment,
            contains="Ready.",
            timeout=1200,
        )
        if file_digest(source_jar) != expected_jar:
            raise RuntimeError(
                "Source preparation changed the already-verified production JAR"
            )
        jdk = Path(
            run_cli(
                output,
                "offline-java",
                [ROOT / "tools/bootstrap.sh", "--offline"],
                environment,
            )
        )
        if not jdk.is_relative_to(cache) or not (jdk / "bin/java").is_file():
            raise RuntimeError("First source build did not install its own private JDK")
        apps = list((cache / "source-apps/apps").glob("*/Emberwood Kotlin.app"))
        if len(apps) != 1:
            raise RuntimeError("Cold source build must publish exactly one native app")
        app = apps[0].resolve()
        runtime = app / "Contents/runtime/Contents/Home"
        if file_digest(app / "Contents/app/emberwood-kotlin.jar") != expected_jar:
            raise RuntimeError("Cached source app has different game bytes")
        before = {"app": snapshot(app), "jdk": snapshot(jdk)}
        run_cli(
            output,
            "version",
            [launcher, "--offline", "--version"],
            environment,
            contains="Emberwood Kotlin",
        )
        run_cli(
            output,
            "invalid",
            [launcher, "--offline", "--invalid"],
            environment,
            expected=2,
            contains="Use no arguments",
        )
        run_cli(
            output,
            "missing-data-dir",
            [launcher, "--offline", "--data-dir"],
            environment,
            expected=2,
            contains="Use no arguments",
        )
        run_cli(
            output,
            "headless",
            [launcher, "--offline"],
            {**environment, "JAVA_TOOL_OPTIONS": "-Djava.awt.headless=true"},
            expected=2,
            contains="graphical desktop",
        )
        run_cli(
            output,
            "invalid-vm-option",
            [launcher, "--offline"],
            {**environment, "JAVA_TOOL_OPTIONS": "-XX:EmberwoodInvalidOption=1"},
            expected=2,
            contains="private JDK is not cached",
        )
        cached = run_cli(
            output,
            "reuse-cache",
            [ROOT / "tools/source_mac_app.sh", jdk, source_jar],
            environment,
        )
        if Path(cached) != app:
            raise RuntimeError("Unchanged inputs did not reuse the same native app")
        packaged = list((ROOT / "dist").glob("emberwood-kotlin-*/Emberwood Kotlin.app"))
        if len(packaged) != 1:
            raise RuntimeError(
                "Expected one independently verified distribution for source parity"
            )
        packaged_runtime = packaged[0] / "Contents/runtime/Contents/Home"
        runtime_digest = tree_digest(runtime)
        if runtime_digest != tree_digest(packaged_runtime):
            raise RuntimeError("The source and packaged native runtimes differ")
        if (
            file_digest(packaged[0] / "Contents/app/emberwood-kotlin.jar")
            != expected_jar
        ):
            raise RuntimeError("The source and packaged games differ")
        run_cli(
            output,
            "offline-native-launch",
            [
                sys.executable,
                ROOT / "tools/mac_bundle_smoke.py",
                app,
                "--output",
                output / "launch",
                "--launch-command",
                json.dumps([str(launcher), "--offline"]),
            ],
            environment,
            timeout=180,
        )
        after = {"app": snapshot(app), "jdk": snapshot(jdk)}
        if before != after:
            raise RuntimeError("Offline use replaced or changed cached app/JDK files")
        result.update(
            {
                "result": "PASS",
                "app": str(app),
                "game_jar_sha256": expected_jar,
                "runtime_tree_sha256": runtime_digest,
                "packaged_app": str(packaged[0]),
                "source_matches_packaged_jar_and_runtime": True,
                "before": before,
                "after": after,
                "launch": json.loads((output / "launch/result.json").read_text()),
                "limits": "Physical startup/close and cache checks passed; inspect captured title/pause/cleanup frames. LaunchServices status is not arbitrary JVM exit-code propagation.",
            }
        )
        (output / "provenance.json").write_text(json.dumps(result, indent=2) + "\n")
        app_path_file.write_text(str(app) + "\n")
        print(
            f"PASS: real source preparation, CLI errors, offline cache and native launch: {app}"
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        result["error"] = str(error)
        raise
    finally:
        completion.write_text(json.dumps(result, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/source-mac-native")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run this real native-source check on macOS.")
    verify_native_source(args.output.resolve())


if __name__ == "__main__":
    main()
