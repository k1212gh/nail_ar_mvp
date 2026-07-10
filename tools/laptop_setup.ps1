<#
  laptop_setup.ps1 — 노트북 데모 준비 자동 점검/설치.
  사용:  powershell -ExecutionPolicy Bypass -File tools\laptop_setup.ps1
  하는 일: 파이썬 확인 → 의존성 설치 → import 검증 → adb/안경 연결 확인 → 준비상태 요약.
  (관리자 불필요. 드라이버 문제 시에만 Fix-ADB-Driver-ADMIN.cmd 안내.)
#>
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "== 네일 AR 데모 노트북 점검 ==" -ForegroundColor Cyan
Write-Host "repo: $root`n"

function Ok($m){ Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn($m){ Write-Host "  [!!] $m" -ForegroundColor Yellow }

# 1) 파이썬
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { Warn "python 없음 →  winget install Python.Python.3.11  후 새 창에서 재실행"; return }
Ok ("python " + (python -c "import sys;print(sys.version.split()[0])"))

# 2) 의존성 설치
Write-Host "`n[의존성 설치] pip install -r requirements.txt (torch 포함, 수분 걸릴 수 있음)..." -ForegroundColor Cyan
python -m pip install --disable-pip-version-check -q -r requirements.txt
if ($?) { Ok "pip install 완료" } else { Warn "pip install 실패 — 인터넷/파이썬 확인" }

# 3) import 검증 (에지 서버가 실제로 켜질 수 있는지)
Write-Host "`n[import 검증]" -ForegroundColor Cyan
$chk = python -c "import cv2,numpy,mediapipe,cryptography,ultralytics;print('IMPORTS_OK')" 2>&1
if ($chk -match 'IMPORTS_OK') { Ok "cv2/numpy/mediapipe/cryptography/ultralytics 모두 OK (에지 서버 실행 가능)" }
else { Warn ("import 실패: " + $chk); Warn "pip install -r requirements.txt 다시 실행" }

# 4) adb + 안경 연결
Write-Host "`n[adb / 안경 연결]" -ForegroundColor Cyan
$adb = (Get-Command adb -ErrorAction SilentlyContinue)
if (-not $adb) {
  $cand = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter adb.exe -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($cand) { $adb = $cand.FullName }
}
if (-not $adb) { Warn "adb 없음 →  winget install Genymobile.scrcpy  (adb 포함)"; }
else {
  $adbExe = if ($adb.Source) { $adb.Source } else { $adb }
  $devs = (& $adbExe devices) 2>&1 | Select-String "device$"
  if ($devs) { Ok ("안경 연결됨: " + ($devs -join ', ').Trim()) }
  else { Warn "안경이 'device'로 안 뜸 → USB 재연결 + '디버깅 허용'. 그래도 안 되면 관리자로 tools\ar_helper\Fix-ADB-Driver-ADMIN.cmd" }
}

Write-Host "`n== 요약 ==" -ForegroundColor Cyan
Write-Host "위가 모두 [OK]면 준비 완료. 데모 실행은 docs\DEMO_RUNBOOK.md 의 B 단계:"
Write-Host "  터미널1:  python web\edge_serve.py"
Write-Host "  터미널2:  adb reverse tcp:8443 tcp:8443 ;  앱 실행(monkey ... NailMesh)"
