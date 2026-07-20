# watch_deploy.ps1 — 젠킨스-라이트: git 커밋/푸시를 감지하면 자동으로 빌드+설치+실행.
# PC에서 이걸 한 번 켜두면, 이 PC에서 커밋하거나 다른 데서 push 한 걸 pull 해서 자동 배포한다.
#
# 사용:  powershell -File tools\watch_deploy.ps1                 # 30초 간격 감시
#        powershell -File tools\watch_deploy.ps1 -Interval 15
#
# 동작: N초마다 git fetch -> 원격이 앞서면 pull(ff-only) -> HEAD 가 바뀌었으면 deploy_mirror.ps1 실행.
# (빌드 러너 = 이 PC. Unity+ARDK 가 여기 있으므로 클라우드로 못 옮김.)
param([int]$Interval = 30)
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$deploy = Join-Path $PSScriptRoot "deploy_mirror.ps1"
$last = (git rev-parse HEAD).Trim()
Write-Host "[watch] 감시 시작 @ $last (interval ${Interval}s). Ctrl+C 종료." -ForegroundColor Cyan

while ($true) {
    try {
        git fetch -q 2>$null
        # 원격 업스트림이 있으면, 앞선 만큼 ff-only pull
        $up = (git rev-parse --abbrev-ref '@{u}' 2>$null)
        if ($up) {
            $behind = (git rev-list "HEAD..@{u}" --count 2>$null)
            if ($behind -and [int]$behind -gt 0) {
                Write-Host "[watch] 원격 $behind 커밋 앞섬 -> pull" -ForegroundColor Yellow
                git pull -q --ff-only 2>$null
            }
        }
        $head = (git rev-parse HEAD).Trim()
        if ($head -ne $last) {
            Write-Host "[watch] 새 커밋 감지 $head -> 자동 배포" -ForegroundColor Green
            & powershell -ExecutionPolicy Bypass -File $deploy
            $last = $head
        }
    } catch { Write-Host "[watch] $_" -ForegroundColor Red }
    Start-Sleep -Seconds $Interval
}
