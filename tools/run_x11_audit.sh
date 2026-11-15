#!/usr/bin/env bash
# Give the native audit real window-manager focus and Alt+F4 behavior inside Xvfb.
set -euo pipefail
(( $# > 0 )) || { printf '%s\n' 'Usage: tools/run_x11_audit.sh COMMAND [ARGUMENTS...]' >&2; exit 2; }
unset WAYLAND_DISPLAY
export XDG_SESSION_TYPE=x11
manager=${EMBERWOOD_OPENBOX:-openbox}
log=$(mktemp "${TMPDIR:-/tmp}/emberwood-window-manager.XXXXXX")
"$manager" --sm-disable >"$log" 2>&1 &
manager_pid=$!
cleanup() {
    kill "$manager_pid" 2>/dev/null || true
    wait "$manager_pid" 2>/dev/null || true
    rm -f -- "$log"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
ready=false
for ((attempt=0; attempt<100; attempt++)); do
    if ! kill -0 "$manager_pid" 2>/dev/null; then cat "$log" >&2; exit 2; fi
    state=$(xprop -root _NET_SUPPORTING_WM_CHECK 2>/dev/null || true)
    case $state in *'window id #'*) ready=true; break ;; esac
    sleep 0.1
done
if ! $ready; then cat "$log" >&2; printf '%s\n' 'Window manager did not become ready.' >&2; exit 2; fi
"$@"
