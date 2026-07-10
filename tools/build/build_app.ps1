<#
  build_app.ps1 — build android/ into a debug APK using the portable buildkit.
  Prereq: setup_buildkit.ps1 finished (writes C:\Users\k1212\android-buildkit\env.json).
  Uses the portable Gradle + JDK17 + SDK (no admin, no wrapper).
#>
param([string]$Task = 'assembleDebug')
$KIT = 'C:\Users\k1212\android-buildkit'
$env:JAVA_HOME    = (Get-ChildItem "$KIT\jdk" -Directory | Where-Object Name -like 'jdk*' | Select-Object -First 1).FullName
$env:ANDROID_HOME = "$KIT\android-sdk"
$env:ANDROID_SDK_ROOT = "$KIT\android-sdk"
$GRADLE = "$KIT\gradle\gradle-8.9\bin\gradle.bat"
$proj = 'c:\Users\k1212\Desktop\Toy\nail_ar_mvp\android'

Write-Host "JAVA_HOME = $env:JAVA_HOME"
Write-Host "ANDROID   = $env:ANDROID_HOME"
if (-not (Test-Path "$env:JAVA_HOME\bin\java.exe")) { Write-Host "JDK missing - run setup_buildkit.ps1" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $GRADLE)) { Write-Host "Gradle missing - run setup_buildkit.ps1" -ForegroundColor Red; exit 1 }

# local.properties -> sdk.dir (AGP reads this)
$sdkEsc = ($env:ANDROID_HOME -replace '\\','\\')
Set-Content -Path "$proj\local.properties" -Value "sdk.dir=$sdkEsc" -Encoding ascii
Write-Host "wrote local.properties"

Write-Host "=== gradle $Task ===" -ForegroundColor Cyan
& $GRADLE -p $proj $Task --no-daemon --stacktrace
$code = $LASTEXITCODE
$apk = "$proj\app\build\outputs\apk\debug\app-debug.apk"
if ((Test-Path $apk)) {
  Write-Host "`nBUILD OK -> $apk  ($([math]::Round((Get-Item $apk).Length/1MB,1)) MB)" -ForegroundColor Green
} else {
  Write-Host "`nBUILD FAILED (exit $code) - no APK." -ForegroundColor Red
}
exit $code
