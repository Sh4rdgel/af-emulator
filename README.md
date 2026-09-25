# Assault Fire Server Emulator

**Language:** **English** | [Tagalog](README-TL.md) | [Cebuano](README-CEB.md) | [简体中文](README-ZH-CN.md) | [More languages](README-LANGUAGES.md)

[![Python](https://img.shields.io/badge/Python-3.12+-blue)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/Engine-Unreal%20Engine%203-lightgrey)](#)
[![Status](https://img.shields.io/badge/status-preservation%20research-orange)](docs/STATUS.md)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An unofficial **Assault Fire PH** preservation and server-emulation project.

The goal is to make the retired PH client usable in a local/isolated environment for preservation, interoperability research, testing, and nostalgia.

> **Supported client:** Assault Fire PH **v1.0.0.24 only**.
>
> Other versions may have different binaries, hashes, packet layouts, TCLS behavior, or offsets and are not currently supported.

> This project is not affiliated with, endorsed by, or sponsored by Tencent, Level Up! Games, or any original rights holder.

---

# ⚠️ IMPORTANT — before you click START in the launcher

For the most reliable first launch, use the **suspended TCLS launch patcher**.

Do **not** click the Assault Fire **START** button yet.

After you have completed the setup below, started the emulator, opened `client.exe` / TCLS, logged in, and reached the normal **START** screen, go to the repository root and run:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\patch_tcls_suspended_launch.py
```

Wait until the helper prints:

```text
TCLS ARMED
Click START in the Assault Fire launcher now.
```

**Only then click START.**

The helper performs the required launch sequence automatically:

```text
TCLS creates TGame.exe suspended
        ↓
TCLS finishes the shared-memory handoff
        ↓
required TGame datetime compatibility patch is applied
        ↓
TGame.exe is resumed
```

This avoids a known legacy TGame startup crash that can happen if the game begins running before the compatibility patch is active.

> **Important:** when using `patch_tcls_suspended_launch.py`, do **not** also run `patch_tgame_datetime.py` for the same launch. The suspended-launch helper already applies the datetime patch.

If the helper reports a **TGame build/signature mismatch**, stop and do not force the patch. This repository currently supports/tests Assault Fire PH **v1.0.0.24 only**.

---

# Start here

If this is your first time using the project, follow the steps below **in order**.

Do not skip a failed step. If a command says **FAILED**, fix that problem before continuing.

## What you need

You need:

- Windows 10/11
- Python 3.12
- Git
- your own Assault Fire PH **v1.0.0.24** installation
- this repository

The repository does **not** include the original game client, maps, packages, executables, or other proprietary game files.

## Important: know your two folders

You will use two different folders.

### Repository folder

This is the folder containing this README and directories such as:

```text
af-emulator
├─ server
├─ tools
├─ docs
├─ tests
└─ README.md
```

Run repository commands from this folder.

Your PowerShell prompt should look similar to:

```text
PS D:\Something\af-emulator>
```

**Do not run the commands from inside `server\`.**

### Game root

Your Assault Fire PH folder is called `<game-root>` throughout the documentation.

For example:

```text
D:\AssaultFirePH
├─ TCLS
│  ├─ Tenio
│  │  └─ TCLS.dll
│  └─ config
│     └─ APClient.dat
└─ Binaries
   └─ Win32
```

In that example:

```text
<game-root> = D:\AssaultFirePH
```

**Do not literally type `<game-root>`. Replace it with your real game folder.**

---

# Quick start

## 1. Download the emulator

Open PowerShell:

```powershell
git clone https://github.com/armangido/af-emulator.git
cd af-emulator
```

If you downloaded a ZIP instead, extract it and `cd` into the extracted repository folder.

## 2. Create the Python environment

Still from the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Checkpoint

This file must now exist:

```text
.venv\Scripts\python.exe
```

If PowerShell says:

```text
.\.venv\Scripts\python.exe is not recognized
```

you are usually in the wrong folder.

Run:

```powershell
cd ..
```

until your prompt is back at the repository root, then try again.

---

## 3. Generate the local RSA key pair

Replace `<game-root>` with your real Assault Fire PH folder:

```powershell
.\.venv\Scripts\python.exe .\tools\setup\generate_local_rsa_keypair.py --client-config-dir "<game-root>\TCLS\config"
```

Example:

```powershell
.\.venv\Scripts\python.exe .\tools\setup\generate_local_rsa_keypair.py --client-config-dir "D:\AssaultFirePH\TCLS\config"
```

This creates:

```text
server\PRIVATE.PEM
<game-root>\TCLS\config\APClient.dat
```

> **Never upload or commit `server\PRIVATE.PEM`.**

---

## 4. Verify TCLS and APClient.dat

Run:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\diagnose_tcls_apclient.py --client-root "<game-root>"
```

Example:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\diagnose_tcls_apclient.py --client-root "D:\AssaultFirePH"
```

### You want to see

```text
class              : validated raw-PEM-compatible PH TCLS build
exact byte match   : YES
same RSA key       : YES
```

If all three are correct, continue to step 5.

### If TCLS is the original/pre-patch build

If the diagnostic reports this SHA256:

```text
13EAD403452E0F25CF00658369BF4BF5FF34ED1B16027F7833FB27D398386CD1
```

fully close `client.exe` and TCLS, then run:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\patch_tcls_apclient_raw_pem.py "<game-root>\TCLS\Tenio\TCLS.dll" --apply
```

The known patched SHA256 is:

```text
3FF351E0ADB594D7544E28DB2E966A6D6EB548E9DF70DAAF4DAF58F2EE438D56
```

The patcher creates:

```text
TCLS.dll.bak
```

and refuses unknown builds.

After patching, **run the diagnostic again**.

Do not continue until it reports:

```text
exact byte match   : YES
same RSA key       : YES
```

---

## 5. Redirect the retired PH services to localhost

Open **PowerShell as Administrator**.

Go back to the repository folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\setup\setup_assaultfire_hosts.ps1
```

The required names are:

```text
127.0.0.1 tversion.levelupgames.ph
127.0.0.1 tauthproxy.levelupgames.ph
127.0.0.1 tdir.levelupgames.ph
```

You normally do not need to edit the hosts file manually; use the helper above.

---

## 6. Start the emulator

Open a normal PowerShell window and return to the repository root.

Set your game folder:

```powershell
$env:AF_CLIENT_ROOT = "<game-root>"
```

Example:

```powershell
$env:AF_CLIENT_ROOT = "D:\AssaultFirePH"
```

Then start the server:

```powershell
.\.venv\Scripts\python.exe .\server\assaultfire_server_v143b.py
```

### The server checks everything before opening ports

Startup is blocked unless all required checks pass.

A healthy startup should include:

```text
[PREFLIGHT] TCLS validated build    : YES
[PREFLIGHT] APClient exact bytes    : YES
[PREFLIGHT] same RSA key            : YES
[PREFLIGHT] hosts tversion.levelupgames.ph    : YES
[PREFLIGHT] hosts tauthproxy.levelupgames.ph  : YES
[PREFLIGHT] hosts tdir.levelupgames.ph        : YES
[PREFLIGHT] PASS - all required checks succeeded.
```

Only after that should the listeners start:

```text
[VERSION] Listening on port 9060
[AUTH] Listening on port 8000
[DIR] Listening on port 9010
[ROLE] Listening on port 65005
[ZONE] Listening on port 65006
```

### If preflight says FAILED

**Do not keep launching the client.**

Read the failed line and fix that exact problem.

Common examples:

| Failure | What to do |
| --- | --- |
| `client root is unknown` | Set `$env:AF_CLIENT_ROOT = "<game-root>"` |
| `TCLS validated build: NO` | Run step 4 again |
| `APClient exact bytes: NO` | Regenerate/reinstall the matching `APClient.dat` |
| `same RSA key: NO` | Regenerate the local RSA pair from step 3 |
| hosts check = `NO` | Run step 5 again from Administrator PowerShell |
| `PRIVATE.PEM not found` | Confirm `server\PRIVATE.PEM` exists |

---

# PvE setup

If you want PvE/dedicated-server gameplay, set these variables **before** starting v143b:

```powershell
$env:AF_CLIENT_ROOT = "<game-root>"
$env:AF_GAME_DIR = "<game-root>\Binaries\Win32"
$env:AF_DS_SPAWNER_ENABLED = "1"

.\.venv\Scripts\python.exe .\server\assaultfire_server_v143b.py
```

Example:

```powershell
$env:AF_CLIENT_ROOT = "D:\AssaultFirePH"
$env:AF_GAME_DIR = "D:\AssaultFirePH\Binaries\Win32"
$env:AF_DS_SPAWNER_ENABLED = "1"

.\.venv\Scripts\python.exe .\server\assaultfire_server_v143b.py
```

The drive letter does not matter. Point `AF_GAME_DIR` at **your actual `Binaries\Win32` folder**.

The stable PvE flow is:

```text
Create room
   ↓
reserve DS capacity
   ↓
press Start
   ↓
start the room bridge
   ↓
first valid gameplay packet
   ↓
start AFDEV
   ↓
SESSION_READY
   ↓
enter UE3 gameplay
```

The selected stock PvE map/settings are passed into the dedicated-server lifecycle.

More detail: **[PvE Runtime](docs/PVE_RUNTIME.md)**.

---

# 7. Launch Assault Fire PH

Keep the emulator PowerShell window open.

Use **one** of the following launch compatibility paths.

## Option A — normal TCLS launch

Run:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\patch_tgame_datetime.py
```

Then launch normally through `client.exe` / TCLS.

## Option B — suspended TCLS handoff

Launch TCLS, log in, and stop at the normal **START** screen.

Then run:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\patch_tcls_suspended_launch.py
```

> The suspended-launch helper already applies the datetime compatibility patch.
>
> **Do not use both launch helpers for the same launch.**

---

# Very common mistakes

Before opening an issue, check these first.

### “.venv python is not recognized”

You are probably inside the wrong folder.

Wrong:

```text
PS D:\Something\af-emulator\server>
```

Correct:

```text
PS D:\Something\af-emulator>
```

### “AP client initialization failed.”

Run step 4 again:

```powershell
.\.venv\Scripts\python.exe .\tools\patches\diagnose_tcls_apclient.py --client-root "<game-root>"
```

Do not guess. Check the TCLS hash, exact-byte result, and RSA result.

### Server starts but client never reaches AUTH

Confirm:

```text
TCLS validated build = YES
APClient exact bytes = YES
same RSA key = YES
hosts checks = YES
```

Then check **[Launcher Errors](docs/LAUNCHER_ERRORS.md)**.

### I copied `<game-root>` exactly

That is a placeholder.

Replace:

```text
<game-root>
```

with something like:

```text
D:\AssaultFirePH
```

### I changed random DLLs/config files and now nothing works

Restore your known-good client copy and repeat the setup from step 3.

Do not apply patches intended for a different TCLS/client hash.

### I am using another Assault Fire version

This repository is currently tested only with:

```text
Assault Fire PH v1.0.0.24
```

Other versions are not expected to work without additional research.

---

# Legacy security-driver note

The original PH client includes a legacy kernel-level security/anti-cheat component designed for an older Windows environment.

On modern Windows it may cause startup failures, crashes, or driver initialization problems **before the emulator is contacted**.

If the client fails before normal VERSION/AUTH traffic appears, the problem may be in the client/OS compatibility layer rather than the emulator.

This project does **not** provide bypass, disabling, kernel-modification, or active security-circumvention instructions.

See **[Vital Setup Notes](docs/VITAL_SETUP_NOTES.md)** for known symptoms and project scope.

---

# What works

The current public baseline is **v143b**.

Working or integrated areas include:

- VERSION / AUTH / DIR / ROLE / ZONE local backend flow
- existing/local profile login path
- dynamic room support
- shared-room multiplayer work
- PvE dedicated-server allocation and lifecycle
- stock-selected PvE map/settings propagation
- lazy AFDEV startup
- v48 AFDEV loader
- v9 multi-peer UDP bridge
- zero-DSKey readiness path
- inventory/shop/profile preservation work

Some features remain partial or under validation, including first-time nickname/account flow and parts of social/progression systems.

See **[Project Status](docs/STATUS.md)** for the current matrix.

---

# Troubleshooting

Use the symptom that actually matches your problem.

| Problem | Read this |
| --- | --- |
| First setup / unsure what to run | [Getting Started](docs/GETTING_STARTED.md) |
| AP/TCLS/TGame launcher error | [Launcher Errors](docs/LAUNCHER_ERRORS.md) |
| TCLS → TGame handoff problem | [Launch Requirements](docs/LAUNCH_REQUIREMENTS.md) |
| PvE / AFDEV / dedicated server | [PvE Runtime](docs/PVE_RUNTIME.md) |
| Legacy driver / modern Windows issue | [Vital Setup Notes](docs/VITAL_SETUP_NOTES.md) |
| Not sure whether a feature exists | [Project Status](docs/STATUS.md) |
| Common question | [FAQ](docs/FAQ.md) |

When reporting a bug, include:

- the exact error text
- what step you were on
- the command you ran
- the last relevant server/client log lines
- your client version
- relevant hashes when the issue involves TCLS/TGame

Do **not** upload `PRIVATE.PEM`, passwords, account credentials, or proprietary game binaries.

---

# Documentation

| Document | Purpose |
| --- | --- |
| [Getting Started](docs/GETTING_STARTED.md) | full first-time setup |
| [Project Status](docs/STATUS.md) | implemented / partial / planned features |
| [PvE Runtime](docs/PVE_RUNTIME.md) | PvE and dedicated-server flow |
| [Launch Requirements](docs/LAUNCH_REQUIREMENTS.md) | TCLS → TGame requirements |
| [Launcher Errors](docs/LAUNCHER_ERRORS.md) | known AP/TCLS/TGame errors |
| [Architecture](docs/ARCHITECTURE.md) | ports, services, and data flow |
| [Research Findings](docs/RESEARCH_FINDINGS.md) | verified protocol/runtime findings |
| [RE Tooling](docs/RE_TOOLING.md) | reusable build validation, symbols, address annotation, and research workflow |
| [FAQ](docs/FAQ.md) | common questions |
| [Contributing](CONTRIBUTING.md) | contributing fixes and research |

---

# Repository layout

```text
server/      emulator/backend and DS lifecycle
tools/       setup, compatibility, bridge, loader, and research tools
docs/        setup, architecture, protocol notes, and troubleshooting
tests/       regression tests
.github/     issue and contribution templates
```

---

# Project scope

This repository contains original emulator code, documentation, and research tooling.

Please do **not** commit:

- original game executables or DLLs
- maps, `.upk`, `.udk`, audio, textures, or other proprietary assets
- private keys
- passwords, tokens, cookies, or account credentials
- raw memory dumps containing proprietary or personal data
- files you do not have permission to redistribute

Users must obtain any required original game files independently and lawfully.

---

# Contributing

Contributions are welcome, especially:

- reproducible protocol findings
- packet parsers/encoders
- client-launch compatibility fixes
- dedicated-server improvements
- regression tests
- documentation corrections

Read **[CONTRIBUTING.md](CONTRIBUTING.md)** before opening a pull request.

---

# License

Original code and documentation in this repository are licensed under the [MIT License](LICENSE).

The license does **not** grant rights to Assault Fire, the original client, executables, DLLs, maps, packages, artwork, audio, trademarks, or other third-party material.
