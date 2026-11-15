# Intel package investigation

These are retained negative or incomplete checks, not release approvals. The
production JAR is `7d9668edebc108b5d3f033f20180874942cea852676f1199a3210dd24e2f6582`.
The original signed Intel application has remained identical across the runs
below: all 119 file/directory entries, file bytes, modes, symlink targets, launcher,
configuration, assets and signature contents match the reviewed baseline.
Only disposable diagnostic copies receive audit classes or rendering options;
the real-game movement probe launches the original `emberwood.MainKt` application.

The common app-tree digest is
`0637aa04f2a2723b24bc64146637b1e34e5fbda10f7eabf80adb384f1abb5d6a`.
The tree algorithm is `tools/package_integrity.py::tree_digest`, rooted at
`Emberwood Kotlin.app`; entry modes are compared separately. The whole runtime
root `Contents/runtime` hashes to
`a93bf5bdeaaaf2272346e6a8dd16a5a9aae5f43054960258a1d9ff10ea60f623`.
The nested Java-home root `Contents/runtime/Contents/Home` hashes to
`dec700c1ef535eb1cedc1a7197d959ccc390c16f51a43594aad209dd24d6520a`.
Different roots explain these two runtime digests; they do not indicate changed
runtime files.

All artifact directories below are relative to `build/`. Their original archives
and sidecars are retained. `package-review.json` and
`cross-run-package-review.json` record exact package provenance; the two real-game
probes use the latter receipt. Package identity does not turn a failed command or
incomplete shutdown check into a pass.

| Workflow | Observed result | Artifact directory |
| --- | --- | --- |
| [43725299181](https://github.com/samsaw123456/emberwood-kt/actions/runs/43725299181) | Intel source profile failed one scene at 40.729 completed Java paints/s against the unchanged minimum of 45; later control/audio stages skipped. Installation and actual source launch/quit passed separately. | `ci-native-final-7d9668ed-macos-intel` |
| [43726910417](https://github.com/samsaw123456/emberwood-kt/actions/runs/43726910417) | Both profiles passed; the full inventory retained one Left observation failure. Later audio skipped. This is the retained launch/profile package baseline. | `ci-native-repeat-7d9668ed-macos-intel` |
| [43732405531](https://github.com/samsaw123456/emberwood-kt/actions/runs/43732405531) | All 280 rows ran; Left failed the capture-overrun guard. No full inventory pass. | `ci-native-panel-marker-7d9668ed-macos-intel` |
| [43736264766](https://github.com/samsaw123456/emberwood-kt/actions/runs/43736264766) | Six focused rows ran; Left failed. Independent native stream and snapshot evidence both retained an old scene while Java paint callbacks advanced. This does not establish screenshot-only caching as the cause. | `ci-capture-trace-7d9668ed-macos-intel` |
| [43738815451](https://github.com/samsaw123456/emberwood-kt/actions/runs/43738815451) | Default buffering: six rows, one Left failure. Applied no-double-buffer option: five failed rows, then lifecycle capture failed before row six. Both actually used Metal; manager buffering changed true to false. The driver correctly refused the planned default-repeat after incomplete evidence. | `ci-buffer-comparison-7d9668ed-macos-intel` |
| [43740408807](https://github.com/samsaw123456/emberwood-kt/actions/runs/43740408807) | Scheduled repaint was executed in 25 distinct capture requests; all six rows ran and Left still failed. Metal and default buffering remained in use. | `ci-scheduled-7d9668ed-macos-intel` |
| [43740419423](https://github.com/samsaw123456/emberwood-kt/actions/runs/43740419423) | Original game failed the initial visible-window lookup before input. Owned-process SIGTERM cleanup passed; no movement or physical Command-Q proof. | `ci-main-movement-7d9668ed-macos-intel` |
| [43741471213](https://github.com/samsaw123456/emberwood-kt/actions/runs/43741471213) | Actual `CGLGraphicsConfig`, default buffering and synchronous painting were confirmed, with only `metal=false` and `opengl=true` in the diagnostic copy. Six rows ran; Left still failed. Native stream and no-signal cleanup receipts were retained. | `ci-opengl-7d9668ed-macos-intel` |
| [43741464146](https://github.com/samsaw123456/emberwood-kt/actions/runs/43741464146) | Original game reached its prompt-free title and completed A. During the Left check, the accessibility focused-window query returned `-25204`; the separate input worker still released the key within 357 ms. Owned-process SIGTERM cleanup passed, which does not prove physical Command-Q. | `ci-main-ready-7d9668ed-macos-intel` |

The focused control artifacts also retain `packaging-driver-review.json` under
`build/controls-capture-native-app/` (or the comparison directory), including
executed graphics/stage receipts, stream hashes and inspected cleanup desktops.
Native streams stop at the first observed lifecycle resize; their final canvas
may already contain resized content before that observation. This tail is not
independent fixed-geometry presentation proof.

The later successful [process-only audio check](https://github.com/samsaw123456/emberwood-kt/actions/runs/43732427910)
uses the same original app tree and has its own fourteen-case/84-WAV independent
review. It does not close the missing Intel control evidence. No alternative
rendering setting from these experiments has been adopted in production. No Intel
archive has been selected for publication from these negative runs. See
[current packaging](../PACKAGING.md), [controls](../CONTROLS.md) and
[performance](../PERFORMANCE.md) for the remaining gates and evidence limits.
