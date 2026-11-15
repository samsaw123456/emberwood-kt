# Emberwood Kotlin 0.1.0 verification record

Publication is pending the complete macOS verification and rendered review.
The four Linux downloads below are staged locally. No tag or release has been
published. Earlier packages are historical evidence, not candidates for this release.

The game JAR is
`ae9686cb8387d5c9f61f4a6cb73d4f9a99803fe6e93e2ce519d495d59b9bdb8c`.
Its 67 Kotlin/JVM tests pass. The current installer and diagnostic suite passes
206 tests locally, with two Mac SDK tests deferred to the native Mac jobs.
Ruff, ShellCheck, Kotlin formatting and the build pass. All 2,107 migrated asset
files match the original Emberwood v1.3.1 artwork byte for byte.

## Downloads and identity

The four Linux files come unchanged from
[run 43747641897](https://github.com/samsaw123456/emberwood-kt/actions/runs/43747641897).
Their complete app contents match the source/bundled control and performance
packages from [run 43747640143](https://github.com/samsaw123456/emberwood-kt/actions/runs/43747640143),
including file bytes, symlink targets and modes. The portable and Debian app
contents also match for each architecture.

```text
c0d66073668d8b2ae64c77a2d16090486df87102c0c48795f7b4f3a6288a8046  emberwood-kotlin-0.1.0-linux-aarch64.tar.gz
f1074c6bf66f74a89b346aaa83f6a28d8369db9cc0fb78310ec86f0c424ec99f  emberwood-kotlin-0.1.0-linux-x86_64.tar.gz
32fd8cc88fba33e957cde8073fb0104e0c487abe8b0bbcab275af6c9052b51ab  emberwood-kotlin_0.1.0_amd64.deb
222235857a5c08785330648b5b4ab6ac9a05fbf12dcca9ae996a1a9408b73939  emberwood-kotlin_0.1.0_arm64.deb
```

| Content | Tree SHA-256 |
| --- | --- |
| Linux x86-64 complete app | `15be72f883ae1587d5843b91f0a15da9dda1274f636b2efdf38dad8bbec7e17f` |
| Linux ARM64 complete app | `63be67ccf903faec6c0f7825ff19d1a1b2fd7766a68c2e1a1eea8ae87f9dd8f5` |
| Linux x86-64 runtime | `a72adb7142f5e7dcaefa535143074f9a8848f42f83ddc4f1b138083235f8c8a4` |
| Linux ARM64 runtime | `22de4a0d41be8e7324cb1c82002832f726a575c47590331360bc6ef373dc4a8e` |

Tree fingerprints use [package_integrity.py](../tools/package_integrity.py):
relative paths, file bytes and symlink targets. Modes are compared separately.
Exact app identity connects the independent tests; an older runnable JAR's pass
is never silently transferred to a changed game.

## Observed results

- Linux source and bundled apps on both architectures complete 280 physical
  control cases each. Every one of the 1,214 referenced frames per inventory has
  been visually inspected. The final aggregation verifies disjoint review
  partitions and original hashes. Actual PCM and physical close are separate checks.
- The current game completes a real native keyboard campaign through all twenty
  levels, six guardians and sixty acorns: 08:19, one natural failure/retry,
  201/378 gems and all twenty hidden fireflies. All 55 retained frames were
  inspected. This is progression evidence, not a substitute for the control audit.
- All four Linux source/bundled audio routes pass fourteen physical cases each:
  56 cases and 336 game-only WAVs. Ordinary Main launch, movement, jumping,
  landing, pause and physical Alt+F4 also pass on each route. These recordings
  verify virtual output PCM; they do not claim a physical speaker listening test.
- Linux low-resource profiles pass all 22 measurement windows and a 180-second
  soak on each architecture, with 128 MiB heap and two processors. Soak paint
  throughput is 62.071/s on x86-64 and 62.184/s on ARM64. Java paint completion is
  distinct from native display presentation; measurements and limits are in
  [PERFORMANCE.md](PERFORMANCE.md).
- The installed user launcher runs the current Linux x86-64 app while IPv4/IPv6
  sockets are denied to its child process and invalid global Java overrides are
  present. Actual Zed task selection also launches the current game. Movement,
  jumping, pause and physical close were inspected in nine installed-app and
  eleven Zed originals. The original Emberwood launchers are preserved.

The unchanged dependency helper also has
[clean Ubuntu 24.04 recovery evidence on both architectures](https://github.com/samsaw123456/emberwood-kt/actions/runs/43720498665).
An isolated container started without seven required library names or package
indexes, refused downloads in offline mode, then installed 21 required/dependency
packages with zero upgrades or removals. Bundled fonts loaded, and healthy
offline reuse left apt history unchanged. Host libraries were not altered.

## macOS qualification in progress

The current ordinary Main app passes bounded physical movement, release,
product-named app menus and Command-Q on Intel and Apple Silicon in
[run 43750035990](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750035990).
All retained frames were inspected: 77 Intel and 64 ARM originals, using labeled
contact sheets and selected full-size originals. Exact review scales, timing and
limits are retained locally. The native identity probe confirms that only the
unused Services menu is detached and other menu items are preserved.

The complete current Mac build, installer, offline source launch, control, PCM,
performance and startup-error matrix is
[run 43750771895](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750771895).
It remains pending here until its results and rendered evidence are reviewed.
No Mac release ZIP is selected on the basis of the focused Main run alone.

See [controls](CONTROLS.md), [audio](AUDIO.md), [performance](PERFORMANCE.md) and
[packaging](PACKAGING.md) for the maintained acceptance details and historical
failures. Mac builds use ad-hoc Hardened Runtime signatures, not Apple
notarization. Native execution is tested on macOS 15; the bundle's declared
minimum of macOS 12 is not a claim that version 12 was tested. No finite test set
establishes absence of every bug. Raw images, PCM and logs are retained locally
under `build/`; workflow artifacts and this record preserve provenance.
