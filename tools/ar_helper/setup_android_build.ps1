<#
  setup_android_build.ps1 — get the android/ test app buildable, then build the APK.
  Two paths (all winget IDs verified 2026-07-01):
    (default) Android Studio  — most reliable; bundles SDK + gradle + wrapper.
    -Cli                      — headless toolchain (JDK17 + Google.AndroidCLI + platform-tools).

  NOTE: winget installs need admin -> this SELF-ELEVATES (approve UAC). Large
  downloads. UNTESTED in the autonomous session (no SDK/device there) — best-effort.
#>
param([switch]$Cli)

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator)
}
if (-not (Test-Admin)) {
    Write-Host "Elevating (approve UAC)..." -ForegroundColor Yellow
    $a = @('-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$PSCommandPath`"")
    if ($Cli) { $a += '-Cli' }
    Start-Process powershell -Verb RunAs -ArgumentList $a
    return
}

$proj = Resolve-Path (Join-Path $PSScriptRoot '..\..\android')

if (-not $Cli) {
    Write-Host "=== Installing Android Studio (bundles SDK + gradle) ===" -ForegroundColor Cyan
    winget install --id Google.AndroidStudio -e --accept-source-agreements --accept-package-agreements
    Write-Host "`nNEXT: open Android Studio -> Open -> '$proj' -> let it sync -> Run/Build APK." -ForegroundColor Green
    Write-Host "APK: android\app\build\outputs\apk\debug\app-debug.apk -> AR-Helper.cmd install <apk>"
    return
}

Write-Host "=== CLI toolchain ===" -ForegroundColor Cyan
winget install --id EclipseAdoptium.Temurin.17.JDK -e --accept-source-agreements --accept-package-agreements
winget install --id Google.AndroidCLI              -e --accept-source-agreements --accept-package-agreements
winget install --id Google.PlatformTools           -e --accept-source-agreements --accept-package-agreements

$sdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
[Environment]::SetEnvironmentVariable('ANDROID_HOME', $sdk, 'User')
$sdkmgr = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter sdkmanager.bat -ErrorAction SilentlyContinue | Select-Object -First 1
if ($sdkmgr) {
    Write-Host "Accepting licenses + installing SDK packages..." -ForegroundColor Cyan
    & $sdkmgr.FullName "--sdk_root=$sdk" "platform-tools" "platforms;android-34" "build-tools;34.0.0"
    'y' * 20 -split '' | & $sdkmgr.FullName "--sdk_root=$sdk" --licenses
} else {
    Write-Host "sdkmanager not found after install — check Google.AndroidCLI." -ForegroundColor Yellow
}
Write-Host "`nGradle wrapper: no winget gradle. Easiest = install Android Studio once to generate it," -ForegroundColor Yellow
Write-Host "or download gradle from gradle.org, then in '$proj' run: gradle wrapper; .\gradlew assembleDebug" -ForegroundColor Yellow
