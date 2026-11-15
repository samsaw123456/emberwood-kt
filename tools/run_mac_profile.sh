#!/usr/bin/env bash
# Retain scheduling evidence without exporting environment or host process data.
set -euo pipefail
: "${JAVA_HOME:?Set JAVA_HOME to the Java 25 JDK}"
output=${1:?Usage: run_mac_profile.sh output-directory [--application-policy] [JVM options]}
shift
mkdir -p -- "$output"
policy=()
if [[ ${1:-} == --application-policy ]]; then
    policy_tool=$(command -v taskpolicy || true)
    if [[ -z "$policy_tool" && -x /usr/sbin/taskpolicy ]]; then policy_tool=/usr/sbin/taskpolicy; fi
    if [[ -z "$policy_tool" ]]; then
        printf '%s\n' 'UNVERIFIED: taskpolicy is unavailable; no application resource policy was applied.' | tee "$output/policy-tool.txt" >&2
        exit 2
    fi
    printf 'Application policy tool: %s\n' "$policy_tool" > "$output/policy-tool.txt"
    policy=("$policy_tool" -a)
    shift
fi
"$JAVA_HOME/bin/jfr" configure --input "$JAVA_HOME/lib/jfr/profile.jfc" --output "$output/pacing.jfc" \
    'jdk.InitialEnvironmentVariable#enabled=false' 'jdk.InitialSystemProperty#enabled=false' 'jdk.SystemProcess#enabled=false'
exec python3 tools/mac_profile_observer.py --output "$output/native-process.jsonl" -- \
    "${policy[@]}" "$JAVA_HOME/bin/java" -Xms32m -Xmx128m -XX:ActiveProcessorCount=2 \
    "-XX:StartFlightRecording=filename=$output/pacing.jfr,settings=$output/pacing.jfc,dumponexit=true" \
    --enable-native-access=ALL-UNNAMED "-Dperformance.output=$output" "$@" \
    -cp build/libs/emberwood-kotlin.jar:build/classes/kotlin/test emberwood.PerformanceAudit
