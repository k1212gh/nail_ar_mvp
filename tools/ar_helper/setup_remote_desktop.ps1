<#
  setup_remote_desktop.ps1 — secure OSS replacement for Tvini "AR Remote Desktop".
  ----------------------------------------------------------------------------------
  Streams THIS PC's desktop to the RayNeo glasses over your OWN LAN, encrypted,
  with NO third-party cloud relay.

  Stack (all open-source, self-hosted):
    * HOST  (this PC)   : Sunshine  (LizardByte.Sunshine)  -> serves an encrypted
                          stream on your LAN only. You hold the keys; nothing leaves
                          your network.
    * CLIENT (glasses)  : Moonlight (moonlight-android)    -> sideload the APK with
                          the AR Helper. Pairs to Sunshine with a 4-digit PIN.

  Security vs Tvini remote desktop:
    - Source-auditable on both ends; pairing is PIN + per-device cert, AES stream.
    - LAN-only by default (no relay server sees your screen).
    - You choose exactly what is shared and when.

  NOTE: Installing Sunshine needs admin (it registers a service + virtual-display
  driver). This script SELF-ELEVATES; approve the UAC prompt.
#>
param([switch]$SkipInstall)

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "Elevating (approve UAC)..." -ForegroundColor Yellow
    Start-Process -FilePath 'powershell' -Verb RunAs -ArgumentList @(
        '-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$PSCommandPath`"")
    return
}

Write-Host "=== Installing Sunshine (LizardByte.Sunshine) ===" -ForegroundColor Cyan
if (-not $SkipInstall) {
    winget install --id LizardByte.Sunshine -e --accept-source-agreements --accept-package-agreements
}

Write-Host "`n=== Firewall: allow Sunshine on the LOCAL network only ===" -ForegroundColor Cyan
# Sunshine uses 47984-48010 (tcp/udp) + 47989/48010. Restrict to private profile.
$ports = @(47984,47989,47990,48010)
foreach ($p in $ports) {
    New-NetFirewallRule -DisplayName "Sunshine TCP $p (LAN)" -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $p -Profile Private -ErrorAction SilentlyContinue | Out-Null
}
New-NetFirewallRule -DisplayName "Sunshine UDP 47998-48010 (LAN)" -Direction Inbound -Action Allow `
    -Protocol UDP -LocalPort 47998-48010 -Profile Private -ErrorAction SilentlyContinue | Out-Null
Write-Host "Firewall rules added (Private profile only)."

Write-Host "`n=== NEXT STEPS ===" -ForegroundColor Green
Write-Host @"
1) Open Sunshine WebUI:  https://localhost:47990  (set username/password on first run)
2) On the GLASSES, sideload Moonlight:
     - Download moonlight-<ver>.apk from  https://github.com/moonlight-stream/moonlight-android/releases
     - Verify checksum, then:  tools\ar_helper\AR-Helper.cmd install <path-to-moonlight.apk>
3) In Moonlight on the glasses, add this PC by LAN IP, enter the PIN Sunshine shows.
4) Stream. Everything stays on your LAN.
See docs/AR_SETUP.md for the full walkthrough + troubleshooting.
"@
