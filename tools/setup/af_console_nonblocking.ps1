# Assault Fire one-click console behavior helper.
#
# Classic Windows Console Host can pause a console process when QuickEdit
# selection mode is active and the user clicks/drags inside the window.
# Disable QuickEdit for the CURRENT console only so server/helper output keeps
# flowing even when the console window is clicked.
#
# This does not change the user's global console/registry settings.

if (-not ("AFConsoleMode" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class AFConsoleMode
{
    private const int STD_INPUT_HANDLE = -10;
    private const uint ENABLE_QUICK_EDIT_MODE = 0x0040;
    private const uint ENABLE_EXTENDED_FLAGS = 0x0080;

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr GetStdHandle(int nStdHandle);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);

    public static bool DisableQuickEdit()
    {
        IntPtr input = GetStdHandle(STD_INPUT_HANDLE);
        if (input == IntPtr.Zero || input == new IntPtr(-1))
            return false;

        uint mode;
        if (!GetConsoleMode(input, out mode))
            return false;

        mode |= ENABLE_EXTENDED_FLAGS;
        mode &= ~ENABLE_QUICK_EDIT_MODE;
        return SetConsoleMode(input, mode);
    }
}
"@
}

function Disable-AFConsoleBlockingSelection {
    try {
        [void][AFConsoleMode]::DisableQuickEdit()
    } catch {
        # Non-console hosts (some terminals/IDE shells) may not expose a
        # traditional console input handle. They do not need this workaround.
    }
}
