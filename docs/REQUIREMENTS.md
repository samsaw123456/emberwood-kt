# Port and quality requirements

The existing Godot project stays unchanged. This standalone Kotlin/JVM25 game
keeps twenty levels, sixty acorns, 378 gems, twenty hidden fireflies, four ordinary
monster species, six animal guardians, five weapons and eight armor sets. Preserve
fixed-step physics, double jump, dash, checkpoint gear/retry, moving/crumbling
platforms, secret discovery, gated progression, pause, settings and ending.
The removed chests, bonus shields and following companion must remain absent.

Quality requirements: current stable Kotlin/Gradle and Java25; simple fresh-install onboarding;
private dependency bootstrap/bundled runtime; no account or network needed to
play; adversarial reviews and repeated actual playtesting; external evidence of
every physical command (including alternate keys), focus/release and audio;
low-resource profiling; Git tracking/public GitHub; Linux and macOS distribution.

These requirements incorporate the user's transferable guidance from the related
Turbo Tides, memory-game and TUI sessions: observe literal left/right behavior and
every command, complete the mechanics and physics, repeat adversarial testing,
use current JVM/Kotlin/Gradle versions, and provide simple fresh/offline onboarding
with dependency setup, a readable README, and a visible launcher/icon. TUI-specific
ANSI interfaces and unrelated game content are outside this port's scope.

Mandatory control coverage is recorded in CONTROLS.md and generated native audit
artifacts. Simulation victories are supplementary. A successful build does not
prove platform launch, native input, audio or performance. Do not mark absent
facilities or untested rows passed. No finite test set establishes zero bugs.

## Working checklist

Current assessment (final platform verification remains open):

| Area | Evidence and remaining work |
| --- | --- |
| Core loop | Simulation and normal-rate native input complete all 20 levels, six guardians and 60 acorns. Final-commit CI at cacc4dc ends at 08:19 with one actual fall/retry, 201/378 gems and all 20 fireflies; its job succeeds. The d5499672 repeat separately records Java and wrapper exit 0. The earlier ce6 run remains historical evidence. |
| Physics | Automated regressions cover jump/dash limits, collision sweeps, rising-platform carry, crumble/recovery, mushrooms and boss caps. Full native traversal supplements these; final platform control reruns remain open. |
| Interaction | Every binding/state is inventoried. Final 88283267 Linux x64 and ARM64 source/bundled inventories and the Mac ARM native bundle pass all 280 rows with every rendered frame reviewed, actual fourteen-case audio proof and physical window close. Mac source uses explicit shared proof after full app-tree identity, source startup/close and performance checks; no second physical inventory is claimed. Intel review remains open. |
| Navigation/camera | Original routes and menu choices are preserved. Ordinary/Gentle camera direction was visually reviewed; final platform rows remain open. |
| State | Reset, pause, checkpoint treasure, boss defeat persistence and settings are covered by tests and native fixtures. Blocked audio initialization/shutdown has regressions; actual Linux Alt+F4 and both Mac architectures' Command+Q close the final main apps cleanly. Intel command inventory remains open after the capture-harness failure. |
| Feel/accessibility | Original art/fonts, keyboard focus, alternate keys, sound and Gentle motion remain. Footer overlap and unavailable-audio status are corrected and inspected. Both Mac architectures pass modal-free ordinary onboarding; Both architectures now pass all fourteen physical audio cases with independently reviewed PCM. Actual PCM is software-output proof, not speaker-hardware testing; timing findings remain documented. |
| Polish | Original resources are byte-verified. All regions, guardians, monsters and equipment were visually reviewed. The native twenty-level ending and every final Linux and Mac ARM control frame were inspected; Intel review remains open. |
| Robustness/performance | Both dedicated Linux architectures and both Mac architectures' actual source/bundle 180-second profiles pass their measured budgets. All Mac performance frames were reviewed; Intel's early blank startup capture is explicitly distinguished from its subsequent normally rendered title and scenes. Fresh/offline/install/upgrade/removal and Zed loading were exercised. Both architectures pass the final installer/PCM/main-app repeat and clean Ubuntu dependency recovery; container dependency proof remains separate from desktop input. |
| Scope exclusions | Controller/touch, networking, accounts, camera switches and new easter eggs are not implemented in this parity port. The original hidden fireflies remain. |

- Rules: preserve goals, camp progression, boss gates, win/replay; verify full route.
- Physics: fixed-step gravity/acceleration/jump/coyote/buffer, boundaries, swept
  walls/projectiles, moving carry, crumble/recovery, safe retry and dash limits.
- Interaction: every binding, pressed vs held, cooldowns, collisions, gear choices.
- Navigation/camera: original routes, no softlocks, left/right visible motion,
  bounded camera, reachable menu/scroll choices.
- State: title/play/pause/respawn/completion/win/restart; freeze and clear input;
  defeated bosses persist; independent saved settings and atomic updates.
- Feel/accessibility: migrated art, clear text, alternate keys, focus, mute,
  gentle motion, window resize/letterbox; no generic marketing interface.
- Polish: counts, spelling, art/collision alignment, cues, endings, credits.
- Robustness: bounded heap, idle CPU, frame times/RSS, unsupported OS/arch,
  fresh/offline/update/uninstall and paths with spaces; clean test data.
- Evidence: inspect rendered before/during/after frames and game-only audio,
  document failures, fixes, repeated results and remaining platform gaps.
