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
screen capture. The same source and packaged control audit runs in the native
Linux/macOS CI matrix. Inspect its results; a workflow definition is not evidence
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
- Build, lint and automated tests: **passed**, 41 tests. The simulation campaign
  reaches all 20 levels, all 60 acorns and 20 hidden fireflies, all six guardians
  and all 13 equipment unlocks with zero retries. Optional gems collected by this
  route: 196 of 378. This is simulation evidence, not a physical-input playthrough.
- Artwork review: all eight regions, six guardians, four regular monsters and
  thirteen equipment appearances were rendered and visually inspected.
- Actual Linux sound: the fourteen M/Sound cases passed on the previous recorded
  source and bundled candidates. Captured game-only PCM proves mute, interruption
  of an active cue and restored output, including the original gem pitches.
  The new audio candidate is undergoing its own repeat; see PERFORMANCE.md.
- Linux installation and native launcher: **passed** with invalid global Java
  and internet socket creation blocked. The separate application opens through
  the desktop registry and closes using physical Alt+F4. See PACKAGING.md.
- Zed onboarding: **passed in Zed 1.28.1** with isolated editor data. The actual
  task picker loads Play Emberwood Kotlin; selecting it launches the game. Return,
  movement, jump, pause and window close were exercised in that launched window.
  Screenshots are retained in `build/zed-audit/`.
- Native campaign: **all twenty levels passed** on JAR `ce6f5af4…` using
  normal-rate physical OS keys from the title through victory. It collected all
  60 acorns, all 20 fireflies, 199/378 optional gems, and defeated
  all six guardians. One actual fall in Sunlit Ridge exercised checkpoint recovery;
  final time was 08:21 with one retry. All twenty completion frames and guardian
  before/defeated pairs were inspected. Evidence: `build/campaign-native-twenty/`.
  The earlier separate first-three-level run also passed, including a spike retry.
- Final native controls, performance and macOS installed
  execution: **pending final runs**. See PERFORMANCE.md for measurements and
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
`d5499672bb8cd4dd0708f5701d89cbf7dc81f4c3f480aa728c456c5b74bb30af`.
Separate `ktlintFormat`, then `check fatJar`, completed successfully with all
41 tests. Original-resource verification and the six installer fixtures passed
again. The complete native campaign evidence is pinned to the earlier JAR
`ce6f5af4fba0455e977936eead904e24608083fc8b256d4d07b406aaddbd3bf8`.
Native playthrough attempts use ordinary input and real campfire retries;
every retry is retained in their results, and no state fixture or teleport counts
as campaign progress.

No finite audit proves the absence of all bugs. Platform facilities that have not
been exercised remain explicitly unverified in the final coverage record.
