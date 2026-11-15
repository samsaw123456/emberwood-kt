"""Bundle a native Java 25 desktop runtime and an offline app on Linux or macOS."""

import argparse
import gzip
import hashlib
import os
import platform
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = ".emberwood-kotlin-managed"
NAME = "Emberwood Kotlin"


def call(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def checksum(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n")


def build_deb(app, version, arch, dist):
    if not shutil.which("dpkg-deb"):
        print("dpkg-deb is unavailable; the portable Linux archive is still produced.")
        return
    architecture = "amd64" if arch == "x86_64" else "arm64"
    with tempfile.TemporaryDirectory(prefix="emberwood-deb-") as temporary:
        stage = Path(temporary)
        shutil.copytree(app, stage / "opt/emberwood-kotlin", symlinks=True)
        metadata = stage / "DEBIAN"
        metadata.mkdir()
        (metadata / "control").write_text(
            f"Package: emberwood-kotlin\nVersion: {version}\nArchitecture: {architecture}\n"
            "Maintainer: Samuel Callahan Sierra <samuel@callahansierra.com>\n"
            "Section: games\nPriority: optional\n"
            "Depends: libc6 (>= 2.28), libx11-6, libxext6, libxi6, libxrender1, "
            "libxtst6, libfontconfig1, libfreetype6, zlib1g, libasound2t64 | libasound2\n"
            "Homepage: https://github.com/samsaw123456/emberwood-kt\n"
            "Description: Emberwood forest adventure, independent Kotlin edition\n"
            " Twenty forest levels with animal guardians, weapons and armor.\n"
            " Includes its own Java runtime and works offline after installation.\n",
        )
        applications = stage / "usr/share/applications"
        applications.mkdir(parents=True)
        desktop = applications / "org.emberwood.kotlin.desktop"
        desktop.write_text(
            "[Desktop Entry]\nType=Application\nName=Emberwood Kotlin\n"
            "Comment=Explore twenty forest levels. Play offline.\n"
            "Exec=/opt/emberwood-kotlin/bin/emberwood-kotlin\nIcon=emberwood-kotlin\n"
            "Terminal=false\nCategories=Game;AdventureGame;\nStartupWMClass=Emberwood Kotlin\n",
        )
        if shutil.which("desktop-file-validate"):
            call("desktop-file-validate", desktop)
        icons = stage / "usr/share/icons/hicolor/512x512/apps"
        icons.mkdir(parents=True)
        shutil.copy2(app / "icon.png", icons / "emberwood-kotlin.png")
        documentation = stage / "usr/share/doc/emberwood-kotlin"
        documentation.mkdir(parents=True)
        for name in ("LICENSE", "THIRD_PARTY.md", "README.md"):
            if (ROOT / name).is_file():
                shutil.copy2(ROOT / name, documentation / name)
        (documentation / "copyright").write_text(
            "Emberwood Kotlin\n"
            "Source: https://github.com/samsaw123456/emberwood-kt\n"
            "Copyright (C) 2026 Samuel Callahan Sierra and Emberwood contributors\n"
            "Code license: Apache-2.0, see /usr/share/common-licenses/Apache-2.0.\n"
            "Imported artwork keeps its original licenses, listed in THIRD_PARTY.md\n"
            "and embedded assets/CREDITS.md, assets/licenses/ and assets/fonts/LICENSE.txt.\n"
            "The bundled Temurin runtime includes module notices under runtime/legal.\n",
        )
        (documentation / "changelog.gz").write_bytes(
            gzip.compress(
                f"Emberwood Kotlin {version}: independent Kotlin desktop edition.\n".encode(),
                mtime=0,
            ),
        )
        package = dist / f"emberwood-kotlin_{version}_{architecture}.deb"
        call("dpkg-deb", "--build", "--root-owner-group", stage, package)
        checksum(package)


def build_package(skip_build=False, install=False):
    system = platform.system()
    if system not in {"Linux", "Darwin"}:
        raise SystemExit(
            "Package natively on Linux or macOS; cross-platform runtimes cannot be mixed."
        )
    java_home = Path(
        subprocess.check_output([ROOT / "tools/bootstrap.sh"], text=True).strip()
    )
    environment = dict(os.environ, JAVA_HOME=str(java_home))
    if not skip_build:
        call(
            ROOT / "gradlew",
            "--no-daemon",
            "check",
            "fatJar",
            cwd=ROOT,
            env=environment,
        )
    jar = ROOT / "build/libs/emberwood-kotlin.jar"
    if not jar.is_file():
        raise SystemExit("No game JAR exists. Build the game first.")
    version = (ROOT / "VERSION").read_text().strip()
    target = "macos" if system == "Darwin" else "linux"
    arch = {"arm64": "aarch64", "amd64": "x86_64"}.get(
        platform.machine(), platform.machine()
    )
    if arch not in {"x86_64", "aarch64"}:
        raise SystemExit(f"Unsupported architecture: {arch}")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    stem = f"emberwood-kotlin-{version}-{target}-{arch}"
    destination = dist / stem
    if destination.exists():
        if not (destination / MARKER).is_file():
            raise SystemExit(
                f"Refusing to overwrite an unmarked directory: {destination}"
            )
        shutil.rmtree(destination)
    with tempfile.TemporaryDirectory(
        prefix="emberwood-package-", dir=dist
    ) as temporary:
        stage = Path(temporary)
        app = stage / (NAME + ".app" if system == "Darwin" else NAME)
        content = app / "Contents" if system == "Darwin" else app
        runtime = content / "runtime"
        call(
            java_home / "bin/jlink",
            "--add-modules",
            "java.desktop,java.logging,java.prefs,jdk.crypto.ec",
            "--strip-debug",
            "--no-header-files",
            "--no-man-pages",
            "--compress=zip-6",
            "--output",
            runtime,
        )
        library = content / "Resources" if system == "Darwin" else content / "lib"
        executable = content / "MacOS" if system == "Darwin" else content / "bin"
        library.mkdir(parents=True)
        executable.mkdir(parents=True)
        shutil.copy2(jar, library / "emberwood-kotlin.jar")
        icon = ROOT / "src/main/resources/assets/app/emberwood.png"
        if system == "Linux":
            shutil.copy2(icon, app / "icon.png")
        launcher = executable / "emberwood-kotlin"
        launcher.write_text(
            "#!/bin/sh\nset -eu\n"
            'app_dir=$(CDPATH="" cd -- "$(dirname -- "$0")/.." && pwd)\n'
            'exec "$app_dir/runtime/bin/java" -Xms32m -Xmx256m '
            "--enable-native-access=ALL-UNNAMED "
            + (
                '-Xdock:name="Emberwood Kotlin" '
                '-Xdock:icon="$app_dir/Resources/Emberwood.icns" '
                if system == "Darwin"
                else ""
            )
            + (
                '-jar "$app_dir/Resources/emberwood-kotlin.jar" "$@"\n'
                if system == "Darwin"
                else '-jar "$app_dir/lib/emberwood-kotlin.jar" "$@"\n'
            ),
        )
        launcher.chmod(0o755)
        (content / MARKER).write_text("Managed by Emberwood Kotlin installer\n")
        if system == "Darwin":
            iconset = stage / "Emberwood.iconset"
            iconset.mkdir()
            for size in (16, 32, 128, 256, 512):
                for scale in (1, 2):
                    resolution = min(size * scale, 1024)
                    suffix = "@2x" if scale == 2 else ""
                    call(
                        "sips",
                        "-z",
                        resolution,
                        resolution,
                        icon,
                        "--out",
                        iconset / f"icon_{size}x{size}{suffix}.png",
                        stdout=subprocess.DEVNULL,
                    )
            call("iconutil", "-c", "icns", iconset, "-o", library / "Emberwood.icns")
            shutil.rmtree(iconset)
            with (content / "Info.plist").open("wb") as stream:
                plistlib.dump(
                    {
                        "CFBundleName": NAME,
                        "CFBundleDisplayName": NAME,
                        "CFBundleIdentifier": "org.emberwood.kotlin",
                        "CFBundleExecutable": "emberwood-kotlin",
                        "CFBundleIconFile": "Emberwood.icns",
                        "CFBundlePackageType": "APPL",
                        "CFBundleShortVersionString": version,
                        "CFBundleVersion": version,
                        "NSHighResolutionCapable": True,
                        "LSMinimumSystemVersion": "12.0",
                    },
                    stream,
                )
            # Ad-hoc signing preserves local integrity; it is not Apple notarization.
            call("codesign", "--force", "--deep", "--sign", "-", app)
            call("codesign", "--verify", "--deep", "--strict", app)
        for name in ("README.md", "LICENSE", "THIRD_PARTY.md", "VERSION"):
            shutil.copy2(ROOT / name, stage / name)
        shutil.copy2(
            ROOT / "tools/install.sh", stage / "Install Emberwood Kotlin.command"
        )
        (stage / "Install Emberwood Kotlin.command").chmod(0o755)
        (stage / MARKER).write_text("Managed Emberwood Kotlin package\n")
        shutil.copytree(stage, destination, symlinks=True)
    if system == "Darwin":
        archive = dist / (stem + ".zip")
        call(
            "ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", destination, archive
        )
    else:
        archive = dist / (stem + ".tar.gz")
        with tarfile.open(archive, "w:gz") as output:
            output.add(destination, arcname=stem)
    checksum(archive)
    if system == "Linux":
        build_deb(destination / NAME, version, arch, dist)
    print(f"Packaged: {archive} ({archive.stat().st_size / 1024**2:.1f} MiB)")
    if install:
        call(destination / "Install Emberwood Kotlin.command")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--install", action="store_true", help="install for the current user"
    )
    args = parser.parse_args()
    build_package(args.skip_build, args.install)


if __name__ == "__main__":
    main()
