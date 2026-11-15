# Physical control coverage

The complete binding/state inventory and platform-specific results are recorded
in [controls-audit.tsv](controls-audit.tsv). Every row has an explicit result;
unverified platforms and missing audio evidence remain unverified. A simulation
campaign does not mark physical controls passed.

The table retains the audited `7d9668ed` baseline. The `375ae227` macOS Services
menu candidate passes compilation and 67 automated tests, but startup fails on
both Macs before any control input because its post-clear registration check
still sees a menu object. Its native attachment semantics and final-build
inventory remain unverified; no baseline pass transfers to it.
For `7d9668ed`, both Linux x64 source and bundled
runtimes pass all **280 cases**, with clean exit and all **1,214 referenced frames**
per run inspected. Exact disjoint reviewer journals are validated by
`build/audit-{source,packaged}-7d9668ed-final/review/all-frames-reviewed.json`;
complete results are in each `controls-reviewed.tsv` and `REVIEW.md`.

Fourteen physical M/Sound cases and 84 game-only PCM recordings per runtime
supply actual output proof in
`build/ci-audio-jump-fixed-linux-x64/build/audio-linux/{source,packaged}/independent-review/`.
The corresponding `game-smoke/independent-review/` records actual MainKt
movement, jump, pause and physical Alt+F4 with clean exit. The installed offline
app additionally passed in `build/installed-user-audit-7d9668ed/`.
This establishes software playback through an isolated virtual output, without
claiming speaker-hardware testing.

Linux ARM64 source and bundled inventories also pass all **280 cases** in
CI43725299181. All **1,214 frames per runtime** are independently reviewed, with
exact disjoint journals and complete results at
`build/ci-final-7d9668ed-linux-arm64/build/{audit,audit-packaged}/REVIEW.md`.
The full inventory correctly displays unavailable sound on its device-free host;
matching application bytes, runtime and physical bindings pass the separate
actual PCM and real-main Alt+F4 checks in `build/ci-audio-jump-fixed-linux-arm64/`.

macOS ARM passes all **280 native cases**, with every one of the **1,214 frames**
independently inspected. Actual fourteen-case PCM, physical Command-Q and both
source/packaged performance routes also pass. The complete result and exact
supporting hashes are at
`build/ci-native-final-7d9668ed-macos-arm/build/controls-native-app/REVIEW.md`.
Its source column records shared proof from the identical app, as defined below.

Intel's first source performance run measured 40.729 Java paints/second in one
boss window, below the 45 paints/second budget; this is not native presentation
FPS. Its control and audio stages did not run. That
failure remains at `build/ci-native-final-7d9668ed-macos-intel/`. The separate
instrumented repeat passed both performance routes and ran all 280 controls.
One Left-arrow row failed: 21 captures retained the previous presentation nonce,
extending the held input to 3.31 seconds and reaching the world boundary before
release/braking could be proved. The other 279 assertions passed, but complete
rendered control review remains pending. Evidence is preserved at
`build/ci-native-repeat-7d9668ed-macos-intel/`; the failed row is not credited.

The subsequent panel-marker run 43732405531 also fails only Left. Its retained
first/latest rejected PNGs are byte-identical across the whole scene; the
accepted frame arrives after the fox reaches the boundary. The marker-only
hypothesis is disproved. The six inspected originals and timings are recorded in
`build/ci-native-panel-marker-7d9668ed-macos-intel/build/controls-native-app/review/native-left-failure-review.json`.

The six-case diagnostic 43736264766 reproduces Left's failure with independent
snapshot and stream captures of the same old surface. Java reaches 140 fresh-nonce
drawing callbacks before the stream presents the new surface approximately 3.06 seconds
later; the callbacks precede Swing's final buffer publication. All 23 referenced
frames and three additional originals were inspected;
ordered Java and stream traces completed without data loss. The native
publication/compositor/capture cause remains unresolved. The subsequent buffering
comparison is recorded below; no full Intel pass is credited. Exact observations:
`build/ci-capture-trace-7d9668ed-macos-intel/build/controls-capture-native-app/review/native-java-paint-review.json`.

The comparison helper at commit `8048087` passed three local six-case routes:
18 cases, all 75 referenced frames plus three startup originals inspected, and
three clean exits. Actual buffering states were true/false/true on the same
XRender backend and viewport. `build/audit-buffer-pair-7d9668ed/comparison-review.json`
records the exact images, metadata and scope. Intel comparison 43738815451
observed the same Metal backend with buffering true then false. The default
repeated Left's failure; the disabled copy produced incomplete scenes and
aborted before the sixth row, so the third launch was blocked. All retained
control and diagnostic originals were inspected. The buffering override is not
a correction, and final inventory verdicts remain unchanged. Exact receipts:
`build/ci-buffer-comparison-7d9668ed-macos-intel/build/controls-capture-comparison/native-visual-review.json`.

The test-only scheduled-repaint branch at `fb688398` passed six local physical
cases, with all 25 referenced frames and startup inspected, exit 0 and 26 distinct
request nonces. Failed requests now retain distinct originals and cannot let
their old marker satisfy a later request. This does not change production
rendering or the ordinary full audit's synchronous state observations. Local
evidence: `build/audit-source-7d9668ed-scheduled-repaint/REVIEW.md`.

Intel scheduled run 43740408807 still fails Left's strict held/release proof.
The actual Metal backend retains enabled buffering, and all 25 requests used
scheduled repaint with distinct nonces. The held capture returned 26 old frames
before accepting the fox at the boundary after a 3.319-second physical hold.
All 24 referenced frames, startup and 18 retained rejected originals were
inspected; the other five filtered rows pass only their diagnostic scope.
The independent stream presents the new nonce 2.858 seconds after its Java
drawing callback, with 165 newer callbacks in between; the total recorded
safepoint time in that gap is 93.928 ms. The 677 ordered Java callbacks and clean
collection/cleanup do not establish native presentation responsiveness. Exact review:
`build/ci-scheduled-7d9668ed-macos-intel/build/controls-capture-native-app/review/native-review.json`.
Normal repaint scheduling has therefore not resolved the failure. The separate
real-Main probe 43740419423 stopped before sending any input because its initial
guard ran before the ordinary window was ready. Its owned process was terminated
and the corrected bounded readiness check ran separately in 43741464146. That
retry reached ordinary gameplay: A moved and stopped normally, but the first
Left showed a 3.123-second gap between complete stream frames despite its
independently bounded 356.831 ms OS-level hold/release. The next frame showed the
fox at the boundary; later animation there is not braking proof. All 80 original
images were independently reviewed. Main's held capture timed out reading
AXFocusedWindow, whereas NativeAudit's snapshot path makes no such AX request.
No causal conclusion follows from that difference. Cleanup again used SIGTERM,
so physical Quit is not proved by this probe. Exact review:
`build/ci-main-ready-7d9668ed-macos-intel/build/main-movement-native-app/independent-review/review.json`.

The six-case CGL diagnostic 43741471213 also fails only Left. It actually uses
`CGLGraphicsConfig`, enabled buffering and the two requested graphics properties.
The first/latest rejected whole scenes remain at the start, while the accepted
frame reaches the wall after a 3.355-second hold (21 stale reads then one fresh).
All 24 referenced frames, startup and both rejected originals were inspected.
Exact scope and hashes:
`build/ci-opengl-7d9668ed-macos-intel/build/controls-capture-native-app/review/native-review.json`.
The alternate backend has not resolved this failure. Production rendering flags
are unchanged, and no full Intel pass is credited.

The stream-only ordinary-Main run 43743043450 reproduced the first-Left delay
without synchronous window queries during the hold or early recovery. Its live
native sample records all 568 AppKit main-thread samples in Services-menu
population, including 560 waiting synchronously for a VoiceShortcutClient XPC
reply. Left was physically released and acknowledged after 357.015 ms. The
native surface still froze and then showed the fox at the boundary, so recovery
remains failed. Evidence is under
`build/ci-main-stream-sampled-7d9668ed-macos-intel/build/main-movement-native-app/`.
A Mac-only candidate removes that unused native Services submenu through public
AppKit APIs while preserving the other application-menu items. It is not yet
accepted as a fix or credited as control coverage.

The paired snapshot attempt 43743028454 and retry 43743527267 stopped before
Left or live sampling: their independent release timing limits failed during
D preparation and Return respectively. All four and three original frames were
inspected. These invalid trials remain at
`build/ci-main-snapshot-sampled-7d9668ed-macos-intel/` and
`build/ci-main-snapshot-sampled-repeat-7d9668ed-macos-intel/`; neither supplies a
snapshot-versus-stream treatment comparison or physical Quit proof.

Current Intel audio separately passes all fourteen physical M/Sound cases and
84 game-only recordings in run 43732427910. Both waveform sheets and both cleanup
desktops were inspected, and all 119 original app entries match the passing
source/packaged launch and performance evidence. The exact journal is
`build/ci-audio-current-7d9668ed-macos-intel/build/audio-native-app/pcm/independent-review/review.json`.
Complete physical control review is still required before the Intel rows pass.

For macOS, a source column can say **SHARED PROOF** only after the complete
cached source and packaged app trees match, including game, runtime, launcher
configuration and signatures, and actual source startup, physical close and
performance pass. The full physical inventory runs on the bundle; a second
physical source inventory is never implied.

The earlier 88283267 and d5499672 results remain build-specific baselines in
[the verification history](history/verification-investigation.md). The old table is preserved at
`build/regressions/jump-order/controls-baseline-88283267.tsv`. Fixtures used to
reach individual states do not count as campaign traversal.

Automatic assertions, visual inspection and audio-output verification are
recorded separately in the coverage TSV and [verification record](VERIFICATION.md).
A failed or unfinished final-build rerun does not inherit a previous build's pass.

Before sending input, native audits require audio initialization to finish or
report an explicit unavailable result. A still-pending initialization aborts
within 15 seconds. On macOS a read-only accessibility check additionally requires
the ordinary game window with no modal alert or attached sheet; Java focus flags
alone are insufficient. These checks never approve a permission dialog. Missing
audio remains unverified by the separate output audit.

Copied macOS application audits can set `audit.inputSocket` to a private external
test controller. The controller binds its guard, keyboard, pointer and capture sessions to
the exact game PID, checks the ordinary native window, and uses its existing
Accessibility and screen-capture access. The game exchanges IPC only; neither it
nor the helper requests or grants permissions. `audit.root` and `audit.python`
identify the checkout and interpreter when LaunchServices starts outside the
repository. Without the socket property, the normal direct helper is unchanged.
Pointer presses and wheel events require the verified main game window. Focus-loss
tests register their separate same-process auxiliary window by its native ID;
registration observes AX focus and native-window publication for up to two seconds,
without input, and records every attempt. Movement and release there cannot
authorize a new press. Cleanup attempts every owned button release after failed acknowledgements or
disconnected sessions; any release failure is reported. This implementation
does not mark native macOS controls passed until their actual run and frame review.
The control audit writes `completion.json` after cleanup, with the actual case
count, failures and any exception. A full pass requires all 280 cases and no filter.

| Physical binding | State / expected effect |
| --- | --- |
| A, Left arrow (separately) | Playing: move and face left; release brakes |
| D, Right arrow (separately) | Playing: move and face right; release brakes |
| Space, W, Up arrow (separately) | Playing: held-height jump; release then press for double jump; no third jump |
| Left Shift, Right Shift (separately) | Playing: dash facing direction; one per press, cooldown/air limit |
| J | Playing: selected weapon once per press; locked or unequipped weapon does nothing |
| R | Playing: hurt/retry then checkpoint; unavailable in other states |
| Escape, P (separately) | Playing/retrying: pause; paused: resume; unavailable in title/results |
| M | All states: toggle sound preference; mute/unmute available output; retain unavailable status if the device failed |
| Tab, Left Shift+Tab, Right Shift+Tab | Menus: forward/backward focus and wrap |
| Up, Down | Menus: previous/next enabled action |
| Return, keypad Enter, Space | Menus: activate focused Start/Resume/Continue/Replay, gear or setting |
| Mouse left | Click Start, pause, Resume, restart, Continue, replay, every gear/settings action |
| Mouse middle, mouse right | No game/menu action |
| Mouse wheel up/down | Paused: scroll armor; no gameplay effect |
| Armor Previous / More | Paused: reach all eight sets; skip unavailable controls |
| Sound / Gentle motion | Title/paused: actual audio output / decorative-motion change |
| A+D / opposing arrows | Playing: cancel movement predictably |
| Jump+dash, turn+shoot, held/repeated inputs | Playing: obey priority, facing, cooldown; recover on release |
| Release while focus lost, then return | Playing → paused; no stuck action or automatic resume |
| Mouse release while focus lost | Title: toggle once, clear hover/pressed styling, no activation on return |
| Close window / OS quit | Exit and close audio; saved preferences remain |

Camera tracking is intentional: in the interior of a level, Gentle motion keeps
the fox at its tracking anchor while terrain moves in the opposite direction.
A/Left faces the fox left and moves terrain screen-right; D/Right faces the fox
right and moves terrain screen-left. Near world edges, the camera cannot follow
farther, so the fox moves across the screen instead. Cases 014–017 separately
exercise all four bindings after the real Gentle-motion menu toggle, checking
visible facing, independent spike landmarks and stopping after release. The
ordinary-camera cases also check visible fox movement and scrolling landmarks.

Every Gentle-motion menu binding additionally enters gameplay through Start or
Resume and records the original bat wings frozen after enabling it, then moving
after the same binding disables it. For title-menu rows, the isolated fixture
restages TITLE between activations because there is no return-to-title command.
That setup preserves the actual selected setting and is separate from the
physical input and rendered animation being tested.

The test window uses a non-interactive black/white nonce marker to confirm that
the desktop has presented the requested frame before capture. Twenty cells encode
fixed anchors and a fresh 16-bit nonce; stale frames and ambiguous cells are
rejected. A startup capture checks this before any player input. This test-only
marker tolerates capture color conversion without weakening artwork checks.
A zero-inset panel border paints it immediately after the actual game scene on
every repaint, preserving layout and input geometry. First/latest rejected
captures are retained in bounded memory during each case and written after
input release. A stale capture never becomes a successful held or release frame.
Saved PNGs retain the actual window size and letterboxing. The marker belongs
only to the audit. Input and
presentation latency tables are retained with the frames. Keyboard input uses
an additional `awt-key-receipts.jsonl` journal of every delivered press/release,
including key code, location, modifiers, event time and current case. It uses
one persistent native connection; cold server startup is recorded separately
from each delivered command. Linux batches use an independent X11 connection
and verify the OS key state before acknowledging the request. Both platforms
still require the game's key-listener receipt and the visible gameplay result.
This avoids coupling injected keys to Robot's shared AWT rendering lock without
changing the game's input handlers or simulation timing.

On macOS, the injector records actual per-side Shift flags in
`physical-os-state.jsonl`; AWT reports modifier transitions only when the
aggregate Shift state changes. The staggered-key cases still require the visible
dash and release/recovery behavior. Failed acknowledgements also release attempted
keys, so a test failure cannot intentionally leave a modifier held for later cases.
Wheel injection accounts for Quartz's sign convention, then independently checks
the delivered wheel-event direction and visible armor-page change. These harness
adaptations follow [Apple's modifier flags](https://github.com/apple-oss-distributions/IOHIDFamily/blob/main/IOHIDSystem/IOKit/hidsystem/IOLLEvent.h)
and the Java 25 [native Robot implementation](https://github.com/openjdk/jdk/blob/jdk-25%2B36/src/java.desktop/macosx/native/libawt_lwawt/awt/CRobot.m);
they do not reverse the game's input mapping or fabricate Java input events.

TITLE, PAUSED, RESPAWNING, CHAPTER_COMPLETE and WON additionally exercise disabled
gameplay bindings one at a time. Directions/jump/dash/weapon/retry cannot mutate
those states except stated menu navigation/activation. There is no countdown or
interactive loading state, controller/touch mapping, camera switch, fullscreen
shortcut, networking, accounts or text input. Window resize is supported with
letterboxing at a minimum 800×600 size. OS window-management shortcuts belong to
the operating system, not additional game commands.

If output initialization fails, title/pause buttons and gameplay/result footers
consistently display unavailable. Physical M still changes the saved preference,
without claiming sound has become available. The separate missing-output audit
checks this behavior in all six states using a real provider failure.

Audio capture must target this game's output ports, never the microphone or
system mix. A muted flag, rendered label, synthesized PCM unit test or successful
line-open alone is insufficient proof. Missing display/audio/accessibility on
any target remains explicitly unverified until actual execution succeeds.
