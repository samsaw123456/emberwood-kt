#!/usr/bin/env bash
# Private-cache locking shared by Java bootstrap and native app preparation.
acquire_cache_lock() {
    local lock=$1 description=$2 attempt=0 owner recovery
    [[ ! -L "$lock" ]] || { printf 'Refusing a symbolic cache lock: %s\n' "$lock" >&2; return 2; }
    # Noclobber uses exclusive file creation. Some mkdir implementations report
    # success for a racing EEXIST, so a directory is not the ownership token.
    while ! (set -o noclobber; printf '%s\n' "$$" > "$lock") 2>/dev/null; do
        if [[ -f "$lock" && -r "$lock" ]]; then
            owner=$(cat "$lock")
            if [[ $owner =~ ^[0-9]+$ ]] && ! kill -0 "$owner" 2>/dev/null; then
                # Only one waiter may remove this dead owner's file. The hard-link
                # claim also lets a delayed waiter distinguish a replacement lock.
                recovery=$lock.recovery-$owner
                if ln -- "$lock" "$recovery" 2>/dev/null; then
                    if [[ $(cat "$recovery") == "$owner" && "$lock" -ef "$recovery" ]]; then rm -f -- "$lock"; fi
                    rm -f -- "$recovery"
                    continue
                fi
            fi
        fi
        ((attempt+=1))
        if ((attempt >= 300)); then
            printf 'Another %s is still running, or its lock recovery was interrupted. Lock: %s\n' "$description" "$lock" >&2
            return 2
        fi
        sleep 1
    done
}

release_cache_lock() {
    local lock=$1
    if [[ -f "$lock" && ! -L "$lock" && $(cat "$lock" 2>/dev/null) == "$$" ]]; then rm -f -- "$lock"; fi
}
