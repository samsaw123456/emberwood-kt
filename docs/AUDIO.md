# Desktop playback

## Current build

Production JAR `88283267eefaf417da4965a1248c1b70b9188effd71f6ee3f69cc2c1911e5bc1`
has actual-output proof for all fourteen physical sound-control cases on Linux
x86-64/ARM64 and native Mac Intel/ARM64. Each case measures an audible reference,
cutoff while playing, suppressed output, and restored output. A functional mute
pass is distinct from uninterrupted audio quality.

| Platform and evidence | Physical sound controls | Continuity finding |
| --- | --- | --- |
| Linux x86-64, source and bundle, run 43719750356 | 14/14 per route; all 168 WAVs inspected | No interior exact-zero span of at least 2 ms |
| Linux ARM64, source and bundle, run 43719750356 | 14/14 per route; all 168 WAVs inspected | Three mute cutoffs have a 10.667 ms zero interval before a 1.56–1.63 ms residual tail; reference/restored cues are intact |
| Mac ARM64, native app with test-only trace, run 43719992137 | 14/14; all 84 WAVs inspected | No interior exact-zero span of at least 2 ms in this repeat; earlier 11.604 ms gap remains unexplained |
| Mac Intel, native app with test-only trace, run 43719992137 | 14/14; all 84 WAVs inspected | No interior exact-zero span of at least 2 ms in this repeat; earlier four 16.52–24.06 ms gaps remain unexplained |

All waveform panels were visually inspected and their measurements independently
recomputed. Muted windows are exactly silent; cutoff windows have a nonzero
prefix and silent tail; restored feedback measures 880/1175 Hz within 2 Hz.
Linux captures the game's own stream through a private virtual PipeWire output;
it does not prove speaker hardware playback. Mac capture is restricted to the
exact app process through ScreenCaptureKit. No microphone or system mix is used.

The final Intel Mac matrix `43715704373` completed both performance routes but
its audio step was skipped after a test-only control-marker failure. The separate
native trace repeat above supplies fresh actual-output proof with the same
production game/runtime. Its adapter retains exact generated and native-submitted
PCM without changing production buffers or synthesis. Instrumentation changes
diagnostic timing, so the absence of a repeated gap does not identify the earlier
cause. Audio continuity remains unresolved; the game is not described as having
flawless output.

Evidence: [final Linux output run](https://github.com/samsaw123456/emberwood-kt/actions/runs/43719750356)
and [native Mac trace repeat](https://github.com/samsaw123456/emberwood-kt/actions/runs/43719992137).
Independent journals and original recordings are retained under
`build/ci-audio-dependencies-linux-{x64,arm64}/build/audio-linux/{source,packaged}/independent-review/`
and `build/ci-audio-trace-macos-{arm,intel}/audio-native-app/pcm/independent-review/`.
The original failures and untraced recordings remain in the investigation history.

## Playback implementation

Emberwood synthesizes its existing cues as 22050 Hz, mono, signed 16-bit
little-endian PCM. Linux uses Java Sound. The macOS backend uses Apple's
AudioToolbox output queue directly, without constructing a Java
Sound mixer or enumerating input devices. The native default output is left to
AudioToolbox; the game does not change device selection or microphone permissions.
The failed Intel named-mixer experiment remains recorded in PERFORMANCE.md and
its artifacts. Both architectures now have prompt-free native-app startup and
all fourteen physical sound-control cases verified under the shared Hardened
Runtime signing policy. Audio continuity remains a separate investigation below.

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

## Investigation history

Diagnostic run `43705516072`, JAR `bdba1782`, passed all SDK/JVM layout comparisons
and three real queue lifecycle cycles per runtime on both Mac architectures.
The ARM installed app starts without a permission dialog, and all 14 separate
mute/menu activation cases pass with captured output on both the source and
bundled runtimes. Those 168 recordings and six inspected waveform sheets remain
under `build/ci-audioqueue-macos-arm/mac-output-diagnostic/`.

Audio quality remains a separate check: two bundled ARM reference recordings
contain three interior silence gaps of 21.75–43.44 ms. Capture timestamps are
continuous at those locations, but the cause is not yet established. These PCM
fixtures launch Java directly; they do not establish native app scheduling.
`independent-review.md` and `continuity-review.json` retain the exact observations.
The later `d5499672` repeat in run `43707637231` passes all 28 source/bundled
control cases, with no interior exact-zero span of at least 2 ms in any of its
168 recordings. The older gaps did not recur; that does not establish their
cause. Its capture timestamp discontinuities occur after the affected short cues
have ended, and are recorded separately under `build/ci-contexts-macos-arm/`.

On Intel, the earlier standalone queue probes passed, but the native game window
produced a microphone permission dialog and audio initialization remained pending.
No permission was granted and the input guard sends no keys in this state.
Run `43707637231` then isolated an empty window, the audio worker, ordered
window/audio startup, and the concurrent production window. All four raw-JVM
contexts start without a dialog and clean up fully. The later native app still
prompts; following fixtures wait inside `AudioQueueStart`, ultimately in Core
Audio's device stream-usage registration. Those later fixtures may be affected
by incomplete cleanup of the native app's pending request. Own-app stacks,
strict cleanup, and launcher/signing comparisons are the next checks; AWT ordering
is not established as the cause. Evidence is retained under
`build/ci-contexts-macos-intel/mac-output-diagnostic/`. These older failures are
retained; they are not relabeled as passes after the signing correction.

The subsequent hardened native-app trial `43712978391`, at production JAR
`88283267…5bc1`, passed all fourteen physical audio cases on both ARM64 and
Intel. The app launches through LaunchServices with unchanged game/runtime
bytes; only the outer launcher signing policy changes. Independent recomputation
of all 168 recordings confirms audible reference/restored cues, a nonzero
prefix followed by silence when muting a playing cue, completely silent muted
output, and the 880/1175 Hz unmute feedback within 2 Hz. All four overview
waveform sheets and three enlarged Intel gap comparisons were inspected.
Startup stacks show the audio worker writing or waiting for free output buffers,
rather than blocked in `AudioQueueStart`. No microphone permission was granted.
The exact two JIT/library allowances are documented in `MAC_SIGNING_TRIAL.md`;
the production builder now applies that same verified policy.

There are four interior zero spans of 16.52–24.06 ms in three Intel recordings:
`CHAPTER_COMPLETE-full`, `CHAPTER_COMPLETE-cut`, and `WON-long`. Capture
timestamps remain continuous at those intervals. After the second gem gap and
the long cue gap, pitch, phase and envelope agree with the continuously advancing
intact reference; cue duration does not grow. This is evidence of missing output
within the ongoing cue timeline, not evidence establishing whether the device,
output path or capture omitted it. ARM has no interior zero span of at least
2 ms in this trial. Separate capture timestamp discrepancies are retained for
both architectures, including three ARM long-cue windows. Functional mute proof
does not imply flawless audio continuity. The final native-app repeat retains
diagnostic timing evidence; no speculative buffer change is made.

Evidence: `build/ci-hardened-pcm-macos-{arm,intel}/mac-entitlement-trial/native-pcm/`,
including `independent-pcm-review.json`, original WAV/timestamp receipts and
Intel `independent-gap-comparison.json`.

The final Linux x86-64 source and bundled-runtime repeat at the same `88283267`
JAR also passed all fourteen physical cases each. All 168 WAVs were measured;
six waveform sheets were inspected and restored feedback independently measured
at 880/1175 Hz within 2 Hz. Hash-qualified evidence is in
`build/audio-states-{source,packaged}-88283267/REVIEW.md` and `root-review.json`.
The ordinary Linux CI runners have no output device; a separate private virtual
PipeWire session establishes output coverage without
capturing microphones or changing the user's live audio configuration.

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
The source/bundle local x86-64 runs passed all 28 physical cases with both recorder
protocols, under `build/audio-linux-private-portable/` and
`build/audio-linux-private-final/`. The compatibility run uses the installed
recorder with its sample-count capability hidden; it is not a claim that a local
PipeWire 1.0 installation was tested. All 336 analyzed WAVs were independently
recomputed and their eight waveform sheets inspected. Every retained longer
capture has an identical first 96,000 samples. The modern source run contains one
10.667 ms zero interval at a mute cutoff, followed by about 1.4 ms of residual
tail and then silence; reference and restored cues have no interior zero span of
at least 2 ms. This observation is retained separately from the fourteen passing
control assertions and the earlier Mac mid-cue gaps. Private-session normal and
forced-failure cleanup were exercised.

The complete CI repeat `43716755578` passes on Linux x86-64 and ARM64 with
production JAR `88283267…5bc1`. It uses actual PipeWire 1.0.5 and WirePlumber
0.4.17. All 56 source/bundled control cases and 336 analyzed WAVs were independently
recomputed; eight waveform sheets and three cutoff-detail plots were inspected.
All complete recordings retain the identical first 96,000 samples. Feedback
tones measure 880/1175 Hz within 2 Hz, muted cues are exactly silent, and every
reference/restored cue is present. Three ARM source cutoff recordings have a
10.667 ms zero interval followed by 1.6–1.9 ms of residual tail, then lasting
silence. No reference, long, unmute or restored cue has an interior zero span of
at least 2 ms, and neither packaged route has one in any recording. This cutoff
observation remains distinct from the prior Mac mid-cue gaps.

Both package archive checksums and embedded game hashes were independently
checked, and all private services exited. This closes actual ARM64 application
output coverage through the virtual sink. Evidence is under
`build/ci-audio-final-linux-{x64,arm64}/build/audio-linux/`, with per-route
`independent-review/` journals, original recordings and `independent-provenance.json`
at the audit root. The separate real-main screenshots cover physical launch and
Alt+F4; their visual review is recorded separately.

The final installer-integration repeat `43719750356` also passes all 56 physical
cases and 336 analyzed WAVs with the unchanged production JAR/runtime. Every
waveform panel and all three cutoff-detail plots were inspected. The three ARM
mute-edge observations now occur in source `TITLE-Mouse-cut` and packaged
`WON-cut`/`PAUSED-Return-cut`: 10.667 ms of zero samples, a 1.56–1.63 ms residual
tail, then lasting silence. No reference, long, unmute or restored cue has an
interior exact-zero span of at least 2 ms. Both x86-64 routes have none in any
recording. All complete capture prefixes match the analyzed samples exactly;
all private services exit successfully. This newer artifact contains the final
dependency-aware installer and is retained separately under
`build/ci-audio-dependencies-linux-{x64,arm64}/`, with each route's independent
PCM journal and the separate package/runtime identity review.

## Final ARM native repeat and trace diagnostic

The final ARM native app in run `43715704373` passes all fourteen cases with
unchanged JAR/runtime bytes and a clean native shutdown. All 84 original WAVs,
two waveform sheets, and the enlarged gap/reference comparison were inspected.
The source and packaged Mac performance runs use the same game and runtime.
The one zero span in `CHAPTER_COMPLETE-long` runs from 1.1055625 to 1.1171667
seconds of the recording, beginning 938.5208 ms into the cue. Its 11.6042 ms
length is close to one 256-sample production block at 22050 Hz.

The cue's total audible span is 957.8125 ms versus 957.7917 ms for the intact
reference: a one-sample difference at the 48000 Hz capture rate. The final
1047 Hz decay after the gap agrees with the continuously advancing reference
(correlation 0.99957), rather than a cue paused for the missing interval.
Capture timestamps are continuous at that gap. Separate 16.60–19.00 ms
timestamp discrepancies in nine other recordings are retained; all complete
reference/long cues still have their expected duration. This narrows the
observation to missing samples within an ongoing timeline, without identifying
the source, native queue, output device or recorder as the cause.

That run's diagnostic logs contain 33 GC pauses, at most 12.012 ms, and a maximum
total safepoint of 12.524 ms. They lack a shared clock anchor with the recordings,
so no exact GC/gap correlation is claimed. Download/extraction file timestamps
are not audio-event timestamps. The comparison and measurements remain in
`build/ci-native-final-macos-arm/build/audio-native-app/pcm/independent-gap-comparison.json`
and its `independent-review/` journal.

For a bounded diagnostic on an actual Mac, run after building the test classes
and packaged app:

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

The actual traced repeat `43719992137` passes on both Mac architectures at the
same production JAR/runtime. All 168 WAVs, four waveform sheets and four cleanup
desktops were independently inspected. No interior exact-zero span of at least
2 ms recurs. The trace retains 118,687 ARM / 115,438 Intel events and about
2.4 MiB of exact nonzero PCM per architecture, below both bounds. All 23,685 ARM
and 23,035 Intel submitted blocks match the generated bytes exactly. The eight
startup blocks are exact silence; every queued buffer is returned before
synchronous disposal. One final Intel zero block is intentionally not enqueued
when close makes its write return zero. No audible block is lost upstream.

All 56 complete reference/long/unmute/restored cues per architecture were matched
to their actual submitted segments. Correlation after ordinary 22050→48000 Hz
resampling is at least 0.99772, without deleting or shifting intervals within a
cue. Fourteen mute-cut windows retain their separate cutoff assertions because
reset intentionally discards queued audio. Capture PTS discrepancies remain
recorded in ten ARM and nine Intel windows; they are not edited out.

The 168 recorder clock anchors per architecture validate the same host-time base
as [the pinned OpenJDK macOS implementation](https://github.com/openjdk/jdk25u/blob/jdk-25.0.5%2B8/src/hotspot/os/bsd/os_bsd.cpp).
Java wall-anchor residuals stay within their 1 ms resolution. Intel wall time
runs about 500 ppm faster than host time during this recording, so direct host
time is used for the sample comparison. The trace's extra allocations produce
GC/safepoint measurements distinct from the uninstrumented performance run;
these are retained without treating them as production performance results.
Because the missing-PCM gaps did not recur, this trace does not assign a cause
to older artifacts or justify a speculative buffer change. Exact block sequences,
clock fits, per-cue correlations and cleanup are retained in
`build/ci-audio-trace-macos-{arm,intel}/audio-native-app/independent-trace-review/`.
