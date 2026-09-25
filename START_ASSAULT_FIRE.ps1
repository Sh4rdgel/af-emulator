#requires -Version 5.1
<#
Assault Fire PH v1.0.0.24 - one-click setup + launcher.

Recommended layout:

    AssaultFirePH\
    |-- Binaries\Win32\TGame.exe
    |-- TCLS\client.exe
    |-- TCLS\Tenio\TCLS.dll
    |-- TGame\...
    |-- af-emulator\
        |-- START_ASSAULT_FIRE.ps1

The repository contents may also be copied directly into the game root.

This script does NOT download or redistribute Assault Fire game files.
When PvE support is prepared, TGame_AFDEV.exe is made as a local private copy
of the user's exact validated TGame.exe.
#>

[CmdletBinding()]
param(
    [switch]$SetupOnly,
    [switch]$SkipPythonInstall,
    [switch]$KeepServer
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$EXPECTED_TGAME_SHA256 = "B4273F2658CA94EEBC559A997FDFCD02D51E77CE75B892250C1DB7FB80C70B51"
$TCLS_ORIGINAL_SHA256 = "13EAD403452E0F25CF00658369BF4BF5FF34ED1B16027F7833FB27D398386CD1"
$TCLS_PATCHED_SHA256  = "3FF351E0ADB594D7544E28DB2E966A6D6EB548E9DF70DAAF4DAF58F2EE438D56"

function Write-Title([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor Cyan
}

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "[AF-ONECLICK] $Text" -ForegroundColor Yellow
}

function Stop-WithMessage([string]$Message) {
    Write-Host ""
    Write-Host "[AF-ONECLICK] ERROR: $Message" -ForegroundColor Red
    Write-Host ""
    Write-Host "Nothing else will be launched. Fix the message above, then run this script again."
    Read-Host "Press Enter to close"
    exit 1
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Quote-PS([string]$Value) {
    return "'" + $Value.Replace("'", "''") + "'"
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Backup-IfExists([string]$Path, [string]$Reason) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backup = "$Path.$Reason.$stamp.bak"
    Copy-Item -LiteralPath $Path -Destination $backup -Force
    Write-Host "[BACKUP] $Path"
    Write-Host "      -> $backup"
}

function Invoke-Checked([string]$Exe, [string[]]$Arguments, [string]$Description) {
    Write-Host "[RUN] $Description"
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

function Find-GameRoot([string]$RepoRoot) {
    $candidates = New-Object System.Collections.Generic.List[string]
    $candidates.Add($RepoRoot)

    $parent = Split-Path -Parent $RepoRoot
    if ($parent) { $candidates.Add($parent) }

    $grand = if ($parent) { Split-Path -Parent $parent } else { $null }
    if ($grand) { $candidates.Add($grand) }

    foreach ($candidate in $candidates) {
        $client = Join-Path $candidate "TCLS\client.exe"
        $tcls = Join-Path $candidate "TCLS\Tenio\TCLS.dll"
        $tgame = Join-Path $candidate "Binaries\Win32\TGame.exe"
        if (
            (Test-Path -LiteralPath $client -PathType Leaf) -and
            (Test-Path -LiteralPath $tcls -PathType Leaf) -and
            (Test-Path -LiteralPath $tgame -PathType Leaf)
        ) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

function Resolve-Python312 {
    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $resolved = (& $pyLauncher.Source -3.12 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
            if ($LASTEXITCODE -eq 0 -and $resolved) {
                $resolved = $resolved.Trim()
                if (Test-Path -LiteralPath $resolved -PathType Leaf) {
                    return $resolved
                }
            }
        } catch {}
    }

    $pf86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:ProgramFiles "Python312\python.exe")
    )
    if ($pf86) {
        $candidates += (Join-Path $pf86 "Python312\python.exe")
    }

    foreach ($candidate in $candidates) {
        if (-not $candidate -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        try {
            $version = (& $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null | Select-Object -First 1)
            if ($LASTEXITCODE -eq 0 -and $version.Trim() -eq "3.12") {
                return $candidate
            }
        } catch {}
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) {
        try {
            $version = (& $python.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null | Select-Object -First 1)
            if ($LASTEXITCODE -eq 0 -and $version.Trim() -eq "3.12") {
                return $python.Source
            }
        } catch {}
    }

    return $null
}

function Ensure-Python312 {
    $python = Resolve-Python312
    if ($python) {
        Write-Host "[OK] Python 3.12: $python" -ForegroundColor Green
        return $python
    }

    if ($SkipPythonInstall) {
        throw "Python 3.12 is missing and -SkipPythonInstall was supplied."
    }

    Write-Host "[SETUP] Python 3.12 was not found."
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw (
            "Python 3.12 is required and winget is not available for automatic installation. " +
            "Install Python 3.12 from https://www.python.org/downloads/ and run this script again."
        )
    }

    Write-Host "[SETUP] Installing Python 3.12 with winget. This is a one-time step..."
    & $winget.Source install --exact --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install Python 3.12 (exit $LASTEXITCODE)."
    }

    Start-Sleep -Seconds 2
    $python = Resolve-Python312
    if (-not $python) {
        throw "Python 3.12 installation finished, but python.exe could not be located. Reboot Windows and run this script again."
    }

    Write-Host "[OK] Python 3.12 installed: $python" -ForegroundColor Green
    return $python
}

function Ensure-Venv([string]$RepoRoot, [string]$BootstrapPython) {
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    $requirements = Join-Path $RepoRoot "requirements.txt"
    $marker = Join-Path $RepoRoot ".venv\.af_requirements_sha256"

    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        Write-Host "[SETUP] Creating Python environment..."
        Invoke-Checked -Exe $BootstrapPython -Arguments @("-m", "venv", (Join-Path $RepoRoot ".venv")) -Description "create .venv"
    } else {
        Write-Host "[OK] Python environment already exists." -ForegroundColor Green
    }

    if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
        throw "requirements.txt is missing from the emulator folder."
    }

    $wantedHash = Get-Sha256 $requirements
    $currentHash = ""
    if (Test-Path -LiteralPath $marker -PathType Leaf) {
        $currentHash = (Get-Content -LiteralPath $marker -Raw).Trim().ToUpperInvariant()
    }

    if ($currentHash -ne $wantedHash) {
        Write-Host "[SETUP] Installing/updating emulator Python dependencies..."
        Invoke-Checked -Exe $venvPython -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "-r", $requirements) -Description "install requirements"
        Set-Content -LiteralPath $marker -Value $wantedHash -Encoding ASCII
    } else {
        Write-Host "[OK] Python dependencies are already installed." -ForegroundColor Green
    }

    return $venvPython
}

function Test-AFHosts {
    $hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
    if (-not (Test-Path -LiteralPath $hostsPath -PathType Leaf)) {
        return $false
    }

    $wanted = @(
        "tversion.levelupgames.ph",
        "tauthproxy.levelupgames.ph",
        "tdir.levelupgames.ph"
    )
    $seen = @{}
    foreach ($name in $wanted) { $seen[$name] = @() }

    foreach ($line in Get-Content -LiteralPath $hostsPath) {
        $content = ($line -split "#", 2)[0].Trim()
        if (-not $content) { continue }
        $parts = $content -split "\s+"
        if ($parts.Count -lt 2) { continue }
        $ip = $parts[0]
        foreach ($rawName in $parts[1..($parts.Count - 1)]) {
            $name = $rawName.ToLowerInvariant()
            if ($seen.ContainsKey($name)) {
                $seen[$name] += $ip
            }
        }
    }

    foreach ($name in $wanted) {
        $values = @($seen[$name])
        if ($values.Count -ne 1 -or $values[0] -ne "127.0.0.1") {
            return $false
        }
    }
    return $true
}

function Ensure-Hosts([string]$RepoRoot) {
    if (Test-AFHosts) {
        Write-Host "[OK] Windows hosts mappings already point to 127.0.0.1." -ForegroundColor Green
        return
    }

    $hostScript = Join-Path $RepoRoot "tools\setup\setup_assaultfire_hosts.ps1"
    if (-not (Test-Path -LiteralPath $hostScript -PathType Leaf)) {
        throw "Hosts setup helper is missing: $hostScript"
    }

    Write-Host "[SETUP] Repairing Assault Fire localhost mappings..."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $hostScript
    if ($LASTEXITCODE -ne 0 -or -not (Test-AFHosts)) {
        throw "Windows hosts setup did not verify successfully."
    }
    Write-Host "[OK] Hosts mappings verified." -ForegroundColor Green
}

function Stop-RunningGameProcesses {
    $running = @(
        Get-Process -Name "client", "TGame", "TGame_AFDEV" -ErrorAction SilentlyContinue
    )
    if ($running.Count -eq 0) {
        return
    }

    Write-Host ""
    Write-Host "Assault Fire is already running. Setup/patching needs it closed."
    foreach ($p in $running) {
        Write-Host ("  {0} PID={1}" -f $p.ProcessName, $p.Id)
    }
    $answer = Read-Host "Close these Assault Fire processes automatically? [Y/n]"
    if ($answer -and $answer -notmatch "^(?i)y(es)?$") {
        throw "Close client.exe/TGame.exe/TGame_AFDEV.exe, then run this script again."
    }

    foreach ($p in $running) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 800
}

function Stop-ExistingEmulatorServer([string]$RepoRoot) {
    $matches = @()
    try {
        $matches = @(
            Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match "assaultfire_server_v143b\.py" -and
                $_.CommandLine.IndexOf(
                    $RepoRoot,
                    [System.StringComparison]::OrdinalIgnoreCase
                ) -ge 0
            }
        )
    } catch {}

    if ($matches.Count -eq 0) {
        return
    }

    Write-Host ""
    foreach ($p in $matches) {
        Write-Host "[FOUND] Existing emulator server PID=$($p.ProcessId)"
    }
    $answer = Read-Host "Stop the existing emulator server and start a clean one? [Y/n]"
    if ($answer -and $answer -notmatch "^(?i)y(es)?$") {
        throw "An emulator server is already running."
    }

    foreach ($p in $matches) {
        Stop-Process -Id ([int]$p.ProcessId) -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 800
}

function Ensure-PermanentTCLS([string]$RepoRoot, [string]$GameRoot, [string]$VenvPython) {
    $tcls = Join-Path $GameRoot "TCLS\Tenio\TCLS.dll"
    $hash = Get-Sha256 $tcls

    if ($hash -eq $TCLS_PATCHED_SHA256) {
        Write-Host "[OK] TCLS.dll permanent compatibility patch is already installed." -ForegroundColor Green
        return
    }

    if ($hash -ne $TCLS_ORIGINAL_SHA256) {
        throw (
            "Unsupported TCLS.dll build. Expected the verified original or patched PH v1.0.0.24 DLL, " +
            "but found SHA256 $hash. Nothing was modified."
        )
    }

    Write-Host ""
    Write-Host "Your TCLS.dll is the verified ORIGINAL PH build."
    Write-Host "The emulator can install the verified permanent raw-PEM compatibility patch once."
    Write-Host "It creates TCLS.dll.bak and verifies the final SHA256."
    Write-Host ""
    $answer = Read-Host "Patch TCLS.dll permanently so you do not have to do this setup again? [Y/n]"
    if ($answer -and $answer -notmatch "^(?i)y(es)?$") {
        throw (
            "The current emulator preflight requires the verified patched TCLS build. " +
            "No patch was applied because you selected No."
        )
    }

    $patcher = Join-Path $RepoRoot "tools\patches\patch_tcls_apclient_raw_pem.py"
    Invoke-Checked -Exe $VenvPython -Arguments @($patcher, $tcls, "--apply") -Description "apply verified permanent TCLS compatibility patch"

    $after = Get-Sha256 $tcls
    if ($after -ne $TCLS_PATCHED_SHA256) {
        throw "TCLS.dll patch finished but final SHA256 is unexpected: $after"
    }
    Write-Host "[OK] TCLS.dll permanently patched and verified." -ForegroundColor Green
}

function Ensure-Keys([string]$RepoRoot, [string]$GameRoot, [string]$VenvPython) {
    $privateKey = Join-Path $RepoRoot "server\PRIVATE.PEM"
    $publicKey = Join-Path $RepoRoot "generated\APClient.dat"
    $clientConfig = Join-Path $GameRoot "TCLS\config"
    $clientAP = Join-Path $clientConfig "APClient.dat"
    $generator = Join-Path $RepoRoot "tools\setup\generate_local_rsa_keypair.py"
    $diagnose = Join-Path $RepoRoot "tools\patches\diagnose_tcls_apclient.py"

    if (-not (Test-Path -LiteralPath $clientConfig -PathType Container)) {
        throw "Missing client config folder: $clientConfig"
    }

    $needGenerate = (
        -not (Test-Path -LiteralPath $privateKey -PathType Leaf) -or
        -not (Test-Path -LiteralPath $publicKey -PathType Leaf)
    )

    if ($needGenerate) {
        Write-Host "[SETUP] Local RSA/APClient pair is incomplete; generating a fresh matching pair..."
        Backup-IfExists $privateKey "oneclick_old"
        Backup-IfExists $publicKey "oneclick_old"
        Invoke-Checked -Exe $VenvPython -Arguments @(
            $generator,
            "--client-config-dir", $clientConfig,
            "--force"
        ) -Description "generate and install local RSA/APClient pair"
    } else {
        $copyNeeded = $true
        if (Test-Path -LiteralPath $clientAP -PathType Leaf) {
            try {
                $copyNeeded = ((Get-Sha256 $clientAP) -ne (Get-Sha256 $publicKey))
            } catch {
                $copyNeeded = $true
            }
        }

        if ($copyNeeded) {
            Write-Host "[SETUP] Installing this emulator's matching APClient.dat..."
            Backup-IfExists $clientAP "oneclick_old"
            Copy-Item -LiteralPath $publicKey -Destination $clientAP -Force
        } else {
            Write-Host "[OK] APClient.dat already matches the emulator public key." -ForegroundColor Green
        }
    }

    Write-Host "[CHECK] Verifying TCLS + APClient + PRIVATE.PEM..."
    & $VenvPython $diagnose --client-root $GameRoot
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] TCLS/RSA/APClient verification passed." -ForegroundColor Green
        return
    }

    Write-Host "[REPAIR] Existing RSA files are inconsistent. Rebuilding the local pair..."
    Backup-IfExists $privateKey "oneclick_mismatch"
    Backup-IfExists $publicKey "oneclick_mismatch"
    Backup-IfExists $clientAP "oneclick_mismatch"

    Invoke-Checked -Exe $VenvPython -Arguments @(
        $generator,
        "--client-config-dir", $clientConfig,
        "--force"
    ) -Description "regenerate matching local RSA/APClient pair"

    & $VenvPython $diagnose --client-root $GameRoot
    if ($LASTEXITCODE -ne 0) {
        throw "TCLS/RSA/APClient verification still fails after automatic repair."
    }
    Write-Host "[OK] TCLS/RSA/APClient repaired and verified." -ForegroundColor Green
}

function Ensure-AFDev([string]$GameRoot) {
    $win32 = Join-Path $GameRoot "Binaries\Win32"
    $tgame = Join-Path $win32 "TGame.exe"
    $afdev = Join-Path $win32 "TGame_AFDEV.exe"

    $tgameHash = Get-Sha256 $tgame
    if ($tgameHash -ne $EXPECTED_TGAME_SHA256) {
        throw (
            "Unsupported TGame.exe. This project currently supports Assault Fire PH v1.0.0.24 only. " +
            "Expected SHA256 $EXPECTED_TGAME_SHA256 but found $tgameHash. Nothing was patched."
        )
    }
    Write-Host "[OK] TGame.exe is the validated PH v1.0.0.24 build." -ForegroundColor Green

    $replace = $false
    if (-not (Test-Path -LiteralPath $afdev -PathType Leaf)) {
        $replace = $true
        Write-Host "[SETUP] TGame_AFDEV.exe is missing."
    } else {
        $afdevHash = Get-Sha256 $afdev
        if ($afdevHash -ne $EXPECTED_TGAME_SHA256) {
            Write-Host "[REPAIR] Existing TGame_AFDEV.exe is not the validated build."
            Backup-IfExists $afdev "oneclick_wrong_build"
            $replace = $true
        }
    }

    if ($replace) {
        Write-Host "[SETUP] Creating TGame_AFDEV.exe from YOUR OWN validated TGame.exe..."
        Copy-Item -LiteralPath $tgame -Destination $afdev -Force
    }

    $finalHash = Get-Sha256 $afdev
    if ($finalHash -ne $EXPECTED_TGAME_SHA256) {
        throw "TGame_AFDEV.exe verification failed after local copy."
    }

    Write-Host "[OK] PvE AFDEV runtime is present and verified." -ForegroundColor Green
    Write-Host "     (Local private copy only; the emulator repository does not redistribute this game binary.)"
}

function Wait-ForLaunchGate([string]$StatusPath, [int]$TimeoutSeconds = 45) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $last = $null

    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $StatusPath -PathType Leaf) {
            try {
                $last = Get-Content -LiteralPath $StatusPath -Raw | ConvertFrom-Json
                if ($last.launch_ready -eq $true) {
                    return $last
                }

                if ($last.passed -eq $false -and $last.errors -and @($last.errors).Count -gt 0) {
                    $joined = (@($last.errors) -join "; ")
                    throw "Server preflight failed: $joined"
                }
            } catch {
                if ($_.Exception.Message -like "Server preflight failed:*") {
                    throw
                }
            }
        }
        Start-Sleep -Milliseconds 250
    }

    if ($last) {
        $errors = if ($last.errors) { @($last.errors) -join "; " } else { "no detailed error was recorded" }
        throw "Timed out waiting for game launch gate UNLOCKED. Last preflight: $errors"
    }
    throw "Timed out waiting for server preflight_status.json."
}

Write-Title "Assault Fire PH - ONE CLICK SETUP + PLAY"

$self = $MyInvocation.MyCommand.Path
if (-not $self) {
    Stop-WithMessage "Could not determine the launcher script path."
}
$self = (Resolve-Path -LiteralPath $self).Path

if (-not (Test-IsAdministrator)) {
    Write-Host "[AF-ONECLICK] Administrator access is required for the Windows hosts file and runtime launch patches."
    Write-Host "[AF-ONECLICK] Asking Windows for permission..."
    try {
        $elevatedArgs = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", ('"' + $self + '"')
        )
        if ($SetupOnly) { $elevatedArgs += "-SetupOnly" }
        if ($SkipPythonInstall) { $elevatedArgs += "-SkipPythonInstall" }
        if ($KeepServer) { $elevatedArgs += "-KeepServer" }

        Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $elevatedArgs
    } catch {
        Stop-WithMessage "Administrator elevation was cancelled or failed: $($_.Exception.Message)"
    }
    exit 0
}

try {
    $repoRoot = Split-Path -Parent $self
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "server\assaultfire_server_v143b.py") -PathType Leaf)) {
        throw "START_ASSAULT_FIRE.ps1 must stay in the root of the af-emulator folder."
    }

    $gameRoot = Find-GameRoot $repoRoot
    if (-not $gameRoot) {
        throw (
            "Could not find the Assault Fire PH game root. Put the ENTIRE af-emulator folder inside your " +
            "Assault Fire game folder, or copy the emulator contents directly into the game root. " +
            "The game root must contain TCLS\client.exe, TCLS\Tenio\TCLS.dll, and Binaries\Win32\TGame.exe."
        )
    }

    $win32 = Join-Path $gameRoot "Binaries\Win32"
    $clientExe = Join-Path $gameRoot "TCLS\client.exe"

    Write-Host "[OK] Emulator : $repoRoot" -ForegroundColor Green
    Write-Host "[OK] Game root: $gameRoot" -ForegroundColor Green

    Write-Step "Closing old Assault Fire processes"
    Stop-RunningGameProcesses
    Stop-ExistingEmulatorServer $repoRoot

    Write-Step "Checking Python 3.12 and emulator dependencies"
    $bootstrapPython = Ensure-Python312
    $venvPython = Ensure-Venv $repoRoot $bootstrapPython

    Write-Step "Checking the exact supported game build"
    Ensure-AFDev $gameRoot

    Write-Step "Checking TCLS.dll"
    Ensure-PermanentTCLS $repoRoot $gameRoot $venvPython

    Write-Step "Preparing the local RSA/APClient pair"
    Ensure-Keys $repoRoot $gameRoot $venvPython

    Write-Step "Checking Windows hosts mappings"
    Ensure-Hosts $repoRoot

    $env:AF_CLIENT_ROOT = $gameRoot
    $env:AF_GAME_DIR = $win32
    $env:AF_DS_SPAWNER_ENABLED = "1"

    Write-Host ""
    Write-Host "[READY] First-time setup checks are complete." -ForegroundColor Green
    Write-Host "[READY] PvE DS spawning is enabled."
    Write-Host "[READY] You no longer need to set AF_CLIENT_ROOT / AF_GAME_DIR manually."

    if ($SetupOnly) {
        Write-Host ""
        Write-Host "-SetupOnly was selected, so the server/client will not be launched."
        Read-Host "Press Enter to close"
        exit 0
    }

    Write-Step "Starting the emulator server"
    $statusPath = Join-Path $repoRoot "runtime\preflight_status.json"
    Remove-Item -LiteralPath $statusPath -Force -ErrorAction SilentlyContinue

    $serverScript = Join-Path $repoRoot "server\assaultfire_server_v143b.py"
    $serverCommand = (
        "Set-Location -LiteralPath " + (Quote-PS $repoRoot) + "; " +
        "& " + (Quote-PS $venvPython) + " " + (Quote-PS $serverScript)
    )

    $serverWindow = Start-Process -FilePath "powershell.exe" -WorkingDirectory $repoRoot -PassThru -ArgumentList @(
        "-NoProfile",
        "-NoExit",
        "-Command",
        $serverCommand
    )

    Write-Host "[WAIT] Waiting for server preflight and listener gate..."
    $status = Wait-ForLaunchGate $statusPath 45
    Write-Host "[OK] Server launch gate is UNLOCKED. Server PID=$($status.server_pid)" -ForegroundColor Green

    Write-Step "Starting the automatic TGame launch helper"
    $helper = Join-Path $repoRoot "tools\patches\patch_tcls_suspended_launch.py"
    $helperCommand = (
        "Set-Location -LiteralPath " + (Quote-PS $repoRoot) + "; " +
        "& " + (Quote-PS $venvPython) + " " + (Quote-PS $helper) + " --timeout 900"
    )

    $helperWindow = Start-Process -FilePath "powershell.exe" -WorkingDirectory $repoRoot -PassThru -ArgumentList @(
        "-NoProfile",
        "-Command",
        $helperCommand
    )

    Start-Sleep -Milliseconds 700

    Write-Step "Launching Assault Fire client.exe for you"
    Start-Process -FilePath $clientExe -WorkingDirectory (Split-Path -Parent $clientExe) | Out-Null

    Write-Title "YOU ARE DONE WITH SETUP"
    Write-Host "The emulator server is running."
    Write-Host "The launch helper is running automatically."
    Write-Host "The Assault Fire launcher was opened automatically."
    Write-Host ""
    Write-Host "What you do now:" -ForegroundColor Green
    Write-Host "  1. Log in normally in the Assault Fire launcher."
    Write-Host "  2. When the START button appears, click START."
    Write-Host ""
    Write-Host "You do NOT need to run the server, patcher, hosts helper, or client.exe manually anymore."
    Write-Host "The temporary suspended-launch patch and TGame datetime patch are applied automatically every launch."
    Write-Host ""
    Write-Host "[WAIT] Waiting for TGame.exe to appear (up to 15 minutes)..."

    $deadline = (Get-Date).AddMinutes(15)
    while ((Get-Date) -lt $deadline) {
        $game = Get-Process -Name "TGame" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($game) {
            Write-Host ""
            Write-Host "[SUCCESS] TGame.exe launched. PID=$($game.Id)" -ForegroundColor Green

            if ($KeepServer) {
                Write-Host "[SUCCESS] -KeepServer was selected; the emulator server will remain running."
                Start-Sleep -Seconds 2
                exit 0
            }

            Write-Host "[SESSION] This one-click window will stay open while you play."
            Write-Host "[SESSION] When TGame.exe closes, it will stop the emulator server automatically."

            try {
                Wait-Process -Id $game.Id
            } catch {}

            Write-Host ""
            Write-Host "[CLEANUP] TGame.exe closed. Stopping the emulator server..."
            try {
                if ($status.server_pid) {
                    Stop-Process -Id ([int]$status.server_pid) -Force -ErrorAction SilentlyContinue
                }
            } catch {}
            try {
                if ($serverWindow -and -not $serverWindow.HasExited) {
                    Stop-Process -Id $serverWindow.Id -Force -ErrorAction SilentlyContinue
                }
            } catch {}

            Write-Host "[CLEANUP] Done." -ForegroundColor Green
            Read-Host "Press Enter to close"
            exit 0
        }

        if ($helperWindow.HasExited -and $helperWindow.ExitCode -ne 0) {
            throw "The automatic launch helper exited with code $($helperWindow.ExitCode). Check its window/log output."
        }
        Start-Sleep -Seconds 1
    }

    throw "Timed out waiting for TGame.exe. The server is still running; check the launcher/helper window for the exact error."
}
catch {
    Stop-WithMessage $_.Exception.Message
}
