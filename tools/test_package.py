"""Smoke-test the real archive's installation, bundled runtime, upgrade and removal."""

import argparse
import os
import platform
import plistlib
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="extracted native package directory")
    args = parser.parse_args()
    package = args.package.resolve()
    installer = package / "Install Emberwood Kotlin.command"
    if not installer.is_file():
        parser.error("The directory has no shipped installer.")
    with tempfile.TemporaryDirectory(prefix="emberwood package home ") as temporary:
        home = Path(temporary)
        env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / "data"))
        subprocess.run([installer], env=env, check=True, timeout=60)
        mac = platform.system() == "Darwin"
        app = (
            home / "Applications/Emberwood Kotlin.app"
            if mac
            else home / "data/emberwood-kotlin/app"
        )
        if mac:
            with (app / "Contents/Info.plist").open("rb") as stream:
                executable = plistlib.load(stream)["CFBundleExecutable"]
            launcher = app / "Contents/MacOS" / executable
        else:
            launcher = app / "bin/emberwood-kotlin"
        # A deliberately unusable Java environment proves the bundle supplies its own.
        env.update(
            JAVA_HOME="/missing-global-java", EMBERWOOD_JAVA_HOME="/missing-global-java"
        )
        version = subprocess.check_output(
            [launcher, "--version"], env=env, text=True, timeout=30
        )
        assert "Emberwood Kotlin" in version and "Java 25." in version, version
        assert (ROOT / "VERSION").read_text().strip() in version, version
        if mac:
            subprocess.run(["plutil", "-lint", app / "Contents/Info.plist"], check=True)
            subprocess.run(
                ["codesign", "--verify", "--deep", "--strict", app], check=True
            )
            subprocess.run(
                ["open", "-W", "-n", app, "--args", "--version"],
                env=env,
                check=True,
                timeout=60,
            )
            subprocess.run(
                ["python3", ROOT / "tools/mac_bundle_smoke.py", app],
                env=env,
                check=True,
                timeout=90,
            )
        else:
            desktop = home / "data/applications/org.emberwood.kotlin.desktop"
            subprocess.run(["desktop-file-validate", desktop], check=True)
        settings = (
            home / "Library/Application Support/Emberwood Kotlin/settings.properties"
            if mac
            else home / "data/emberwood-kotlin/settings.properties"
        )
        settings.parent.mkdir(parents=True, exist_ok=True)
        saved_preferences = "muted=true\ngentle=true\nbest=123.5\n"
        settings.write_text(saved_preferences)
        (app / "obsolete.txt").write_text("previous package")
        subprocess.run([installer], env=env, check=True, timeout=60)
        assert not (app / "obsolete.txt").exists()
        assert settings.read_text() == saved_preferences
        subprocess.run([launcher, "--version"], env=env, check=True, timeout=60)
        subprocess.run([installer, "--uninstall"], env=env, check=True, timeout=60)
        assert not app.exists()
        assert settings.read_text() == saved_preferences
        print(
            "PASS: native package install, bundled Java25, version, launcher metadata, replacement and removal"
        )


if __name__ == "__main__":
    main()
