# adb_env.ps1 — resolve the winget-installed scrcpy/adb paths (100% local, open-source).
# Dot-source this from other helper scripts:  . "$PSScriptRoot\adb_env.ps1"
# Sets $script:ADB and $script:SCRCPY to full exe paths (or $null if not found).
#
# Backend: force adb's LEGACY (AdbWinApi / usb_windows) backend. Verified that adb
# 37.0.0 honors ADB_LIBUSB=0 (trace shows usb_windows.cpp, not usb_libusb). The
# libusb backend can't open the RayNeo's composite ADB interface on Windows
# ("missing endpoints"); the legacy backend + the ADB interface GUID registered by
# Fix-ADB-Driver-ADMIN.cmd works. Keep this consistent for ALL helper adb/scrcpy calls.
$env:ADB_LIBUSB = '0'

function Resolve-ScrcpyDir {
    $base = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    $adb = Get-ChildItem $base -Recurse -Filter adb.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match 'scrcpy' } | Select-Object -First 1
    if ($adb) { return Split-Path $adb.FullName -Parent }
    return $null
}

$dir = Resolve-ScrcpyDir
if ($dir) {
    $script:ADB    = Join-Path $dir 'adb.exe'
    $script:SCRCPY = Join-Path $dir 'scrcpy.exe'
} else {
    # fallback: whatever is on PATH
    $script:ADB    = (Get-Command adb    -ErrorAction SilentlyContinue).Source
    $script:SCRCPY = (Get-Command scrcpy -ErrorAction SilentlyContinue).Source
}

if (-not $script:ADB) { Write-Warning 'adb.exe not found. Install with: winget install Genymobile.scrcpy' }
