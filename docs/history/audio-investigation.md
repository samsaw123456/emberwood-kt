# Audio investigation archive

Archived 2026-11-15. This chronology covers builds through `88283267`, before
the current `7d9668ed` jump-input correction. It preserves failed native startup
experiments, recorded PCM gaps, later functional passes and their limits. Artifact
paths are relative to the project root. Historical passes do not establish
current-build control coverage; see [current audio evidence](../AUDIO.md).

## Retained 88283267 baseline

Previous JAR `88283267eefaf417da4965a1248c1b70b9188effd71f6ee3f69cc2c1911e5bc1`
has actual-output proof for all fourteen physical sound-control cases on Linux
x86-64/ARM64 and native Mac Intel/ARM64. Each case measures an audible reference,
cutoff while playing, suppressed output, and restored output. A functional mute
pass is distinct from uninterrupted audio quality.

| Platform and evidence | Physical sound controls | Continuity finding |
| --- | --- | --- |
| Linux x86-64, source and bundle, run 43719750356 | 14/14 per route; all 168 WAVs inspected | No interior exact-zero span of at least 2 ms |
| Linux ARM64, source and bundle, run 43719750356 | 14/14 per route; all 168 WAVs inspected | Three mute cutoffs have a 10.667 ms zero interval before a 1.56–1.63 ms residual tail; reference/restored cues are intact |
| Mac ARM64, native app without trace, run 43721920267 | 14/14; all 84 WAVs inspected | No interior exact-zero span of at least 2 ms in this repeat; earlier 11.604 ms gap remains unexplained |
| Mac Intel, native app without trace, run 43721920267 | 14/14; all 84 WAVs inspected | No interior exact-zero span of at least 2 ms in this repeat; earlier four 16.52–24.06 ms gaps remain unexplained |

All waveform panels were visually inspected and their measurements independently
recomputed. Muted windows are exactly silent; cutoff windows have a nonzero
prefix and silent tail; restored feedback measures 880/1175 Hz within 2 Hz.
Linux captures the game's own stream through a private virtual PipeWire output;
it does not prove speaker hardware playback. Mac capture is restricted to the
exact app process through ScreenCaptureKit. No microphone or system mix is used.

The final Intel Mac matrix `43715704373` completed both performance routes but
its audio step was skipped after a test-only control-marker failure. The separate
native repeat above supplies fresh actual-output proof with the same production
game/runtime and no trace adapter. The preceding traced repeat `43719992137`
also passed, retaining exact generated and native-submitted PCM. Neither repeat
reproduced the earlier gaps. This confirms the successful output was not confined
to the instrumented path, but a bounded repeat cannot identify the earlier cause
or prove flawless playback on every machine. Production buffers, synthesis and
verification thresholds remain unchanged.

Evidence: [final Linux output run](https://github.com/samsaw123456/emberwood-kt/actions/runs/43719750356)
and [untraced native Mac repeat](https://github.com/samsaw123456/emberwood-kt/actions/runs/43721920267).
Independent journals and original recordings are retained under
`build/ci-audio-dependencies-linux-{x64,arm64}/build/audio-linux/{source,packaged}/independent-review/`
and `build/ci-audio-untraced-macos-{arm,intel}/build/audio-native-app/pcm/independent-review/`.
The [traced repeat](https://github.com/samsaw123456/emberwood-kt/actions/runs/43719992137),
original failures and earlier recordings remain in the investigation history.

The final untraced recordings preserve thirteen capture-PTS discrepancies on ARM
and one on Intel, separately from PCM continuity. All complete short and long cues
retain their expected duration within one 48 kHz sample. The paired host/wall
clock receipts cover all 168 recordings; maximum observed GC pauses are 26.048 ms
on ARM and 5.441 ms on Intel. No PCM gap recurred to correlate with a pause. These
receipts retain clock-rate differences and sampling uncertainty rather than
equating wall time with the monotonic capture clock. Both cleanup screenshots per
architecture were inspected, and all original recording hashes match the native
completion receipts. Cross-run package checks also verify unchanged runtime,
application contents and signing policy.

## Output backend, contexts and signing investigation

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
contexts started without a dialog and cleaned up fully. The later native app
in that experiment still prompted; following fixtures
waited inside `AudioQueueStart`, ultimately in Core Audio's device stream-usage
registration. Those fixtures may have been affected by incomplete cleanup of
the native app's pending request. Subsequent exact-process stacks, strict cleanup
and signing comparisons led to the verified Hardened Runtime trial below;
AWT ordering was not established as the cause. Evidence is retained under
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
The exact two JIT/library allowances are documented in
[the signing trial](../MAC_SIGNING_TRIAL.md);
the production builder adopted that same verified policy.

There are four interior zero spans of 16.52–24.06 ms in three Intel recordings:
`CHAPTER_COMPLETE-full`, `CHAPTER_COMPLETE-cut`, and `WON-long`. Capture
timestamps remain continuous at those intervals. After the second gem gap and
the long cue gap, pitch, phase and envelope agree with the continuously advancing
intact reference; cue duration does not grow. This is evidence of missing output
within the ongoing cue timeline, not evidence establishing whether the device,
output path or capture omitted it. ARM has no interior zero span of at least
2 ms in this trial. Separate capture timestamp discrepancies are retained for
both architectures, including three ARM long-cue windows. Functional mute proof
does not imply flawless audio continuity. Subsequent native-app repeats retained
diagnostic timing evidence; no speculative buffer change was made.

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

## Historical private Linux output repeats
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

## Historical ARM native gap

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

## Historical bounded trace repeat
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
