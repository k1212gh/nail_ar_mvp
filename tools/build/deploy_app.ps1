<#
  deploy_app.ps1 — install the built APK on the glasses, launch it, and grab a
  screenshot (binary-safe via pull) so we can verify it runs.
#>
param(
  [string]$Apk = 'c:\Users\k1212\Desktop\Toy\nail_ar_mvp\android\app\build\outputs\apk\debug\app-debug.apk',
  [string]$Pkg = 'com.example.nailar',
  [string]$Shot = 'c:\Users\k1212\Desktop\Toy\nail_ar_mvp\samples\app_on_glasses.png'
)
. "c:\Users\k1212\Desktop\Toy\nail_ar_mvp\tools\ar_helper\adb_env.ps1"
if (-not (Test-Path $Apk)) { Write-Host "APK not found: $Apk (build first)" -ForegroundColor Red; exit 1 }

# ensure device
$dev = (& $ADB devices) | Select-Object -Skip 1 | Where-Object { $_ -match '\tdevice' }
if (-not $dev) { & $ADB kill-server 2>$null|Out-Null; & $ADB start-server 2>$null|Out-Null; Start-Sleep 2 }

Write-Host "=== install $([math]::Round((Get-Item $Apk).Length/1MB,1))MB ===" -ForegroundColor Cyan
& $ADB install -r -t "$Apk" 2>&1 | Select-Object -Last 2

Write-Host "=== grant camera permission (avoid prompt) ===" -ForegroundColor Cyan
& $ADB shell pm grant $Pkg android.permission.CAMERA 2>&1 | Out-Null

Write-Host "=== launch ===" -ForegroundColor Cyan
& $ADB shell monkey -p $Pkg -c android.intent.category.LAUNCHER 1 2>&1 | Select-Object -Last 1
Start-Sleep -Seconds 4

Write-Host "=== foreground activity ===" -ForegroundColor Cyan
(& $ADB shell dumpsys activity activities 2>&1) | Select-String 'topResumedActivity' | Select-Object -First 1

Write-Host "=== screenshot -> $Shot ===" -ForegroundColor Cyan
& $ADB shell screencap -p /sdcard/_appshot.png 2>$null
& $ADB pull /sdcard/_appshot.png "$Shot" 2>&1 | Select-String 'pulled' | Out-Null
& $ADB shell rm /sdcard/_appshot.png 2>$null
if (Test-Path $Shot) { "screenshot saved: $((Get-Item $Shot).Length) bytes" } else { "screenshot failed" }
