#!/usr/bin/env bash
# Keep native release, source and audit launchers on the same output-only policy.
set -euo pipefail
fail() { printf 'Emberwood Kotlin: %s\n' "$*" >&2; exit 2; }
(($# == 1)) || fail 'Usage: sign_mac_app.sh APP'
[[ $(uname -s) == Darwin ]] || fail 'Native Mac signing requires macOS.'
root=$(CDPATH="" cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
app=$1
[[ -d "$app/Contents/MacOS" && -f "$app/Contents/Info.plist" ]] || fail 'Expected a complete native app bundle.'
policy=$root/tools/mac_runtime_entitlements.plist
work=$(mktemp -d "${TMPDIR:-/tmp}/emberwood-sign.XXXXXX")
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

# HotSpot's MAP_JIT code cache and bundled native libraries need these two
# allowances. Output-only playback needs no microphone/resource entitlement.
# Both architectures passed native startup and process-only PCM with this policy.
# Sign only the outer executable; preserve the already-signed bundled runtime.
codesign --force --sign - --options runtime --entitlements "$policy" "$app" >&2
codesign --verify --deep --strict "$app" >&2
details=$(codesign --display --verbose=4 "$app" 2>&1) || fail 'Cannot read the resulting signature.'
[[ $details =~ flags=0x([[:xdigit:]]+) ]] || fail 'The resulting signature has no code flags.'
flags=${BASH_REMATCH[1]}
(( (16#$flags & 0x10000) != 0 )) || fail 'The resulting signature does not enable Hardened Runtime.'
codesign --display --entitlements :- "$app" > "$work/observed.plist"

# Canonical XML distinguishes Boolean true from strings or other plist values.
# Sorting is sufficient for this flat, two-Boolean dictionary and ignores key
# ordering; any extra key/value or different type makes the comparison fail.
plutil -convert xml1 -o "$work/expected.xml" "$policy"
plutil -convert xml1 -o "$work/observed.xml" "$work/observed.plist"
LC_ALL=C sort "$work/expected.xml" > "$work/expected.sorted"
LC_ALL=C sort "$work/observed.xml" > "$work/observed.sorted"
cmp -s "$work/expected.sorted" "$work/observed.sorted" || fail 'The resulting entitlements differ from the exact output-only policy.'
printf 'Verified native app signature: flags=0x%s, two JIT/library entitlements.\n' "$flags" >&2
