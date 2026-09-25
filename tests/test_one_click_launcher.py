from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "START_ASSAULT_FIRE.ps1"
README = ROOT / "README.md"


class OneClickLauncherTests(unittest.TestCase):
    def text(self, path):
        return path.read_text(encoding="utf-8", errors="replace")

    def test_one_click_entrypoint_exists(self):
        self.assertTrue(SCRIPT.is_file())

    def test_script_detects_game_beside_or_around_repo(self):
        s = self.text(SCRIPT)
        self.assertIn('TCLS\\client.exe', s)
        self.assertIn('TCLS\\Tenio\\TCLS.dll', s)
        self.assertIn('Binaries\\Win32\\TGame.exe', s)
        self.assertIn('Find-GameRoot', s)

    def test_script_bootstraps_python_and_requirements(self):
        s = self.text(SCRIPT)
        self.assertIn('Python.Python.3.12', s)
        self.assertIn('"requirements.txt"', s)
        self.assertIn('"-m", "venv"', s)
        self.assertIn('"pip", "install"', s)

    def test_existing_python312_is_detected_before_winget(self):
        s = self.text(SCRIPT)
        self.assertIn('"python312.exe"', s)
        self.assertIn('"python312"', s)
        self.assertIn('"python3.12.exe"', s)
        self.assertIn('@("py.exe", "py")', s)
        self.assertIn('"-V:3.12"', s)
        self.assertIn('"--list-paths"', s)
        self.assertIn('.venv\\Scripts\\python.exe', s)
        self.assertIn('PythonCore\\3.12\\InstallPath', s)
        self.assertLess(
            s.index('foreach ($name in @('),
            s.index('Trying Windows Package Manager (winget)'),
        )
        self.assertIn(
            'Do not trust the winget exit code by itself',
            s,
        )

    def test_launcher_prints_revision_for_stale_zip_diagnosis(self):
        s = self.text(SCRIPT)
        self.assertIn('2026-09-25-oneclick-v7', s)
        self.assertIn('Launcher revision: $LAUNCHER_REVISION', s)

    def test_launcher_does_not_elevate_entire_process(self):
        s = self.text(SCRIPT)
        self.assertIn(
            "Stay in the user's normal PowerShell environment",
            s,
        )
        self.assertIn(
            'Administrator permission only for the hosts-file repair',
            s,
        )
        self.assertNotIn(
            'Administrator access is required for the Windows hosts file and runtime launch patches.',
            s,
        )

    def test_plain_py_default_312_is_accepted(self):
        s = self.text(SCRIPT)
        self.assertIn('Python Launcher default is 3.12', s)
        self.assertIn('return $pyLauncher.Source', s)
        self.assertIn('py -m venv', s)

    def test_native_command_output_cannot_pollute_return_values(self):
        s = self.text(SCRIPT)
        self.assertIn(
            '& $Exe @Arguments 2>&1 | ForEach-Object',
            s,
        )
        self.assertIn(
            'Write-Host ([string]$_)',
            s,
        )
        self.assertIn('$exitCode = $LASTEXITCODE', s)

    def test_existing_wrong_version_venv_is_recreated(self):
        s = self.text(SCRIPT)
        self.assertIn(
            'Existing .venv is not Python 3.12; recreating it',
            s,
        )
        self.assertIn(
            'Remove-Item -LiteralPath $venvDir -Recurse -Force',
            s,
        )

    def test_openprocess_runtime_components_are_elevated(self):
        s = self.text(SCRIPT)
        self.assertIn(
            'Administrator permission is required for the server runtime',
            s,
        )
        self.assertIn(
            'Administrator permission is required for the TGame launch helper',
            s,
        )
        self.assertGreaterEqual(s.count('-Verb RunAs'), 3)
        self.assertIn(
            "$env:AF_DS_PYTHON=",
            s,
        )
        self.assertIn(
            "OpenProcess/WriteProcessMemory",
            s,
        )

    def test_console_windows_disable_quickedit_blocking(self):
        s = self.text(SCRIPT)
        helper = self.text(ROOT / "tools" / "setup" / "af_console_nonblocking.ps1")
        self.assertIn('af_console_nonblocking.ps1', s)
        self.assertGreaterEqual(
            s.count('Disable-AFConsoleBlockingSelection'),
            3,
        )
        self.assertIn('ENABLE_QUICK_EDIT_MODE = 0x0040', helper)
        self.assertIn('ENABLE_EXTENDED_FLAGS = 0x0080', helper)
        self.assertIn('mode &= ~ENABLE_QUICK_EDIT_MODE', helper)
        self.assertIn('SetConsoleMode', helper)

    def test_permanent_tcls_patch_is_prompted_and_hash_guarded(self):
        s = self.text(SCRIPT)
        self.assertIn(
            '13EAD403452E0F25CF00658369BF4BF5FF34ED1B16027F7833FB27D398386CD1',
            s,
        )
        self.assertIn(
            '3FF351E0ADB594D7544E28DB2E966A6D6EB548E9DF70DAAF4DAF58F2EE438D56',
            s,
        )
        self.assertIn('patch_tcls_apclient_raw_pem.py', s)
        self.assertIn('Patch TCLS.dll permanently', s)

    def test_script_prepares_local_afdev_from_owned_tgame(self):
        s = self.text(SCRIPT)
        expected = 'B4273F2658CA94EEBC559A997FDFCD02D51E77CE75B892250C1DB7FB80C70B51'
        self.assertIn(expected, s)
        self.assertIn('TGame_AFDEV.exe', s)
        self.assertIn(
            'Copy-Item -LiteralPath $tgame -Destination $afdev -Force',
            s,
        )
        self.assertNotIn('Invoke-WebRequest', s)

    def test_script_handles_keys_hosts_server_helper_and_client(self):
        s = self.text(SCRIPT)
        for marker in (
            'generate_local_rsa_keypair.py',
            'diagnose_tcls_apclient.py',
            'setup_assaultfire_hosts.ps1',
            'assaultfire_server_v143b.py',
            'patch_tcls_suspended_launch.py',
            'AF_CLIENT_ROOT',
            'AF_GAME_DIR',
            'AF_DS_SPAWNER_ENABLED',
            'preflight_status.json',
            'Start-Process -FilePath $clientExe',
        ):
            self.assertIn(marker, s)

    def test_readme_promotes_one_click_path(self):
        s = self.text(README)
        self.assertIn('Easiest way — use the one-click script', s)
        self.assertIn('START_ASSAULT_FIRE.ps1', s)
        self.assertIn('TGame_AFDEV.exe', s)


if __name__ == "__main__":
    unittest.main()
