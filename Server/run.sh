#!/usr/bin/env bash
# Project Insanity Server - Run (Linux)
cd "$(dirname "$0")"

JAVA_CMD="java"
command -v java >/dev/null 2>&1 || JAVA_CMD="mise x -- java"

$JAVA_CMD -Xmx1024m -cp "bin:deps/poi.jar:deps/mysql.jar:deps/mina.jar:deps/slf4j.jar:deps/slf4j-nop.jar:deps/jython.jar:deps/log4j-1.2.15.jar" server.Server
