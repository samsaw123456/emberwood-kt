# Port and quality requirements

This port does not modify the existing Godot project; unrelated concurrent
checkout changes are preserved. This standalone Kotlin/JVM25 game
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

Current assessment: current-build Linux controls, campaign, playback and
low-resource profiles are verified. Both Macs pass ordinary gameplay movement,
native application-menu labels and physical Quit; their complete current matrix
is still pending. The production JAR is `ae9686cb` (full hash in
[VERIFICATION.md](VERIFICATION.md)); no previous-build pass is silently transferred.
The build passes 67 Kotlin/JVM tests, and the current tools suite passes 206 Python
tests with two native-SDK skips on Linux. All 59 Python files pass Ruff checks.

| Area | Current evidence and remaining work |
| --- | --- |
| Core loop | Normal-rate native input completes all 20 levels, six guardians and 60 acorns. All 55 images inspected; 08:19, one real fall/checkpoint retry, 201/378 gems and all 20 fireflies. Pipeline/job success is retained without a separate per-PID numeric exit claim. |
| Physics | Collision, moving/crumbling platform, mushroom, dash and guardian-cap regressions pass. Actual-handler jump-order tests fail before the fix and pass after it; current Linux physical jumps prove release cuts beyond gravity, double jump and no third-jump impulse. |
| Interaction | All 280 bindings/states pass through real input in source and bundled Linux runtimes on both CPUs, with all 1,214 referenced frames inspected per route. Current Mac focused and ordinary-game passes remain partial until its full inventory closes. |
| Navigation/camera | Original routes and menu choices preserved. All four direction bindings, normal/Gentle tracking, facing and interior release are independently reviewed on all four Linux routes. Both Mac ordinary A/Left checks pass; remaining current full rows stay unverified. |
| State | Pause, retry, checkpoint gear, boss persistence, settings and held/focus cleanup have automated and full current Linux native coverage. Separate actual Main closes physically on all four Linux routes and both Macs. |
| Feel/accessibility | Original art/fonts, alternate bindings, keyboard focus and Gentle motion preserved. Every Linux Gentle-motion menu binding visibly freezes and restores animation. Current Linux actual PCM passes all 56 cases; current Mac PCM is pending. Device-free control desktops correctly retain Sound unavailable. |
| Polish | All 2,107 migrated resources retain their hashes. Every current Linux inventory frame and campaign image was inspected. Both physical Mac application menus correctly say Emberwood Kotlin and omit unused Services while preserving other commands. No generic marketing interface was added. |
| Robustness/performance | Linux source-JVM profiles pass all 22 windows and 180-second low-resource soaks; exact budgets and measurement limits are in PERFORMANCE.md. Native Mac ordinary A/Left stream gaps stay below 36 ms around the tested holds/recovery, with physical Quit and no cleanup signals. Full Mac source/bundled performance remains pending. Fresh/offline dependency recovery, install/upgrade/remove, installed launcher and actual Zed task have separate evidence. |
| Scope exclusions | Controller/touch, networking, accounts, camera switches and new easter eggs are not implemented in this parity port. Original hidden fireflies remain. |

The current full run is [43750771895](https://github.com/samsaw123456/emberwood-kt/actions/runs/43750771895).
[CONTROLS.md](CONTROLS.md), [VERIFICATION.md](VERIFICATION.md), [AUDIO.md](AUDIO.md)
and [PERFORMANCE.md](PERFORMANCE.md) contain exact receipts and limitations.
[Historical investigations](history/verification-investigation.md) preserve the
failed Services-registration candidate, native stalls, capture overruns and their
original outcomes; later passes do not erase those trials.

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
