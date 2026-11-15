# Native packages and toolchains

The current candidate JAR is
`ae9686cb8387d5c9f61f4a6cb73d4f9a99803fe6e93e2ce519d495d59b9bdb8c`.
Its required final native reviews remain in progress. The prior `375ae227`
candidate [failed macOS startup on both architectures](https://github.com/samsaw123456/emberwood-kt/actions/runs/43745233648)
and was not shipped. The `7d9668ed` evidence and staged archives below are retained
baseline results, not verification of the current candidate. Publication remains
pending a passing build and the required native reviews.

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

The shared Mac builder sets `apple.awt.application.name=Emberwood Kotlin` for
the native About, Hide and Quit labels. The pinned Java launcher says to
“use it if set”; it otherwise substitutes the main class name.
[OpenJDK 25 launcher source](https://github.com/openjdk/jdk25u/blob/jdk-25.0.5%2B8/src/java.base/macosx/native/libjli/java_md_macosx.m#L778-L808)
An explicit `-Xdock:name` would take precedence, but this recipe adds no competing
name option. Inner quotes preserve the space through `jpackage`'s option parser;
the builder checks the generated configuration before signing. A real pinned
`jpackage` fixture verified the complete property and executed its native launcher.
Source and release recipe fixtures pass. The actual packaged application then
passed the physical menu-label check on both Mac architectures in
[run 43750035990](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750035990).
About, Hide and Quit display Emberwood Kotlin; Escape closes the menu. After
physical Command-Q, the owned PID and window are gone, modifiers are released,
no cleanup signal is sent and the `open -W` launcher exits zero. This route does
not retain a numeric JVM exit status. The targeted check does not replace the
final complete inventory.

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
system installer. The portable installer, direct app launcher and source GUI
launcher also share `tools/ensure_linux_desktop.sh`. It checks the actual AWT,
font and audio libraries with the private runtime's library paths, including
Fontconfig, which Java loads dynamically. Healthy desktops install nothing.
When a known library is missing and `apt-get` is available, only its required
packages are installed using normal root, sudo or PolicyKit authorization, then
the libraries are checked again. Empty package indexes are refreshed first so
the current distribution selects the correct ALSA ABI; no operating-system
upgrade is performed. Other package managers and unknown dependencies
receive named recovery instructions; they are not claimed to install automatically.
`--offline` never downloads packages. Help, version, build-only, invalid argument
and headless source launches keep their existing behavior without dependency
installation. Failed dependency recovery leaves a prior installed app intact.
Mac bundles declare macOS 12 as their minimum and require the matching CPU
architecture; native CI verification currently runs on macOS 15, not every earlier
version.
Ad-hoc signing verifies package integrity but does not replace Apple signing or
notarization; no signing identity or Apple account is used by this repository.

The CI matrix builds and tests on Linux x86-64/ARM64 and macOS Intel/Apple Silicon.
Linux runs the full physical-input inventory through both the source JAR and the
packaged runtime. Mac checks actual installation and the cached source launcher,
profiles both native apps, then runs the full control inventory and fourteen
sound-output cases through the packaged native app. The source and packaged Mac
JAR/runtime identities are compared separately; source launcher smoke tests are
not a second complete control audit. Every job retains its evidence. A configured
matrix is not proof of a successful run: consult the actual workflow results and
the project's audit records before claiming a platform verified.

## Installer and dependency checks

The source bootstrap was exercised from an empty private cache: official pinned
JDK download, checksum verification, extraction, Java 25 validation and offline
reuse. Global Java remains unchanged. Installer fixtures cover first install,
replacement, removal, difficult shell/desktop paths, unmarked-directory refusal,
offline/invalid JDK errors, tampered checksums and interrupted-install rollback.
Twenty dependency/source-dispatch fixtures cover healthy, missing, unsupported,
offline and failed-recovery paths without changing host libraries. Bash syntax,
ShellCheck and Ruff check/format checks pass for the tooling.

Actual private-runtime fault injection reproduced both missing-AWT startup failure
and failure to load the game's bundled fonts without Fontconfig. This led to the
shared Linux preflight. It is also verified by
[clean dependency recovery on both Ubuntu 24.04 architectures](https://github.com/samsaw123456/emberwood-kt/actions/runs/43720498665).
Each disposable official container began with empty package indexes and seven
missing library names. Offline launch refused downloads. Ordinary recovery then
refreshed indexes, selected the correct ALSA ABI and installed 21 required or
transitive packages with zero upgrades or removals. Real Java and the bundled
fonts loaded; healthy offline reuse left apt history unchanged. The app was
read-only, host libraries were untouched and the owned containers were removed.
This headless check does not replace actual desktop testing.

The packaged helper remains exactly
`b4ba5221f51dbf2b60cb7cfa169543171e496d2139509320f2731a4092b017d4`,
so that container proof applies to the current packages. Receipts are under
`build/ci-dependencies-linux-{x64,arm64}/dependency-container/` and
`build/portable-linux-dependency-review/`.

## Current candidate package evidence

The current `ae9686cb` Linux packages from
[run 43747640143](https://github.com/samsaw123456/emberwood-kt/actions/runs/43747640143)
passed source and bundled control inventories on both architectures. All four
inventories have 280 cases and 1,214 referenced frames, with disjoint visual
review journals. The native twenty-level campaign ran on Linux x86-64.
Their complete application entries match the corresponding
[audio and installer run 43747641897](https://github.com/samsaw123456/emberwood-kt/actions/runs/43747641897)
in bytes, symlink targets and modes. That separate run verifies installation,
upgrade/removal, fourteen sound-output cases per route and ordinary Main launch,
movement, jump, pause and physical Alt+F4 on both architectures. The four original
audio-and-installer archives and checksum sidecars are staged unchanged in
`build/release-ae9686cb/assets/`; `build/release-ae9686cb/linux-staging.json`
records the selection. No release has been published. Exact comparisons are in
`build/ci-final-ae9686cb-linux-{x64,arm64}/audio-package-identity.json` and
`package-review.json`. Audio and actual-game review journals remain under
`build/ci-audio-ae9686cb-linux-{x64,arm64}/`.

The installed user's separate app and actual Zed Play task also run this current
JAR. The installed app tree is
`15be72f883ae1587d5843b91f0a15da9dda1274f636b2efdf38dad8bbec7e17f`.
It used its bundled runtime with invalid global Java values and a child-only
rule denying IPv4/IPv6 sockets. Root inspected nine full-size installed-app
originals and eleven full-size Zed originals through movement, jump and pause.
Physical Alt+F4 removed the owned PID and window; these routes do not retain a
numeric JVM exit status. The local reviews are recorded in
`build/installed-user-audit-ae9686cb/review.json` and
`build/zed-audit-ae9686cb/review.json`; the original Emberwood launchers remain.

The current Mac application-name fix changes only the launcher configuration and
its outer signature resources relative to the prior same-JAR bundles. Independent
inspection of all 119 file/symlink entries confirms unchanged game, runtime,
metadata and 2,107 original assets. Both new ordinary-Main checks in
[run 43750035990](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750035990)
passed bounded movement, the physical application menu and Command-Q. The three
menu desktops and final clear desktop were independently inspected per
architecture. A separate post-game native probe confirms that only Services is
removed and all eight sibling identities, actions, targets and shortcuts remain
unchanged. Archive, signature-log and menu review receipts are in
`build/ci-main-name-budget-ae9686cb-macos-{arm,intel}/`. These are targeted checks;
the final source-cache equality, profiles, full controls and audio checks in
[run 43750771895](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750771895)
are still pending independent review.

## Retained Linux baseline package and launcher evidence

The retained Linux baseline game JAR is
`7d9668edebc108b5d3f033f20180874942cea852676f1199a3210dd24e2f6582`.
The four retained Linux baseline archives came unchanged from
[run 43725301448](https://github.com/samsaw123456/emberwood-kt/actions/runs/43725301448).
Both native architectures passed actual per-user installation, bundled Java
25.0.5 execution, desktop registration, replacement and removal while retaining
saved settings. Independent archive inspection verifies all four supplied
checksums, current README/installer/helper, correct ELF and Debian architectures,
and all 2,107 unchanged imported assets. Portable and Debian app trees match in
file contents, symlink targets and modes.

The app trees also match their respective full-control builds from
[run 43725299181](https://github.com/samsaw123456/emberwood-kt/actions/runs/43725299181)
exactly. This ties those historical files to the corresponding source and bundled
280-case inventories. All referenced frames were reviewed. Actual source/bundled
sound and real-main launch, movement, jump, pause and physical Alt+F4 were checked
separately on both architectures. See [controls](CONTROLS.md) and
[audio](AUDIO.md) for coverage and output limits.

Archive and native-install receipts are in
`build/ci-audio-jump-fixed-linux-{x64,arm64}/package-review.json` and
`native-job.log`; cross-run app comparisons are in
`build/ci-final-7d9668ed-linux-{x64,arm64}/cross-run-release-identity.json`.
The retained baseline manifest records each exact archive and origin. Those
archives were not rebuilt or rewritten during selection.

The user's separate **Emberwood Kotlin** app was previously upgraded to the
retained `7d9668ed` baseline JAR at `~/.local/share/emberwood-kotlin/app`.
The original Emberwood launcher remained unchanged. That desktop-registry launch
used invalid global Java variables
and a child-only rule denying internet sockets. Start, held/released movement,
jump/landing, pause and physical Alt+F4 were inspected in all nine original
frames. The process used the installed private runtime; closing removed the
window and process. Evidence is in `build/installed-user-audit-7d9668ed/`.
The actual Zed project task was also loaded and played through movement, jump,
pause and close; see `build/zed-audit-7d9668ed/result.json`.

## Retained Mac baseline package and launcher evidence

Both architectures in [run 43725299181](https://github.com/samsaw123456/emberwood-kt/actions/runs/43725299181)
passed installation, upgrade, removal, native signature validation and actual
cached-source offline launch. Ten original launch, Dock, paused-menu, quit and
cleanup images per architecture were inspected. Both routes had ordinary
nonmodal game windows, readable text and the migrated fox icon. Physical
Command-Q removed the game without a fallback termination signal, with released
modifiers and no remaining dialog. This startup/pause/close check is separate
from the full command inventory and sound-output test.

The original ZIP sidecars, Mach-O architecture, app metadata and unchanged assets
were checked. Each complete signed source-cache app equals its packaged app,
including launcher, configuration, icon, signature and runtime. Runtime entry
bytes, symlink targets and modes also match the previously reviewed runtime.
Receipts are in
`build/ci-native-final-7d9668ed-macos-{arm,intel}/package-review.json`, with
per-route `packaging-review.json` and `REVIEW.md` in the launch directories.

Apple Silicon completed both 180-second native performance profiles, all 280
physical control cases with all 1,214 referenced frames reviewed, and fourteen
actual process-only PCM cases. Its source control coverage is explicitly shared
proof from the identical packaged app, not a second physical inventory.

The first Intel source profile failed one scene at 40.729 frames/s against the
unchanged minimum of 45, and later controls/audio were skipped.
[Repeat 43726910417](https://github.com/samsaw123456/emberwood-kt/actions/runs/43726910417)
passed both profiles but retained one Left-control observation failure; audio
was again skipped. All 119 original app entries match the first current Intel
package exactly, including signature, configuration, symlink targets and modes.
Both launch/quit routes passed again and all ten new original frames were
inspected. These identity and launch checks do not turn the failed control run
into a pass. The separate [audio run 43732427910](https://github.com/samsaw123456/emberwood-kt/actions/runs/43732427910)
then passed all fourteen physical cases, with all 84 WAVs and cleanup frames
independently reviewed. Its retained original ZIP matches all 119 app entries
exactly. A complete passing control inventory and rendered review remain required
before selecting the Intel archive. Repeat launch/profile receipts are under
`build/ci-native-repeat-7d9668ed-macos-intel/`; current PCM and app comparisons are
under `build/ci-audio-current-7d9668ed-macos-intel/`.
[Performance](PERFORMANCE.md) and [audio](AUDIO.md) retain measured results and
limits, including historical audio gaps whose cause remains unexplained.
The [Intel package investigation](history/packaging-investigation.md) preserves
subsequent failed control, buffering, rendering and real-game diagnostics with
their unchanged application identities. Those checks have not closed the Intel
release gate.

The shared signing policy followed a real two-architecture isolated trial:
[run 43712978391](https://github.com/samsaw123456/emberwood-kt/actions/runs/43712978391)
verified nonmodal startup, all fourteen sound cases and clean shutdown with
unchanged game/runtime bytes. Earlier ordinary ad-hoc signatures prompted for
microphone access on Intel; no access was granted. Those failed experiments and
primary references remain in [the signing investigation](MAC_SIGNING_TRIAL.md).
The native signature is checked after building, installing and upgrading.

Java's bundle-version parser requires a positive first internal component:
release `0.1.0` therefore uses `CFBundleVersion=1.1.0` while displaying `0.1.0`.
The builder passes `adventure-games` to `jpackage`, which adds the category prefix;
native installation checks `public.app-category.adventure-games`. Signed
management resources live under `Contents/Resources`, and `ditto` preserves
bundles during installation. Fixtures and actual native package tests check
these rules.

The [release verification record](RELEASE-0.1.0.md) will list final archive hashes
and workflow origins when the remaining gates close. Older builds remain
historical evidence. No Apple notarization or universal bug-free claim is
implied by these bounded tests.
