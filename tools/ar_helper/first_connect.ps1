<#
  first_connect.ps1 — run this the moment the glasses are connected.
  One flow: verify adb sees the device -> dump identity -> offer camera focus check.
  If no device yet, points you at the driver fix.
#>
. "$PSScriptRoot\adb_env.ps1"
if (-not $ADB) { Write-Host "adb missing. winget install Genymobile.scrcpy" -ForegroundColor Red; exit 1 }

Write-Host "=== 1) adb devices ===" -ForegroundColor Cyan
$dev = (& $ADB devices) | Select-Object -Skip 1 | Where-Object { $_ -match '\S' }
$dev
$authorized = $dev | Where-Object { $_ -match '\tdevice' }

if (-not $authorized) {
    Write-Host "`nNo authorized device." -ForegroundColor Yellow
    if ($dev -match 'unauthorized') {
        Write-Host " -> Accept the 'Allow USB debugging' prompt in the glasses, then re-run." -ForegroundColor Yellow
    } else {
        Write-Host " -> Run tools\ar_helper\Fix-ADB-Driver-ADMIN.cmd (admin), or use WiFi ADB (AR-Helper.cmd connect)." -ForegroundColor Yellow
    }
    exit 2
}

Write-Host "`n=== 2) device identity ===" -ForegroundColor Cyan
& powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\device_info.ps1"

Write-Host "`n=== 3) near-focus test (risk a) ? ===" -ForegroundColor Cyan
$ans = Read-Host "Run camera focus test now? [y/N]"
if ($ans -match '^[yY]') {
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\capture_focus_test.ps1" -Torch
} else {
    Write-Host "Skip. Later: capture_focus_test.ps1 -Torch  |  mirror: AR-Helper.cmd mirror" -ForegroundColor DarkGray
}
Write-Host "`nDone. See START_HERE.md / docs\AR_SETUP.md for next steps." -ForegroundColor Green
