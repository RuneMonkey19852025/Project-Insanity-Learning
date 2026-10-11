#!/usr/bin/env bash
# Project Insanity Server - Build (Linux)
cd "$(dirname "$0")"

JAVAC_CMD="javac"
command -v javac >/dev/null 2>&1 || JAVAC_CMD="mise x -- javac"

mkdir -p bin
$JAVAC_CMD -version

$JAVAC_CMD -classpath "deps/log4j-1.2.15.jar:deps/jython.jar:deps/xstream.jar:deps/mina.jar:deps/mysql.jar:deps/poi.jar:deps/slf4j.jar:deps/slf4j-nop.jar" \
  -d bin \
  src/server/event/*.java \
  src/server/model/items/*.java \
  src/server/model/minigames/*.java \
  src/server/model/npcs/*.java \
  src/server/model/objects/*.java \
  src/server/model/players/*.java \
  src/server/model/players/skills/*.java \
  src/server/model/players/packets/*.java \
  src/server/model/shops/*.java \
  src/server/net/*.java \
  src/server/task/*.java \
  src/server/util/*.java \
  src/server/world/*.java \
  src/server/util/log/*.java \
  src/server/*.java \
  src/server/world/map/*.java
