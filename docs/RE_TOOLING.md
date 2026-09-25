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

## 3. Resolve crash and trace addresses

For one address:

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py resolve 0x00DA2765
```

For a whole text log:

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py annotate crash.log --out crash.annotated.log
```

AFRE annotates addresses only when they are inside the validated TGame image and sufficiently close to a known symbol.

## 4. Detect loader/catalog drift

The AFDEV loader still contains build-specific constants. Check that its important addresses agree with the central catalog:

```powershell
.\.venv\Scripts\python.exe .\tools\research\afre.py audit-loader
```

If this reports a mismatch, investigate it before copying either value into another script.

## 5. Diff structured captures

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
