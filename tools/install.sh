#!/usr/bin/env bash
# Shipped inside each application archive; never requires Python or a global Java.
set -euo pipefail
bundle=$(CDPATH="" cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
marker=.emberwood-kotlin-managed
fail() { printf '%s\n' "Emberwood Kotlin: $*" >&2; exit 2; }
(( $# <= 1 )) || fail 'Usage: Install Emberwood Kotlin.command [--uninstall]'
case ${1:-} in ''|--uninstall) ;; *) fail 'Usage: Install Emberwood Kotlin.command [--uninstall]' ;; esac
case $(uname -s) in
    Linux)
        app="$bundle/Emberwood Kotlin"
        base=${XDG_DATA_HOME:-$HOME/.local/share}
        destination="$base/emberwood-kotlin/app"
        desktop="$base/applications/org.emberwood.kotlin.desktop"
        icon="$base/icons/hicolor/512x512/apps/emberwood-kotlin.png"
        ;;
    Darwin)
        marker=Contents/.emberwood-kotlin-managed
        app="$bundle/Emberwood Kotlin.app"
        destination="$HOME/Applications/Emberwood Kotlin.app"
        ;;
    *) fail 'This installer supports Linux and macOS.' ;;
esac
if [[ ${1:-} == --uninstall ]]; then
    if [[ -e "$destination" ]]; then
        [[ -f "$destination/$marker" ]] || fail "Refusing to remove an unmarked directory: $destination"
        if [[ $(uname -s) == Darwin ]]; then
            registrar=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
            if [[ -x "$registrar" ]]; then "$registrar" -u "$destination"; fi
        fi
        rm -rf -- "$destination"
    fi
    if [[ $(uname -s) == Linux ]]; then rm -f -- "$desktop" "$icon"; fi
    printf '%s\n' 'Emberwood Kotlin removed. Saved settings were kept.'
    exit 0
fi
[[ -f "$app/$marker" ]] || fail 'The complete app must be beside this installer. Extract the downloaded archive first.'
if [[ -e "$destination" && ! -f "$destination/$marker" ]]; then fail "Refusing to replace an unmarked directory: $destination"; fi
parent=$(dirname -- "$destination")
mkdir -p -- "$parent"
work=$(mktemp -d "$parent/.emberwood-install.XXXXXX")
cleanup() {
    if [[ ! -e "$destination" && -e "$work/previous" ]]; then mv -- "$work/previous" "$destination"; fi
    rm -rf -- "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
cp -R -- "$app" "$work/app"
# Retain the previous app until the staged replacement is complete.
if [[ -e "$destination" ]]; then mv -- "$destination" "$work/previous"; fi
if ! mv -- "$work/app" "$destination"; then
    [[ ! -e "$work/previous" ]] || mv -- "$work/previous" "$destination"
    fail 'Could not install the replacement; the previous app was restored.'
fi
if [[ $(uname -s) == Linux ]]; then
    mkdir -p -- "$(dirname -- "$desktop")" "$(dirname -- "$icon")"
    cp -- "$destination/icon.png" "$icon"
    # Freedesktop Exec quoting is not shell quoting. Escape its reserved characters.
    executable="$destination/bin/emberwood-kotlin"
    # Literal dollars/backticks belong to the desktop path, never shell expansion.
    # shellcheck disable=SC2016
    executable=$(printf '%s' "$executable" | sed -e 's/\\/\\\\\\\\/g' -e 's/"/\\\\"/g' -e 's/\$/\\\\$/g' -e 's/`/\\\\`/g' -e 's/%/%%/g')
    cat > "$desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Emberwood Kotlin
Comment=Explore twenty forest levels. Play offline.
Exec=/bin/sh "$executable"
Icon=emberwood-kotlin
Terminal=false
Categories=Game;AdventureGame;
StartupWMClass=Emberwood Kotlin
DESKTOP
    if command -v update-desktop-database >/dev/null; then update-desktop-database "$(dirname -- "$desktop")"; fi
else
    registrar=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
    if [[ -x "$registrar" ]]; then "$registrar" -f "$destination"; fi
fi
printf '%s\n' "Installed: $destination" 'Open Applications and choose Emberwood Kotlin.'
