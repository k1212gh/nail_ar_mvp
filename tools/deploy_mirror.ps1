# deploy_mirror.ps1 — 미러 테스트 앱 원커맨드 자동 배포 (로컬 CI).
# 우리가 수동으로 하던 시퀀스를 한 방에: [빌드] -> 설치 -> reverse -> 성공 실행 시퀀스 -> 설정 푸시 -> 모니터.
#
# 사용:
#   powershell -File tools\deploy_mirror.ps1               # 빌드+설치+실행
#   powershell -File tools\deploy_mirror.ps1 -NoBuild      # 이미 빌드된 APK로 설치+실행만
#   powershell -File tools\deploy_mirror.ps1 -Reboot       # 카메라 HAL wedge 시 재부팅 먼저
#
# 자동 트리거(젠킨스식): git post-merge/post-commit 훅이나 watch_deploy 가 이걸 호출한다.
param(
    [switch]$NoBuild,
    [switch]$Reboot,
    [string]$Unity = "C:\Program Files\Unity\Hub\Editor\2022.3.36f1\Editor\Unity.exe",
    [string]$Pkg   = "com.DefaultCompany.NailMirror",
    [string]$Apk   = "Nail\NailMirror_AUTO.apk"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
function Log($m){ Write-Host "[deploy] $m" -ForegroundColor Cyan }
function Sleep-S($s){ Start-Sleep -Seconds $s }

# --- 0) 에지 서버 살아있게 (추론 8443 + 모니터 8080) ---
$srv = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*edge_serve*" }
if (-not $srv) {
    Log "에지 서버 기동"
    $env:GLOG_minloglevel="2"
    Start-Process python -ArgumentList "web\edge_serve.py" -WorkingDirectory $repo -WindowStyle Hidden `
        -RedirectStandardOutput "$env:TEMP\edge_out.log" -RedirectStandardError "$env:TEMP\edge_err.log" | Out-Null
    Sleep-S 8
} else { Log "에지 서버 이미 실행중 (pid $($srv.ProcessId))" }

# --- 1) 빌드 (Unity batch, BuildMirrorDev = Development Build = logcat 로그 나옴) ---
if (-not $NoBuild) {
    $blog = "$env:TEMP\unity_deploy_build.log"
    if (Test-Path $blog) { Remove-Item $blog -Force }
    Log "Unity 빌드 시작 (BuildMirrorDev)… (~2-3분)"
    $p = Start-Process $Unity -ArgumentList @("-batchmode","-nographics","-quit","-projectPath","$repo\Nail",
        "-executeMethod","CIBuild.BuildMirrorDev","-buildTarget","Android","-logFile",$blog) -PassThru -WindowStyle Hidden
    $p.WaitForExit()
    $ok = Select-String -Path $blog -Pattern "\[CIBuild\] result=Succeeded" -Quiet
    if (-not $ok) { Write-Host "[deploy] 빌드 실패 — $blog 확인" -ForegroundColor Red; exit 1 }
    Log "빌드 성공"
}
if (-not (Test-Path $Apk)) { Write-Host "[deploy] APK 없음: $Apk" -ForegroundColor Red; exit 1 }

# --- 2) 디바이스 확인 (USB 또는 WiFi adb) ---
$dev = (adb devices | Select-String "device$")
if (-not $dev) { Write-Host "[deploy] 안경 미연결 (adb devices 비어있음) — USB 꽂거나 'adb connect <ip>'" -ForegroundColor Red; exit 1 }
Log "디바이스 연결됨"

if ($Reboot) {
    Log "재부팅(카메라 HAL 초기화)…"; adb reboot | Out-Null; adb wait-for-device | Out-Null
    for ($i=0; $i -lt 60; $i++){ if ((adb shell getprop sys.boot_completed).Trim() -eq "1"){ break }; Sleep-S 2 }
    Sleep-S 6
}

# --- 3) 설치 (서명 불일치면 제거 후 재설치) ---
Log "설치…"
$r = adb install -r $Apk 2>&1
if ($r -match "INSTALL_FAILED_UPDATE_INCOMPATIBLE|signatures do not match") {
    Log "서명 불일치 -> 제거 후 재설치"; adb uninstall $Pkg | Out-Null; $r = adb install $Apk 2>&1
}
if ($r -notmatch "Success") { Write-Host "[deploy] 설치 실패: $r" -ForegroundColor Red; exit 1 }
Log "설치 성공"

# --- 4) reverse (USB 경로. WiFi 서버면 edgeUrl 로 대체하므로 실패해도 무시) ---
adb reverse tcp:8443 tcp:8443 2>&1 | Out-Null

# --- 5) 성공 실행 시퀀스: 권한 없이 실행 -> 실행 중 부여 (이 순서라야 카메라가 열림) ---
Log "실행 시퀀스 (권한없이 실행 -> 부여)"
adb shell pm revoke $Pkg android.permission.CAMERA 2>&1 | Out-Null
adb shell am force-stop $Pkg 2>&1 | Out-Null
Sleep-S 3
adb logcat -c 2>&1 | Out-Null
adb shell monkey -p $Pkg -c android.intent.category.LAUNCHER 1 2>&1 | Out-Null
Sleep-S 6
adb shell pm grant $Pkg android.permission.CAMERA 2>&1 | Out-Null
Sleep-S 8

# --- 6) 설정 푸시 (부팅 즉시 MirrorMesh 라 mode 는 불필요, 여기선 게이팅 off 로 시작) ---
python web\push_calib.py "pkg=$Pkg" gate=0 lifesize=0 2>&1 | Write-Host

# --- 7) 상태 요약 ---
$open = adb logcat -d -s Unity 2>&1 | Select-String "CAMERA OPEN OK|OpenCamera failed" | Select-Object -Last 1
$ip = python -c "import sys;sys.path.insert(0,'web');import serve;print(serve.lan_ip())"
Log "카메라: $open"
Write-Host ""
Write-Host "  ★ 무선 모니터: http://${ip}:8080/monitor  (같은 WiFi 브라우저)" -ForegroundColor Green
Write-Host "  안경 착용 상태 유지 필요 (잠금되면 앱 멈춤)." -ForegroundColor Yellow
