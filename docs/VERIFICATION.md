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
- Kotlin formatting: **passed**. The final source is formatted with ktlint.
- Final compiled tests, native controls, actual sound, performance, packaged
  launch and macOS execution: **pending final runs**. Detailed results will replace
  this entry after execution and visual inspection.

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

No finite audit proves the absence of all bugs. Platform facilities that have not
been exercised remain explicitly unverified in the final coverage record.
