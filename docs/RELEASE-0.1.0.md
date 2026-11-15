# Emberwood Kotlin 0.1.0 verification record

These six archives are a retained historical baseline, **not release candidates**.
A later input-order regression found a real release-then-press bug within one
simulation step. Its correction requires fresh game packages and final control,
campaign, performance and audio verification. This record will be replaced with
the new package identities and observed results before publication; a dispatched
workflow is not a passing test.

## Retained baseline SHA-256 values

```text
c096a1ace7b8a59b3d3fa2ff01c2f0007eddb6898ea55a227e9dd697793d75f6  emberwood-kotlin-0.1.0-linux-aarch64.tar.gz
c1813f2dd96678ed1ad3c73dd8ed229673f901e7d28eb2b28103cc87ba1a77b9  emberwood-kotlin-0.1.0-linux-x86_64.tar.gz
72549db75488b1f4060d4b8e8ba80ade55ad7f769c15148a9f4e532700c1226a  emberwood-kotlin-0.1.0-macos-aarch64.zip
251bf7b922c7bb576964d55d5689d791462bc52b724466bdd7c46e3b97f8b621  emberwood-kotlin-0.1.0-macos-x86_64.zip
f196ac11cdae0c20731ba9fb7d0489a97c1299e929bb8938bdc0ed0b7e6a10f1  emberwood-kotlin_0.1.0_amd64.deb
363d733349f3ecc4ddc6a82025aa5c41701161a1bd30201f28704b85b6347f25  emberwood-kotlin_0.1.0_arm64.deb
```

The four Linux files are unchanged artifacts from
[run 43719750356](https://github.com/samsaw123456/emberwood-kt/actions/runs/43719750356)
at commit `2564e3cb8f61015fb3cfd081d80f3d2da91cf28b`.
The Mac apps originate from
[run 43715704373](https://github.com/samsaw123456/emberwood-kt/actions/runs/43715704373)
at `8f0b905`. Their ZIP copies refresh only the top-level README. Every other
entry's uncompressed bytes, symlink target, mode, timestamps, comments, extra
fields and recorded platform/version attributes match the original. ZIP storage
may differ: compression, offsets and 107 data-descriptor flags per archive.
The extracted apps and their signature contents are unchanged.

## Identity across the checks

All six downloads contain the same game JAR:
`88283267eefaf417da4965a1248c1b70b9188effd71f6ee3f69cc2c1911e5bc1`.
All 2,107 imported asset files match the original migrated assets. The dependency
recovery change affects the Linux launch/install scripts; it does not change the
game or runtime used by the completed control and performance audits.

| Content | Tree SHA-256 |
| --- | --- |
| Linux x86-64 runtime | `a72adb7142f5e7dcaefa535143074f9a8848f42f83ddc4f1b138083235f8c8a4` |
| Linux ARM64 runtime | `22de4a0d41be8e7324cb1c82002832f726a575c47590331360bc6ef373dc4a8e` |
| Apple Silicon complete signed app | `cfa85fd9f850eb028e15734907c84d3db8f3970a6425b11fbe8a4cbbeff2022b` |
| Intel Mac complete signed app | `2df70a9f30706428f1f3ae86b4e315a17ad219c679bc21fe5c7cf5446dd4d4ab` |

Tree fingerprints use [package_integrity.py](../tools/package_integrity.py):
relative paths, file contents and symlink targets; modes were compared separately.
The table names each hash root. Native Mac audit `original_runtime_sha256` covers
`Emberwood Kotlin.app/Contents/runtime`, including its outer bundle metadata;
older package-review `runtime_sha256` covers only `Contents/runtime/Contents/Home`.
Those different roots produce different digests even for the same unchanged app.
The complete 119-entry app comparison is the decisive cross-run identity check.
Each Linux portable app matches its Debian package app tree, including modes.
Every runtime entry also matches its architecture's full-control baseline in
[run 43712421975](https://github.com/samsaw123456/emberwood-kt/actions/runs/43712421975).
On both Macs, the complete packaged app tree matches the cached source app used
for the actual offline source launch and performance profile.

The later [uninstrumented audio run 43721920267](https://github.com/samsaw123456/emberwood-kt/actions/runs/43721920267)
retains original ZIPs whose 119 app entries per architecture match these same
apps exactly, including configuration, signature contents, modes and symlink
targets. Its before/after original-app fingerprints are also unchanged.

The latest Intel native control retry is
[run 43721802571](https://github.com/samsaw123456/emberwood-kt/actions/runs/43721802571).
Its retained original ZIP matches all 119 Intel app entries above, including
modes, symlink targets, configuration and signature contents; the before/after
app fingerprints are unchanged. That identity proof does not turn its failed
control result into a pass: it completed 280 cases with three failed observations.
A successful corrected audit and complete rendered review remain required.

## Verified scope and limits

Linux x86-64 and ARM64 have complete 280-case source and bundled control reviews.
The real 20-level native keyboard campaign ran on Linux x86-64. The final installer
revision passed install/upgrade/removal and saved-settings checks. Its four source/bundled routes
also passed actual Main launch, movement, jump, pause and physical Alt+F4 with clean
Java exit; all 36 full-size Main frames were inspected. All 56 sound cases and
336 WAVs were reviewed separately.

[Clean dependency recovery run 43720498665](https://github.com/samsaw123456/emberwood-kt/actions/runs/43720498665)
passed on both Ubuntu 24.04 architectures. An official disposable container began
without seven required library names or package indexes, refused downloads in
offline mode, then refreshed indexes and installed 21 required/dependency packages
with zero upgrades or removals. The real bundled fonts loaded and healthy offline
reuse left apt history unchanged. The app was read-only; host libraries were not
changed. This container proof supplements the separate actual desktop checks.

Both Mac installers, native app icons, offline cached source launch, physical
Command-Q and source/packaged 180-second performance profiles passed. Apple
Silicon's complete native control inventory passed. The final uninstrumented Mac
audio repeat passed all 28 physical cases and 168 independently reviewed WAVs on
both architectures, with no interior exact-zero span of at least 2 ms. Capture
timestamp discrepancies are recorded separately from the PCM samples.
The earlier Intel control run rejected a test-only presentation marker. The next
full run completed but retained three movement/jump observation failures and a
separate shutdown-monitor error. Their resolution and complete rendered review
are the remaining control gate.

[The Mac audio trace repeat](https://github.com/samsaw123456/emberwood-kt/actions/runs/43719992137)
passed all 28 cases and 168 WAVs with the unchanged production JAR/runtime. It adds
a test-only recording provider/property to a disposable audit app, so it is
explicitly instrumented evidence. Earlier Mac gaps did not recur in that trace or
the subsequent uninstrumented run, but their cause remains unresolved. Three final
Linux ARM mute-edge recordings contain a documented 10.667 ms zero interval
followed by a 1.56–1.63 ms residual tail before
silence; reference, restored and long cues have no such gaps. No claim of flawless
audio or absence of all bugs follows from these measurements.

See [controls](CONTROLS.md), [audio](AUDIO.md), [performance](PERFORMANCE.md) and
[packaging](PACKAGING.md) for the maintained acceptance details. Mac builds use
ad-hoc Hardened Runtime signatures, not Apple notarization; native Mac execution
was verified on macOS 15, while the bundle declares version 12 as its minimum.
Large raw images, PCM, logs and before/after manifests are retained locally under
`build/`; this tracked record preserves the release identities and workflow links.
