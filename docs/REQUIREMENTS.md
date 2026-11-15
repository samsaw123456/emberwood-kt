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

Current assessment: final cross-platform verification remains open.

Build `7d9668ed` fixes the observed same-step jump release/re-press ordering
fault. Seven actual-handler regressions pass (three failed on the old code),
and its full 60-test suite passed. Candidate `375ae227` additionally removes the
unused native Services menu on macOS and passes 67 automated tests. Both native
Mac startup trials fail its post-clear registration check before input; an
observation-only probe is pending. First-arrow and final-build checks remain
open; the table below retains
the audited baseline's scope. No pass is silently transferred across runnable
game hashes.

| Area | Evidence and remaining work |
| --- | --- |
| Core loop | Exact-build normal-rate native input completes all 20 levels, six guardians and 60 acorns in CI43725299181. All 55 images inspected; 08:19, one real fall/retry, 201/378 gems and all 20 fireflies. Job/command succeeds with JAR hash retained. |
| Physics | Automated collision, platform, crumble, mushroom, dash and boss-cap regressions pass. Actual-handler jump-order tests fail before the fix and pass after it; native jump observations prove release cuts beyond gravity and no third-jump impulse. |
| Interaction | Final Linux source/bundle on both architectures and macOS ARM bundle each pass all 280 cases with all 1,214 referenced frames inspected, fourteen actual audio cases and physical window close. Mac ARM source has exact-app shared proof; Intel final controls remain open. |
| Navigation/camera | Original routes and menu choices preserved. Ordinary/Gentle camera motion and facing independently reviewed for all bindings on both final Linux architectures/source/bundle and macOS ARM. Final Intel rows remain open. |
| State | Pause, restart, checkpoint gear, boss persistence, settings and held/focus cleanup have automated and native coverage. Final Linux source/bundle closes physically on both architectures; both macOS ARM native launch routes pass physical Command-Q and complete control review. |
| Feel/accessibility | Original assets/fonts, keyboard focus, alternate keys and Gentle motion preserved. All eight Gentle menu bindings prove visible animation freeze/restoration. Final Linux audio passes on both CPUs and both macOS architectures pass fourteen actual PCM cases; unavailable-output six-state feedback separately inspected. |
| Polish | All 2,107 migrated resources are hash-verified. Final native campaign, every Linux source/bundle inventory frame on both CPUs and all macOS ARM control frames inspected. No generic marketing interface added; Intel visual review remains explicit. |
| Robustness/performance | Final Linux CI profiles and installer/runtime routes pass on both architectures; macOS ARM source and bundled profiles pass. Intel's first profile retained a failed 40.729 Java paints/second boss window; the repeat passed both Java-paint throughput profiles. These are not continuous native presentation-rate measurements. Repeated Intel Left checks fail, including ordinary Main in run 43741464146 with an independently bounded 357 ms hold: the own-window stream has a 3.123 s publication gap and then shows the fox at the left boundary. Scheduled repaint, disabled buffering and OpenGL did not correct the failure. A stream-only live native sample now places all 568 AppKit main-thread samples in Services-menu population, including 560 waiting for a synchronous VoiceShortcutClient XPC reply. The Mac-only unused-Services removal candidate still needs native validation; complete Intel rendered controls remain open. Its independent fourteen-case audio repeat passes. Source offline cache, install/upgrade/remove and actual Zed task loading have evidence; fresh Ubuntu dependency recovery is separately recorded. |
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
