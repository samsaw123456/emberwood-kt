# Verification record

This is a separate port of Emberwood v1.3.1, original commit
`7146ac838c0db21afe9406ea4546cb094aa9721f`. This port does not modify that
project; unrelated concurrent changes in its checkout are preserved.
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

The production JAR is
`ae9686cb8387d5c9f61f4a6cb73d4f9a99803fe6e93e2ce519d495d59b9bdb8c`.
Linux verification is complete for the recorded scope below. Both Macs pass the
ordinary-game movement/menu/Quit check; their full current control, PCM and
performance matrix remains pending in
[run 43750771895](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750771895).
The per-platform [coverage table](controls-audit.tsv) preserves that distinction.

| Check | Current result and evidence |
| --- | --- |
| Formatting, lint and build | Separate `ktlintFormat`, then `check fatJar`: 67 Kotlin/JVM tests pass. The current Python suite passes 206 tests with two macOS-SDK fixtures skipped on Linux; Ruff checks all 59 Python files. Actual native SDK execution is a separate CI gate. Log: `build/logs/python-final-app-name-budget.log`. |
| Assets and parity data | All 2,107 migrated resources retain their hashes; 20 levels, 60 acorns, 378 gems and 20 hidden fireflies remain authoritative. `tools/check_assets.py` verifies the manifest. |
| Every Linux control | Source and bundled runtimes on x86-64 and ARM64 each pass all 280 unfiltered cases. All 1,214 referenced frames per route were inspected and hashed, with exact disjoint journals and declared review scale. [CONTROLS.md](CONTROLS.md) maps the four canonical directories and receipts. |
| Actual Linux audio and OS close | All 56 physical M/Sound cases across four routes pass, with 336 game-only WAVs and all eight waveform sheets independently checked. All 36 ordinary Main images were inspected; physical Alt+F4 leaves no window and all four Java/driver exits are 0. Exact matching-app identities and limits are recorded in [AUDIO.md](AUDIO.md). |
| Complete native campaign | All 20 levels, six guardians and 60 acorns completed through normal-rate physical input. All 55 originals inspected, including every level entry/completion, guardian before/after, one real fall/retry and the ending: 08:19, one retry, 201/378 gems and all 20 fireflies. Receipt: `build/ci-campaign-ae9686cb/campaign-native/review/native-review.json`. |
| Low-resource Linux profile | Both source-JVM routes pass all 22 measured windows, including a 180-second soak with a 128 MiB heap and two visible processors. All 56 game captures inspected. These measure completed Java paints, not continuous display-frame rates; no separate bundled profile or process-RSS measurement is claimed. [PERFORMANCE.md](PERFORMANCE.md) retains exact metrics and limits. |
| Installed Linux launcher | The actual installed app runs through `gtk-launch` with invalid global Java and child-only INET/INET6 denial. Start, D/release, Space/landing, pause and physical Alt+F4 pass; all nine originals opened full-size. Receipt: `build/installed-user-audit-ae9686cb/review.json`. |
| Actual editor task | Zed loads the Play Emberwood Kotlin task and launches the game; Start, D/release, Space/landing, pause and physical Alt+F4 pass while Zed remains open. All eleven originals opened full-size. Receipt: `build/zed-audit-ae9686cb/review.json`. |
| Ordinary macOS game | Both architectures pass bounded A/Left movement, interior recovery, correctly named native About/Hide/Quit items, Services absence, physical Escape and Command-Q, with no cleanup signals or remaining game window/PID. This is targeted actual-Main evidence, not the full inventory. Exact journals follow below. |

The full Linux controls and campaign are from
[run 43747640143](https://github.com/samsaw123456/emberwood-kt/actions/runs/43747640143).
The campaign contains 3,427 physical input batches / 3,732 edges, with no state
fixture, teleport or direct simulation step. Its chapter-five fall uses natural
checkpoint recovery; it is not R-key evidence. Its pipeline/job succeeds under
`bash -e -o pipefail`; no independent per-PID numeric campaign exit receipt exists.
The detached installed/editor launches likewise prove PID/window disappearance,
without a captured numeric JVM exit code.

Current macOS ordinary-game evidence is from
[run 43750035990](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750035990):

- ARM: `build/ci-main-name-budget-ae9686cb-macos-arm/build/main-movement-native-app/independent-movement-review/review.json`.
  All 64 originals were inspected at the scales recorded in the journal. A/Left
  holds last 351.724/358.373 ms; native stream timestamp gaps around hold/recovery
  are at most 34.780/35.411 ms.
- Intel: `build/ci-main-name-budget-ae9686cb-macos-intel/build/main-movement-native-app/root-review/review.json`.
  All 77 originals were inspected: 66 stream frames in 576-pixel cells and eleven
  other originals at full size. A/Left holds last 352.781/350.849 ms; corresponding
  native gaps are at most 34.850/34.700 ms.

Both runs use ordinary Main, no scene fixtures, forced painting, rendering override
or live sampler. The fox moves left and rests on interior ground before the native
menu is physically opened. Command-Q removes the game with its modifier released;
`open -W` returns 0, which is not a separate kernel JVM exit measurement. Finite
successful observations do not prove uniformly smooth behavior under every load.

The six-case focused ARM run 43747451930 and unchanged Intel repeat 43748162685
also pass their strict native menu probes: only the exact Services item is removed,
and all eight remaining sibling identities/actions/keys survive preparation and
show. The first Intel trial's A capture overrun remains a failed trial; it is not
relabeled by the later pass. The failed `375ae227` registration assertion and the
native observations that corrected it are retained in the history. Current
production removes the unused Services menu item without clearing registration;
no graphics override, permission bypass or global setting is used.

## Earlier evidence

[Historical verification and investigations](history/verification-investigation.md)
retain the d549/882/7d baselines, failed candidates and timing trials, their exact
limitations, and the diagnostics that exposed jump ordering and native Services waits. They are not substitutes for the
current runnable build's inventory and campaign above.

## Review findings corrected

- On Intel macOS, the first arrow could block AppKit while it populated the unused
  Services menu through a synchronous VoiceShortcutClient request. The game now
  detaches only that exact submenu on AppKit using public APIs. Native probes
  preserve all other menu identities/actions; ordinary Main movement and physical
  menu/Quit pass on both architectures. The complete current matrix is still required.
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
  hint. Every current Linux control frame was inspected after this fix; earlier Mac
  reviews retain their build-specific scope.
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
  baseline; the retained 7d9668ed build repeated them successfully on both
  architectures. Current ae9686cb Linux output is closed; current Mac PCM remains
  pending in the matrix linked above. Missing native
  libraries and failed output resets now become explicit audio-unavailable
  states without letting mute or window close hang the interface.

The current ae9686cb build passes separate `ktlintFormat`, then `check fatJar`,
with all 67 Kotlin/JVM tests. Its complete Linux inventories and native
twenty-level campaign are recorded above; the current full Mac matrix remains open.
Native playthrough attempts use ordinary input and real campfire retries;
every retry is retained in their results, and no state fixture or teleport counts
as campaign progress.

No finite audit proves the absence of all bugs. Platform facilities that have not
been exercised remain explicitly unverified in the final coverage record.
