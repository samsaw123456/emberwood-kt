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

The default soak is 180 seconds. `-Dperformance.soakSeconds=30` is available for
a shorter CI pass. Results, screenshots and their limits are written under
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
