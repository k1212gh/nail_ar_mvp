# deploy_mirror.ps1 -- one-command auto-deploy for the mirror test app (local CI).
# Encodes the working sequence: [build] -> install -> reverse -> success launch -> push cfg -> monitor.
# ASCII-only on purpose: Windows PowerShell 5.1 mis-parses UTF-8-without-BOM (Korean/special chars).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools\deploy_mirror.ps1            # build+install+run
#   powershell -ExecutionPolicy Bypass -File tools\deploy_mirror.ps1 -NoBuild   # install+run only
#   powershell -ExecutionPolicy Bypass -File tools\deploy_mirror.ps1 -Reboot    # reboot first (HAL wedge)
param(
    [switch]$NoBuild,
    [switch]$Reboot,
    [string]$Unity = "C:\Program Files\Unity\Hub\Editor\2022.3.36f1\Editor\Unity.exe",
    [string]$Pkg   = "com.DefaultCompany.NailMirror",
    [string]$Apk   = "Nail\NailMirror_AUTO.apk"
)
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
function Log($m){ Write-Host "[deploy] $m" -ForegroundColor Cyan }

# 0) edge server up (infer 8443/8444 + monitor 8080). Detect by PORT, not process name --
#    the Store python runs as python3.11.exe, so name-based checks miss it and spawn duplicates.
$listening = Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Log "starting edge server"
    $env:GLOG_minloglevel = "2"
    Start-Process python -ArgumentList "web\edge_serve.py" -WorkingDirectory $repo -WindowStyle Hidden `
        -RedirectStandardOutput "$env:TEMP\edge_out.log" -RedirectStandardError "$env:TEMP\edge_err.log" | Out-Null
    for ($i=0; $i -lt 40; $i++){ if (Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue){ break }; Start-Sleep 1 }
} else { Log "edge server already listening on 8443" }

# 1) build (Unity batch; BuildMirrorDev = Development Build so Debug.Log reaches logcat)
if (-not $NoBuild) {
    $blog = "$env:TEMP\unity_deploy_build.log"
    if (Test-Path $blog) { Remove-Item $blog -Force }
    Log "Unity build (BuildMirrorDev)... ~2-3 min"
    $p = Start-Process $Unity -ArgumentList @("-batchmode","-nographics","-quit","-projectPath","$repo\Nail",
        "-executeMethod","CIBuild.BuildMirrorDev","-buildTarget","Android","-logFile",$blog) -PassThru -WindowStyle Hidden
    $p.WaitForExit()
    if (-not (Select-String -Path $blog -Pattern "result=Succeeded" -Quiet)) {
        Write-Host "[deploy] BUILD FAILED -- see $blog" -ForegroundColor Red; exit 1 }
    Log "build ok"
}
if (-not (Test-Path $Apk)) { Write-Host "[deploy] APK missing: $Apk" -ForegroundColor Red; exit 1 }

# 2) device check (USB or WiFi adb)
if (-not (adb devices | Select-String "device$")) {
    Write-Host "[deploy] NO DEVICE (adb devices empty) -- plug USB or 'adb connect <ip>'" -ForegroundColor Red; exit 1 }
Log "device connected"

if ($Reboot) {
    Log "reboot (reset camera HAL)..."; adb reboot | Out-Null; adb wait-for-device | Out-Null
    for ($i=0; $i -lt 60; $i++){ if ((adb shell getprop sys.boot_completed).Trim() -eq "1"){ break }; Start-Sleep 2 }
    Start-Sleep 6
}

# 3) install (uninstall+reinstall on signature mismatch)
Log "install"
$r = adb install -r $Apk 2>&1 | Out-String
if ($r -match "INSTALL_FAILED_UPDATE_INCOMPATIBLE|signatures do not match") {
    Log "signature mismatch -> uninstall + reinstall"; adb uninstall $Pkg | Out-Null; $r = adb install $Apk 2>&1 | Out-String }
if ($r -notmatch "Success") { Write-Host "[deploy] INSTALL FAILED: $r" -ForegroundColor Red; exit 1 }
Log "install ok"

# 4) reverse (USB path; ignored when using WiFi edgeUrl)
adb reverse tcp:8443 tcp:8443 2>&1 | Out-Null

# 5) success launch sequence: run WITHOUT permission -> grant WHILE running (camera only opens this way)
Log "launch sequence (run then grant)"
adb shell pm revoke $Pkg android.permission.CAMERA 2>&1 | Out-Null
adb shell am force-stop $Pkg 2>&1 | Out-Null
Start-Sleep 3
adb logcat -c 2>&1 | Out-Null
adb shell monkey -p $Pkg -c android.intent.category.LAUNCHER 1 2>&1 | Out-Null
Start-Sleep 6
adb shell pm grant $Pkg android.permission.CAMERA 2>&1 | Out-Null
Start-Sleep 8

# 6) push config (boots straight into MirrorMesh; start with gating/lifesize off)
python web\push_calib.py "pkg=$Pkg" gate=0 lifesize=0 2>&1 | Write-Host

# 7) status
$open = adb logcat -d -s Unity 2>&1 | Select-String "CAMERA OPEN OK|OpenCamera failed" | Select-Object -Last 1
$ip = (python -c "import sys;sys.path.insert(0,'web');import serve;print(serve.lan_ip())").Trim()
Log "camera: $open"
Write-Host ""
Write-Host "  MONITOR (phone/laptop on same WiFi):  http://${ip}:8080/monitor" -ForegroundColor Green
Write-Host "  Keep the glasses ON (locked = app pauses)." -ForegroundColor Yellow
