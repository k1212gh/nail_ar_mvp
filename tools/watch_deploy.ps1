# watch_deploy.ps1 -- Jenkins-lite: auto build+install+run when a new commit/push is detected.
# Run this once on the PC; it deploys on every new commit (local or pulled from remote).
# ASCII-only (PowerShell 5.1 mis-parses UTF-8-without-BOM).
#
# Usage:  powershell -ExecutionPolicy Bypass -File tools\watch_deploy.ps1
#         powershell -ExecutionPolicy Bypass -File tools\watch_deploy.ps1 -Interval 15
#
# Loop: every N sec -> git fetch -> if remote ahead, ff-only pull -> if HEAD changed, run deploy_mirror.ps1.
# Build runner = this PC (Unity+ARDK live here; cannot move to cloud).
param([int]$Interval = 30)
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$deploy = Join-Path $PSScriptRoot "deploy_mirror.ps1"
$last = (git rev-parse HEAD).Trim()
Write-Host "[watch] watching @ $last (interval ${Interval}s). Ctrl+C to stop." -ForegroundColor Cyan

while ($true) {
    try {
        git fetch -q 2>$null
        $up = (git rev-parse --abbrev-ref '@{u}' 2>$null)
        if ($up) {
            $behind = (git rev-list "HEAD..@{u}" --count 2>$null)
            if ($behind -and [int]$behind -gt 0) {
                Write-Host "[watch] remote ahead by $behind -> pull" -ForegroundColor Yellow
                git pull -q --ff-only 2>$null
            }
        }
        $head = (git rev-parse HEAD).Trim()
        if ($head -ne $last) {
            Write-Host "[watch] new commit $head -> deploy" -ForegroundColor Green
            & powershell -ExecutionPolicy Bypass -File $deploy
            $last = $head
        }
    } catch { Write-Host "[watch] $_" -ForegroundColor Red }
    Start-Sleep -Seconds $Interval
}
