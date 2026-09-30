#!/bin/bash
# usage: k.sh <name> [args]  runs src/main.kf with the given mode
# Requires a KOF 0.5.0 runtime: $KOF_HOME/bin/kof, `kof` on PATH, or
# KOFFUSTER_KOF_JAR pointing at a staged kof.jar.
export JDK_JAVA_OPTIONS="-Djdk.httpclient.allowRestrictedHeaders=host ${EXTRA_JAVA:-}"
n=$1; shift
MAIN="$(cd "$(dirname "$0")/.." && pwd)/src/main.kf"
if [ -n "${KOFFUSTER_KOF_JAR:-}" ]; then
    timeout ${T:-60} java -jar "$KOFFUSTER_KOF_JAR" run "$MAIN" "$n" "$@" 2>&1 | grep -v -E "JAVA_TOOL_OPTIONS|JDK_JAVA_OPTIONS" | cut -c1-300 | head -${L:-30}
elif [ -n "${KOF_HOME:-}" ] && [ -x "$KOF_HOME/bin/kof" ]; then
    timeout ${T:-60} "$KOF_HOME/bin/kof" run "$MAIN" "$n" "$@" 2>&1 | grep -v -E "JAVA_TOOL_OPTIONS|JDK_JAVA_OPTIONS" | cut -c1-300 | head -${L:-30}
else
    timeout ${T:-60} kof run "$MAIN" "$n" "$@" 2>&1 | grep -v -E "JAVA_TOOL_OPTIONS|JDK_JAVA_OPTIONS" | cut -c1-300 | head -${L:-30}
fi