#!/usr/bin/env bash
# One native bundle recipe for release packaging and the local source launcher.
set -euo pipefail
fail() { printf 'Emberwood Kotlin: %s\n' "$*" >&2; exit 2; }
(($# == 5)) || fail 'Usage: build_mac_app.sh JAVA_HOME JAR LINKED_RUNTIME STAGING_DIR VERSION'
[[ $(uname -s) == Darwin ]] || fail 'Native Mac app construction requires macOS.'
root=$(CDPATH="" cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
java_home=$1
jar=$2
runtime=$3
stage=$4
version=$5
[[ -x "$java_home/bin/jpackage" ]] || fail 'The private JDK has no jpackage executable.'
[[ -f "$jar" && -x "$runtime/bin/java" ]] || fail 'The game JAR and linked desktop runtime must exist.'
[[ $version =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]] || fail 'The release version must contain three numeric components.'
# CFBundleVersion cannot start with zero; preserve the public release version below.
major=$((10#${BASH_REMATCH[1]} + 1))
bundle_version=$major.${BASH_REMATCH[2]}.${BASH_REMATCH[3]}
mkdir -p -- "$stage"
app=$stage/Emberwood\ Kotlin.app
[[ ! -e "$app" && ! -L "$app" ]] || fail "App output already exists: $app"
work=$(mktemp -d "$stage/.mac-build.XXXXXX")
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
iconset=$work/Emberwood.iconset
mkdir -- "$iconset" "$work/input"
source_icon=$root/src/main/resources/assets/app/emberwood.png
for size in 16 32 128 256 512; do
    for scale in 1 2; do
        suffix=""
        [[ $scale == 1 ]] || suffix=@2x
        sips -z "$((size * scale))" "$((size * scale))" "$source_icon" \
            --out "$iconset/icon_${size}x${size}${suffix}.png" >&2
    done
done
iconutil -c icns "$iconset" -o "$work/Emberwood.icns" >&2
cp -- "$jar" "$work/input/emberwood-kotlin.jar"
"$java_home/bin/jpackage" --type app-image --name 'Emberwood Kotlin' --dest "$stage" \
    --input "$work/input" --main-jar emberwood-kotlin.jar --main-class emberwood.MainKt \
    --runtime-image "$runtime" --app-version "$bundle_version" --vendor 'Emberwood contributors' \
    --mac-package-identifier org.emberwood.kotlin --mac-app-category public.app-category.adventure-games \
    --icon "$work/Emberwood.icns" --java-options -Xms32m --java-options -Xmx256m \
    --java-options --enable-native-access=ALL-UNNAMED >&2
printf '%s\n' 'Managed by Emberwood Kotlin installer' > "$app/Contents/Resources/.emberwood-kotlin-managed"
plist_buddy=$(command -v PlistBuddy || printf '%s' /usr/libexec/PlistBuddy)
"$plist_buddy" -c "Set :CFBundleShortVersionString $version" "$app/Contents/Info.plist" >&2
if ! "$plist_buddy" -c 'Set :LSMinimumSystemVersion 12.0' "$app/Contents/Info.plist" 2>/dev/null; then
    "$plist_buddy" -c 'Add :LSMinimumSystemVersion string 12.0' "$app/Contents/Info.plist" >&2
fi
# Prepare inner signatures once, then apply the tested host policy without
# re-signing or modifying those bundled runtime files.
codesign --force --deep --sign - "$app" >&2
"$root/tools/sign_mac_app.sh" "$app"
printf '%s\n' "$app"
