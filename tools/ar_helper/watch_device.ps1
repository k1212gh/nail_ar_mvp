# watch_device.ps1 — poll until the glasses appear in adb, then print identity.
# Runs bounded (default ~5 min) so it never hangs forever.
param([int]$TimeoutSec = 300, [int]$IntervalSec = 3)
. "$PSScriptRoot\adb_env.ps1"
if (-not $ADB) { exit 1 }
& $ADB start-server | Out-Null
$elapsed = 0
while ($elapsed -lt $TimeoutSec) {
    $line = (& $ADB devices) | Select-Object -Skip 1 | Where-Object { $_ -match '\S' }
    if ($line) {
        if ($line -match 'unauthorized') {
            Write-Host "DEVICE FOUND but UNAUTHORIZED — accept the 'Allow USB debugging' prompt in the glasses." -ForegroundColor Yellow
            & $ADB devices -l
            exit 3
        }
        Write-Host "DEVICE CONNECTED after $elapsed s:" -ForegroundColor Green
        & $ADB devices -l
        exit 0
    }
    Start-Sleep -Seconds $IntervalSec
    $elapsed += $IntervalSec
}
Write-Host "Timed out after $TimeoutSec s — no device. Re-check the glasses ADB setting." -ForegroundColor Red
exit 2
