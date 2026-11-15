# Performance verification

The native performance audit opens the actual Swing window, captures its rendered
output, and uses operating-system keys for movement, jumping, retry, pause and a
three-minute movement/projectile soak. Original level fixtures separately cover
eight regions, four ordinary monster species and six guardians. Fixtures are
performance scenes, not evidence of completing those levels through input.

Run it after `./gradlew check fatJar`, using Java 25:

```sh
env -u WAYLAND_DISPLAY XDG_SESSION_TYPE=x11 xvfb-run -a tools/run_x11_audit.sh \
  "$JAVA_HOME/bin/java" --enable-native-access=ALL-UNNAMED \
  -Xms32m -Xmx128m -XX:ActiveProcessorCount=2 \
  -cp build/libs/emberwood-kotlin.jar:build/classes/kotlin/test \
  emberwood.PerformanceAudit
```

On a real desktop, omit the `env ... tools/run_x11_audit.sh` prefix. The isolated
X11 setup needs Xvfb, Openbox and `xprop`; native keyboard injection uses Python 3
and the platform's input APIs. The X11 environment is
necessary when using Xvfb from a Wayland session, so Java's Robot captures the
isolated X11 display instead of opening a desktop screencast portal. The audit
uses synchronous painting and a screen capture; `Robot.waitForIdle()` would wait
behind continuous animation and distort command timing.

Keyboard injection runs through the shared persistent `PhysicalKeys` helper,
separately from AWT's X11 lock; independent AWT event receipts still establish
when the core commands arrive. Robot captures the actual displayed frames.
Before starting the measurement or sending any physical input, the audit waits
for audio initialization to resolve. A pending provider aborts with no input.
On macOS it also requires a native, nonmodal game window belonging to the exact
process. These checks prevent automation from interacting with an unexpected
permission prompt.

The default soak is 180 seconds, including all four platform CI jobs.
`-Dperformance.soakSeconds=30` is available for a shorter diagnostic run; it does
not replace the full soak. Results, screenshots and their limits are written under
`build/performance/`. External process RSS can also be measured with
`/usr/bin/time -v` on Linux. A 128 MiB Java heap limit does not mean the complete
process uses 128 MiB. `ActiveProcessorCount=2` limits JVM parallelism; it does not
emulate a particular older processor or cap its clock speed.

`completion.json` is the authoritative finish record, with `result`,
`measured_windows`, `soak_seconds`, `failed_scenes`, `failures` and `exception`.
It is cleared before each run, then written after input/window cleanup and
measurement export. PASS requires all 22 windows and no failed assertion or
exception. A missing record means the audit did not complete. This is essential
for the isolated macOS application probe because LaunchServices' successful
`open -W` status alone does not establish the Java audit's result.

The audit requires at least 45 painted frames/second, mean painting within a
16.67 ms frame budget, and simulation progress at least 90% of wall time. Static
menus must make no simulation progress and repaint no more than twice a second.
Retained heap growth after collection must stay below 16 MiB across the soak.

## Baseline and follow-up

The first valid Linux/Xvfb run used Temurin 25.0.5, a 1152×648 content area, a
128 MiB maximum heap and two processors visible to the JVM. All rendered regions,
monsters, guardians, movement, jumping and retry screenshots were inspected.
The three-minute loop stayed playable, completed normal gem pickups and had no
deaths; simulation kept pace with elapsed real time. Retained heap decreased
from 17,283,600 to 14,104,168 bytes. Independently sampled peak process RSS was
260,532 KiB (254.4 MiB).

The baseline **failed** the painting budget: the boar scene averaged 16.722 ms,
and the active soak averaged 34.065 frames/second with 26.550 ms painting. The
other twenty measured windows passed. This identified rendering work for a
measured optimization and rerun; it is not a performance completion claim.
Baseline evidence is retained in `build/performance-baseline/`, with 31
deterministic rendering reference images in `build/render-audit-baseline/`.

A reusable RGB composition buffer was tried and rejected after measurement. It
increased many scenes to 19–25 ms mean painting; the canopy, for example, changed
from 59.443 frames/second and 4.766 ms painting to 43.454 frames/second and
22.174 ms painting. That trial was stopped before the soak once the regression
was clear. Its logs and screenshots remain in `build/performance-buffer-trial/`.
The buffer change was reverted.

The replacement caches nearest-neighbor image resizing, with at most 8 MiB of
cached pixels. All 31 deterministic renderer reference images and the actual
native title screenshot match the baseline pixel for pixel. Original asset files
remain unchanged.

| Measured scene | Baseline frames/s / mean paint | Scaled cache frames/s / mean paint |
| --- | --- | --- |
| Forest region | 55.254 / 16.481 ms | 61.199 / 8.938 ms |
| River region | 58.806 / 11.928 ms | 61.505 / 6.247 ms |
| Three-minute input soak | 34.065 / 26.550 ms | 57.757 / 13.622 ms |

The optimized soak passed every criterion: 179.983 seconds of simulation during
180.013 seconds of wall time, no deaths, and retained heap of 18,866,568 bytes
before / 18,819,856 after. Peak process RSS was 257,636 KiB (251.6 MiB). Process
CPU during the soak averaged 39.192% of one core. Heap and process RSS are distinct
measurements; the small RSS difference between runs is not a memory-saving claim.
These process measurements include Robot and the audit instrumentation alongside
the running game window.

That complete optimized run still **failed** two short frame-budget windows:
the boar scene at 18.147 ms and the warmup at 18.123 ms. The shared eight-CPU host
had load averages around 14–16; a one-second sample measured 3.42% idle CPU and
6.46% I/O wait. Other work was left untouched. This contention is a measured
limitation of the run, not grounds for changing the thresholds or marking those
rows passed. Evidence is retained in `build/performance-scaled-long/`, including
the independent host sample and exact pixel comparisons. A dedicated platform
run or repeat under suitable conditions must resolve the remaining scene checks.

The final verification report must record the optimized build's measurements and
actual native platform runs. macOS and other hardware remain unverified by this
Linux baseline. No finite test establishes performance on every low-resource
machine.

## Native macOS measurements

The subsequent macOS CI runs completed the full audit on both native
architectures with the same 128 MiB heap and two-processor JVM configuration.
Both **failed** the minimum frame-rate criterion in every active scene. Their
static title and pause screens passed, simulation kept pace, and retained heap
did not grow.

| Native runner | Soak frames/s | Mean paint | Simulation / wall seconds | Retained heap before / after |
| --- | --- | --- | --- | --- |
| macOS ARM64 | 18.417 | 5.250 ms | 179.850 / 180.055 | 11,866,632 / 10,706,392 bytes |
| macOS x86-64 | 27.408 | 4.937 ms | 179.950 / 180.060 | 11,568,304 / 11,479,920 bytes |

The ARM64 desktop constrained the content area to 1024×648; Intel used
1152×648. These are real native window measurements, not Linux emulation.
Evidence is retained under `build/ci-third-macos-arm/build/performance/` and
`build/ci-third-macos-intel/build/performance/`.

Low recorded paint time does not prove that native presentation is fast:
`paintNanos` measures the custom drawing body, excluding Swing background
clearing and later buffer presentation. The low frame rates therefore require
further scheduling/presentation diagnosis before macOS performance can pass.
No frame-rate thresholds have been relaxed.

The fourth ARM64 CI run reproduced the failure at 18.132 frames/second and
4.504 ms mean painting during the full soak. Its Java Flight Recording identifies
timer scheduling as the immediate bottleneck: 5,021 recorded `TimerQueue` parks
requested a median 15.988 ms but lasted a median 59.791 ms (79.802 ms at the 95th
percentile). The event thread spent 241.835 seconds waiting for its event queue
during the 278-second recording, versus 0.265 seconds waiting for Metal flushes.
All four periodic thread dumps place it in `EventQueue.getNextEvent`. Even the
audit's requested 20 ms measurement sleeps lasted a median 69.137 ms. The JFR's
resident-set event reports a process high-water mark of 343,015,424 bytes
(327.1 MiB), distinct from the 128 MiB heap cap and roughly 12.2 MiB retained
heap after the soak.

A separate 30-second Metal-disabled diagnostic did not solve this: its timer
parks still lasted a median 55.703 ms for 15.988 ms requested, and mean paint costs
rose to roughly 21–33 ms. This diagnostic is not a shipped setting. The recordings
and screenshots are preserved under `build/ci-fourth-macos-arm/build/performance/`
and `performance-metal-disabled/`. Reproduce the scheduling inspection with:

```sh
"$JAVA_HOME/bin/jfr" view thread-cpu-load path/to/pacing.jfr
"$JAVA_HOME/bin/jfr" print --json \
  --events jdk.ThreadPark,jdk.JavaMonitorWait,jdk.ThreadSleep path/to/pacing.jfr
```

These observations establish timer oversleep, but do not by themselves establish
App Nap or the runner's process policy. Apple documents timer throttling as one
effect of [App Nap](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/power_efficiency_guidelines_osx/AppNap.html).
The next diagnostic records native foreground/background-policy observations for
only the launched Java PID, alongside `window-focus.tsv` assertions that each
measurement begins and ends with a visible, active, keyboard-focused window.
A separate `taskpolicy -a` run compares Apple's application resource policy;
the [Apple command documentation](https://github.com/apple-oss-distributions/system_cmds/blob/main/taskpolicy/taskpolicy.8)
describes that scope. The default full run and its failures remain authoritative.
No global power setting, production rendering workaround or busy-spin loop is
introduced to obtain a passing number.

## Native Linux CI measurements

Both dedicated Linux architectures passed all 22 resource-measurement windows,
including the full three-minute soak. x86-64 passed the complete audit. ARM64
failed only the separate physical A/release core-loop assertion; its screenshots
showed correct leftward movement but did not establish completed braking at the
fixed-delay check. That run remains failed, and its result is not relabeled as a
complete pass.

| Native runner | Soak frames/s | Mean paint | Retained heap before / after |
| --- | --- | --- | --- |
| Linux x86-64 | 62.098 | 1.628 ms | 19,704,800 / 19,598,128 bytes |
| Linux ARM64 | 62.136 | 1.835 ms | 19,705,512 / 19,645,928 bytes |

The core loop now records observed operating-system key receipt and separately
waits for braking/landing/retry, all with bounded timeouts. Actual receipt and
recovery timings are written to `core-input-latency.tsv`. The fourth native run
then passed the complete audit on both architectures, including all 22 windows
and the physical core loop:

| Native runner | Soak frames/s | Mean paint | Process CPU, one core | Retained heap before / after |
| --- | --- | --- | --- | --- |
| Linux x86-64 | 62.120 | 1.724 ms | 10.372% | 19,719,392 / 19,555,880 bytes |
| Linux ARM64 | 62.172 | 1.912 ms | 11.117% | 19,635,256 / 19,586,800 bytes |

Evidence is retained under `build/ci-fourth-linux-x64/build/performance/` and
`build/ci-fourth-linux-arm/build/performance/`. These passes do not erase the
previous failed run.

The Mac timing investigation also exposed a separate audit assumption: equal
requested left/right hold durations need not return to the same location when
native sleeps overshoot. The core loop now requires each direction to travel
more than 65 pixels from its own observed starting position, with left-release
recovery additionally requiring zero horizontal velocity. It still excludes the
world wall (`x > 40`), so reaching a
boundary cannot masquerade as braking. `core-positions.tsv` retains the initial,
right-release, pre-left and stopped positions. The fifth native Linux run passed
the corrected core loop and all 22 measurements on both architectures: its soak
was 62.118 frames/s at 1.703 ms mean paint on x86-64, and 62.196 frames/s at
1.681 ms on ARM64. Evidence is retained under
`build/ci-fifth-linux-x64/build/performance/` and
`build/ci-fifth-linux-arm/build/performance/`.

Linux CI had no audio device; actual audio output is tested separately on the
local PipeWire desktop. The native CI artifacts are under
`build/ci-third-linux-x64/build/performance/` and
`build/ci-third-linux-arm/build/performance/`.

## Intel macOS microphone prompt and audio initialization

The fourth Intel run is additionally invalid as unobstructed foreground testing:
its installed-app desktop screenshot shows an unexpected microphone permission
prompt. Permission was not granted. The game only requests a `SourceDataLine`
for playback; it does not request recording. The JFR thread dumps show the audio
thread blocked inside `DirectAudioDevice.nOpen` at 61, 123, 184 and 247 seconds,
then later blocked in start/close. The event-dispatch thread was blocked in
provider close at 309–433 seconds and native close at 495–558 seconds. This can
also interfere with focus and cleanup.

The previous summary text “opened; original cues enabled” used a null error as
its condition and therefore did **not** prove initialization completed. The audit
now distinguishes initialization from an opened, running playback line using
`Audio.ready`; actual audible output is established by the separate process-only
PCM audit. The audio-state fixture waits for that readiness with a bounded
timeout rather than treating the absence of an error as success.

OpenJDK's direct mixer eagerly probes both playback and capture format support.
For its synthetic default mixer, capture-format probing queries the default
input device even when the caller only requested playback. A related
[CoreAudio output-only microphone prompt was fixed in RustAudio](https://github.com/RustAudio/cpal/pull/1070/files)
by avoiding that default-input query. This is a supported diagnosis to test,
not yet proof that a proposed output-device selection resolves Emberwood's
prompt. The current default output must be preserved; microphone permission
and silent disabling of sound are not acceptable substitutes for a verified fix.

Evidence: `build/ci-fourth-macos-intel/build/bundle-launch-macos/desktop-with-dock.png`,
`build/ci-fourth-macos-intel/build/performance/pacing.jfr` and
`build/mac-intel-thread-dumps.txt`.

The shutdown fix publishes the playback line only after initialization completes
and performs potentially blocking native close on a daemon thread. Two hardware
fixtures block initialization and active-device close independently; both prove
that Quit returns within the bounded test deadline and the device is released
when the provider resumes. These regressions passed in the centralized 28-test
run. They do not substitute for the pending native Mac microphone-prompt fix or
its actual startup, PCM and application-close verification.

## Fifth Mac ARM foreground observations

The next default run still failed all active FPS windows: its 180-second soak
rendered 18.348 frames/s at 4.879 ms average paint and 19.872% process CPU. All
44 before/after AWT focus checks passed. All 258 native samples after launch
reported an active, visible, frontmost regular application, with Darwin
background policy zero and nice priority -10. The physical core checks passed.

Its 5,054 TimerQueue waits requested a median 15.990 ms and lasted 58.926 ms
(p95 79.869 ms). The 3,672 requested 20 ms harness sleeps lasted a median
69.688 ms. The event-dispatch thread spent 239.019 seconds parked. Simple focus
loss or an explicitly backgrounded process does not explain these observations;
they still do not establish a particular OS timer-policy cause.

All 28 native screenshots were inspected; no permission prompt obscures this
ARM run. The attempted application-policy comparison did not launch because the
hardcoded `/usr/bin/taskpolicy` path was absent, so there is no policy result to
compare. The next comparison uses an isolated LaunchServices application copy
with the unchanged production JAR, assets and bundled runtime.

That bundled runtime intentionally omits management and JFR modules. The audit
therefore uses `ProcessHandle.info().totalCpuDuration()` for process CPU (and
fails explicitly if unavailable), plus `Runtime.totalMemory() - freeMemory()`
for used heap. Limits, scenes and input remain unchanged. Full-JDK runs can
still retain JFR externally; the exact bundled-runtime probe does not expand the
shipped module set solely to enable instrumentation.

Evidence: `build/ci-fifth-macos-arm-diagnostics/performance/`,
`build/mac-arm-fifth-pacing-analysis.json` and
`build/mac-arm-fifth-visuals/REVIEW.md`.

## ARM application-launch diagnostic

The isolated LaunchServices copy of the actual ARM64 app passed all 22 windows
with a 30-second diagnostic soak. It retained the shipped runtime, original
assets and production JAR `d5499672…30af`, with the same 128 MiB heap cap and two
processors visible to the JVM. The soak measured 51.432 frames/s and 4.835 ms
mean painting; the slowest active scene measured 49.534 frames/s. Retained heap
changed from 14,704,016 to 14,517,440 bytes. Independent native process sampling
recorded a peak RSS of 266,448 KiB across 120 samples.

All 28 rendered frames were inspected, including the core movement, jump, retry,
idle menus, regions, monsters, guardians and soak. The authoritative completion
record reports PASS with no failed scenes, and the external controller completed
cleanup. This distinguishes the actual application context from the earlier
raw-JVM timing failures without changing production timer behavior. This short
diagnostic does not establish the full 180-second soak or Intel application result.

Evidence: `build/ci-native-profile-arm-initialized/performance-native-app/`,
including `completion.json`, `native-app.json`, `measurements.tsv`, native RSS
samples and the frame-by-frame `root-review/` journal.

The subsequent **full 180-second ARM64 application run passed all 22 windows**
with the same production JAR, assets, runtime, heap and processor limits. The soak
measured 51.080 frames/s, 5.039 ms mean painting and 45.546% of one CPU core;
simulation advanced 180.017 seconds during 180.010 seconds of wall time. Every
active scene exceeded 50 frames/s, with the slowest at 50.166, and the highest
mean paint cost was 6.528 ms. Title and pause made no simulation progress or
repaints during their six-second windows; their before/after images are identical.
Their measured process CPU was 8.480% and 13.153%, respectively.

Retained heap rose by 508,232 bytes, from 14,600,688 to 15,108,920, below the
16 MiB growth limit. Independent exact-PID RSS sampling recorded a maximum of
281,632 KiB (275.0 MiB) across 257 samples; this is a sampled maximum, not the OS
high-water mark. All live native observations reported an active, visible,
frontmost app at nice priority zero. All 28 audit frames and the additional native
startup capture were independently inspected, including movement directions,
jump, retry, all scene fixtures and the completed soak. Cleanup and the explicit
completion record passed. No production timer or global policy change was needed.

Full-run evidence: `build/ci-native-profile-arm-full/performance-native-app/`,
including `independent-review.md` and `independent-review.json`. The Intel native
application result and performance on other hardware remain unverified by this
ARM64 pass; the earlier raw-JVM failures remain recorded above.

## Comparing the two Mac launch routes

The README's `./emberwood-kotlin` source launcher directly executes its private
Java runtime. The native application pass above does not establish current
performance for that separate route. A same-runner comparison is available after
building the production JAR, test classes and native package:

```sh
python3 tools/mac_profile_compare.py --java-home "$JAVA_HOME" --soak-seconds 180
```

This runs the raw private-JDK process first, then an isolated native app through
the existing LaunchServices driver. Both use the unchanged production JAR and
test classes, the same 128 MiB heap/two-processor limits and full audit thresholds.
Both use the external controller for real input and screenshots, with the audio
readiness and exact-PID nonmodal-window guard before input. Neither uses JFR,
extra rendering flags, resource-policy changes or production pacing changes.
The raw route retains the source runtime while the app retains its shipped
runtime; this measures the two actual launch contexts rather than attributing
any difference to a single runtime or operating-system mechanism.

Results are separated under `build/performance-launcher-comparison/raw-jvm/`
and `native-app/`, with an aggregate `comparison.json`. Failed raw measurements
remain failed even if the native app passes. The next launch is prevented if
owned-process, input/capture or new-window cleanup cannot be established.
Run `43710832465` completed both routes on the same ARM64 runner at production
JAR `0d3d50e7…3b89`. Both completed all 22 windows and the full 180-second soak,
with the same test classes, 128 MiB heap, two visible processors and 1024×648
content. The direct JVM route failed every active frame-rate window; the native
app passed all 22. The aggregate result correctly remains failed.

| Route | Soak frames/s | Mean paint | Process CPU, one core | Sampled peak RSS |
| --- | --- | --- | --- | --- |
| Direct private-JDK JVM | 17.903 | 5.240 ms | 24.792% | 267,888 KiB |
| Native app through LaunchServices | 51.662 | 6.388 ms | 54.733% | 275,664 KiB |

Both routes kept simulation time aligned with wall time, had no retained heap
growth, and held title/pause completely still. All 56 audit frames plus three
startup/cleanup captures were independently inspected; the native startup capture
catches a canvas before its first paint, followed by complete title frames.
Both processes remained active and frontmost in live observations. The raw JVM
had nice priority −10 and the app zero, with process policy zero for both. These
observations establish a launch-context performance difference, not App Nap as
its specific cause. No production timer change follows from this comparison.

Evidence and exact PNG/metric journals are under
`build/ci-launcher-comparison-arm-0d3d50e7/performance-launcher-comparison/`.
This result confirms that the direct-Java source launch route needs correction;
it is not verification of the subsequently restored audio initialization order.

## Final Linux artifact review before the footer correction

Run `43708730152` passed all 22 windows and the full 180-second soak on both Linux
architectures at production JAR `d5499672…30af`. All 28 screenshots per platform
were independently inspected, and both static-menu image pairs are identical.

| Runner | Soak frames/s | Mean paint | Process CPU, one core | Retained heap before / after |
| --- | --- | --- | --- | --- |
| Linux x86-64 | 62.107 | 1.692 ms | 10.299% | 20,591,032 / 20,436,616 bytes |
| Linux ARM64 | 62.178 | 1.745 ms | 10.732% | 20,102,984 / 20,083,656 bytes |

The slowest active windows were 61.938 and 61.978 frames/s; the highest mean
paint costs were 2.287 and 2.037 ms, respectively. Both ran with Java 25.0.5,
128 MiB maximum heap, two visible processors and 1152×648 content. Physical
movement, braking away from the world edge, jump, retry and pause recovered
correctly. These CI hosts had no audio output line, so their CPU measurements
exclude active audio playback. They also did not record process RSS; the heap
cap is not a complete process-memory measurement.

Evidence and independent frame/metric manifests are in
`build/ci-final-linux-x64/build/performance/independent-review/` and
`build/ci-final-linux-arm64/build/performance/independent-review/`. The known
unavailable-audio footer inconsistency is visible in this older build; these
passes are not relabeled as verification of its subsequent footer correction.
