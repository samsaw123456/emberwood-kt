# Performance verification

The native performance audit opens the actual Swing window, captures its rendered
output, and uses operating-system keys for movement, jumping, retry, pause and a
three-minute movement/projectile soak. Original level fixtures separately cover
eight regions, four ordinary monster species and six guardians. Fixtures are
performance scenes, not evidence of completing those levels through input.

Run it after `./gradlew check fatJar`, using Java 25:

```sh
env -u WAYLAND_DISPLAY XDG_SESSION_TYPE=x11 xvfb-run -a \
  "$JAVA_HOME/bin/java" --enable-native-access=ALL-UNNAMED \
  -Xms32m -Xmx128m -XX:ActiveProcessorCount=2 \
  -cp build/libs/emberwood-kotlin.jar:build/classes/kotlin/test \
  emberwood.PerformanceAudit
```

On a real desktop, omit the `env ... xvfb-run -a` prefix. The X11 environment is
necessary when using Xvfb from a Wayland session, so Java's Robot captures the
isolated X11 display instead of opening a desktop screencast portal. The audit
uses synchronous painting and a screen capture; `Robot.waitForIdle()` would wait
behind continuous animation and distort command timing.

The default soak is 180 seconds, including all four platform CI jobs.
`-Dperformance.soakSeconds=30` is available for a shorter diagnostic run; it does
not replace the full soak. Results, screenshots and their limits are written under
`build/performance/`. External process RSS can also be measured with
`/usr/bin/time -v` on Linux. A 128 MiB Java heap limit does not mean the complete
process uses 128 MiB. `ActiveProcessorCount=2` limits JVM parallelism; it does not
emulate a particular older processor or cap its clock speed.

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
audit's requested 20 ms measurement sleeps lasted a median 69.137 ms.

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
right-release, pre-left and stopped positions. This further correction awaits
the next native rerun; resource thresholds and sustained input are unchanged.

Linux CI had no audio device; actual audio output is tested separately on the
local PipeWire desktop. The native CI artifacts are under
`build/ci-third-linux-x64/build/performance/` and
`build/ci-third-linux-arm/build/performance/`.
