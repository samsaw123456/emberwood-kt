# Emberwood Kotlin

Guide a fox through twenty forest levels, collect three acorns in each, and beat
six animal guardians. This is a separate Kotlin edition using Emberwood's existing
artwork. The original Godot game remains a separate application.

## Play

Download the file for your computer from
[Releases](https://github.com/samsaw123456/emberwood-kt/releases).

- **Ubuntu or Debian:** open the `.deb` file and choose Install. The system installer
  supplies any missing desktop libraries. Open **Emberwood Kotlin** in Applications.
- **Other Linux desktops:** extract the Linux `.tar.gz`, then run **Install Emberwood
  Kotlin.command** inside it. The application is installed for your user, with no
  administrator access. You can also run `Emberwood Kotlin/bin/emberwood-kotlin`
  directly from the extracted folder.
- **macOS:** extract the matching ZIP: `aarch64` for Apple Silicon, `x86_64` for Intel.
  Move **Emberwood Kotlin.app** to Applications, or double-click **Install Emberwood
  Kotlin.command** to install in your own Applications folder. This open-source
  build is ad-hoc signed, not Apple-notarized; macOS may require **Open Anyway** in
  Privacy & Security after your first launch attempt.

The app includes its own Java runtime. You do not need Java, Gradle, Python, Zed,
or an account to play. After downloading, it works offline. Replacing the app
keeps your settings. The original **Emberwood** launcher stays available too.

## Controls

| Action | Keys |
| --- | --- |
| Move | A / D or Left / Right |
| Jump | Space, W or Up; release and press again to double-jump |
| Dash | Shift |
| Use weapon | J, after earning one at a campfire |
| Retry from camp | R |
| Pause, equipment and settings | Esc or P |
| Mute | M |

Campfires save your place within the current level and award equipment. Spikes,
critters and falls send you back to camp. Bosses reveal their gold weak point
while resting. Collect the three acorns to open each exit. Hidden fireflies and
gems are optional. Treasure chests, bonus leaf shields and the following firefly
companion from the reverted Godot update are not part of this edition.

## Build or edit

Clone this repository, then run `./emberwood-kotlin`. The first run downloads a
private, checksum-verified **Temurin Java 25.0.5+8**, uses the checked-in
**Gradle 9.9.1** wrapper, and builds with **Kotlin 2.4.21**. It leaves your global
Java installation alone. Linux/macOS need their normal shell, `tar`, and either
`curl` or `wget` for this source-build route; use a bundled release to skip that.

`./emberwood-kotlin --build` prepares the game without opening a window.
`./emberwood-kotlin --offline` runs an existing up-to-date build with no downloads.
In Zed, choose the **Play Emberwood Kotlin** project task.

For verification, set `JAVA_HOME` to the path printed by `tools/bootstrap.sh`, then
run `./gradlew check fatJar`. Native control tests use `./gradlew nativeAudit` in a
real desktop session (or Xvfb on Linux). `python3 tools/package_app.py --install`
builds a native offline app and registers it for your user. See
[packaging and verification](docs/PACKAGING.md) for details and platform limits.

Code is Apache-2.0. Imported art keeps its original licenses;
[THIRD_PARTY.md](THIRD_PARTY.md) lists attribution and provenance.
