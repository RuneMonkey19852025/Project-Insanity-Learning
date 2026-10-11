#!/usr/bin/env bash
# Project Insanity Client - Run (Linux)
cd "$(dirname "$0")"

JAVA_CMD="java"
command -v java >/dev/null 2>&1 || JAVA_CMD="mise x -- java"

$JAVA_CMD -Xmx1024m -cp bin Jframe 10 0 highmem members 32
