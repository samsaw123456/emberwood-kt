#!/usr/bin/env bash
# Keep downloaded apps and source-launch caches on the same private runtime recipe.
set -euo pipefail
if (($# != 2)); then printf '%s\n' 'Usage: link_runtime.sh JAVA_HOME OUTPUT' >&2; exit 2; fi
java_home=$1
output=$2
[[ -x "$java_home/bin/jlink" ]] || { printf '%s\n' 'The private JDK has no jlink executable.' >&2; exit 2; }
[[ ! -e "$output" && ! -L "$output" ]] || { printf 'Runtime output already exists: %s\n' "$output" >&2; exit 2; }
exec "$java_home/bin/jlink" --add-modules java.desktop,java.logging,java.prefs,jdk.crypto.ec \
    --strip-debug --no-header-files --no-man-pages --compress=zip-6 --output "$output"
