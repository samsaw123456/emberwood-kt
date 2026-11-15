# Verification record

This is a separate port of Emberwood v1.3.1, original commit
`7146ac838c0db21afe9406ea4546cb094aa9721f`. The Godot checkout is unchanged.
Verification distinguishes simulation tests, physical input in a native window,
inspected rendered output, actual audio capture and installed-package testing.
Fixtures used to reach a menu or scene do not count as traversing a level.

## Reproduce

```sh
export JAVA_HOME="$(tools/bootstrap.sh)"
./gradlew check fatJar
python3 tools/check_assets.py
python3 -m unittest discover -s tools -p 'test_install.py' -v
./gradlew nativeAudit
java --enable-native-access=ALL-UNNAMED -Xmx256m \
  -cp build/libs/emberwood-kotlin.jar:build/classes/kotlin/test \
  emberwood.CampaignAudit 20
java --enable-native-access=ALL-UNNAMED -Xmx128m -XX:ActiveProcessorCount=2 \
  -cp build/libs/emberwood-kotlin.jar:build/classes/kotlin/test \
  emberwood.PerformanceAudit
python3 tools/package_app.py --skip-build
python3 tools/audit_package.py
```

Use a real desktop or an isolated Xvfb display for native tests. macOS needs a
logged-in graphical session and permission for synthesized keyboard input and
screen capture. Linux audits run the source and packaged runtime directly. macOS audits use
`python3 tools/mac_app_profile.py --audit controls` to exercise an isolated copy
through LaunchServices. `--audit audio` captures only that game process, and
`--app PATH` selects the actual cached source app when required. The shared
signing policy and exact game/runtime hashes are retained in both paths. Inspect its results; a workflow definition is not evidence
that a platform passed.

For actual Linux audio output, `tools/audio_audit.py` requires PipeWire and Python
Xlib. Give it the application's launch command after `--`. It links only that
process's playback ports to an isolated recorder, presses M through X11, and
compares audible, muted and restored PCM. It never records the microphone or
desktop mix. Java audio flags alone do not satisfy this check.

## Current evidence

The current candidate JAR is
`375ae22702bfc62711180138abc3b01ef309339cd636cdfa0d170b8b04e0c0fd`.
It removes the unused macOS Services submenu through public AppKit APIs before
showing the window. Formatting, checks and all **67 Kotlin/JVM tests** pass,
including seven menu-identity/native-callback regressions. Native run43745233648
fails before input on both Mac architectures: exact parent-item removal returns,
but the post-clear `servicesMenu` getter remains nonnull. Both audits execute
zero cases; the subsequent strict menu probe is skipped. Owned cleanup leaves
no game window or modal, without signals. The Intel cleanup original was
inspected at full size; evidence is
`build/ci-controls-menu-candidate-375ae227-macos-intel/build/controls-capture-native-app/review/native-review.json`.
An observation-only native probe will distinguish retained versus recreated
registration and actual menu attachment. The candidate is not accepted as a fix;
first-arrow, menu and final-build validation remain open.
The current full tools suite passes **188 Python tests** (two macOS SDK tests
skipped on Linux); Ruff and formatting pass for all 57 Python files.
An isolated Linux candidate regression also passed six physical cases with exit 0:
A/Left, D/Right, Return and lifecycle. All 25 referenced frames plus startup were
inspected, including the original 800×600 resized image. Exact evidence:
`build/audit-menu-candidate-375ae227-linux/review/native-review.json`.
This limited check does not replace the candidate's complete inventory.

The retained audit baseline below is
`7d9668edebc108b5d3f033f20180874942cea852676f1199a3210dd24e2f6582`.
It fixes the reproduced same-step jump release/re-press defect. Formatting,
checks and its **60 Kotlin/JVM tests** passed; the three failing pre-fix regressions
and green repeat remain in `build/regressions/jump-order/`. The full tools suite
at that earlier `f095925` checkpoint ran 181 Python tests successfully
(two macOS SDK tests skipped on Linux). Ruff checks and all 55 file-format
checks, ShellCheck and the 2,107-asset integrity
check pass. The actual Mac SDK checks run separately on their native hosts, including the
new stream-buffer/PNG diagnostic fixture explicitly included in CI.
The retained platform passes below apply to that baseline, not automatically to
the new menu candidate.

- Linux x64 source and bundled controls: **280/280 passed per runtime** with
  exit 0, all 1,214 referenced frames independently inspected, and exact disjoint
  hashes validated. See `build/audit-{source,packaged}-7d9668ed-final/REVIEW.md`
  and `controls-reviewed.tsv`.
- Actual Linux audio and main-app lifecycle: **passed on both architectures**
  in CI43725301448. All 56 physical audio cases, 336 analyzed WAVs and 36 original
  main-app frames were independently reviewed. Each source/bundled route starts,
  moves, jumps, pauses and closes through physical Alt+F4. Evidence:
  `build/ci-audio-jump-fixed-linux-{x64,arm64}/build/audio-linux/{source,packaged}/`,
  with PCM and `game-smoke/independent-review/` journals. Playback is captured
  from a private game-only virtual output; no speaker-hardware claim is made.
  One ARM bundled mute-cutoff residual is preserved in AUDIO.md.
- Complete native campaign: **all 20 levels passed** in CI43725299181 at
  commit `9533e5c5cc1bad10ed119aab7edb2549d5f3cb7a`, with the exact JAR hash
  retained. All 55 original frames were inspected: entries, completions, six
  guardian before/defeated pairs, title, retry and ending. Actual OS input
  collected 60 acorns, all 20 fireflies and 201/378 gems; the ending shows 08:19
  and one real fall/retry. The CI play command succeeded under `-e -o pipefail`;
  no separate per-PID numeric exit file was emitted. Full provenance and frame
  hashes: `build/ci-campaign-7d9668ed/campaign-native/review/native-review.json`.
- Installed Linux offline launch: **passed** with invalid global Java, blocked
  internet sockets, actual desktop registry launch and physical Alt+F4.
  All nine originals were reviewed in `build/installed-user-audit-7d9668ed/`.
- Zed task: **passed through the actual task picker**, followed by Start,
  movement/release, jump/landing, pause and physical close. All eleven full-size
  frames and exact process/JAR identity were inspected. Evidence:
  `build/zed-audit-7d9668ed/result.json`.
- Missing output: **passed through actual provider failure**. Physical M
  hold/release/re-press in all six states consistently retains unavailable.
  All 19 frames were inspected; seven filtered cases and cleanup exit 0.
  Evidence: `build/audit-source-7d9668ed-missing-audio-footer/REVIEW.md`.
- Linux ARM source/bundled: **280/280 fully passed per runtime**, all 1,214
  referenced frames independently inspected, disjoint journal hashes verified,
  matching-build actual audio and physical close passed. Complete tables:
  `build/ci-final-7d9668ed-linux-arm64/build/{audit,audit-packaged}/controls-reviewed.tsv`.
  Both native commands and their CI job succeeded; no separate per-PID numeric
  exit file was emitted.
- macOS ARM native controls: **280/280 fully passed**, all 1,214 referenced
  frames independently inspected and every disjoint journal/hash validated.
  Actual fourteen-case PCM, physical Command-Q, both ordinary native launch
  routes and both 180-second performance routes pass. The full cached source
  and packaged app trees are identical, including runtime/configuration/signing.
  Source controls therefore use explicitly labelled shared proof from the
  bundle's physical inventory. Complete receipts:
  `build/ci-native-final-7d9668ed-macos-arm/build/controls-native-app/REVIEW.md`.
- Intel's first source performance run failed one boss window at 40.729 Java
  paints/second versus a 45 paints/second budget, so controls/audio were skipped.
  These counters do not measure native presentation FPS. That failed evidence
  remains intact. The separate diagnostic repeat passed both performance
  routes and ran all 280 controls: 279 assertions passed, while Left failed its
  strict release/braking guard after 21 stale-nonce captures extended the hold
  to 3.31 seconds and the fox reached the world boundary. All four failure
  originals were inspected; the wall stop is not release proof. That run skipped
  audio; complete Intel rendered control review remains pending. Evidence:
  `build/ci-native-repeat-7d9668ed-macos-intel/build/controls-native-app/review/native-left-failure-review.json`.
- The panel-marker Intel repeat, run 43732405531, also ran all 280 cases
  with only Left failing the strict release/braking guard. Its fifteen rejected
  snapshots retain the old scene, not just the nonce: the first/latest rejected
  PNGs are byte-identical with the fox at its start, before the accepted frame
  jumps to the world boundary at 00:04. The physical hold lasted 3.377 seconds.
  All six failure/diagnostic originals were inspected. The failure remains at
  `build/ci-native-panel-marker-7d9668ed-macos-intel/build/controls-native-app/review/native-left-failure-review.json`.
- The six-case Intel diagnostic, run 43736264766, reproduced the Left failure.
  Both native snapshots and the independent own-window stream retain the same
  old surface while Java reaches 140 fresh-nonce drawing callbacks before the stream
  presents it, about 3.06 seconds later. Those callbacks precede Swing's final
  buffer publication. This excludes a marker-only error and
  an isolated snapshot-manager cache explanation; it does not yet identify the
  native publication/compositor/capture cause. All 23 referenced frames, startup and
  both rejected originals were inspected. Collection and cleanup passed
  separately from the command failure: 719 ordered Java paint records and 458
  stream records with 42 retained images, without dropped/truncated data.
  Evidence: `build/ci-capture-trace-7d9668ed-macos-intel/build/controls-capture-native-app/review/native-java-paint-review.json`.
  The subsequent same-runner buffering comparison is recorded below;
  no game change or full Intel pass is inferred.
- Intel actual audio: **all fourteen physical M/Sound cases passed** in
  the separate run 43732427910. All 84 WAVs, two waveform sheets and two cleanup
  desktops were independently inspected; the complete 119-entry original app
  matches the successful source/packaged launch and performance evidence.
  `build/ci-audio-current-7d9668ed-macos-intel/build/audio-native-app/pcm/independent-review/review.json`
  retains the exact game hash and output scope. This does not promote the
  still-pending control inventory.
- Test-only panel marker regression: **twelve physical Linux cases passed**,
  with all 72 referenced frames plus startup inspected, exit 0 and no stale
  captures. The marker now paints after the actual game scene without changing
  content insets. This verifies the helper locally; the independent full Intel
  repeat did not resolve whole-scene capture staleness, as recorded above. Evidence:
  `build/audit-source-7d9668ed-panel-marker/REVIEW.md`.

- Opt-in Java paint journal: **six filtered physical Linux cases passed**
  with all 25 referenced frames plus startup inspected, clean exit and 380
  ordered completed paints. Direct frame counters and nano/epoch brackets are
  retained without dropped records. This verifies the diagnostic locally;
  Java paint completion alone is not native presentation proof. Evidence:
  `build/audit-source-7d9668ed-paint-trace/REVIEW.md`.
- Buffering comparison helper at commit `8048087`: **three local six-case
  routes passed**, 18 cases total, with all 75 referenced frames and three
  startup originals inspected and every process exiting 0. The observed
  RepaintManager state was true/false/true before window creation and after
  readiness; all three retained the same XRender backend, panel flags and
  geometry. Exact evidence: `build/audit-buffer-pair-7d9668ed/comparison-review.json`.
  The 58 Kotlin/JVM tests and 29 focused Python driver checks pass at this
  revision, with the production JAR unchanged. This is a bounded local
  diagnostic, not a Mac or production-fix verdict.
- Intel comparison 43738815451 observed the Metal backend in both copies,
  with buffering true then false. The default repeated the Left presentation
  timeout; disabling buffering produced incomplete captures without the fox,
  HUD or nonce, failed all five recorded cases and aborted the lifecycle row.
  The strict barrier prevented the third launch. All 28 retained default
  control/diagnostic originals and all ten disabled originals were inspected.
  This rejects the proposed buffering change as a correction; the exact native
  cause remains unresolved. `build/ci-buffer-comparison-7d9668ed-macos-intel/build/controls-capture-comparison/native-visual-review.json`
  retains the scope and the old failed-request image-overwrite limitation.
- Scheduled-repaint helper at `fb688398`: **six local physical cases passed**,
  with all 25 referenced frames plus startup inspected and exit 0. All 26
  snapshot requests used normal repaint scheduling, unique request nonces and
  unchanged enabled buffering. The regression also proves that failed requests
  retain distinct first/latest originals and cannot reuse a stale request's
  nonce. Evidence: `build/audit-source-7d9668ed-scheduled-repaint/REVIEW.md`.
  This local result does not establish the native Mac behavior.
- Intel scheduled repaint, run 43740408807: **Left still fails** its strict
  moving/interior release guard. The actual Metal backend and enabled buffering
  are retained; all 25 requests use scheduled repaint and distinct nonces.
  Twenty-six stale reads precede the accepted wall frame, extending the physical
  hold to 3.319 seconds. All 24 referenced frames, startup and 18 retained
  rejected originals were inspected. The five other filtered rows pass their
  limited diagnostic scope. The independent stream presents the new nonce
  2.858 seconds after its first Java callback, with 165 newer drawing callbacks
  in between. The gap contains 93.928 ms of recorded safepoints. All 32 stream
  originals were independently reviewed; the 677 Java callbacks are ordered.
  Trace collection and cleanup pass separately from the failed command proof.
  Evidence: `build/ci-scheduled-7d9668ed-macos-intel/build/controls-capture-native-app/review/native-review.json`.
  Normal repaint scheduling has not resolved the failure.
- The ordinary Main probe 43740419423 stopped before any input: its first guard
  ran before the native window was ready. It records no movement, and cleanup
  used SIGTERM on its owned process, so neither ordinary-game responsiveness nor
  physical-Quit proof is established. The app tree is unchanged. A corrected
  bounded readiness check ran separately in 43741464146 and reached gameplay.
  All 80 originals were independently reviewed: A moves/stops normally, while
  the first Left has a 3.123-second gap between complete stream frames despite
  an independently bounded 356.831 ms OS-level hold/release. The next frame
  shows the fox at the boundary, without damage, respawn or a modal. Main's
  held capture times out reading AXFocusedWindow; NativeAudit's snapshot route
  does not make this AX request. The causal distinction is unresolved. Cleanup
  uses SIGTERM, with no physical-Quit claim. Evidence:
  `build/ci-main-ready-7d9668ed-macos-intel/build/main-movement-native-app/independent-review/review.json`.
  No full Intel pass is inferred.
- The focused CGL diagnostic 43741471213: **Left still fails** with observed
  `CGLGraphicsConfig`, unchanged enabled buffering and the exact expected
  properties. Twenty-one stale reads precede the fresh wall frame after a
  3.355-second physical hold. All 24 referenced frames, startup and both rejected
  originals were inspected; 345 ordered Java drawing callbacks and 25 distinct
  snapshot invocations were retained. This alternate backend does not resolve
  the failure. Evidence:
  `build/ci-opengl-7d9668ed-macos-intel/build/controls-capture-native-app/review/native-review.json`.
  The production launcher and rendering flags remain unchanged; no full
  280-command pass is inferred from this diagnostic.
- Ordinary-Main stream-only run 43743043450 identifies a native wait during
  the first Left failure: all 568 AppKit main-thread samples are inside
  Services-menu population; 560 wait synchronously for a VoiceShortcutClient
  XPC reply. The physical Left release is acknowledged after 357.015 ms, but
  the native image freezes and later reaches the boundary. No synchronous
  window queries run during the held/early-release interval. The live sample
  is retained at
  `build/ci-main-stream-sampled-7d9668ed-macos-intel/build/main-movement-native-app/live-sample.txt`.
  A focused Mac-only candidate removes the unused Services submenu through
  public AppKit APIs; native validation and affected final-build checks are
  still required. No corrected-game pass is inferred from source review.
- Snapshot observation 43743028454 failed its unchanged 50 ms release limit
  during D preparation (52.838 ms late). Retry 43743527267 failed during Return:
  OS-up acknowledgement arrived 51.580 ms after its deadline, although up was
  posted only 8.579 ms late. Neither reached Left, streaming or live sampling.
  All four and three original frames respectively were inspected; the latter
  visibly starts the level before the timing guard aborts. Both preserve owned
  SIGTERM cleanup rather than physical Quit proof. Exact journals:
  `build/ci-main-snapshot-sampled-7d9668ed-macos-intel/build/main-movement-native-app/independent-review/review.json`
  and `build/ci-main-snapshot-sampled-repeat-7d9668ed-macos-intel/build/main-movement-native-app/independent-review/review.json`.

## Earlier evidence

[Historical verification and investigations](history/verification-investigation.md)
retain the d549/882 baselines, failed attempts, their exact limitations, and the
diagnostics that exposed the jump-order defect. They are not substitutes for the
current runnable build's inventory and campaign above.

## Review findings corrected

- A jump release followed by a fresh press in the same simulation step could
  cut the new jump. A fresh logical press now clears only the older release;
  press-then-release still cuts correctly, and overlapping alternate keys retain
  their aggregate action. The actual-handler matrix fails before the fix and
  passes after it, alongside strict physical release/double/third-jump evidence.
- Completed-level gems could be counted twice; totals now use one authoritative
  completed/current-level rule, including the ending display.
- Rising platforms need relative-motion collision checks to carry the fox.
- Mushrooms only launch a fox that approaches their top, avoiding a bounce from
  beneath terrain.
- Swing's default focus traversal swallowed Tab; the game now handles it.
- Late armor now opens within the visible equipment list. Locked and unequipped
  gear have distinct labels, and current armor capacity is shown.
- Switching between held left/right Shift keys no longer bypasses the requirement
  to release the dash action before dashing again.
- Static menus stop repainting continuously; victory particles continue until
  finished. State transitions discard paused wall time and stale input.
- Failed settings writes remain visible without overlapping title instructions.
- Trail section names now follow the nearest sign passed in world coordinates,
  including backtracking. Original sign insertion order is not spatial order.
- Zed rejected the unsupported `reveal: on_error` value and hid the Play task.
  The task now uses supported reveal/hide settings, verified in the editor itself.
- Paused and result menus drew gameplay instructions underneath their own footer.
  The gameplay footer is now hidden in menus; results retain an explicit M/sound
  hint. Every final Linux and Mac ARM control frame was inspected after this fix.
- A blocked audio provider could hang window disposal. Initializing devices are
  no longer published to UI controls, and native close runs outside the interface
  thread. Two regression tests exercise blocked initialization and blocked native
  shutdown, including eventual device release. Output readiness now requires an
  opened, running line; absence of an error alone is not evidence of readiness.
- A Sound button retained hover styling after the pointer moved away during
  focus loss. Focus cleanup now clears hover, pressed styling and the pointer
  shape. Its new physical-input regression brings the inventory to 280 cases.
- Intel Mac startup exposed Java Sound's recording-device probing during output
  initialization. A playback-only AudioQueue backend replaces that Mac path;
  seven native-callback regression tests pass. Native ABI, startup, lifecycle
  and captured-PCM checks passed on both Mac architectures in the retained
  baseline; the corrected 7d9668ed build repeats them successfully on both
  architectures, with the independent Intel audio run recorded above. Missing native
  libraries and failed output resets now become explicit audio-unavailable
  states without letting mute or window close hang the interface.

The current 7d9668ed build passes separate `ktlintFormat`, then `check fatJar`,
with all 60 tests. Its complete Linux inventories, macOS ARM inventory and native
twenty-level campaign are recorded above; Intel's final repeat remains open.
Native playthrough attempts use ordinary input and real campfire retries;
every retry is retained in their results, and no state fixture or teleport counts
as campaign progress.

No finite audit proves the absence of all bugs. Platform facilities that have not
been exercised remain explicitly unverified in the final coverage record.
