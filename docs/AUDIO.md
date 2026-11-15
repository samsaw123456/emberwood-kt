# Desktop playback

## Current validation status

The current candidate JAR is
`ae9686cb8387d5c9f61f4a6cb73d4f9a99803fe6e93e2ce519d495d59b9bdb8c`.
It changes native macOS application-menu preparation. Its 67 unit tests pass.
Fresh Linux output and complete control verification are complete; native Mac
output and its complete control inventory remain pending in
[run 43750771895](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750771895).
The separate [ordinary Mac Main repeat](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750035990)
passes bounded movement, actual application-menu labels and physical Quit on both
architectures. Its visible Sound-on label is not a replacement for the pending
current-build PCM captures.

| Current ae9686cb evidence | Physical sound controls | Continuity finding |
| --- | --- | --- |
| Linux x86-64, source and bundle, run 43747641897 | 14/14 per route; all 168 WAVs independently checked | No interior exact-zero span of at least 2 ms |
| Linux ARM64, source and bundle, run 43747641897 | 14/14 per route; all 168 WAVs independently checked | No interior exact-zero span of at least 2 ms |

All eight waveform sheets were inspected, with independent original-prefix,
PCM-metric, suppression/cutoff/restoration and feedback-frequency checks. The
real Main game also passes launch, screen-right movement, release, jump, landing,
pause and physical Alt+F4 on both source/bundled routes. All 36 original image
hashes were checked and every frame inspected in labeled 576 px contact-sheet
cells; this is not a claim of 36 full-size inspections. All four game processes
and six private audio daemons exit 0. This remains isolated virtual PipeWire
output, without microphone/hardware access or changes to the user's session.
Recorded delivery outliers include 379.8 ms for the x86-64 source PAUSED mouse
mute and 377.5 ms for ARM64 bundled mouse restoration; functional passes do not
establish uniformly low event latency.

Evidence: [current Linux run 43747641897](https://github.com/samsaw123456/emberwood-kt/actions/runs/43747641897),
`build/ci-audio-ae9686cb-linux-{x64,arm64}/build/audio-linux/{source,packaged}/independent-review/`
and each route's `game-smoke/independent-review/`.

The retained audio evidence below belongs to baseline JAR
`7d9668edebc108b5d3f033f20180874942cea852676f1199a3210dd24e2f6582`.
That build fixed release-then-press ordering for a new jump within one simulation
tick. Its output verification completed on Linux x86-64/ARM64 and native Mac Intel/ARM64:
84 physical cases and 504 original WAVs across the six measured routes. Complete
Intel control review remained unfinished. None of those recordings is relabeled
as candidate output proof. The historical record retains still earlier evidence
with its original build identity.

| Retained 7d9668ed build and evidence | Physical sound controls | Continuity finding |
| --- | --- | --- |
| Linux x86-64, source and bundle, run 43725301448 | 14/14 per route; all 168 WAVs independently checked | No interior exact-zero span of at least 2 ms |
| Linux ARM64, source and bundle, run 43725301448 | 14/14 per route; all 168 WAVs independently checked | One packaged title mute cutoff has a 10.667 ms zero interval followed by a 1.583 ms residual tail; all uninterrupted cues are intact |
| Mac ARM64, native app without trace, run 43725299181 | 14/14; all 84 WAVs independently checked | No interior exact-zero span of at least 2 ms; earlier gaps remain unexplained |
| Mac Intel, native app without trace, run 43732427910 | 14/14; all 84 WAVs independently checked | No interior exact-zero span of at least 2 ms; earlier gaps remain unexplained |

All eight Linux waveform sheets were visually inspected. Independent checks cover the
original capture prefixes, all reported PCM measurements, suppression, cutoff,
restoration and the 880/1175 Hz feedback tones. The source and bundled real game
also passed physical launch, movement, release, jump, landing, pause and Alt+F4
on both architectures; all 36 rendered frames were inspected. Every private
audio daemon exited with code zero. This measures the game's own PCM through an
isolated virtual PipeWire output, without microphones, hardware devices or changes
to the user's audio session; it does not claim speaker playback.

Evidence: [retained Linux output run](https://github.com/samsaw123456/emberwood-kt/actions/runs/43725301448).
Original recordings and independent journals are retained under
`build/ci-audio-jump-fixed-linux-{x64,arm64}/build/audio-linux/{source,packaged}/independent-review/`;
the actual game screenshots and hash journals are in each route's
`game-smoke/independent-review/` folder.

The retained Mac ARM native app also passes all fourteen cases: M in six states,
and mouse/Return/Space/keypad Enter Sound activation in TITLE and PAUSED. Both
waveform sheets and both actual cleanup desktop images were inspected. All 84
original hashes match the completion manifest, with the expected game/runtime
and no trace provider. Complete short/long cue spans remain within one sample
of 8094/45975 frames at 48 kHz. Nine capture-PTS discrepancies of 15.187–19.667 ms
at the 0.96-second buffer boundary are retained separately; there is no matching
PCM zero gap. All 84 paired clock anchors were checked; the largest GC pause was
16.082 ms and the largest safepoint 16.281292 ms. No PCM gap recurred to correlate.
This bounded run does not establish the cause of earlier gaps or universal
glitch-free playback. Evidence: [retained Mac run](https://github.com/samsaw123456/emberwood-kt/actions/runs/43725299181),
`build/ci-native-final-7d9668ed-macos-arm/build/audio-native-app/pcm/independent-review/`.

The separate [retained Intel output run](https://github.com/samsaw123456/emberwood-kt/actions/runs/43732427910)
closes the audio step skipped by the two earlier baseline matrix runs. All
14 physical cases, 84 original WAVs, both waveform sheets and both cleanup
desktops were independently reviewed. Complete cue durations are intact and no
uninterrupted cue has a zero gap of at least 2 ms. Eight recorder PTS discrepancies
of 18.857–19.955 ms occur at 1.94 seconds, after the cues ended. All 84 paired
anchors were checked: wall time runs 489.345–500.419 ppm faster than host time,
which is retained in the analysis. Maximum GC/safepoint pauses are 6.649/6.812669 ms;
no PCM gap recurred to correlate. Evidence:
`build/ci-audio-current-7d9668ed-macos-intel/build/audio-native-app/pcm/independent-review/`.

For each Mac architecture, the source and download use byte-identical native
apps/runtimes and the same launch method. Original-app before/after hashes and
independent package-tree comparisons support sharing this one physical audio
inventory across those launch routes; it is not presented as a second recording
run. Current functional output passes do not erase historical continuity gaps
or establish their cause.

## Playback implementation

Emberwood synthesizes its existing cues as 22050 Hz, mono, signed 16-bit
little-endian PCM. Linux uses Java Sound. The macOS backend uses Apple's
AudioToolbox output queue directly, without constructing a Java
Sound mixer or enumerating input devices. The native default output is left to
AudioToolbox; the game does not change device selection or microphone permissions.
The failed named-mixer experiment and subsequent verified signing correction
remain in [the historical investigation](history/audio-investigation.md).
Prompt-free startup and physical output evidence are listed by build above;
output initialization alone does not establish working sound controls.

The queue owns eight 512-byte buffers, at most 4096 bytes of application-managed
PCM storage. Startup primes them with silence, starts playback, and confirms
Apple's actual `kAudioQueueProperty_IsRunning` value before reporting readiness.
This property can change after the start call returns, as described in
[Apple's running-state documentation](https://developer.apple.com/documentation/audiotoolbox/kaudioqueueproperty_isrunning).

A native callback returns consumed buffers to a bounded pool; the synthesis
thread fills and enqueues them. The callback never acquires the native-operation
lock, so a synchronous reset/disposal callback cannot deadlock the caller.
Callback exceptions are retained and reported to the writer rather than crossing
the native boundary: the [Java 25 Linker contract](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html)
warns that an uncaught upcall exception terminates the VM. Native memory and the
callback stub use a shared arena because AudioToolbox invokes callbacks on its
own thread when no callback run loop is supplied.
[AudioQueueNewOutput](https://developer.apple.com/documentation/audiotoolbox/audioqueuenewoutput(_:_:_:_:_:_:_:))
documents that thread choice and creates a playback queue only.

Mute clears queued voices immediately and coalesces a reset request for the
existing audio thread. That thread resets the device before mixing its next
block; a new cue added after the stop is retained. No native reset runs on the
event thread, so a blocked device cannot hang a mute or menu action. The Mac
backend discards queued audio with
[AudioQueueReset](https://developer.apple.com/documentation/audiotoolbox/audioqueuereset(_:));
`AudioQueueFlush` would instead ensure queued audio is played. A reset generation
also discards a writer's pending pre-reset block. Disposal uses
[AudioQueueDispose with immediate=true](https://developer.apple.com/documentation/audiotoolbox/audioqueuedispose(_:_:)),
which is synchronous and ends callbacks before the shared arena is closed.
If disposal fails, callback memory is retained rather than freed while native
code might still reference it. Errors remain explicit. The outer audio lifecycle
keeps potentially blocked initialization/shutdown away from the event thread.

## Reproducible verification

`MacAudioOutputTest` exercises exact PCM bytes and bounded buffer ownership,
backpressure/reset recovery, close while a writer is blocked, callbacks during
synchronous disposal, partial allocation failure, invalid states, and exception
containment through real Java FFM upcalls. The fake queue opens no hardware.
The outer `AudioTest` regressions also cover a blocked reset without blocking
Mute/Quit, asynchronous reset errors becoming explicitly unavailable, and
preserving a new cue queued immediately after stop.

On each Mac architecture, independently compare the installed SDK's ABI receipt
with the JVM layouts before testing playback:

```sh
mkdir -p build/mac-audio-output
clang -std=c11 -Wall -Wextra -Werror tools/mac_audio_layout.c \
  -framework AudioToolbox -o build/mac-audio-output/sdk-layout
build/mac-audio-output/sdk-layout > build/mac-audio-output/sdk-layout.json
"$JAVA_HOME/bin/java" --enable-native-access=ALL-UNNAMED \
  -cp build/libs/emberwood-kotlin.jar:build/classes/kotlin/test \
  emberwood.MacAudioOutputProbe --layouts > build/mac-audio-output/jvm-layout.json
python3 - <<'PY'
import json
from pathlib import Path
root = Path('build/mac-audio-output')
assert json.loads((root / 'sdk-layout.json').read_text()) == json.loads((root / 'jvm-layout.json').read_text())
PY
"$JAVA_HOME/bin/java" --enable-native-access=ALL-UNNAMED \
  -cp build/libs/emberwood-kotlin.jar:build/classes/kotlin/test \
  emberwood.MacAudioOutputProbe
```

Repeat the no-argument native probe with the packaged runtime and production JAR.
It checks three open/start/write/reset/close cycles, not audible cue correctness.
The actual game-window audit must additionally prove prompt-free startup and all
14 M/Sound control cases using process-only captured PCM, inspect its waveform
and continuity evidence, and close the installed app through its real interface.
No native Mac pass is implied by compilation or the fake-queue tests.

## Isolated Linux output verification

After building the test classes and Linux package, run
`python3 tools/linux_audio_ci.py --java-home "$JAVA_HOME"`. The manual
`linux-audio.yml` workflow runs this on both Linux architectures. It needs Xvfb,
Openbox, Python Xlib and Pillow, PipeWire with its ALSA plugin, WirePlumber and DBus.
All sound sockets, ALSA configuration and state live in a temporary private
directory. The private server contains one virtual output and no hardware/input
devices; WirePlumber runs its policy-only profile, and the private DBus cannot
activate external services. Every owned process is stopped and the private
directory removed afterward, including failed audits.

The existing sound-control audit uses real X11 keys/mouse and links the recorder
only to the launched game's playback port. Its fourteen cases and numerical
assertions are unchanged. Newer `pw-record` stops at exactly 96,000 frames;
PipeWire 1.0 lacks that option, so the fallback retains a complete longer
`*.capture.wav` and analyzes its first 96,000 frames without changing samples.
Incomplete captures fail. This verifies actual application PCM through the
Linux audio stack into a virtual output, rather than speaker hardware playback.
It never captures a microphone or the user's system mix.

Each route also launches the real game, separately from the state fixture, and
uses physical input to start, move right, release, jump, land, pause and close
with Alt+F4. The helper binds input to the exact owned window and checks both
process exit and the empty desktop. Screenshots remain explicitly unreviewed
until a person or visual reviewer inspects them; the CI artifact retains every
frame. The workflow validates and retains the rebuilt distribution archives and
checksums alongside the PCM evidence.

The policy-only configurations follow the upstream
[WirePlumber 0.4 policy context](https://github.com/PipeWire/wireplumber/blob/0.4.17/src/config/policy.conf)
and [PipeWire ALSA client interface](https://github.com/PipeWire/pipewire/blob/master/pipewire-alsa/alsa-plugins/pcm_pipewire.c).

## Optional bounded native trace

For a diagnostic on an actual Mac, run after building the test classes and
packaged app:

```sh
python3 tools/mac_app_profile.py --audit audio --audio-trace
```

The opt-in test provider records exact generated PCM, native enqueued PCM,
enqueue/callback/reset/disposal events and fixture commands in memory, then
writes `trace/events.tsv`, `trace/samples.s16le` and `trace/summary.json` after
the producer exits and native disposal completes. Exact zero blocks have an
explicit lossless encoding. The trace is bounded to 262,144 events and 8 MiB of
nonzero PCM; overflow or incomplete cleanup fails its summary and the driver.
Three real-FFM regression tests cover byte preservation and callback forwarding,
overflow without altering playback, and callback lifetime through blocked
synchronous disposal. The diagnostic does not change the production JAR, queue
size or synthesis. Its instrumentation overhead and provider adapter are
excluded from performance claims.

Paired Java monotonic/wall anchors and recorder host/wall anchors allow events
to be compared with capture PTS, including anchor uncertainty. Apple's
[host-clock documentation](https://developer.apple.com/documentation/coremedia/cmclockgethosttimeclock())
identifies `mach_absolute_time` as the macOS time base. These anchors are recorded
alongside every native capture; they do not manufacture a common clock for older
artifacts. A valid trace must first prove sample identity and complete cleanup
before it is used to attribute a gap.
Callback timing indicates that AudioToolbox acquired a buffer for reuse, not
that its samples reached a speaker; Apple explicitly makes that distinction in
the [output-callback contract](https://developer.apple.com/documentation/audiotoolbox/audioqueueoutputcallback).
Queued-sample and process-capture evidence must therefore be compared separately.

## Preserved investigation history

The [historical audio record](history/audio-investigation.md) retains all earlier
backend/lifecycle trials, microphone dialogs, signing experiments, private Linux
output repeats and traced/untraced Mac recordings. The earlier Intel
16.52–24.06 ms gaps and ARM 11.604 ms gap remain unexplained: samples were missing
within an advancing cue, with phase and total duration preserved. Later bounded
repeats did not reproduce them. Functional mute passes do not imply universally
glitch-free playback, and neither producer, device nor recorder has been assigned
as the cause without evidence. No speculative production buffer change followed.
