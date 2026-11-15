# Physical control coverage

The complete binding/state inventory and platform-specific results are recorded
in [controls-audit.tsv](controls-audit.tsv). Every row has an explicit result;
unverified platforms and missing audio evidence remain unverified. A simulation
campaign does not mark physical controls passed.

The current production JAR is
`ae9686cb8387d5c9f61f4a6cb73d4f9a99803fe6e93e2ce519d495d59b9bdb8c`.
All four Linux inventories pass **280 unfiltered cases** each. Every one of the
**1,214 referenced frames per run** was inspected, with exact disjoint reviewer
journals and original-byte hashes. The current Mac full inventories are still
pending; their rows remain **UNVERIFIED**, despite successful focused and
ordinary-game checks. No earlier-build pass is transferred to this JAR.

| Current Linux route | Canonical evidence directory |
| --- | --- |
| x86-64 source | `build/ci-final-ae9686cb-linux-x64/build/audit` |
| x86-64 bundled | `build/ci-final-ae9686cb-linux-x64/build/audit-packaged` |
| ARM64 source | `build/ci-final-ae9686cb-linux-arm64/build/audit` |
| ARM64 bundled | `build/ci-final-ae9686cb-linux-arm64/build/audit-packaged` |

Every directory contains `controls-reviewed.tsv`, `completion.json`, `REVIEW.md`,
`review/case-NNN.jpg`, and `review/all-frames-reviewed.json`. The final receipt
checks all 280 case IDs, their original frames and the four independent review
journals. Journals record actual contact-sheet scales and original-pixel/full-size
supplements; they do not claim that every image was opened full-size. Native
commands and both jobs succeeded in
[run 43747640143](https://github.com/samsaw123456/emberwood-kt/actions/runs/43747640143);
no separate per-PID numeric full-control exit receipt was emitted.

The control desktops have no output device and correctly show **Sound unavailable**.
All fourteen physical M/Sound cases per route separately pass actual game-only
PCM checks in [run 43747641897](https://github.com/samsaw123456/emberwood-kt/actions/runs/43747641897):
`build/ci-audio-ae9686cb-linux-{x64,arm64}/build/audio-linux/{source,packaged}/independent-review/review.json`.
The 84 recordings per route and reviewed waveforms establish software playback
through private virtual outputs, without a speaker-hardware claim. Each full-build
`audio-package-identity.json` proves identical application bytes, modes and symlinks.
Observed delivery-latency outliers remain documented in [AUDIO.md](AUDIO.md).

The corresponding audio route's `game-smoke/independent-review/review.json`
separately proves actual Main movement, release, jump, landing, pause and physical
Alt+F4, with nine inspected originals, Java/driver exit 0 and no remaining window.
Case 279 inside the inventory itself is programmatic lifecycle/preferences;
this separate evidence supplies physical OS-close proof.

On both Macs, [ordinary-game run 43750035990](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750035990)
passes bounded A/Left movement and interior release/recovery, a physical click
of the correctly named application menu, Services absence, Escape and Command-Q.
The exact images, stream timings and cleanup limits are linked in
[VERIFICATION.md](VERIFICATION.md). ARM's six-case focused run and Intel's unchanged
six-case repeat also pass strict native menu identity checks. These limited checks
do not substitute for the full 280 rows, actual PCM and source/bundle equivalence
being evaluated in [run 43750771895](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750771895).

The complete current twenty-level native campaign is reviewed separately; fixture
states used in the control inventory do not establish campaign traversal.
The previous `7d9668ed` table is retained at
`build/regressions/mac-services/controls-baseline-7d9668ed.tsv`. Earlier failed
Services candidates, timing overruns, native-stall diagnostics and their exact
limitations remain in [the investigation history](history/verification-investigation.md).

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
