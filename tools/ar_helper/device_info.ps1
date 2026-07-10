# device_info.ps1 — identify the connected AR glasses and dump the facts that
# decide the project architecture (model, chipset, RAM, Android, cameras).
# Usage:  powershell -ExecutionPolicy Bypass -File tools\ar_helper\device_info.ps1
. "$PSScriptRoot\adb_env.ps1"
if (-not $ADB) { exit 1 }

$devs = (& $ADB devices) | Select-Object -Skip 1 | Where-Object { $_ -match '\S' }
if (-not $devs) {
    Write-Host "No device in `adb devices`." -ForegroundColor Yellow
    Write-Host "On RayNeo X3: Settings > General > About Device (highlight) > swipe LEFT 10x until 'adb' appears at top."
    Write-Host "Then re-run this script."
    exit 2
}
Write-Host "=== adb devices ===" -ForegroundColor Cyan
& $ADB devices -l

function P($k) { (& $ADB shell getprop $k).Trim() }

Write-Host "`n=== Identity ===" -ForegroundColor Cyan
[pscustomobject]@{
    Brand        = P 'ro.product.brand'
    Model        = P 'ro.product.model'
    Device       = P 'ro.product.device'
    Name         = P 'ro.product.name'
    Android      = P 'ro.build.version.release'
    SDK          = P 'ro.build.version.sdk'
    Chipset_HW   = P 'ro.hardware'
    Chipset_SoC  = P 'ro.board.platform'
    ABI          = P 'ro.product.cpu.abi'
} | Format-List

Write-Host "=== RAM / resolution ===" -ForegroundColor Cyan
(& $ADB shell cat /proc/meminfo) | Select-String 'MemTotal'
(& $ADB shell wm size)
(& $ADB shell wm density)

Write-Host "`n=== Cameras (camera2 ids) ===" -ForegroundColor Cyan
(& $ADB shell cmd media.camera get-camera-info 2>$null) | Select-Object -First 40
Write-Host "(if empty above, camera enumeration needs an app; will probe in the focus test)"

Write-Host "`n=== Sideload allowed? ===" -ForegroundColor Cyan
"mercury_install_allowed = " + (P 'persist.sys.mercury_install_allowed')
