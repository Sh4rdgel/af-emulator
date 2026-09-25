# Reverse-Engineering Workflow

This project now keeps build-specific Assault Fire PH **v1.0.0.24** reverse-engineering knowledge in one place instead of copying addresses into one-off probes.

The first tool is:

```text
tools/research/afre.py
tools/research/af_symbols_10024.json
```

AFRE v1 is deliberately static/read-only. It does not attach to, patch, hook, suspend, or modify a running game process.

## 1. Validate the executable first

Point `AF_GAME_DIR` at your real `Binaries\Win32` directory:

```powershell
$env:AF_GAME_DIR = "D:\YourGameFolder\Binaries\Win32"
.\.venv\Scripts\python.exe .\tools\research\afre.py status
```

Or pass an executable explicitly:

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py status --exe "D:\YourGameFolder\Binaries\Win32\TGame_AFDEV.exe"
```

AFRE validates the SHA-256, image base, image size, and original entry point before treating the binary as the supported build.

## 2. Use named symbols instead of memorizing addresses

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py symbols
.\.venv\Scripts\python.exe .\tools\research\afre.py symbols --filter World
.\.venv\Scripts\python.exe .\tools\research\afre.py symbol GWorld
.\.venv\Scripts\python.exe .\tools\research\afre.py layout APlayerController
```

When a new address or structure offset is verified, add it to `af_symbols_10024.json` so future tools share the finding.

Check the catalog itself before doing a longer RE session:

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py audit-catalog
```

You can also export all known absolute symbols as an IDA IDC script or CSV:

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py export-labels --format idc --out af_10024_labels.idc
.\.venv\Scripts\python.exe .\tools\research\afre.py export-labels --format csv --out af_10024_labels.csv
```

## 3. Query the UE3 object database

The object database is:

```text
tools/research/af_objects_10024.json
```

It stores reflection layouts, gameplay objects, native TG classes, script classes, bit masks, and known layout conflicts recovered from prior project research.

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py objects
.\.venv\Scripts\python.exe .\tools\research\afre.py objects --filter Player
.\.venv\Scripts\python.exe .\tools\research\afre.py object PVEPlayerController
.\.venv\Scripts\python.exe .\tools\research\afre.py field PVEPlayerController HUD
.\.venv\Scripts\python.exe .\tools\research\afre.py find-field Connection
.\.venv\Scripts\python.exe .\tools\research\afre.py names --core-only
.\.venv\Scripts\python.exe .\tools\research\afre.py names --runtime-only
.\.venv\Scripts\python.exe .\tools\research\afre.py audit-objects
.\.venv\Scripts\python.exe .\tools\research\afre.py conflicts
```

The database deliberately records unresolved conflicts instead of silently choosing one value. In particular, prior live PVE lifecycle work used the controller fields around `+0x370`, while later AFDEV loader code uses the `+0x66C` family. Keep both until object ownership is revalidated.

Do not store live UObject instance addresses in this file; those are session-specific. Store stable class layouts, constructors, vtables, functions, relationships, and verified masks.

## 4. Query protocol knowledge

Packet and protocol research is kept separately in:

```text
tools/research/af_protocol_10024.json
```

Use AFRE instead of searching old packet logs manually:

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py packets
.\.venv\Scripts\python.exe .\tools\research\afre.py packets --filter Chat
.\.venv\Scripts\python.exe .\tools\research\afre.py packet A403
.\.venv\Scripts\python.exe .\tools\research\afre.py packet C2ZN_ReqChatP2P
.\.venv\Scripts\python.exe .\tools\research\afre.py voice
.\.venv\Scripts\python.exe .\tools\research\afre.py audit-protocol
```

Every packet entry carries a validation status. Live captures, client-ID recovery, emulator-only implementations, tentative names, and unknown paths must remain distinguishable.

Voice is intentionally recorded as unknown until a real two-client voice session identifies its transport and packet format. Do not reuse FF02 as a voice candidate; it is tracked as telemetry/anti-bot reporting.

## 5. Resolve crash and trace addresses



For one address:

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py resolve 0x00DA2765
```

For a whole text log:

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py annotate crash.log --out crash.annotated.log
```

AFRE annotates addresses only when they are inside the validated TGame image and sufficiently close to a known symbol.

## 6. Detect loader/catalog drift

The AFDEV loader still contains build-specific constants. Check that its important addresses agree with the central catalog:

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py audit-loader
```

If this reports a mismatch, investigate it before copying either value into another script.

## 7. Diff structured captures

When research produces JSON before/after captures, compare them with:

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py json-diff before.json after.json
```

This is preferred over manually scanning large dumps for changed fields.

## Working rule

Before creating another `probe_*_vNN.py`:

1. validate the exact TGame/AFDEV build;
2. check whether the symbol or layout already exists in the catalog;
3. use `resolve`, `annotate`, or `json-diff` where possible;
4. if new information is verified, promote it into the catalog;
5. keep experimental code separate until the finding is reproducible.

The long-term goal is for probes to become temporary discovery tools while verified knowledge becomes permanent project data.
