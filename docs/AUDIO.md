# Desktop playback

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

## Current native evidence

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
forced-failure cleanup were exercised. The dedicated ARM64 repeat remains pending.
