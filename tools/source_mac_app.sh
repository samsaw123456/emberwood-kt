#!/usr/bin/env bash
# Prepare a verified native app locally; stdout contains only its absolute path.
set -euo pipefail
fail() { printf 'Emberwood Kotlin: %s\n' "$*" >&2; exit 2; }
(($# == 2)) || fail 'Usage: source_mac_app.sh JAVA_HOME JAR'
[[ $(uname -s) == Darwin ]] || fail 'The native source launcher requires macOS.'
root=$(CDPATH="" cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=tools/cache_lock.sh
source "$root/tools/cache_lock.sh"
java_home=$(CDPATH="" cd -- "$1" && pwd)
jar=$(CDPATH="" cd -- "$(dirname -- "$2")" && pwd)/$(basename -- "$2")
[[ -f "$jar" && -f "$java_home/lib/modules" ]] || fail 'The game and complete private JDK must be prepared first.'
if command -v sha256sum >/dev/null; then hash_command=(sha256sum)
elif command -v shasum >/dev/null; then hash_command=(shasum -a 256)
else fail 'A SHA-256 utility is required (sha256sum or shasum).'; fi
hash_stream() { local digest; digest=$("${hash_command[@]}") || return; printf '%s\n' "${digest%% *}"; }
hash_file() { hash_stream < "$1"; }
hash_tree() (
    cd -- "$1"
    # Escaped relative names keep spaces/newlines unambiguous; links are not followed.
    find . \( -type f -o -type l \) -print0 |
        while IFS= read -r -d '' entry; do
            if [[ -L "$entry" ]]; then
                digest=$(readlink "$entry" | hash_stream) || exit
                printf 'link %s %q\n' "$digest" "$entry"
            else
                digest=$(hash_file "$entry") || exit
                printf 'file %s %q\n' "$digest" "$entry"
            fi
        done | LC_ALL=C sort | hash_stream
)
cache=${EMBERWOOD_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/emberwood-kotlin}/source-apps
mkdir -p -- "$cache/runtimes" "$cache/apps"
cache=$(CDPATH="" cd -- "$cache" && pwd)
lock=$cache/build.lock
work=""
cleanup() { [[ -z "$work" ]] || rm -rf -- "$work"; release_cache_lock "$lock"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
acquire_cache_lock "$lock" 'native app preparation'
marker=.emberwood-kotlin-source-cache
replace_cache() {
    local destination=$1
    [[ ! -L "$destination" ]] || fail "Refusing a symbolic cache entry: $destination"
    if [[ -e "$destination" ]]; then
        [[ -f "$destination/$marker" ]] || fail "Refusing to replace an unmarked cache entry: $destination"
        mv -- "$destination" "$destination.invalid-$(date +%s)-$$"
    fi
    printf '%s\n' 'Managed Emberwood Kotlin source cache' > "$work/$marker"
    mv -- "$work" "$destination"
    work=""
}
valid_tree() {
    local destination=$1 subtree=$2 expected actual
    [[ ! -L "$destination" && -f "$destination/$marker" && -f "$destination/tree.sha256" && -d "$destination/$subtree" ]] || return 1
    expected=$(cat "$destination/tree.sha256")
    [[ $expected =~ ^[0-9a-f]{64}$ ]] || return 1
    actual=$(hash_tree "$destination/$subtree") || return 1
    [[ $actual == "$expected" ]]
}
runtime_key=$({
    # Include native libraries as well as modules. Java 25 linkable runtimes
    # need no jmods directory; hashing the actual tree supports either layout.
    hash_tree "$java_home" || exit
    hash_file "$root/tools/link_runtime.sh" || exit
} | hash_stream)
runtime_cache=$cache/runtimes/$runtime_key
if ! valid_tree "$runtime_cache" runtime || [[ ! -x "$runtime_cache/runtime/bin/java" ]]; then
    printf '%s\n' 'Preparing the private Mac app runtime (cached for later launches).' >&2
    work=$(mktemp -d "$cache/.runtime.XXXXXX")
    "$root/tools/link_runtime.sh" "$java_home" "$work/runtime" >&2
    hash_tree "$work/runtime" > "$work/tree.sha256"
    replace_cache "$runtime_cache"
fi
runtime=$runtime_cache/runtime
runtime_hash=$(cat "$runtime_cache/tree.sha256")
jar_hash=$(hash_file "$jar")
app_key=$({
    printf '%s\n' "$jar_hash" "$runtime_hash"
    for file in "$java_home/bin/jpackage" "$root/tools/build_mac_app.sh" "$root/tools/sign_mac_app.sh" \
        "$root/tools/mac_runtime_entitlements.plist" "$root/VERSION" "$root/src/main/resources/assets/app/emberwood.png"; do hash_file "$file" || exit; done
} | hash_stream)
app_cache=$cache/apps/$app_key
app=$app_cache/Emberwood\ Kotlin.app
if ! valid_tree "$app_cache" 'Emberwood Kotlin.app' || ! codesign --verify --deep --strict "$app" 2>/dev/null; then
    printf '%s\n' 'Preparing Emberwood Kotlin as a native Mac app (cached for later launches).' >&2
    work=$(mktemp -d "$cache/.app.XXXXXX")
    "$root/tools/build_mac_app.sh" "$java_home" "$jar" "$runtime" "$work" "$(cat "$root/VERSION")" >&2
    cmp -- "$jar" "$work/Emberwood Kotlin.app/Contents/app/emberwood-kotlin.jar" || fail 'The native app changed the game JAR.'
    [[ $(hash_tree "$runtime") == "$runtime_hash" ]] || fail 'Native app construction modified the cached input runtime.'
    hash_tree "$work/Emberwood Kotlin.app" > "$work/tree.sha256"
    replace_cache "$app_cache"
fi
printf '%s\n' "$app"
