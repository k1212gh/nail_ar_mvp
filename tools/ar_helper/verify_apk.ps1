<#
  verify_apk.ps1 — verify an APK's integrity BEFORE sideloading (security step).
  Since sideloaded APKs (Moonlight, ScreenStream, your build) run with real
  permissions, confirm the file is exactly what you expect before installing.

  Usage:
    verify_apk.ps1 app.apk                       # print SHA-256 + size
    verify_apk.ps1 app.apk -Expected <sha256>    # compare to a known-good hash
#>
param(
    [Parameter(Mandatory)][string]$Path,
    [string]$Expected
)
if (-not (Test-Path $Path)) { Write-Host "Not found: $Path" -ForegroundColor Red; exit 1 }
$item = Get-Item $Path
$sha = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLower()
Write-Host "file  : $($item.Name)"
Write-Host ("size  : {0:N0} bytes ({1:N2} MB)" -f $item.Length, ($item.Length/1MB))
Write-Host "sha256: $sha"

if ($Expected) {
    $exp = $Expected.Trim().ToLower()
    if ($sha -eq $exp) {
        Write-Host "MATCH  [OK]  integrity verified - safe to install." -ForegroundColor Green
        exit 0
    } else {
        Write-Host "MISMATCH [X]  expected $exp" -ForegroundColor Red
        Write-Host "DO NOT INSTALL - the file differs from the known-good hash." -ForegroundColor Red
        exit 2
    }
} else {
    Write-Host "`nNo -Expected hash given. Compare this SHA-256 with the value published" -ForegroundColor Yellow
    Write-Host "on the official release page (e.g. GitHub releases) before installing." -ForegroundColor Yellow
}
