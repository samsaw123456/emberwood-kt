#!/usr/bin/env bash
# Shared first-run recovery for the source launcher and portable Linux app.
set -euo pipefail
runtime=${1:-}
[[ -n "$runtime" ]] || { printf '%s\n' 'Usage: ensure_linux_desktop.sh JAVA_HOME [--launch] [--offline]' >&2; exit 2; }
shift
launch=false
offline=false
for option in "$@"; do
    case $option in
        --launch) launch=true ;;
        --offline) offline=true ;;
        *) printf 'Unknown desktop-check option: %s\n' "$option" >&2; exit 2 ;;
    esac
done
[[ $(uname -s) == Linux ]] || exit 0
# Leave genuine headless launches to the game's existing CLI diagnostic.
if $launch && [[ -z ${DISPLAY:-} ]]; then exit 0; fi

fail() {
    local message="Emberwood Kotlin: $*"
    printf '%s\n' "$message" >&2
    if [[ -n ${DISPLAY:-} && ! -t 2 ]]; then
        if command -v zenity >/dev/null; then
            zenity --error --title='Emberwood Kotlin' --text="$message" 2>/dev/null || true
        elif command -v kdialog >/dev/null; then
            kdialog --error "$message" --title 'Emberwood Kotlin' 2>/dev/null || true
        elif command -v notify-send >/dev/null; then
            notify-send -a 'Emberwood Kotlin' -u critical 'Emberwood Kotlin could not start' "$message" 2>/dev/null || true
        fi
    fi
    exit 2
}

[[ -x "$runtime/bin/java" ]] || fail 'The private Java runtime is incomplete. Extract a fresh complete application download.'
headless_probed=false
respect_explicit_headless() {
    local status=0 properties
    properties=$("$runtime/bin/java" -XshowSettings:properties -version 2>&1) || status=$?
    if ((status != 0)); then printf '%s\n' "$properties" >&2; exit "$status"; fi
    if printf '%s\n' "$properties" | awk 'tolower($1) == "java.awt.headless" && tolower($3) == "true" {found=1} END {exit !found}'; then exit 0; fi
    headless_probed=true
}
if $launch && [[ "${JAVA_TOOL_OPTIONS:-} ${JDK_JAVA_OPTIONS:-} ${_JAVA_OPTIONS:-}" == *java.awt.headless* ]]; then
    respect_explicit_headless
fi
command -v ldd >/dev/null || fail 'The desktop dependency check needs ldd from the system libc tools. On Ubuntu/Debian, use the .deb download to install its declared dependencies.'

fontconfig_library() {
    local directory file machine candidate cache linker
    local -a directories
    command -v od >/dev/null || fail 'The desktop check needs od from the system core utilities.'
    machine=$(od -An -j18 -N2 -tu2 "$runtime/bin/java" | awk '{$1=$1; print}') || fail 'Cannot inspect the private Java executable architecture.'
    [[ -n "$machine" ]] || fail 'The private Java executable has no readable architecture.'
    IFS=: read -r -a directories <<< "${LD_LIBRARY_PATH:-}"
    directories=("$runtime/lib" "$runtime/lib/server" "${directories[@]:-}")
    for directory in "${directories[@]}"; do
        [[ -n "$directory" ]] || continue
        for file in "$directory/libfontconfig.so.1" "$directory/libfontconfig.so"; do
            [[ -r "$file" ]] || continue
            candidate=$(od -An -j18 -N2 -tu2 "$file" | awk '{$1=$1; print}') || fail "Cannot inspect the font library architecture: $file"
            if [[ -n "$machine" && "$candidate" == "$machine" ]]; then printf '%s\n' "$file"; return; fi
        done
    done
    linker=$(command -v ldconfig || true)
    if [[ -z "$linker" && -x /sbin/ldconfig ]]; then linker=/sbin/ldconfig; fi
    [[ -n "$linker" ]] || fail 'The desktop check needs ldconfig from the system libc tools to locate the font library.'
    cache=$(LC_ALL=C "$linker" -p) || fail 'Cannot read the system library cache.'
    while IFS= read -r file; do
        [[ -r "$file" ]] || continue
        candidate=$(od -An -j18 -N2 -tu2 "$file" | awk '{$1=$1; print}') || fail "Cannot inspect the font library architecture: $file"
        if [[ -n "$machine" && "$candidate" == "$machine" ]]; then printf '%s\n' "$file"; return; fi
    done < <(printf '%s\n' "$cache" | awk '$1 == "libfontconfig.so.1" || $1 == "libfontconfig.so" {sub(/^.* => /, ""); print}')
}

missing_libraries() {
    local library report fontconfig
    local -a libraries
    libraries=("$runtime/lib/libawt_xawt.so" "$runtime/lib/libfontmanager.so" "$runtime/lib/libjsound.so")
    # Java dlopens fontconfig, so ldd on its own native libraries cannot find it.
    fontconfig=$(fontconfig_library) || return $?
    if [[ -n "$fontconfig" ]]; then libraries+=("$fontconfig"); else printf '%s\n' libfontconfig.so.1; fi
    for library in "${libraries[@]}"; do
        [[ -f "$library" ]] || fail "The private Java runtime is missing $library. Extract a fresh complete download."
        # libjvm/libjava belong to the bundle, not to system dependency recovery.
        report=$(LC_ALL=C LD_LIBRARY_PATH="$runtime/lib:$runtime/lib/server${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ldd "$library" 2>&1) || fail "Cannot inspect $library: $report"
        if [[ $report == *'version '*'not found'* ]]; then
            fail "This Java runtime is incompatible with the system libraries: $report. Use a current supported Linux desktop; the installer will not upgrade the operating system."
        fi
        printf '%s\n' "$report" | awk '/=> not found/ {print $1}'
    done
}

missing=$(missing_libraries | sort -u)
[[ -n "$missing" ]] || exit 0
if $launch && ! $headless_probed; then
    # Only the missing-library path needs another JVM. Respect -Djava.awt.headless
    # from any JVM options variable without parsing the user's option quoting.
    respect_explicit_headless
fi
$offline && fail "Missing desktop libraries: $missing. Offline mode will not download them. Run the installer or source launcher once online; Ubuntu/Debian users can use the .deb download."

apt=$(command -v apt-get || true)
[[ -n "$apt" ]] || fail "Missing desktop libraries: $missing. Install the packages providing these libraries with your system package manager, then retry. Automatic recovery is available with apt-get; no system changes were made."
select_packages() {
    packages=()
    while IFS= read -r library; do
        case $library in
            libX11.so.6) package=libx11-6 ;;
            libXext.so.6) package=libxext6 ;;
            libXi.so.6) package=libxi6 ;;
            libXrender.so.1) package=libxrender1 ;;
            libXtst.so.6) package=libxtst6 ;;
            libxcb.so.1) package=libxcb1 ;;
            libXau.so.6) package=libxau6 ;;
            libXdmcp.so.6) package=libxdmcp6 ;;
            libasound.so.2)
                if command -v apt-cache >/dev/null && apt-cache show libasound2t64 >/dev/null 2>&1; then package=libasound2t64; else package=libasound2; fi ;;
            libfreetype.so.6) package=libfreetype6 ;;
            libfontconfig.so.1) package=libfontconfig1 ;;
            libexpat.so.1) package=libexpat1 ;;
            libpng16.so.16)
                if command -v apt-cache >/dev/null && apt-cache show libpng16-16t64 >/dev/null 2>&1; then package=libpng16-16t64; else package=libpng16-16; fi ;;
            libbz2.so.1.0) package=libbz2-1.0 ;;
            libz.so.1) package=zlib1g ;;
            *) fail "Missing library $library has no supported automatic package mapping. Install its package using your system package manager, then retry. No system changes were made." ;;
        esac
        case " ${packages[*]:-} " in *" $package "*) ;; *) packages+=("$package") ;; esac
    done <<< "$missing"
}
select_packages
run_package_manager() {
    local -a command installer
    command=("$apt" "$@")
    if [[ $(id -u) == 0 ]]; then
        installer=("${command[@]}")
    elif [[ -t 0 ]] && command -v sudo >/dev/null; then
        installer=(sudo -- "${command[@]}")
    elif command -v pkexec >/dev/null; then
        installer=(pkexec "${command[@]}")
    else
        fail "Install the missing packages in a terminal with: sudo apt-get install ${packages[*]}. No administrator authorization tool is available here."
    fi
    "${installer[@]}"
}
# Minimal images can have no apt indexes; choose the ALSA ABI only after the
# actual distribution's package metadata is available.
command -v apt-cache >/dev/null || fail 'The apt package metadata tool is missing. Repair apt or use the system package installer before retrying.'
indexes_ready=true
for package in "${packages[@]}"; do
    if ! apt-cache show "$package" >/dev/null 2>&1; then indexes_ready=false; fi
done
if ! $indexes_ready; then
    printf '%s\n' 'Refreshing package information for the missing desktop libraries.' >&2
    run_package_manager -o Acquire::Retries=1 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 update || fail 'Could not refresh package information. Check the internet connection and repository configuration, then retry the installer.'
    select_packages
fi
printf 'Emberwood Kotlin needs these desktop packages: %s\n' "${packages[*]}" >&2
run_package_manager install --yes --no-install-recommends -- "${packages[@]}" || fail "The system installer did not finish. Retry the installer, or run: sudo apt-get install ${packages[*]}. If package downloads are outdated, run sudo apt-get update first."
remaining=$(missing_libraries | sort -u)
[[ -z "$remaining" ]] || fail "The system installer returned, but these libraries are still missing: $remaining. Reinstall the matching desktop packages before retrying."
printf '%s\n' 'Desktop dependencies are ready.' >&2
