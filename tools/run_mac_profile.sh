#!/usr/bin/env bash
# Retain scheduling evidence without exporting environment or host process data.
set -euo pipefail
: "${JAVA_HOME:?Set JAVA_HOME to the Java 25 JDK}"
output=${1:?Usage: run_mac_profile.sh output-directory [JVM options]}
shift
mkdir -p -- "$output"
"$JAVA_HOME/bin/jfr" configure --input "$JAVA_HOME/lib/jfr/profile.jfc" --output "$output/pacing.jfc" \
    'jdk.InitialEnvironmentVariable#enabled=false' 'jdk.InitialSystemProperty#enabled=false' 'jdk.SystemProcess#enabled=false'
exec python3 tools/mac_profile_observer.py --output "$output/native-process.jsonl" -- \
    "$JAVA_HOME/bin/java" -Xms32m -Xmx128m -XX:ActiveProcessorCount=2 \
    "-XX:StartFlightRecording=filename=$output/pacing.jfr,settings=$output/pacing.jfc,dumponexit=true" \
    --enable-native-access=ALL-UNNAMED "-Dperformance.output=$output" "$@" \
    -cp build/libs/emberwood-kotlin.jar:build/classes/kotlin/test emberwood.PerformanceAudit
