# Earlier verification evidence

This is a historical record of earlier builds, diagnostics and failed attempts.
A pass applies only to the named build and scope. Pending or failed statements
below describe that checkpoint, not the current release status. See the
[current verification record](../VERIFICATION.md) and
[physical coverage table](../controls-audit.tsv) for current results.


The strengthened native jump audit exposed a production ordering defect:
releasing jump and pressing it again before the next simulation step can apply
the old release to the new jump. The actual Linux failure is retained at
`build/audit-native-timing-linux/jump-observations.jsonl`. The minimal input-order
fix now passes all seven actual-handler regressions; three failed on the old
code. Before/after XML is retained in `build/regressions/jump-order/`. The
88283267 results below remain build-specific baseline evidence; they do not
verify the corrected runnable build.
The current-build repeats and remaining platform gaps are recorded in the current verification record linked above.

- Corrected jump-order native diagnostic: **nine filtered cases passed** on
  `7d9668ed`, with all 59 referenced frames and the startup frame inspected at
  `build/audit-jump-order-fixed-linux/REVIEW.md`. This includes all four ordinary
  directions, Space/W/Up separately, the alternate-jump release chord and window
  lifecycle. Observed short-release velocity changes exceed measured gravity;
  second jumps retain their full impulse and third presses do not renew it.
  This focused diagnostic does not mark the full inventory passed.
- Original resources: **passed**. SHA-256 checks cover all 2,107 migrated files;
  level data contains 20 levels, 60 acorns and 378 gems.
- Installer fixtures: **passed**. Seven tests cover first install, replacement,
  removal, difficult paths through real Gio, unrelated-directory preservation,
  invalid/offline JDK errors, bad checksums and interrupted-install rollback.
- Bootstrap: **passed**. Empty-cache Java download, checksum, extraction and
  offline reuse were exercised without changing system Java.
- Kotlin formatting: **passed**. The current production candidate is formatted with ktlint.
- Build, lint and automated tests: **passed**, 58 tests. The simulation campaign
  reaches all 20 levels, all 60 acorns and 20 hidden fireflies, all six guardians
  and all 13 equipment unlocks with zero retries. Optional gems collected by this
  route: 196 of 378. This is simulation evidence, not a physical-input playthrough.
- Artwork review: all eight regions, six guardians, four regular monsters and
  thirteen equipment appearances were rendered and visually inspected.
- Actual Linux sound: **all fourteen M/Sound cases passed on final 88283267**
  source and bundled runtimes, with 84 WAVs captured for each. Game-only PCM proves
  mute, interruption of an active cue and restored output. The root reviewer
  inspected all waveform sheets and independently checked the original 880/1175 Hz
  gem pitches. Evidence: `build/audio-states-source-88283267/` and
  `build/audio-states-packaged-88283267/`, including `REVIEW.md` and
  `root-review.json`. The earlier d549 records remain preserved separately.
- Linux installation and native launcher: **passed** with invalid global Java
  and internet socket creation blocked. The separate application opens through
  the desktop registry and closes using physical Alt+F4. See PACKAGING.md.
- Final Linux installer integration: **passed on both architectures** in run
  43719750356. Both source and packaged routes repeat all fourteen physical audio
  cases and the real-main Start/move/jump/pause/Alt+F4 sequence. All 336 analyzed
  WAVs and 36 original game/closed-desktop frames were independently inspected;
  all four game processes exit 0. Package review verifies the unchanged game and
  complete runtime bytes, symlinks and modes against the full-control baseline.
  Records: `build/ci-audio-dependencies-linux-{x64,arm64}/`, under
  `build/audio-linux/{source,packaged}/` and `package-review.json`.
- Clean Linux dependency recovery: **passed on both architectures** in run
  43720498665. Disposable Ubuntu 24.04 containers start with missing desktop
  libraries and empty package indexes, refuse an offline first run clearly,
  install actual dependencies, load Java and the bundled fonts, then reuse them
  offline without another package-manager action. The containers are removed;
  host libraries are unchanged. Records:
  `build/ci-dependencies-linux-{x64,arm64}/dependency-container/`. These headless
  dependency checks are separate from the actual desktop-control proof.
- Zed onboarding: **passed in Zed 1.28.1** with isolated editor data. The actual
  task picker loads Play Emberwood Kotlin; selecting it launches the game. Return,
  movement, jump, pause and window close were exercised in that launched window.
  Screenshots are retained in `build/zed-audit/`.
- Historical cacc4dc CI campaign: **all twenty levels passed** in run 43712421975 at
  commit `cacc4dcf060b013d211bd2f45376355ea7e71602`, with normal-rate physical
  input. All 35 requested images were inspected: twenty completion frames, six
  guardian before/defeated pairs, title, actual retry and final. The ending shows 08:19, one retry,
  201/378 gems and all twenty fireflies. The Bash pipeline used `-e -o pipefail`
  and completed successfully. This job did not retain its built JAR hash or a
  separate Java/wrapper exit breakdown; the exact commit and job log are retained
  in `build/ci-campaign-88283267/`. See `campaign-native/REVIEW.md`.
- Instrumented native campaign baseline: **all twenty levels and clean process shutdown passed** on
  baseline JAR `d5499672…` using normal-rate physical OS keys from title to victory.
  It collected all 60 acorns, all 20 fireflies and 201/378 optional gems, and defeated
  all six guardians. One actual fall in Sunlit Ridge exercised checkpoint recovery;
  the inspected ending shows 08:19 and one retry. All twenty completion frames,
  twelve guardian before/defeated frames, title, retry and final were inspected.
  Java and wrapper independently returned 0; owned-process signal tracing confirms
  normal Java exit before the wrapper stopped its own window manager. Evidence:
  `build/campaign-native-d5499672-clean-exit/REVIEW.md` and its 35-frame hash manifest.
  The first d549 run reached victory but returned unexplained status 143; that
  original evidence remains at `build/campaign-native-d5499672/` and is not called
  a clean shutdown. The separately instrumented repeat supplies a clean pass for that historical build.
- Historical native campaign: all twenty levels passed on JAR `ce6f5af4…` using
  normal-rate physical OS keys from the title through victory. It collected all
  60 acorns, all 20 fireflies, 199/378 optional gems, and defeated
  all six guardians. One actual fall in Sunlit Ridge exercised checkpoint recovery;
  final time was 08:21 with one retry. All twenty completion frames and guardian
  before/defeated pairs were inspected. Evidence: `build/campaign-native-twenty/`.
  The earlier separate first-three-level run also passed, including a spike retry.
- Historical 88283267 Linux x64 controls: **all 280 rows passed on source and bundled runtimes**
  at JAR `88283267eefaf417da4965a1248c1b70b9188effd71f6ee3f69cc2c1911e5bc1`.
  Each run exited 0. All 1,208 referenced PNGs per run were visually inspected;
  disjoint reviewer journals and hashes cover every frame. Fourteen actual audio
  cases per runtime and installed physical Alt+F4 complete the output/lifecycle
  evidence. Consolidated records: `build/audit-source-88283267-final/REVIEW.md`,
  its `controls-reviewed.tsv`, and the corresponding packaged directory.
  Both final Linux CI architectures passed automatic source/package audits in
  run 43712421975. ARM source and bundled visual review is also complete: every
  one of the 1,208 frames per run is covered by disjoint, hash-verified journals.
  Consolidated ARM records are under `build/ci-final-8828-linux-arm64/build/`,
  in `audit/controls-reviewed.tsv` and `audit-packaged/controls-reviewed.tsv`.
  That original CI host had no output device. Run 43716755578 now completes
  exact-build ARM output and physical close: fourteen physical audio cases and
  84 analyzed WAVs per runtime, plus real MainKt Alt+F4, exit 0 and an empty
  desktop. Independent waveform and original-frame review records are in
  `build/ci-audio-final-linux-arm64/build/audio-linux/{source,packaged}/`, under
  `independent-review/` and `game-smoke/`. Capture uses only game output through
  a private virtual PipeWire sink; no speaker-hardware claim is made. Short
  residual tails in three ARM source mute-cutoff captures remain documented.
- Linux control baseline d5499672: **all 280 rows passed** on source and bundled
  runtimes, including inspection of all 1,198 referenced frames per run, separated
  projectile supplements for all five weapons, actual fourteen-case audio output,
  and installed physical window close. Each full run exited 0. Consolidated rows:
  `build/audit-source-d5499672-final/controls-reviewed.tsv` and the corresponding
  `build/audit-packaged-d5499672-final/controls-reviewed.tsv`.
- Missing-output status: **passed on historical 88283267**. An isolated empty ALSA configuration
  caused an actual SourceDataLine initialization failure. Physical M was held,
  released and pressed again in all six states; all 19 native frames retain
  unavailable instead of incorrectly claiming on/off. The seven-case run and
  cleanup exited 0. Evidence: `build/audit-source-88283267-missing-audio-footer/REVIEW.md`.
  The earlier 0d3d proof remains at `build/audit-source-missing-audio-footer/`.
  Source and bundled 0d3d runs each completed all 280 automatic cases and exited 0;
  their manual review stopped when the final constructor-order preservation changed
  the JAR. Those incomplete reviews do not establish a final-build pass.
- Historical 88283267 Mac ARM native app: **all 280 control rows passed**, with all 1,208
  referenced frames inspected and hashed. Fourteen physical M/Sound cases and
  84 game-only PCM recordings pass separate independent review. Real installed
  and source-launched apps show the original icon, open without a permission
  dialog, and close through physical Command+Q with no forced termination.
  Both native source and packaged 180-second performance profiles pass.
  Evidence: `build/ci-native-final-macos-arm/`, including the control
  `REVIEW.md`, `package-review.json`, both launch reviews, and independent
  performance/audio review folders. Complete app-tree identity justifies the
  source column's explicit **SHARED PROOF**; it does not claim a second physical
  source inventory. Captured audio continuity findings remain in the audio
  journal, including one 11.604 ms interval during final cue decay; this is not
  a claim of flawless audio or speaker-hardware testing.
- Historical Intel Mac inventory on 88283267, run 43721802571: **280 cases executed, three failed**.
  The three failed command rows remain failed: Left's audit-only `Toolkit.sync`
  blocked for 2.789 seconds, and blocking screenshots delayed the Space/W second
  press until after the first jump landed. Current-frame nonce receipts and actual
  rendered frames distinguish these harness timing errors from a direction or jump
  implementation defect. The other 277 rows pass automatically, with complete
  visual review deferred until the corrected final run. A separate native-process
  monitor identity failure occurred during shutdown; clean monitor completion is
  not claimed. Original logs, 1,199 referenced frames and failure reviews remain
  under `build/ci-native-intel-controls-88283267/`. The test-only corrections keep
  strict movement, airborne, jump-count and release assertions. That historical
  attempt did not establish a full control pass; the later status is recorded
  in the current verification record.
- First 88283267 Intel Mac control attempt: **failed before input**. Screenshot color
  conversion changed the test marker from RGB(251,1,4) to (250,3,1), so all 279
  attempted before-frame checks and the final lifecycle capture timed out. The
  retained title/paused screenshots show normal game windows, but this attempt
  supplies no physical control coverage; audio was skipped. The test-only
  monochrome nonce correction now passes actual startup/frame checks in focused
  run 43720497291. All 26 cases and 108 referenced frames were inspected; 25 pass,
  while Left-arrow retains a capture-overrun failure: the 2897.8 ms screenshot
  delay let the visible fox reach the left edge outside the observer's old scan
  region. Actual direction is correct; the failed observer row required
  correction and retest at that checkpoint. No complete Intel control pass is inferred. The focused
  review is under `build/ci-native-intel-marker-88283267/`. Evidence: `build/ci-native-final-macos-intel/build/controls-native-app/`
  and its `presentation-failure-review.md`. Both actual source/package
  180-second performance profiles pass independent review of all 58 frames;
  Intel's early blank packaged startup capture is retained alongside the later
  normally rendered title and measured scenes. Ordinary source/installed launch
  and physical Command+Q also pass ten separately inspected original frames,
  without promoting the failed control inventory. Separately, audio-only
  run 43719992137 now passes all fourteen physical M/Sound cases and 84 game-only
  PCM recordings on the same final game/runtime. Its two waveform sheets and two
  cleanup desktops were independently inspected; evidence is under
  `build/ci-audio-trace-macos-intel/audio-native-app/pcm/independent-review/`.
  A fresh untraced run 43721920267 also passes all fourteen cases and 84 recordings
  on each Mac architecture, with every waveform panel and both cleanup desktops
  independently inspected. Original app-tree identity matches the reviewed
  source/package apps. Evidence: `build/ci-audio-untraced-macos-{arm,intel}/`,
  including `cross-run-package-review.json` and
  `build/audio-native-app/pcm/independent-review/`. Earlier continuity findings
  remain preserved separately; these repeats do not prove flawless hardware audio.
  This does not inherit control coverage from the failed run.
- First actual Mac ARM application control run: **failed** on the d549 baseline.
  All 280 rows completed; 18 failed rows plus one pointer-cleanup error remain
  preserved in `build/ci-mac-native-controls-first/`. A camera-boundary fixture,
  delayed auxiliary-window registration and injected modifier flags caused those
  harness failures. The final 26-case ARM native-app diagnostic subsequently
  passed all automatic checks; every frame was inspected. Its 25 input rows show
  correct motion, dash, M press/release and focus recovery, with raw OS/AWT receipts.
  The lifecycle image exposed a resize/capture race, now fixed in the test harness
  and verified by the final full ARM native-app rerun. Historical evidence:
  `build/ci-mac-targeted-88283267/`. That filtered diagnostic alone did not
  establish all 280 Mac rows.

## Historical checkpoint before current ae9686cb Linux consolidation

The following retained checkpoint describes earlier builds and investigation stages. Its words “current,” “pending” and “unresolved” describe that checkpoint, not today's acceptance record. See [the current verification](../VERIFICATION.md) and [current coverage](../CONTROLS.md) for present outcomes. Failed trials remain failed; successful later evidence does not rewrite them.

### Retained control investigation

The table retains the audited `7d9668ed` baseline. Current candidate `ae9686cb`
removes only the exact macOS Services menu item and preserves registration;
formatting/build and 67 automated tests pass. In run43747451930, ARM passes all
six focused rows and the strict post-show menu-identity probe. Intel passes five
rows, including Left, but A fails release/braking proof when a 1,149.49 ms held
screenshot request extends input to the world boundary; this failed row is
retained. All 53 ARM and 40 Intel snapshot/cleanup originals were inspected.
Exact journals are in each
`build/ci-controls-detachment-ae9686cb-macos-{arm,intel}/build/controls-capture-native-app/review/native-review.json`.
Neither run is a full280 audit; no baseline pass transfers to this candidate.
The unchanged Intel repeat43748162685 passes all six focused rows and its strict
native menu probe. All 25 referenced plus 16 additional originals were inspected
and hashed; every directional binding moves and brakes at an interior position,
and all eight non-Services menu records are preserved. The prior A-overrun trial
remains failed. Exact repeat evidence:
`build/ci-controls-detachment-repeat-ae9686cb-macos-intel/build/controls-capture-native-app/review/native-review.json`.
The candidate's complete twenty-level native campaign also passes with all 55
originals inspected, but campaign success does not mark the full inventory passed.

The earlier `375ae227` Services candidate passed compilation and 67 tests, but startup failed on
both Macs before any control input because its post-clear registration check
still sees a menu object. The subsequent five-phase native probe on both Macs
shows the same registered object already detached; registration becomes nil only
after showing the window, with every sibling identity/action/key unchanged.
That observation does not exercise game input. The rebuilt removal-only candidate
above verifies exact detachment; its complete native game and final-build
inventory remain unverified.
For `7d9668ed`, both Linux x64 source and bundled
runtimes pass all **280 cases**, with clean exit and all **1,214 referenced frames**
per run inspected. Exact disjoint reviewer journals are validated by
`build/audit-{source,packaged}-7d9668ed-final/review/all-frames-reviewed.json`;
complete results are in each `controls-reviewed.tsv` and `REVIEW.md`.

Fourteen physical M/Sound cases and 84 game-only PCM recordings per runtime
supply actual output proof in
`build/ci-audio-jump-fixed-linux-x64/build/audio-linux/{source,packaged}/independent-review/`.
The corresponding `game-smoke/independent-review/` records actual MainKt
movement, jump, pause and physical Alt+F4 with clean exit. The installed offline
app additionally passed in `build/installed-user-audit-7d9668ed/`.
This establishes software playback through an isolated virtual output, without
claiming speaker-hardware testing.

Linux ARM64 source and bundled inventories also pass all **280 cases** in
CI43725299181. All **1,214 frames per runtime** are independently reviewed, with
exact disjoint journals and complete results at
`build/ci-final-7d9668ed-linux-arm64/build/{audit,audit-packaged}/REVIEW.md`.
The full inventory correctly displays unavailable sound on its device-free host;
matching application bytes, runtime and physical bindings pass the separate
actual PCM and real-main Alt+F4 checks in `build/ci-audio-jump-fixed-linux-arm64/`.

macOS ARM passes all **280 native cases**, with every one of the **1,214 frames**
independently inspected. Actual fourteen-case PCM, physical Command-Q and both
source/packaged performance routes also pass. The complete result and exact
supporting hashes are at
`build/ci-native-final-7d9668ed-macos-arm/build/controls-native-app/REVIEW.md`.
Its source column records shared proof from the identical app, as defined below.

Intel's first source performance run measured 40.729 Java paints/second in one
boss window, below the 45 paints/second budget; this is not native presentation
FPS. Its control and audio stages did not run. That
failure remains at `build/ci-native-final-7d9668ed-macos-intel/`. The separate
instrumented repeat passed both performance routes and ran all 280 controls.
One Left-arrow row failed: 21 captures retained the previous presentation nonce,
extending the held input to 3.31 seconds and reaching the world boundary before
release/braking could be proved. The other 279 assertions passed, but complete
rendered control review remains pending. Evidence is preserved at
`build/ci-native-repeat-7d9668ed-macos-intel/`; the failed row is not credited.

The subsequent panel-marker run 43732405531 also fails only Left. Its retained
first/latest rejected PNGs are byte-identical across the whole scene; the
accepted frame arrives after the fox reaches the boundary. The marker-only
hypothesis is disproved. The six inspected originals and timings are recorded in
`build/ci-native-panel-marker-7d9668ed-macos-intel/build/controls-native-app/review/native-left-failure-review.json`.

The six-case diagnostic 43736264766 reproduces Left's failure with independent
snapshot and stream captures of the same old surface. Java reaches 140 fresh-nonce
drawing callbacks before the stream presents the new surface approximately 3.06 seconds
later; the callbacks precede Swing's final buffer publication. All 23 referenced
frames and three additional originals were inspected;
ordered Java and stream traces completed without data loss. The native
publication/compositor/capture cause remains unresolved. The subsequent buffering
comparison is recorded below; no full Intel pass is credited. Exact observations:
`build/ci-capture-trace-7d9668ed-macos-intel/build/controls-capture-native-app/review/native-java-paint-review.json`.

The comparison helper at commit `8048087` passed three local six-case routes:
18 cases, all 75 referenced frames plus three startup originals inspected, and
three clean exits. Actual buffering states were true/false/true on the same
XRender backend and viewport. `build/audit-buffer-pair-7d9668ed/comparison-review.json`
records the exact images, metadata and scope. Intel comparison 43738815451
observed the same Metal backend with buffering true then false. The default
repeated Left's failure; the disabled copy produced incomplete scenes and
aborted before the sixth row, so the third launch was blocked. All retained
control and diagnostic originals were inspected. The buffering override is not
a correction, and final inventory verdicts remain unchanged. Exact receipts:
`build/ci-buffer-comparison-7d9668ed-macos-intel/build/controls-capture-comparison/native-visual-review.json`.

The test-only scheduled-repaint branch at `fb688398` passed six local physical
cases, with all 25 referenced frames and startup inspected, exit 0 and 26 distinct
request nonces. Failed requests now retain distinct originals and cannot let
their old marker satisfy a later request. This does not change production
rendering or the ordinary full audit's synchronous state observations. Local
evidence: `build/audit-source-7d9668ed-scheduled-repaint/REVIEW.md`.

Intel scheduled run 43740408807 still fails Left's strict held/release proof.
The actual Metal backend retains enabled buffering, and all 25 requests used
scheduled repaint with distinct nonces. The held capture returned 26 old frames
before accepting the fox at the boundary after a 3.319-second physical hold.
All 24 referenced frames, startup and 18 retained rejected originals were
inspected; the other five filtered rows pass only their diagnostic scope.
The independent stream presents the new nonce 2.858 seconds after its Java
drawing callback, with 165 newer callbacks in between; the total recorded
safepoint time in that gap is 93.928 ms. The 677 ordered Java callbacks and clean
collection/cleanup do not establish native presentation responsiveness. Exact review:
`build/ci-scheduled-7d9668ed-macos-intel/build/controls-capture-native-app/review/native-review.json`.
Normal repaint scheduling has therefore not resolved the failure. The separate
real-Main probe 43740419423 stopped before sending any input because its initial
guard ran before the ordinary window was ready. Its owned process was terminated
and the corrected bounded readiness check ran separately in 43741464146. That
retry reached ordinary gameplay: A moved and stopped normally, but the first
Left showed a 3.123-second gap between complete stream frames despite its
independently bounded 356.831 ms OS-level hold/release. The next frame showed the
fox at the boundary; later animation there is not braking proof. All 80 original
images were independently reviewed. Main's held capture timed out reading
AXFocusedWindow, whereas NativeAudit's snapshot path makes no such AX request.
No causal conclusion follows from that difference. Cleanup again used SIGTERM,
so physical Quit is not proved by this probe. Exact review:
`build/ci-main-ready-7d9668ed-macos-intel/build/main-movement-native-app/independent-review/review.json`.

The six-case CGL diagnostic 43741471213 also fails only Left. It actually uses
`CGLGraphicsConfig`, enabled buffering and the two requested graphics properties.
The first/latest rejected whole scenes remain at the start, while the accepted
frame reaches the wall after a 3.355-second hold (21 stale reads then one fresh).
All 24 referenced frames, startup and both rejected originals were inspected.
Exact scope and hashes:
`build/ci-opengl-7d9668ed-macos-intel/build/controls-capture-native-app/review/native-review.json`.
The alternate backend has not resolved this failure. Production rendering flags
are unchanged, and no full Intel pass is credited.

The stream-only ordinary-Main run 43743043450 reproduced the first-Left delay
without synchronous window queries during the hold or early recovery. Its live
native sample records all 568 AppKit main-thread samples in Services-menu
population, including 560 waiting synchronously for a VoiceShortcutClient XPC
reply. Left was physically released and acknowledged after 357.015 ms. The
native surface still froze and then showed the fox at the boundary, so recovery
remains failed. Evidence is under
`build/ci-main-stream-sampled-7d9668ed-macos-intel/build/main-movement-native-app/`.
A Mac-only candidate removes that unused native Services submenu through public
AppKit APIs while preserving the other application-menu items. It is not yet
accepted as a fix or credited as control coverage.

The paired snapshot attempt 43743028454 and retry 43743527267 stopped before
Left or live sampling: their independent release timing limits failed during
D preparation and Return respectively. All four and three original frames were
inspected. These invalid trials remain at
`build/ci-main-snapshot-sampled-7d9668ed-macos-intel/` and
`build/ci-main-snapshot-sampled-repeat-7d9668ed-macos-intel/`; neither supplies a
snapshot-versus-stream treatment comparison or physical Quit proof.

Current Intel audio separately passes all fourteen physical M/Sound cases and
84 game-only recordings in run 43732427910. Both waveform sheets and both cleanup
desktops were inspected, and all 119 original app entries match the passing
source/packaged launch and performance evidence. The exact journal is
`build/ci-audio-current-7d9668ed-macos-intel/build/audio-native-app/pcm/independent-review/review.json`.
Complete physical control review is still required before the Intel rows pass.


### Retained verification checkpoint

The current removal-only candidate JAR is
`ae9686cb8387d5c9f61f4a6cb73d4f9a99803fe6e93e2ce519d495d59b9bdb8c`
at commit `39d59a5`. It detaches the exact registered Services submenu, verifies
both former-parent index absence and the submenu's nil parent, and leaves native
registration and all other menu actions intact. Formatting, check and fatJar
pass with **67 Kotlin/JVM tests**. In run43747451930, ARM passes all six focused
physical rows and the strict before/prepared/shown menu-identity probe: only the
Services item is removed, with all eight sibling records unchanged. All 25
referenced frames and 28 additional originals were inspected.
Intel starts and finishes six rows, but A fails its interior/release guard:
the held screenshot request takes 1,149.49 ms, extending A's received hold to
1,448.83 ms and reaching the world boundary before braking can be proved. Its
single held capture has the current nonce, unlike the historical repeated-stale
Left failure. Left, D, Right, Return and programmatic lifecycle pass; the strict
postgame menu probe is skipped after A's failure. All 24 referenced frames and
16 additional originals were inspected. Exact frame hashes, limits and all four
direction timings are retained at
`build/ci-controls-detachment-ae9686cb-macos-{arm,intel}/build/controls-capture-native-app/review/native-review.json`.
No full inventory or physical menu/Quit pass is inferred from these focused runs.

The unchanged Intel repeat, run43748162685 at the same commit and JAR, passes
all six focused rows and the strict native menu probe. All 25 referenced and
16 additional originals were inspected, including full-size startup, resized
content and empty-desktop cleanup. A/Left/D/Right visibly move and brake at
interior positions; all four held captures return their current nonce on the
first read. Their AWT holds are 601.14/775.86/580.84/803.20 ms respectively.
The eight remaining menu sibling records match exactly before/after show.
Evidence: `build/ci-controls-detachment-repeat-ae9686cb-macos-intel/build/controls-capture-native-app/review/native-review.json`.
This is six-case partial coverage; the earlier A-overrun trial remains failed.

The current candidate also completes the full normal-rate native campaign in
CI43747640143. All 55 original frames were inspected: twenty entries/completions,
six guardian before/defeated pairs, title, the real chapter-five fall and ending.
The ending shows **08:19, one retry, 201/378 gems and all twenty fireflies**;
all sixty acorns were collected. The 3,427 physical input batches contain
3,732 edges, with no state fixtures or direct simulation stepping. The retry is
natural checkpoint recovery, not a tested R press. The native pipeline and job
succeed under `bash -e -o pipefail`; no separate numeric per-PID exit receipt
exists. Exact hashes and limits:
`build/ci-campaign-ae9686cb/campaign-native/review/native-review.json`.
The runner correctly shows unavailable audio; actual output and the complete
control inventory remain separate checks.

Current ae9686cb Linux source and bundled playback/lifecycle pass on both
architectures in CI43747641897. All 56 physical audio cases, 336 WAVs and eight
waveform sheets were independently reviewed, with no uninterrupted interior
silence gap of at least 2 ms. All 36 ordinary Main images were inspected in
labelled contact sheets; original-pixel travel, settling, jump and landing were
checked, and physical Alt+F4 ends each of the four routes with process exit 0.
Receipts: `build/ci-audio-ae9686cb-linux-{x64,arm64}/build/audio-linux/{source,packaged}/independent-review/review.json`
and the adjacent `game-smoke/independent-review/review.json`. This is private
game-only virtual output, not a speaker-hardware claim.

The first menu candidate JAR is
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
The subsequent native observation run43746599584 at `f589a33` completed on both
Mac architectures. Removal immediately detaches the exact item; both immediate
post-set getters retain the same registered pointer, and the after-show getter
returns nil. All eight other application-menu records are unchanged through all
five phases, including identities, actions, targets, key equivalents and modifiers.
Exact observations and hashes are in
`build/ci-services-registration-375ae227-macos-{arm,intel}/build/mac-services-registration/independent-review.json`.
This raw-JDK observation does not exercise game input or a rendered menu. The
source correction now removes only the item and verifies detachment, leaving
native registration intact; its rebuilt candidate and limited native results are
identified above.
The first candidate is not accepted as a fix, and first-arrow, physical menu and
final-build validation remain open.
The current full tools suite passes **201 Python tests** (two macOS SDK tests
skipped on Linux); Ruff and formatting pass for all 59 Python files. The full
run is retained in `build/logs/python-final-measured-mac-fixtures.log`.
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
