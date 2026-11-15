# Physical control coverage

The complete binding/state inventory and platform-specific results are recorded
in [controls-audit.tsv](controls-audit.tsv). Every row has an explicit result;
unverified platforms and missing audio evidence remain unverified. A simulation
campaign does not mark physical controls passed.

The native audit injects OS input and captures before/during/after window frames.
Its automatic assertions are followed by inspection of every referenced frame.
Source results live in `build/audit/controls.tsv`; bundled-runtime results live
in `build/audit-packaged/controls.tsv`. The complete inventory contains 280 cases.
Automatic assertions, visual inspection and audio-output verification are
recorded separately in the coverage TSV and [verification record](VERIFICATION.md).
A failed or unfinished final-build rerun does not inherit a previous build's pass.

Before sending input, native audits require audio initialization to finish or
report an explicit unavailable result. A still-pending initialization aborts
within 15 seconds. On macOS a read-only accessibility check additionally requires
the ordinary game window with no modal alert or attached sheet; Java focus flags
alone are insufficient. These checks never approve a permission dialog. Missing
audio remains unverified by the separate output audit.

| Physical binding | State / expected effect |
| --- | --- |
| A, Left arrow (separately) | Playing: move and face left; release brakes |
| D, Right arrow (separately) | Playing: move and face right; release brakes |
| Space, W, Up arrow (separately) | Playing: held-height jump; release then press for double jump; no third jump |
| Left Shift, Right Shift (separately) | Playing: dash facing direction; one per press, cooldown/air limit |
| J | Playing: selected weapon once per press; locked or unequipped weapon does nothing |
| R | Playing: hurt/retry then checkpoint; unavailable in other states |
| Escape, P (separately) | Playing/retrying: pause; paused: resume; unavailable in title/results |
| M | All states: mute/unmute output and displayed setting |
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

The test window uses a non-interactive 6×6 color marker to confirm that the desktop
has presented the requested frame before capture. Saved PNGs retain the actual
window size and letterboxing. The marker belongs only to the audit. Input and
presentation latency tables are retained with the frames. Keyboard input uses
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

Audio capture must target this game's output ports, never the microphone or
system mix. A muted flag, rendered label, synthesized PCM unit test or successful
line-open alone is insufficient proof. Missing display/audio/accessibility on
any target remains explicitly unverified until actual execution succeeds.
