# Physical control coverage

All rows begin **unverified**. A successful simulation campaign does not mark
these rows passed. The native audit uses OS input, captures before/during/after
frames and checks independently measured orange-fox pixel movement for directions.
Results live in `build/audit/controls.tsv` and `build/audit-package/controls.tsv`.
Final statuses and inspected image evidence are summarized in VERIFICATION.md.

| Physical binding | State / expected effect | Verification |
| --- | --- | --- |
| A, Left arrow (separately) | Playing: accelerate screen-left, face left; release brakes | Pending native frames |
| D, Right arrow (separately) | Playing: accelerate screen-right, face right; release brakes | Pending native frames |
| Space, W, Up arrow (separately) | Playing: held-height jump; release then press for double jump; no third jump | Pending native frames |
| Left Shift, Right Shift (separately) | Playing: dash facing direction; one per press, cooldown/air limit | Pending native frames |
| J | Playing: selected weapon once per press; locked weapon does nothing | Pending native frames |
| R | Playing: hurt/retry then checkpoint; unavailable in other states | Pending native frames |
| Escape, P (separately) | Playing/retrying: pause; paused: resume; unavailable in title/results | Pending native frames |
| M | All states: mute/unmute output and displayed setting | Pending native frames + output loopback |
| Tab, Left Shift+Tab, Right Shift+Tab | Menus: forward/backward focus and wrap | Pending native frames |
| Up, Down | Menus: previous/next enabled action | Pending native frames |
| Return, keypad Enter, Space | Menus: activate focused Start/Resume/Continue/Replay, gear or setting | Pending native frames |
| Mouse left | Click Start, pause, Resume, restart, Continue, replay, every gear/settings action | Pending native frames |
| Mouse middle, mouse right | No game/menu action | Pending native frames |
| Mouse wheel up/down | Paused: scroll armor; no gameplay effect | Pending native frames |
| Armor Previous / More | Paused: reach all eight sets; skip unavailable controls | Pending native frames |
| Sound / Gentle motion | Title/paused: actual audio output / decorative-motion change | Pending frames + audio |
| A+D / opposing arrows | Playing: cancel movement predictably | Pending native frames |
| Jump+dash, turn+shoot, held/repeated inputs | Playing: obey priority, facing, cooldown; recover on release | Simulation + native audit pending |
| Release while focus lost, then return | Playing → paused; no stuck action or automatic resume | Pending native frames |
| Close window / OS quit | Exit and close audio; saved preferences remain | Pending packaged launch |

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
