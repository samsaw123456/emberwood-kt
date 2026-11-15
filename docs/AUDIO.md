# Desktop playback

Emberwood synthesizes its existing cues as 22050 Hz, mono, signed 16-bit
little-endian PCM. Linux uses Java Sound. The macOS backend under verification
uses Apple's AudioToolbox output queue directly, without constructing a Java
Sound mixer or enumerating input devices. The native default output is left to
AudioToolbox; the game does not change device selection or microphone permissions.
The failed Intel named-mixer experiment remains recorded in PERFORMANCE.md and
its artifacts. Native evidence for the replacement is recorded below; the Intel
GUI startup issue remains unresolved.

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

On Intel, the standalone queue probes pass, but the actual game window still
produces a microphone permission dialog and audio initialization remains pending.
No permission was granted and the input guard sends no keys in this state.
The next no-input diagnostic separates an empty window, the audio worker, ordered
window/audio startup, and the concurrent production window; own-process Java and
native stacks are captured before cleanup. The Intel game is not verified.
