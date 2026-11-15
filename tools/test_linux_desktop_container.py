"""Prove real desktop dependency recovery inside a disposable Ubuntu container."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r"""set -eu
rm -rf /var/lib/apt/lists/*
mkdir -p /var/lib/apt/lists/partial
test ! -w /app
set +e
/app/bin/ensure-linux-desktop /app/runtime --offline > /evidence/offline.log 2>&1
offline_status=$?
set -e
test "$offline_status" -eq 2
grep -q 'Offline mode will not download' /evidence/offline.log
/app/bin/ensure-linux-desktop /app/runtime > /evidence/recovery.log 2>&1
/app/bin/emberwood-kotlin --version > /evidence/version.log 2>&1
/app/runtime/bin/java -Djava.awt.headless=true -cp /evidence:/app/lib/emberwood-kotlin.jar FontDependencyProbe > /evidence/game-fonts.log 2>&1
dpkg-query -W -f='${Package}\t${Version}\t${Status}\n' libxtst6 libfontconfig1 libasound2t64 > /evidence/installed-packages.tsv
sha256sum /var/log/apt/history.log > /evidence/history-before.sha256
/app/bin/ensure-linux-desktop /app/runtime --offline > /evidence/healthy-offline.log 2>&1
sha256sum /var/log/apt/history.log > /evidence/history-after.sha256
cmp /evidence/history-before.sha256 /evidence/history-after.sha256
printf 'PASS: real cold-index recovery, bundled fonts and offline reuse.\n'
"""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(output):
    output.mkdir(parents=True, exist_ok=True)
    receipt = {"result": "FAIL", "image": "ubuntu:24.04"}
    name = "emberwood-dependencies-" + uuid.uuid4().hex[:12]
    created = False
    try:
        docker = shutil.which("docker")
        if docker is None:
            raise RuntimeError(
                "Docker is unavailable; this real recovery check is unverified."
            )
        apps = list((ROOT / "dist").glob("emberwood-kotlin-*/Emberwood Kotlin"))
        if len(apps) != 1:
            raise RuntimeError(
                "Prepare exactly one native Linux package before this check."
            )
        app = apps[0].resolve()
        helper = app / "bin/ensure-linux-desktop"
        if helper.read_bytes() != (ROOT / "tools/ensure_linux_desktop.sh").read_bytes():
            raise RuntimeError("The packaged dependency helper is stale.")
        jar = app / "lib/emberwood-kotlin.jar"
        if digest(jar) != digest(ROOT / "build/libs/emberwood-kotlin.jar"):
            raise RuntimeError("The package contains a different game JAR.")
        java_home = Path(os.environ.get("JAVA_HOME", ""))
        javac = java_home / "bin/javac"
        if not javac.is_file():
            raise RuntimeError(
                "Set JAVA_HOME to the pinned private JDK for the font probe."
            )
        probe = output / "FontDependencyProbe.java"
        probe.write_text(
            "class FontDependencyProbe { public static void main(String[] args) throws Exception { "
            'Class.forName("emberwood.Assets"); System.out.println("Bundled game fonts loaded"); } }\n'
        )
        subprocess.run([javac, "-d", output, probe], check=True, timeout=30)
        with (output / "pull.log").open("w") as log:
            subprocess.run(
                [docker, "pull", "ubuntu:24.04"],
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=120,
            )
        receipt.update(
            image_identity=json.loads(
                subprocess.check_output(
                    [
                        docker,
                        "image",
                        "inspect",
                        "ubuntu:24.04",
                        "--format",
                        "{{json .RepoDigests}}",
                    ],
                    text=True,
                    timeout=15,
                )
            ),
            game_sha256=digest(jar),
            helper_sha256=digest(helper),
            app_mount="read-only",
            host_library_changes="none",
        )
        command = [
            docker,
            "run",
            "--rm",
            "--name",
            name,
            "--mount",
            f"type=bind,source={app},target=/app,readonly",
            "--mount",
            f"type=bind,source={output},target=/evidence",
            "--env",
            "DEBIAN_FRONTEND=noninteractive",
            "ubuntu:24.04",
            "/bin/bash",
            "-c",
            SCRIPT,
        ]
        (output / "inside.sh").write_text(SCRIPT)
        created = True
        with (output / "container.log").open("w") as log:
            subprocess.run(
                command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=240
            )
        receipt["result"] = "PASS"
        receipt["scope"] = (
            "Real apt refresh/install in disposable Ubuntu24.04; font probe loads actual game Assets; healthy offline repeat leaves apt history unchanged. No graphical display is provided by this container."
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        receipt["error"] = str(error)
        raise
    finally:
        if created:
            try:
                cleanup = subprocess.run(
                    [docker, "rm", "-f", name],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                receipt["cleanup"] = cleanup.stdout + cleanup.stderr
                if (
                    cleanup.returncode != 0
                    and "No such container" not in cleanup.stderr
                ):
                    raise RuntimeError(
                        "Could not confirm removal of the owned container."
                    )
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                receipt["result"] = "FAIL"
                receipt["cleanup_error"] = str(error)
        (output / "completion.json").write_text(json.dumps(receipt, indent=2) + "\n")
        if receipt["result"] != "PASS":
            raise RuntimeError(f"Container verification failed; inspect {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build/dependency-container"
    )
    args = parser.parse_args()
    verify(args.output.resolve())


if __name__ == "__main__":
    main()
