# Native packages and toolchains

The source launcher provisions Temurin **25.0.5+8** into a private cache, with
four platform/architecture URLs and SHA-256 hashes pinned in
`tools/jdk-downloads.tsv`. `EMBERWOOD_JAVA_HOME` can select another complete JDK
25; `EMBERWOOD_CACHE_DIR` moves the private cache. Neither changes system Java.

Version evidence, checked 2026-11-15:

- [Gradle's current release metadata](https://services.gradle.org/versions/current)
  reports 9.9.1; the wrapper and distribution hashes match its official values.
- [Kotlin Maven metadata](https://repo.maven.apache.org/maven2/org/jetbrains/kotlin/kotlin-gradle-plugin/maven-metadata.xml)
  lists 2.4.21 as the newest stable release (2.5.0 entries are prereleases).
- [Temurin's Java 25 release](https://github.com/adoptium/temurin25-binaries/releases/tag/jdk-25.0.5%2B8)
  supplies the pinned Java build. This JDK supports linking from its runtime image;
  a `jmods` directory is not required.

The Gradle build caps worker count at two and build heap at 512 MiB. Game launchers
use a 32 MiB initial / 256 MiB maximum heap. These are limits, not performance
measurements; actual game profiling is recorded separately.

Python 3.11 or newer is needed only by maintainers for packaging.
`python3 tools/package_app.py` runs checks and creates a native application from
the fat JAR plus `jlink`'s desktop runtime. Run packaging on each target operating
system/CPU. It does not cross-package a Linux JVM into a macOS application.
Linux portable archives include a per-user installer. macOS ZIPs contain an app
bundle created by the JDK's `jpackage` native launcher, icon, Info.plist, ad-hoc
signature and per-user installer. Runtime and
artwork are bundled unchanged with their notices. No network is used by the app.

Installers stage replacements before moving the prior app, refuse to overwrite
unmarked directories, handle spaces and desktop Exec escaping, and preserve
settings outside the installation. Run the same installer with `--uninstall` to
remove its managed app/launcher while retaining saved settings. System-installed
Debian packages should be removed with the package manager instead.

Linux requires a desktop with X11/XWayland and ordinary font/audio libraries.
Debian packages declare those dependencies for automatic resolution by the
system installer. Portable archives assume those desktop libraries are present.
macOS builds require version 12 or newer and the matching CPU architecture.
Ad-hoc signing verifies package integrity but does not replace Apple signing or
notarization; no signing identity or Apple account is used by this repository.

The CI matrix builds and runs tests plus the physical-input control audit on
Linux x86-64/ARM64 and macOS Intel/Apple Silicon, then repeats that audit using the packaged runtime and JAR before retaining artifacts. A matrix
configuration is not proof of a successful run: consult the actual workflow
results and the project's audit records before claiming a platform verified.

## Installer verification performed locally

The source bootstrap was exercised with an empty private cache: official JDK
archive download, pinned SHA-256, extraction, Java 25 runtime validation, then
network-free cache reuse. The new Temurin build's lack of a `jmods` directory was
caught during this exercise; bootstrap validates modules and jlink uses the
linkable runtime image instead. Java 17 on the user's PATH remains unchanged.

`python3 -m unittest discover -s tools -p 'test_install.py' -v` passes six tests:
missing package/invalid option, install/upgrade/uninstall with a real Gio launcher
(including spaces, dollar and percent in paths), refusal to replace unmarked
personal directories, offline-cache/invalid-JDK failures, rejected tampered-download
checksums, and interrupted replacement with restoration of the prior app. An Exec percent
preflight problem found by this test was fixed by invoking the quoted launcher
through `/bin/sh`, without shell evaluation. ShellCheck 0.11, Bash syntax checks,
and Ruff check/format checks pass for the packaging/bootstrap tooling.

These fixture tests do not substitute for the native game's final package/control
checks or macOS CI results, which are recorded in the overall verification report.

The first macOS installation check caught a copied-bundle signature failure in
the management marker. The bundle now puts that resource under `Contents/Resources`,
uses `jpackage`'s native executable, copies signed bundles with `ditto`, and verifies
signatures after staging and installation. This follows [Apple's bundle-signing
guidance](https://developer.apple.com/library/archive/technotes/tn2206/) and the
[Java 25 packaging tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html).
The corrected macOS path must pass the native CI installation/GUI checks before
it is called verified.

Java 25 also validates macOS's internal `CFBundleVersion` with a positive first
component. Packaging maps the release major version to major + 1 for that build
field (0.1.0 becomes 1.1.0), while `CFBundleShortVersionString`, the game and the
download keep the actual release version 0.1.0. The native installation test
checks both fields. The validation rule is in [OpenJDK's macOS bundle-version
parser](https://github.com/openjdk/jdk25u/blob/master/src/jdk.jpackage/macosx/classes/jdk/jpackage/internal/CFBundleVersion.java).
Both macOS architectures in CI run `43695656000` caught this validation failure;
the metadata correction still requires a successful native package/install run.

## Actual Linux package and launcher checks

The Linux x86-64 candidate was built with `python3 tools/package_app.py --skip-build`.
Both archive and Debian-package SHA-256 files were verified. The actual package
passed `python3 tools/test_package.py dist/emberwood-kotlin-0.1.0-linux-x86_64`:
isolated installation, bundled Java 25 version, desktop metadata, upgrade replacing
obsolete files, and uninstall retaining the settings location.

The installed game was also launched through Gio with invalid `JAVA_HOME` and
`EMBERWOOD_JAVA_HOME` values, while a child-only seccomp rule denied all IPv4/IPv6
socket creation. A separate socket probe confirmed that the restriction was active.
The game rendered, accepted Start/D/Space/Escape, and exited from its window close
command. Its `/proc` executable resolved to the installed private runtime. This
caught a desktop-grouping mismatch: Java's actual window class is `emberwood-MainKt`,
which the installer and Debian desktop files now use.

The separate **Emberwood Kotlin** entry is installed for the current Linux user.
`gtk-launch org.emberwood.kotlin` was exercised with the same offline restriction;
the title and paused screen were inspected. A repeat under an isolated Openbox
window manager pressed physical Alt+F4 and verified that the installed process
exited. The original **Emberwood** desktop entry
and repository remain unchanged. Local evidence is in `build/installed-audit/`,
`build/installed-user-audit/`, `build/installed-physical-close-final.log`, and
`build/package-install-final.log`. This installed candidate matches the measured
game JAR SHA-256
`02b181548e236c13eae655d803e217949dda208ed538e1a4b882dc68a475536a`.
