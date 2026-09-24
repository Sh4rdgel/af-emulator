# Stable PvE / The Altar Bridge and Server Spawner

The current `main` branch carries the solved local The Altar handoff used by the stable **v143b** server.

## Current components

```text
server/assaultfire_server_v143b.py
server/assaultfire_ds_spawner.py
tools/bridge/af_ds_udp_bridge_v9_multi_peer_latch.py
tools/server_spawner/AFDevLoader_v48_spawner_multi_instance.py
```

The repository does **not** redistribute `TGame_AFDEV.exe`, cooked maps, private keys, or runtime player/server state.

## Current lifecycle

```text
A10A CreateRoom
  -> reserve DS slot only
  -> do not start AFDEV

A11E SetGameSettings
  -> store ModeId / MapId / SubModeId / Flags for the room

A3A0 or A113 Start
  -> arm lightweight bridge
  -> return the A11A DS assignment

first valid client DS UDP
  -> v9 bridge latches the first packet
  -> start the room's v48 AFDEV loader

AFDEV ready
  -> load SV-Maya_3_Main with PVEGame.TGSVGame
  -> enable the validated native movement/correction path
  -> apply the room Maya settings
  -> verify the live zero DS key
  -> write SESSION_READY.json

bridge
  -> release the latched first packet
  -> wait for AFDEV's first reply
  -> normal multi-peer UE3 relay becomes live
```

This prevents the old behavior where merely creating a lobby could start a dedicated server.

## Multi-player lifetime

The DS spawner tracks room membership separately from active match membership.

- `A117 QuitMatch` removes only the sending player from the active match.
- A shared AFDEV instance remains alive while other match players remain.
- The final match player ends the round without destroying the logical room.
- `A107 LeaveRoom` removes room membership.
- Room ownership transfers to a remaining player when needed.
- The final room member releases the DS slot.
- A ZONE disconnect is handled per player instead of tearing down another player's session.

## Maya difficulty/settings

`A11E` is the authoritative room-settings update used by the lazy spawn. The selected `SubModeId`/difficulty is carried into AFDEV. A PH-client Hard/Normal HUD label mismatch is tracked separately from the working authoritative room/AFDEV state.

## Configuration

Typical local test environment:

```powershell
$env:AF_GAME_DIR = "D:\YourAssaultFireFolder\Binaries\Win32"
$env:AF_DS_SPAWNER_ENABLED = "1"
$env:AF_DS_MAX_INSTANCES = "4"
.\.venv\Scripts\python.exe .\server\assaultfire_server_v143b.py
```

The default local slot layout uses public bridge ports beginning at UDP 65008 and AFDEV target ports beginning at UDP 7777. Keep these development listeners on a trusted/local network.

## Validation

The repository includes `tests/test_altar_ds_lifecycle.py` for lifecycle/integration invariants. Live Windows validation still depends on a lawfully supplied PH client and AFDEV executable.

## Legacy rollback files

These remain for historical comparison and rollback:

```text
server/assaultfire_server_v94.py
tools/bridge/af_ds_udp_bridge_v5_actor_dump.py
tools/server_spawner/AFDevLoader_v26_pve_natural_loading_completion.py
```

They are no longer the default The Altar path.

See [The Altar runtime](ALTAR_RUNTIME.md), [Project Status](STATUS.md), and [Architecture](ARCHITECTURE.md).
