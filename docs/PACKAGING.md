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
the fat JAR plus `jlink`'s desktop runtime. `tools/link_runtime.sh` owns the common
runtime recipe and `tools/build_mac_app.sh` owns the native Mac bundle recipe,
including its adventure-game category. Run packaging on each target operating
system/CPU. It does not cross-package a Linux JVM into a macOS application.
Linux portable archives include a per-user installer. macOS ZIPs contain an app
bundle created by the JDK's `jpackage` native launcher, icon, Info.plist, ad-hoc
signature and per-user installer. Runtime and
artwork are bundled unchanged with their notices. No network is used by the app.

Source and Zed launches on macOS also use that native bundle recipe and
LaunchServices. The first source build creates a private runtime/app cache;
later launches verify and reuse it without network access. Game JAR, runtime,
packaging-helper, icon and version changes invalidate the relevant cache. A
failed or interrupted build is never published as a finished cache entry, and
unmarked directories are not replaced. Linux keeps its direct private-Java
launcher. The source route needs no Python or global developer-tool installation.

`tools/sign_mac_app.sh` signs only the outer Mac app with Hardened Runtime and
exactly two Boolean entitlements: JIT and library-validation exceptions for the
bundled JVM. It verifies the resulting flags, strict bundle signature and exact
policy. Release, source and configured audit copies share this helper; no
recording entitlement is present. Installed and upgraded bundles are checked
again by the package test.

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
Both macOS architectures in CI run `43695656000` caught this validation failure.
The corrected packages built on both architectures in run `43697597725`.
The ARM Mac also passed actual installation, signature checks, LaunchServices
launch, keyboard play, and application quit. Its four original screenshots were
inspected: the native title and paused equipment menu are legible, the menu bar
identifies Emberwood Kotlin, the Dock uses the existing fox-and-forest icon, and
physical Command+Q removes the window and running indicator. Local evidence is
`build/ci-fourth-macos-arm/build/bundle-launch-macos/visual-review.md`.
Current Mac verification separates the actual LaunchServices app from raw-JVM
audit launches. The native Apple Silicon app passed all 22 strict performance
windows with the exact bundled runtime and a 180-second soak in run
`43709103784`; every frame was inspected. The complete native-app control audit
is a separate gate and must pass before claiming complete Mac coverage.

The ordered raw-JVM probes in run `43707637231` passed empty-window, audio-worker,
window-before-audio and concurrent game startup on both architectures. Apple
Silicon also passed all fourteen physical PCM cases with both source and packaged
runtimes; all 168 WAVs were reviewed and no interior exact-zero span of at least
2 ms recurred. See `docs/AUDIO.md` and `docs/PERFORMANCE.md` for measured results.

The earlier Intel native app displayed a microphone permission dialog. Its own
Java/native stacks identify the output-only AudioQueue start path waiting in
`AudioDeviceCreateIOProcID`; this is not attributed to Java Sound in the current
build. No microphone access was granted. Run `43710417047` showed that adding
explicit `audio-input=false` to an ordinary ad-hoc signature did not resolve it.
The detached dialog also survived app exit, so that run's old layer-0 cleanup
receipt is not proof of a clear desktop; the actual screenshot and review retain
that limitation. Cleanup now checks every visible window layer and never signals
another process.

The Hardened Runtime trial in run `43712978391` then passed on both architectures:
ordinary nonmodal native startup with no microphone dialog, all fourteen
process-only PCM cases, unchanged game/runtime bytes and clean process/window
shutdown. Actual signatures have flags `0x10002` and exactly `allow-jit=true` plus
`disable-library-validation=true`; no recording entitlement is present. The
actual desktop/startup/cleanup images and signature receipts were independently
inspected under `build/ci-hardened-pcm-macos-{arm,intel}/mac-entitlement-trial/`.
This validates the signing policy; final shared-builder installation and complete
native control checks remain separate gates. The earlier experiments and primary
references are preserved in `docs/MAC_SIGNING_TRIAL.md`. All native
audio capture filters contain only the exact launched game PID, with microphone
capture disabled and no system-mix fallback. Missing access, a prompt, incomplete
PCM, or failed cleanup remains a failed/unverified result. Earlier named-mixer and
ad-hoc experiments remain historical evidence, not shipped workarounds.

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
`build/installed-user-audit-d5499672/`, `build/installed-physical-close-d5499672.log`, and
`build/package-install-d5499672.log`. Four actual launcher frames were inspected:
title, right movement, paused equipment and the absent window after Alt+F4.
That installed candidate matched the checked
game JAR SHA-256
`d5499672bb8cd4dd0708f5701d89cbf7dc81f4c3f480aa728c456c5b74bb30af`.

## Native Linux CI artifact review

Both native Linux jobs in run `43708730152` passed actual per-user installation,
private Java 25.0.5 execution with deliberately invalid global Java variables,
upgrade replacement, desktop metadata validation, removal with settings retained,
and both 280-case source/bundled automatic audits. The x86-64 and ARM64 artifacts
were downloaded and independently inspected locally. Their four supplied SHA-256
files matched; runtime executables had the correct ELF machine type; Debian
architecture/dependency/launcher metadata was correct; portable and Debian app
trees were byte-identical (109 x86-64 / 108 ARM64 entries); all 2,107 embedded
asset files matched the unchanged source assets. Both JARs were the audited
`d5499672` build. Complete receipts and native job logs are under
`build/ci-final-linux-{x64,arm64}/package-review.json` and `job.log`.
These are candidate CI artifacts, not a claim that a public release was published.

The same artifact review passed for final JAR `88283267` on both Linux
architectures in run `43712421975`: four supplied checksums, correct ELF/Debian
architectures, matching portable/Debian app trees, all 2,107 original asset files,
and actual native install/upgrade/uninstall with private Java 25 and saved
settings retained. Evidence is under
`build/ci-final-8828-linux-{x64,arm64}/package-review.json` and `job.log`.

The subsequent footer build `0d3d50e7` also passed local package
install/upgrade/uninstall and actual offline launcher play/physical Alt+F4;
`build/installed-user-audit-0d3d50e7/` records that build and its full-size screenshot
review. Prior installed `d5499672` evidence is preserved separately under
`build/installed-user-audit-d5499672/`.

The final initialization-order build `88283267` passed the same real package
installation, upgrade and removal checks, then the actual installed
`gtk-launch org.emberwood.kotlin` entry with internet sockets denied and invalid
global Java settings. Start, D, Space, Escape and physical Alt+F4 were exercised;
the title, right movement, paused menu and absent window were inspected at full
size. The Space still is after landing, so this smoke does not replace the
exhaustive jump audit. Exact JAR/frame hashes and close receipts are preserved in
`build/installed-user-audit-88283267/`; the installer log is
`build/install-88283267.log`. The installed JAR matches
`88283267eefaf417da4965a1248c1b70b9188effd71f6ee3f69cc2c1911e5bc1`.

The same final JAR was launched from the actual **Play Emberwood Kotlin** task in
a fresh isolated Zed 1.28.1 profile. The task picker loaded the checked-in
configuration, the private Java runtime opened the game, and physical
Start/D/Space/Escape/Alt+F4 exercised movement, jumping, pause and process exit.
The terminal hid after success as configured. Seven original screens were
inspected; hashes, runtime identity and review are in
`build/zed-audit-88283267/`. All test-owned processes were cleaned up.

Refactoring packaging to the shared runtime helper was also exercised with a real
Linux rebuild and isolated install/upgrade/uninstall. The complete linked-runtime
tree digest remained
`a72adb7142f5e7dcaefa535143074f9a8848f42f83ddc4f1b138083235f8c8a4`, and the game JAR
remained `88283267`. Receipts are `build/package-shared-{before,after}.json` and
`build/install-shared-88283267.log`; the installed user app was refreshed.
