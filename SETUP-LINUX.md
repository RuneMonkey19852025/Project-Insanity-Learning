# Project Insanity — Linux Setup Notes

Project Insanity 317 (by Sanity), from the Rune-Server 2013 re-upload.
Repo: https://github.com/Johto-Foundry/Project-Insanity-Learning

## Requirements
- Java 8 (installed globally via mise: `java@corretto-8.504.01.1`)
- A display / X11 for the client

## Build & Run

```bash
# Terminal 1 — Server (port 43594)
cd Server
bash build.sh
bash run.sh

# Terminal 2 — Client
cd Client
bash build.sh
bash run.sh
```

Client connects to `127.0.0.1:43594` (set in `Client/src/Client.java`).

## Fixes applied (repo was Windows-oriented + broken on case-sensitive filesystems)

1. **Linux scripts** — added `build.sh` / `run.sh` to both `Server/` and `Client/`
   (the repo only shipped `!Builder.bat` / `!Runner.bat`; classpath uses `:` on Linux).
   Also fixed a bug in the original `!Runner.bat`: `log4j-1.2.15.jar` was missing the
   `deps/` prefix.
2. **Client class-name case** — source declared `Client` (capital C) but 8 files
   (`Animable_Sub5, EntityDef, Entity, Jframe, MouseDetection, ObjectDef,
   ObjectManager, OnDemandFetcher`) still referenced lowercase `client`.
   Renamed all whole-word references to `Client` via sed.
3. **Server data path case** — code referenced `./Data/` (30 refs) but the folder
   was `data/`. Renamed folder to `Data` and normalized 3 lowercase refs
   (`Item.java`, `ItemWeight.java`, `ItemHandler.java`).
4. **CFG path case** — `NPCHandler.java` / `ShopHandler.java` referenced
   `./Data/CFG/` but the folder is `Data/cfg/`.
5. **Client cache path** — signlink expects `./Cache/` but folder was `cache/`;
   renamed to `Cache`.

## Login accounts

First account created on login is auto-registered (PI default behavior).
Default admin rights: edit `Data/characters/<name>.txt` → set `playerRights = 3`
while the server is stopped, or use in-game commands (`::master` etc. if enabled).

## Logs

- Server: `Server/server.log` (when started via run.sh with redirection)
- Client: `Client/client.log`

## Verify server is listening

```bash
ss -tln | grep 43594
```
