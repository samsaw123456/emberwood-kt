# Port and quality requirements

The existing Godot project stays unchanged. This standalone Kotlin/JVM25 game
keeps twenty levels, sixty acorns, 378 gems, twenty hidden fireflies, four ordinary
monster species, six animal guardians, five weapons and eight armor sets. Preserve
fixed-step physics, double jump, dash, checkpoint gear/retry, moving/crumbling
platforms, secret discovery, gated progression, pause, settings and ending.
The removed chests, bonus shields and following companion must remain absent.

Other Codex sessions supplied quality requirements, not racing or terminal-game
features: current stable Kotlin/Gradle and Java25; simple fresh-install onboarding;
private dependency bootstrap/bundled runtime; no account or network needed to
play; adversarial reviews and repeated actual playtesting; external evidence of
every physical command (including alternate keys), focus/release and audio;
low-resource profiling; Git tracking/public GitHub; Linux and macOS distribution.

Mandatory control coverage is recorded in CONTROLS.md and generated native audit
artifacts. Simulation victories are supplementary. A successful build does not
prove platform launch, native input, audio or performance. Do not mark absent
facilities or untested rows passed. No finite test set establishes zero bugs.

## Working checklist

Current assessment (final platform verification remains open):

| Area | Evidence and remaining work |
| --- | --- |
| Core loop | Both simulation and normal-rate native input complete all 20 levels, all six guardians and 60 acorns. Native victory records one actual fall/retry, 199/378 gems and all 20 fireflies. |
| Physics | Automated regressions cover jump/dash limits, collision sweeps, rising-platform carry, crumble/recovery, mushrooms and boss caps. Full native traversal supplements these; final platform control reruns remain open. |
| Interaction | Every binding/state is inventoried. The persistent OS injector fixes measured test-delivery delays; strengthened jump and wheel frames need the final complete inventory rerun. |
| Navigation/camera | Original routes and menu choices are preserved. Ordinary/Gentle camera direction was visually reviewed; final platform rows remain open. |
| State | Reset, pause, checkpoint treasure, boss defeat persistence and settings are covered by tests and native fixtures. Blocked audio initialization/shutdown now has two regression tests; rebuilt app Quit still needs platform rechecks. |
| Feel/accessibility | Original art/fonts, keyboard focus, alternate keys, sound and Gentle motion remain. Footer overlap is corrected and inspected; final Mac output-device and modal-free onboarding checks remain open. |
| Polish | Original resources are byte-verified. All regions, guardians, monsters and equipment were visually reviewed. The native twenty-level ending was inspected; final platform control evidence still needs consolidation. |
| Robustness/performance | Both dedicated Linux architectures passed the prior full matrix. Mac timer pacing and Intel output initialization are under investigation; these are not counted as passes. Fresh/offline/install/upgrade/removal and Zed loading were exercised. |
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
