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
  emberwood.CampaignAudit 3
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

- Original resources: **passed**. SHA-256 checks cover all 2,107 migrated files;
  level data contains 20 levels, 60 acorns and 378 gems.
- Installer fixtures: **passed**. Six tests cover first install, replacement,
  removal, difficult paths through real Gio, unrelated-directory preservation,
  invalid/offline JDK errors, bad checksums and interrupted-install rollback.
- Bootstrap: **passed**. Empty-cache Java download, checksum, extraction and
  offline reuse were exercised without changing system Java.
- Kotlin formatting: **passed**. The current production candidate is formatted with ktlint.
- Build, lint and automated tests: **passed**, 43 tests. The simulation campaign
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
- Zed onboarding: **passed in Zed 1.28.1** with isolated editor data. The actual
  task picker loads Play Emberwood Kotlin; selecting it launches the game. Return,
  movement, jump, pause and window close were exercised in that launched window.
  Screenshots are retained in `build/zed-audit/`.
- Final-commit CI campaign: **all twenty levels passed** in run 43712421975 at
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
  a clean shutdown. The separately instrumented repeat supplies the current pass.
- Historical native campaign: all twenty levels passed on JAR `ce6f5af4…` using
  normal-rate physical OS keys from the title through victory. It collected all
  60 acorns, all 20 fireflies, 199/378 optional gems, and defeated
  all six guardians. One actual fall in Sunlit Ridge exercised checkpoint recovery;
  final time was 08:21 with one retry. All twenty completion frames and guardian
  before/defeated pairs were inspected. Evidence: `build/campaign-native-twenty/`.
  The earlier separate first-three-level run also passed, including a spike retry.
- Final Linux x64 controls: **all 280 rows passed on source and bundled runtimes**
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
  That CI host had no output device. Actual ARM audio and physical window close
  remain pending the separate private-output PCM and real-main smoke checks.
- Linux control baseline d5499672: **all 280 rows passed** on source and bundled
  runtimes, including inspection of all 1,198 referenced frames per run, separated
  projectile supplements for all five weapons, actual fourteen-case audio output,
  and installed physical window close. Each full run exited 0. Consolidated rows:
  `build/audit-source-d5499672-final/controls-reviewed.tsv` and the corresponding
  `build/audit-packaged-d5499672-final/controls-reviewed.tsv`.
- Missing-output status: **passed on final 88283267**. An isolated empty ALSA configuration
  caused an actual SourceDataLine initialization failure. Physical M was held,
  released and pressed again in all six states; all 19 native frames retain
  unavailable instead of incorrectly claiming on/off. The seven-case run and
  cleanup exited 0. Evidence: `build/audit-source-88283267-missing-audio-footer/REVIEW.md`.
  The earlier 0d3d proof remains at `build/audit-source-missing-audio-footer/`.
  Source and bundled 0d3d runs each completed all 280 automatic cases and exited 0;
  their manual review stopped when the final constructor-order preservation changed
  the JAR. Those incomplete reviews do not establish a final-build pass.
- First actual Mac ARM application control run: **failed** on the d549 baseline.
  All 280 rows completed; 18 failed rows plus one pointer-cleanup error remain
  preserved in `build/ci-mac-native-controls-first/`. A camera-boundary fixture,
  delayed auxiliary-window registration and injected modifier flags caused those
  harness failures. The final 26-case ARM native-app diagnostic subsequently
  passed all automatic checks; every frame was inspected. Its 25 input rows show
  correct motion, dash, M press/release and focus recovery, with raw OS/AWT receipts.
  The lifecycle image exposed a resize/capture race, now fixed in the test harness
  and awaiting the full native-app rerun. Evidence: `build/ci-mac-targeted-88283267/`.
  This filtered diagnostic does not establish all 280 Mac rows.
- Final Linux ARM audio/physical-close coverage, Mac full native controls, source-launch
  equivalence, performance and installed execution: **pending final runs/review**. See PERFORMANCE.md for measurements and
  rejected experiments; no failed measurement is being labeled passed.

## Review findings corrected

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
  hint. The rebuilt candidate is undergoing a fresh visual control audit.
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
  seven native-callback regression tests pass, while real Mac ABI, startup,
  lifecycle and captured-PCM checks are still in progress. Missing native
  libraries and failed output resets now become explicit audio-unavailable
  states without letting mute or window close hang the interface.

The current local candidate JAR is
`88283267eefaf417da4965a1248c1b70b9188effd71f6ee3f69cc2c1911e5bc1`.
Separate `ktlintFormat`, then `check fatJar`, completed successfully with all
43 tests. The complete native campaign and clean-exit evidence remains pinned to
the d5499672 JAR; the earlier ce6f5af4 campaign remains available as historical evidence.
Native playthrough attempts use ordinary input and real campfire retries;
every retry is retained in their results, and no state fixture or teleport counts
as campaign progress.

No finite audit proves the absence of all bugs. Platform facilities that have not
been exercised remain explicitly unverified in the final coverage record.
