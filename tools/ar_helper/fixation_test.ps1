<#
  fixation_test.ps1 — Risk (b): does a virtual overlay stay glued to the nail?
  Run AFTER the AR app is on the glasses and rendering an overlay.
  This records a scrcpy capture of the glasses display while you run the motion
  protocol below, so the clip can be reviewed / frame-analyzed afterwards.

  Motion protocol (do each ~5 s while an overlay sits on a nail):
    1) HOLD still            -> baseline jitter
    2) TRANSLATE hand L/R/up/down slowly
    3) ROTATE the finger     -> overlay must follow orientation
    4) MOVE HEAD (look around)-> 3DoF: does the overlay swim off the nail?
  Pass = overlay stays on the nail through 1-3; head-move drift reveals 3DoF-only limits.
#>
param([int]$Seconds = 30)
. "$PSScriptRoot\adb_env.ps1"
if (-not $SCRCPY) { Write-Host "scrcpy missing"; exit 1 }
$dev = (& $ADB devices) | Select-Object -Skip 1 | Where-Object { $_ -match '\tdevice' }
if (-not $dev) { Write-Host "No authorized device. Connect first." -ForegroundColor Yellow; exit 2 }

$outDir = Join-Path (Split-Path $PSScriptRoot -Parent) '..\samples\fixation_test'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$out = Join-Path $outDir 'fixation_capture.mp4'

Write-Host "Recording glasses display for $Seconds s. Run the motion protocol now:" -ForegroundColor Green
Write-Host "  1) hold still  2) translate  3) rotate finger  4) move head" -ForegroundColor Green
& $SCRCPY --record "$out" --time-limit $Seconds --max-size 1600 --no-playback 2>$null
Write-Host "`nSaved: $out  — review for overlay drift (esp. during head motion)." -ForegroundColor Cyan
