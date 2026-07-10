<#
  capture_focus_test.ps1 — Risk (a): near-focus check for the glasses camera.
  Uses scrcpy's CAMERA source (scrcpy 4.0) to mirror/record the glasses camera
  directly — no camera app or DCIM pull needed. Run AFTER the glasses appear in
  `adb devices`.

  Flow:
    1) Lists the glasses cameras.
    2) Records the back camera for N seconds while you slowly move a fingernail
       (or printed text) through ~20 -> 30 -> 40 cm.  (--torch adds light.)
    3) focus_analyze.py --video grades every frame and reports the sharpest one.
  Decides: is 20-40 cm sharp enough for nail detection, or use the phone-camera
  fallback (IMPLEMENTATION_PLAN Phase 2 branch).
#>
param([int]$Seconds = 15, [switch]$Torch, [switch]$LiveOnly)
. "$PSScriptRoot\adb_env.ps1"
if (-not $SCRCPY) { Write-Host "scrcpy missing"; exit 1 }
$dev = (& $ADB devices) | Select-Object -Skip 1 | Where-Object { $_ -match '\tdevice' }
if (-not $dev) { Write-Host "No authorized device. Fix USB (Fix-ADB-Driver-ADMIN.cmd) or WiFi-connect first." -ForegroundColor Yellow; exit 2 }

Write-Host "=== glasses cameras ===" -ForegroundColor Cyan
& $SCRCPY --list-cameras 2>&1 | Where-Object { $_ -match 'camera|--' }

$camArgs = @('--video-source=camera','--camera-facing=back','--no-audio')
if ($Torch) { $camArgs += '--camera-torch' }

if ($LiveOnly) {
    Write-Host "`nLive back-camera view. Hold the nail at 20-40cm and judge sharpness by eye. Close window to stop." -ForegroundColor Green
    & $SCRCPY @camArgs --window-title "Glasses camera (focus check)"
    exit 0
}

$outDir = Join-Path $PSScriptRoot '..\..\samples\focus_test'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$rec = Join-Path $outDir 'focus_camera.mp4'

Write-Host "`nRecording back camera for $Seconds s. Slowly sweep the nail 20 -> 30 -> 40 cm now..." -ForegroundColor Green
& $SCRCPY @camArgs --record "$rec" --time-limit $Seconds --no-playback 2>$null

if (-not (Test-Path $rec)) { Write-Host "Recording failed. Try: AR-Helper.cmd mirror to check the camera." -ForegroundColor Yellow; exit 3 }
Write-Host "`n=== Sharpness analysis ===" -ForegroundColor Cyan
python "$PSScriptRoot\focus_analyze.py" --video "$rec" --every 5
Write-Host "`nBest frame SHARP -> glasses camera capture OK. All BLURRY -> use phone-camera fallback." -ForegroundColor Green
Write-Host "Saved recording: $rec" -ForegroundColor DarkGray
