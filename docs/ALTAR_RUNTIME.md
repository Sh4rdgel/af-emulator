# The Altar runtime

The repository now carries the solved local Assault Fire PH Altar runtime used by the stable v143b path.

## Lifecycle

1. A10A creates/reserves the room only. It does not start AFDEV.
2. A3A0 or A113 arms the lightweight DS bridge and returns the DS assignment path.
3. The first valid client DS UDP packet is latched.
4. The v48 AFDEV loader starts `SV-Maya_3_Main` with `PVEGame.TGSVGame`.
5. The loader preserves the native movement/correction bridge and applies the live zero DS key.
6. `SESSION_READY.json` is written only after the AFDEV world, movement path and DS key are ready.
7. The bridge releases the latched first packet and normal UE3 traffic continues.
8. Match cleanup is player-scoped; a shared DS survives until the last in-match player leaves.

## Difficulty selection

The room owner's live A11E `SetGameSettings` packet is authoritative for the next lazy AFDEV spawn. The server updates both the shared room registry and reserved DS allocation before A113/AFDEV startup.

Validated Maya submodes:

- `0x00001001` — Easy
- `0x00001002` — Normal
- `0x00001003` — Hard

The v48 loader receives the selected `SubModeId` and applies it to the live Maya `GameSettings` / PVE difficulty state before `SESSION_READY`.

A client HUD difficulty label mismatch is tracked separately from the authoritative server/AFDEV difficulty state.

## Runtime files

- `server/assaultfire_server_v143b.py`
- `server/assaultfire_ds_spawner.py`
- `tools/server_spawner/AFDevLoader_v48_spawner_multi_instance.py`
- `tools/bridge/af_ds_udp_bridge_v9_multi_peer_latch.py`

The legacy v94 server, bridge v5 and loader v26 remain available as historical rollback/reference files.

The repository does not redistribute `TGame_AFDEV.exe`, cooked maps, private keys, player state, or runtime DS state.
