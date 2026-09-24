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

The runtime supports per-room Maya settings passed through the server/spawner path. A client HUD difficulty label mismatch is tracked separately from the working server/gameplay handoff.

## Runtime files

- `server/assaultfire_server_v143b.py`
- `server/assaultfire_ds_spawner.py`
- `tools/server_spawner/AFDevLoader_v48_spawner_multi_instance.py`
- `tools/bridge/af_ds_udp_bridge_v9_multi_peer_latch.py`

The legacy v94 server, bridge v5 and loader v26 remain available as historical rollback/reference files.

The repository does not redistribute `TGame_AFDEV.exe`, cooked maps, private keys, player state, or runtime DS state.
