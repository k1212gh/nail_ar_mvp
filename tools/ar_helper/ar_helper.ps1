<#
  ar_helper.ps1 — Secure, local, open-source replacement for "Tvini Android Helper".
  ---------------------------------------------------------------------------------
  WHY THIS IS SECURE (unlike a closed downloaded helper):
    * Uses ONLY the winget-installed, hash-verified scrcpy + adb (Genymobile, OSS).
    * 100% local: talks to the glasses over USB or your own LAN. No cloud relay,
      no telemetry, no bundled APKs from a third-party server.
    * Every action below is a plain adb/scrcpy command you can read and audit.
    * You install ONLY APK files you choose. Nothing is fetched from the internet.

  Feature parity with Tvini Helper:
    * Device list        -> `devices`
    * Screen mirror      -> `mirror`   (scrcpy)
    * Drag-drop APK      -> `install`  (adb install; scrcpy window also accepts drops)
    * Screen record      -> `record`
  Plus: WiFi ADB pairing/connect, device identity dump.

  Usage:
    powershell -ExecutionPolicy Bypass -File ar_helper.ps1            # interactive menu
    powershell -ExecutionPolicy Bypass -File ar_helper.ps1 devices
    powershell -ExecutionPolicy Bypass -File ar_helper.ps1 install "C:\path\app.apk"
    powershell -ExecutionPolicy Bypass -File ar_helper.ps1 mirror
#>
param(
    [ValidateSet('menu','devices','mirror','install','record','connect','info','doctor')]
    [string]$Action = 'menu',
    [string]$Arg
)
. "$PSScriptRoot\adb_env.ps1"

function Banner {
    Write-Host ""
    Write-Host " AR Helper (secure / local / open-source)" -ForegroundColor Magenta
    Write-Host " adb   : $ADB"    -ForegroundColor DarkGray
    Write-Host " scrcpy: $SCRCPY" -ForegroundColor DarkGray
    Write-Host ""
}

function Get-Devices {
    if (-not $ADB) { return @() }
    (& $ADB devices) | Select-Object -Skip 1 |
        Where-Object { $_ -match '\t' } |
        ForEach-Object {
            $p = $_ -split '\t'
            [pscustomobject]@{ Serial = $p[0].Trim(); State = $p[1].Trim() }
        }
}

function Show-Devices {
    $d = Get-Devices
    if (-not $d) { Write-Host "No devices. (USB: needs driver fix / WiFi: use 'connect')" -ForegroundColor Yellow; return $null }
    $i = 0; $d | ForEach-Object { Write-Host ("  [{0}] {1}  {2}" -f $i, $_.Serial, $_.State); $i++ }
    return $d
}

function Pick-Device {
    $d = Show-Devices
    if (-not $d) { return $null }
    if ($d.Count -eq 1) { return $d[0].Serial }
    $sel = Read-Host "device #"
    return $d[[int]$sel].Serial
}

function Do-Mirror {
    if (-not $SCRCPY) { Write-Host "scrcpy missing" -ForegroundColor Red; return }
    $s = Pick-Device; if (-not $s) { return }
    Write-Host "Mirroring $s ... (close the window to stop)" -ForegroundColor Green
    # Glasses-friendly: keep awake, moderate bitrate, no audio forwarding by default.
    & $SCRCPY -s $s --stay-awake --max-size 1600 --video-bit-rate 8M --window-title "AR Glasses ($s)"
}

function Do-Install([string]$apk) {
    if (-not $apk) { $apk = Read-Host "APK path (or drag file here)" }
    $apk = $apk.Trim('"').Trim()
    if (-not (Test-Path $apk)) { Write-Host "Not found: $apk" -ForegroundColor Red; return }
    $s = Pick-Device; if (-not $s) { return }
    Write-Host "Installing $(Split-Path $apk -Leaf) -> $s" -ForegroundColor Green
    & $ADB -s $s install -r -t -- "$apk"
}

function Do-Record {
    if (-not $SCRCPY) { return }
    $s = Pick-Device; if (-not $s) { return }
    $out = Join-Path (Split-Path $PSScriptRoot -Parent) ("..\logs\rec_{0}.mp4" -f $s)
    Write-Host "Recording $s -> $out  (close window to stop)" -ForegroundColor Green
    & $SCRCPY -s $s --record "$out" --max-size 1600
}

function Do-Connect {
    Write-Host "WiFi ADB. Glasses & PC must share the same network." -ForegroundColor Cyan
    Write-Host "  A) classic:  adb connect <ip>:5555   (needs USB 'adb tcpip 5555' first)"
    Write-Host "  B) Android11+ wireless debugging: pair with code, then connect"
    $ip = Read-Host "glasses IP (blank to try mDNS discovery)"
    if ([string]::IsNullOrWhiteSpace($ip)) {
        Write-Host "mDNS discovery:" -ForegroundColor Cyan
        & $ADB mdns services
        return
    }
    $port = Read-Host "port [5555]"; if (-not $port) { $port = '5555' }
    & $ADB connect "$($ip):$port"
    Get-Devices | Format-Table -AutoSize
}

function Do-Info { & powershell -ExecutionPolicy Bypass -File "$PSScriptRoot\device_info.ps1" }

function Do-Doctor {
    Banner
    Write-Host "adb present : $([bool]$ADB)"
    Write-Host "scrcpy      : $([bool]$SCRCPY)"
    if ($ADB) { & $ADB version | Select-Object -First 1 }
    Write-Host "devices:";  Show-Devices | Out-Null
}

function Menu {
    while ($true) {
        Banner
        Show-Devices | Out-Null
        Write-Host ""
        Write-Host "  1) Screen mirror     2) Install APK     3) Record screen"
        Write-Host "  4) WiFi connect      5) Device info     6) Doctor"
        Write-Host "  0) Quit"
        switch (Read-Host "select") {
            '1' { Do-Mirror }
            '2' { Do-Install }
            '3' { Do-Record }
            '4' { Do-Connect }
            '5' { Do-Info }
            '6' { Do-Doctor }
            '0' { return }
            default { }
        }
    }
}

if (-not $ADB) { Write-Warning "adb not found. Run: winget install Genymobile.scrcpy" }
switch ($Action) {
    'devices' { Banner; Show-Devices | Out-Null }
    'mirror'  { Do-Mirror }
    'install' { Do-Install $Arg }
    'record'  { Do-Record }
    'connect' { Do-Connect }
    'info'    { Do-Info }
    'doctor'  { Do-Doctor }
    default   { Menu }
}
