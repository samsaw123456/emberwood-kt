# Emberwood Kotlin

This is the independent Kotlin/JVM port of Emberwood. Never modify the original
`../aie` project as part of this work. Keep the original assets and licenses
unchanged. Do not reintroduce the removed chests, bonus shields or companion.

Use the current pinned Kotlin/Gradle versions and Java 25. Game rules and fixed
simulation steps belong in the simulation; desktop input, rendering and audio
must use that state rather than duplicate rules. Keep original geometry, pickups,
equipment, bosses and routes authoritative in the migrated level data.

Follow the global design, verification, control-by-control audit and game checklist
requirements. Run formatting, lint, tests, native keyboard/mouse/audio checks and
installer tests before shipping. Maintain docs/CONTROLS.md and docs/VERIFICATION.md
with passed, failed and unverified evidence, including platform limitations.
A successful scripted win is not complete control coverage. Recheck screen-left
and screen-right visually for every binding, held/released inputs, focus loss,
settings and every menu. Do not call an untested macOS build verified.

Update executable `emberwood-kotlin`, Zed's Play task, README and packaging together.
Keep the Linux/macOS app identity separate as Emberwood Kotlin. Bundle a private
runtime for downloaded apps; bootstrap source builds without changing global Java.
Prefer plain on-game controls over a marketing page. Preserve legible bundled
fonts, clear keyboard focus, reduced motion, sound settings and offline play.
