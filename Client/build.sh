#!/usr/bin/env bash
# Project Insanity Client - Build (Linux)
cd "$(dirname "$0")"

JAVAC_CMD="javac"
command -v javac >/dev/null 2>&1 || JAVAC_CMD="mise x -- javac"

mkdir -p bin
$JAVAC_CMD -d bin src/*.java
