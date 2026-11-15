# Performance verification

## Current validation status

The current candidate JAR is
`ae9686cb8387d5c9f61f4a6cb73d4f9a99803fe6e93e2ce519d495d59b9bdb8c`.
It detaches the exact unused macOS Services submenu while preserving its native
registration and sibling commands. All 67 unit tests pass. Actual startup-error
acknowledgement passes on both Macs. Fresh Linux performance, PCM, complete control
review and Main smoke verification are complete. The current ordinary Mac Main
launch also passes bounded movement, corrected application-menu labels and physical
Quit on both architectures.
The complete native Mac control inventory and performance/audio remain pending in
the [current full matrix](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750771895).

| Current ae9686cb source-JVM route | Completed Java paints/s during 180 s soak | Mean Java paint | CPU, one core | Retained heap before → after |
| --- | --- | --- | --- | --- |
| Linux x86-64 | 62.071 | 1.832 ms | 9.993% | 20,601,656 → 20,628,768 bytes |
| Linux ARM64 | 62.184 | 1.749 ms | 10.866% | 20,283,208 → 20,194,744 bytes |

Both profiles pass all 22 windows with a 128 MiB heap and two visible processors.
Each route's 1,076 buffered observations independently reproduce the aggregate
metrics; no active interval of at least 100 ms falls below 45 completed Java
paints/s. These are Java painting rates, not continuous display-frame measurements.
All 56 original game captures were inspected in labeled 596 px overview cells,
with four critical originals also opened at full size. Title/pause idle image
pairs are pixel-identical. This job has no audio output device and records neither
process RSS nor GC logs; the separate physical PCM runs do not add playback cost
to these measurements. Only one source-JVM profile per architecture was measured,
not a separate bundled profile. Evidence:
[run 43747640143](https://github.com/samsaw123456/emberwood-kt/actions/runs/43747640143),
`build/ci-final-ae9686cb-linux-{x64,arm64}/build/performance/independent-review/`.

The [ordinary Main repeat 43750035990](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750035990)
passes the unchanged physical-hold, pixel-motion, release, zero-skipped-image and
cleanup requirements on both Macs. Actual A/Left holds last 351.724/358.373 ms on
ARM64 and 352.781/350.849 ms on Intel. Native stream timestamp gaps around those
holds and recovery are at most 34.780/35.411 ms and 34.850/34.700 ms, respectively.
Both foxes visibly travel screen-left, stop on interior ground and remain at rest.
Only after this movement observation, a physical click opens the actual app menu:
About/Hide/Quit correctly identify Emberwood Kotlin and Services is absent.
Physical Escape closes the menu; Command-Q then closes the game, releases the
modifier and leaves no window or cleanup signal. The `open -W` launcher returns
zero; this is not a separately observed kernel JVM exit status.

All 64 ARM originals were hash-checked and inspected: 54 stream images and six
ordinary images in ten labeled 512 px overview sheets, plus the full-size title,
three menu desktops, cleanup desktop and three critical movement originals.
The Intel review covers all 77 originals: 66 stream images in 576 px cells and
eleven other originals at full size. This is finite ordinary-game evidence,
without fixtures, forced painting, pipeline overrides or a live native sampler;
it does not prove every frame is smooth under every load or replace the complete
control inventory. Review journals:
`build/ci-main-name-budget-ae9686cb-macos-arm/build/main-movement-native-app/independent-movement-review/`
and `build/ci-main-name-budget-ae9686cb-macos-intel/build/main-movement-native-app/root-review/`.

The earlier, retained ordinary Intel Main observation of this candidate shows bounded A and
Left holds (352.79/355.83 ms until the key-up post), screen-left movement and
interior recovery. Native stream timestamps continue across those intervals;
their largest gaps are 34.91/35.32 ms. However, the image writer skipped two
requested samples, so the unchanged completeness gate rejects the run before
application-menu inspection or physical Quit. This is partial evidence, not a
completed movement/menu audit or a claim that intermittent stalls are excluded.
The first ARM attempt displays the correct title but stops before input because the
initial diagnostic accepted only Intel's window width. The reader now supports
the measured ARM letterbox geometry without resampling images or changing motion
thresholds. Its [native repeat 43748487574](https://github.com/samsaw123456/emberwood-kt/actions/runs/43748487574)
passes both bounded held/released movement observations with no skipped stream
images. Physical application-menu inspection then finds Services absent but
About/Hide/Quit incorrectly named MainKt, so the run fails before physical Quit.
The shared app builder now supplies the complete application name; its native
menu repeat passes as recorded above. These failed attempts and timing receipts are retained in
`build/ci-main-detachment-ae9686cb-macos-{arm,intel}/build/main-movement-native-app/`.
The ARM geometry/menu evidence is in `build/ci-main-geometry-ae9686cb-macos-arm/`.

The [focused Intel repeat 43748162685](https://github.com/samsaw123456/emberwood-kt/actions/runs/43748162685)
passes all six direction/start/lifecycle cases and the strict native menu probe.
All 51 retained stream images were inspected in labeled half-size sheets, with
four critical originals also inspected at full size. The first held Left nonce
reaches the native stream 122.8 ms after its Java paint; the largest native
timestamp gap around that hold is 80.0 ms. This finite fixture-based observation
does not replace ordinary Main or the complete control inventory. Its independent
review is retained in
`build/ci-controls-detachment-repeat-ae9686cb-macos-intel/build/controls-capture-native-app/independent-stream-review/`.

The preceding candidate `375ae227` failed native startup because it also required
the registration getter to become null immediately after a nil assignment.
The native observations on both Macs instead retain the same detached pointer
until the window is shown. The corrected candidate checks actual detachment and
sibling preservation without changing registration. No movement or release
threshold has been relaxed.

Both actual Intel startup-error desktop images from that failed candidate were
inspected; owned SIGTERM cleanup clears the dialog, but supplies no physical
acknowledgement proof. Its ordinary Main launcher did not redirect Java stderr,
so the original exception is not independently retained there. Separate forced
native-access-denial probes on both Macs verify the expected exception and error
dialog, but reject the accessibility snapshot before input. A reporting-only
correction retains those raw fields. The subsequent ARM receipt identifies an
untitled Swing button whose accessibility name is exposed through its label,
rather than `AXTitle`. The reader now retains `AXDescription` and still requires
the exact error text and one unambiguous enabled OK button. The subsequent
[both-Mac run 43748219576](https://github.com/samsaw123456/emberwood-kt/actions/runs/43748219576)
passes real Return/release and exact-PID kernel exit 1, with no cleanup signals or
remaining windows. All four original error/cleanup desktops were inspected at
full size. These isolated-copy denial tests prove the error path, not ordinary
gameplay. Journals are in
`build/ci-startup-label-ae9686cb-macos-{arm,intel}/build/startup-failure-native-app/independent-review/`.
All failed evidence remains preserved.

The following measurements and investigation belong to the retained baseline JAR
`7d9668edebc108b5d3f033f20180874942cea852676f1199a3210dd24e2f6582`.
That build fixed release-then-press ordering for a new jump within one simulation
tick. Its Linux and both native Mac launch routes completed performance and
audio review. Its Intel control review remained unfinished. These results do
not establish that the new candidate passes; the first Intel failure and
transient slow intervals remain recorded below.

These rates count **completed Java paint calls per second**, not continuously
measured native presentation FPS. The retained captures prove those individual
images were presented; they do not measure every displayed frame. On Intel,
the later control trace found a 3.060-second native surface-publication delay
while Java paint calls continued. Passing paint-throughput averages therefore
do not establish smooth on-screen pacing. A subsequent unchanged-Main probe
also reached the left boundary after a promptly released Left command, with a
3.123-second stream gap. Baseline Intel movement/presentation remained unresolved.
The next live native sample identifies an AppKit Services/Shortcuts synchronous
wait during the continuing stall; the current candidate's separate evidence is
listed above.

| Retained 7d9668ed build and launch route | Completed Java paints/s during soak | Mean Java paint | CPU, one core | Retained heap before → after |
| --- | --- | --- | --- | --- |
| Linux x86-64 | 62.179 | 1.189 ms | 7.872% | 20,540,584 → 20,481,336 bytes |
| Linux ARM64 | 62.177 | 1.691 ms | 10.650% | 20,129,824 → 20,011,392 bytes |
| Mac ARM64, cached source app | 51.050 | 6.029 ms | 45.564% | 14,564,632 → 15,059,488 bytes |
| Mac ARM64, packaged app | 51.197 | 5.113 ms | 49.234% | 14,701,416 → 14,700,704 bytes |
| Mac Intel, cached source app, controlled repeat | 55.732 | 5.881 ms | 96.536% | 14,944,904 → 14,797,168 bytes |
| Mac Intel, packaged app, controlled repeat | 57.235 | 4.700 ms | 85.578% | 14,646,896 → 14,838,896 bytes |

Both Linux routes passed all 22 windows and the full 180-second soak with a
128 MiB heap, two visible processors and 1152×648 content. All 56 original game
frames were visually inspected. The slowest active window was 61.962 frames/s
on x86-64 and 61.972 on ARM64. These hosts had no output line, so their CPU
measurements exclude audio playback; separate actual PCM proof does not add that
cost to these numbers. Process RSS was not recorded. Independent measurements,
original frame hashes and journals are retained in
`build/ci-final-7d9668ed-linux-{x64,arm64}/build/performance/independent-review/`.

Both Mac ARM routes passed all 22 windows and their full 180-second soaks with
the same heap/processor limits and a ready audio output. Their slowest active
windows were 49.977 and 49.673 frames/s. All 58 original captures were inspected,
including the ordinary native startup menus; no rendered defect was found.
The source/package runtime trees match. Peak sampled RSS was 265,824/270,672 KiB,
respectively, across 257 samples each; this is not an OS high-water measurement.
The 1024×648 content remains letterboxed correctly. Evidence and exact hashes:
`build/ci-native-final-7d9668ed-macos-arm/build/performance-{source,native}-app/independent-review/`.

The first retained baseline Intel cached-source profile failed its opossum boss window:
40.729 frames/s against the unchanged minimum of 45. Its mean paint time was
10.489 ms, and its full 180-second soak passed at 56.249 frames/s, 5.669 ms paint
and 88.760% of one CPU core. All 22 windows completed. Sampled RSS peaked at
198,328 KiB; retained heap fell from 14,838,840 to 14,426,608 bytes.

All 29 captured originals were inspected, including the initial empty client
window before the title draws. The 28 game frames render correctly. Every
before/after focus check and every finished-launch native observation stayed
active and frontmost. The adjacent boar window also slowed, then the wolf scene
recovered. The renderer, assets, simulation and audio class bytes match the
previous build. The failed run lacks GC and interval timings, so neither garbage
collection nor host contention is established as its cause.

This failure remains recorded in
[run 43725299181](https://github.com/samsaw123456/emberwood-kt/actions/runs/43725299181),
with independent evidence in
`build/ci-native-final-7d9668ed-macos-intel/build/performance-source-app/independent-review/`.
The controlled Intel source/bundle [repeat 43726910417](https://github.com/samsaw123456/emberwood-kt/actions/runs/43726910417)
passed all 22 gates on each route with the same production JAR/runtime, limits
and 180-second soak. All 58 originals were inspected. The package startup capture
is initially empty; its subsequent title and all 28 game frames render correctly.
Source/package sampled RSS peaked at 202,692/210,776 KiB. Their slowest complete
active windows measured 45.551/55.088 frames/s; the opossum scenes recovered to
54.750/57.760 frames/s. Both output lines were ready and running.

Test-only buffered counters independently reproduce every aggregate from 1,076
sample points per route. They also expose transient slow intervals: 43/978 source
and 9/983 package active intervals of at least 100 ms fall below 45 frames/s.
The worst source interval spans 693.963 ms at 10.087 frames/s and 59.203 ms mean
paint; the worst package interval spans 322.075 ms at 27.944 frames/s. Neither
overlaps a logged GC/safepoint. Maximum GC pauses of 76.588/33.018 ms occur
elsewhere. These observations do not establish whether the earlier failure or
transients came from rendering, JVM compilation, native presentation or host
scheduling. Aggregate passes are not a claim of constant frame pacing.

Independent counter checks, logs, frame hashes and journals are retained in
`build/ci-native-repeat-7d9668ed-macos-intel/build/performance-{source,native}-app/independent-review/`.
The repeat later failed one of 280 control cases after stale captures prolonged
a held Left command; audio was skipped in that matrix. A separate baseline
[audio run](AUDIO.md) subsequently passed all fourteen cases. The subsequent
[control run 43732405531](https://github.com/samsaw123456/emberwood-kt/actions/runs/43732405531)
still fails only the Left case. Its retained first/latest rejected images show
the entire scene unchanged while simulation advances; moving the nonce into
the game's own paint pass did not resolve it. Screenshot caching versus actual
presentation delay remained unresolved at that point. The subsequent bounded
[stream comparison 43736264766](https://github.com/samsaw123456/emberwood-kt/actions/runs/43736264766)
reproduced the delay in both capture paths: one streamed game image is
pixel-identical to the stale screenshot. Java completed 140 newer paint passes
before fresh native pixels appeared 3.060 seconds later. Thirteen logged
safepoints total 182 ms; they do not alone explain that gap. All 42 retained
stream images were inspected, and the trace has no dropped records or selected
images. This locates the delay downstream of Java's completed paint callbacks,
without establishing a specific graphics pipeline or compositor cause. The
trace adds overhead and is not a performance measurement. This control failure
remains open and is distinct from the aggregate performance measurements.
The subsequent [buffering comparison 43738815451](https://github.com/samsaw123456/emberwood-kt/actions/runs/43738815451)
retains a negative result. Both fresh applications report the Metal graphics
configuration on a 1920×1080, 30 Hz display. The default route again delays
native publication for 3.090 seconds after the newer Java paint; 180 Java paint
callbacks continue in that interval, while its 19 safepoints total only 40.361 ms.
Disabling the test copy's RepaintManager buffering makes presentation worse:
most retained images contain partial backgrounds or terrain without the complete
fox, HUD or labels. Four direction cases fail before input, Return fails during
capture, and the lifecycle capture aborts. The required default-repeat route
therefore never starts. All 104 retained stream images across both attempts were
inspected. This incomplete three-route diagnostic supports no production
buffering change; its timing includes tracing and forced audit paints.
Original hashes, GC timing and the independent review are retained in
`build/ci-buffer-comparison-7d9668ed-macos-intel/build/controls-capture-comparison/independent-stream-review.json`.
The [scheduled-repaint diagnostic 43740408807](https://github.com/samsaw123456/emberwood-kt/actions/runs/43740408807)
also fails Left. Its native surface updates 2.858 seconds after the newer Java
paint, with 165 intervening completed paint callbacks and 73 safepoints totaling
93.928 ms. All 32 retained stream images were inspected. This test-only
scheduling change does not resolve the failure. The ordinary Main launcher
probe uses bounded physical holds independent of capture latency. Its first
attempt stopped before input because the test did not await window readiness;
owned SIGTERM cleanup succeeded, but that attempt supplies no movement or
physical-Quit proof.
The corrected [Main retry 43741464146](https://github.com/samsaw123456/emberwood-kt/actions/runs/43741464146)
passed actual title readiness and visibly moved/stopped with A. Its first Left
hold ended after 356.831 ms, with prompt native key-up acknowledgment, but the
stream then had a 3,122.656 ms gap between complete samples. The next image
showed the fox at the left boundary and the timer advancing from 00:06 to 00:09.
All 80 originals were inspected. No damage, respawn or dialog appears; later
animation at the wall cannot prove braking. The Main probe's synchronous
AXFocusedWindow query timed out during that hold. Its independent input worker
had already released the key. NativeAudit's snapshot controller does not make
that same AX query, so this does not establish a common cause for both probes.
The post-error stacks were collected near recovery and do not locate the earlier
delay. Owned SIGTERM cleanup succeeded; physical Quit remains unverified in this
attempt.

The [stream-only Main run 43743043450](https://github.com/samsaw123456/emberwood-kt/actions/runs/43743043450)
removes synchronous AX/snapshot queries during the hold and early recovery, but
still fails Left. The physical hold lasts 357.015 ms; native key-up is promptly
acknowledged. Complete stream samples are then 4.330 seconds apart, and the next
image places the fox at the wall. All 34 original images were inspected. The
concurrent native sample identifies the blocking path: all 568 Main Thread
samples are in AppKit's Services-menu population, including 560 in a synchronous
VoiceShortcutClient XPC reply wait. Its header is 505 ms after Left-down posting
and 127 ms after native key-up acknowledgment, so it observes the continuing
post-release stall, not the physical-held interval. Sample counts are not elapsed
milliseconds, and tracing adds overhead. This is a concrete native blocking path,
not a verified fix or proof that all earlier failures have the same cause.
The separate snapshot-plus-sample run stopped before Left because D release
missed the unchanged timing limit, so it cannot complete a paired comparison.
Production remains unchanged. Exact stream, sample and image hashes are retained
in `build/ci-main-stream-sampled-7d9668ed-macos-intel/build/main-movement-native-app/independent-review/`.

The [OpenGL diagnostic 43741471213](https://github.com/samsaw123456/emberwood-kt/actions/runs/43741471213)
also fails Left. Actual CGLGraphicsConfig reports **software OpenGL**. Native
publication follows the newer Java paint by 2.832 seconds despite 96 intervening
paint callbacks; 23 safepoints total only 42.893 ms. All 34 stream images were
inspected, with the final two resized/padded images excluded from fixed-geometry
comparison. This is another negative diagnostic, not support for a production
graphics override. Exact hashes and timing journals are retained under
`build/ci-main-ready-7d9668ed-macos-intel/build/main-movement-native-app/independent-review/`
and `build/ci-opengl-7d9668ed-macos-intel/build/controls-capture-native-app/independent-stream-review/`.
The earlier failed performance run and prior-build evidence remain preserved.

## Audit method

The native performance audit opens the actual Swing window, captures its rendered
output, and uses operating-system keys for movement, jumping, retry, pause and a
three-minute movement/projectile soak. Original level fixtures separately cover
eight regions, four ordinary monster species and six guardians. Fixtures are
performance scenes, not evidence of completing those levels through input.

Throughput is the difference in `GamePanel.paintedFrames` divided by elapsed
wall time. That counter advances when Java's `paintComponent` finishes;
`paintNanos` measures its Java drawing body. Neither counter observes the later
native-buffer publication, compositor or display scanout. The historical
`frames/s` values and the audit's similarly named output columns all refer to
this Java paint throughput. Screenshots and the separate bounded stream trace
provide presentation evidence within their recorded scope, not continuous
native FPS for these performance windows.

On Linux, run it after `./gradlew check fatJar`, using Java 25:

```sh
env -u WAYLAND_DISPLAY XDG_SESSION_TYPE=x11 xvfb-run -a tools/run_x11_audit.sh \
  "$JAVA_HOME/bin/java" --enable-native-access=ALL-UNNAMED \
  -Xms32m -Xmx128m -XX:ActiveProcessorCount=2 \
  -cp build/libs/emberwood-kotlin.jar:build/classes/kotlin/test \
  emberwood.PerformanceAudit
```

On a real Linux desktop, omit the `env ... tools/run_x11_audit.sh` prefix. The isolated
X11 setup needs Xvfb, Openbox and `xprop`; native keyboard injection uses Python 3
and the platform's input APIs. The X11 environment is
necessary when using Xvfb from a Wayland session, so Java's Robot captures the
isolated X11 display instead of opening a desktop screencast portal. The audit
uses synchronous painting and a screen capture; `Robot.waitForIdle()` would wait
behind continuous animation and distort command timing.

On macOS, build the package and run the unchanged game/runtime through its
actual application launcher:

```sh
python3 tools/mac_app_profile.py --audit performance --soak-seconds 180
```

Use `--app "/absolute/path/Emberwood Kotlin.app"` to measure the cached source
app. The driver makes an isolated test copy, preserves the runtime/JAR bytes and
shared signing policy, and supplies the same 128 MiB heap/two-processor limits.
Its external controller owns test-only input/capture permissions. Raw `java`
startup is retained only as a diagnostic comparison; it is not the Mac source
launcher or the final native-app performance route.

`interval-samples.tsv` retains the existing quarter-second sample points plus
each window's before/after counters. It records raw frame, paint, process CPU,
simulation and heap measurements, with paired monotonic/epoch clocks and the
clock-read span. Samples are buffered and written after measurement, without
extra event-thread polls. The isolated Mac performance configuration also logs
GC and safepoint times to `app-stderr.log`; the production launcher is unchanged.

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

The audit requires at least 45 completed Java paint calls/second, mean Java
painting within a 16.67 ms budget, and simulation progress at least 90% of wall
time. Static
menus must make no simulation progress and repaint no more than twice a second.
Retained heap growth after collection must stay below 16 MiB across the soak.

## Preserved investigation history

The [historical performance record](history/performance-investigation.md) retains
the failed Linux baseline, rejected RGB-buffer trial, bounded image-cache change,
raw-JVM Mac pacing/JFR observations, microphone-initialization investigation,
source/native launcher comparisons and complete 88283267 baseline. Those older
failures were not relabeled as passes. Native launch and signing superseded the
raw-JVM and permission-prompt routes; no busy-spin, global power-policy change
or relaxed performance gate was shipped. The current Intel aggregate failure
and short-interval limits are recorded above, not hidden in the archive.
