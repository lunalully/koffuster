#!/bin/bash
# usage: k.sh <name> [args]  runs tests/<name>/<name>.kf
export JDK_JAVAC_OPTIONS="--enable-preview --release 21"
export JDK_JAVA_OPTIONS="--enable-preview ${EXTRA_JAVA:-}"
n=$1; shift
cd ./kof-runtime-staged
timeout ${T:-60} java -jar kof.jar run tests/$n/$n.kf "$@" 2>&1 | grep -v -E "JAVA_TOOL_OPTIONS|JDK_JAVA_OPTIONS" | cut -c1-300 | head -${L:-30}
