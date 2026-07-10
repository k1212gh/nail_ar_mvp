# fix_adb_driver.ps1 — MUST RUN ELEVATED (admin).
# Fixes the Windows composite-device issue where adb can't open the RayNeo ADB
# interface. Registers the standard ADB WinUSB interface GUID on the device so
# adb's legacy (AdbWinApi) backend can find it, then restarts the interface.
# No downloads. Writes a result log the non-elevated caller can read.
$ErrorActionPreference = 'Stop'
$result = "$env:TEMP\fix_adb_result.txt"
$ADB_GUID = '{F72FE0D4-CBCB-407D-8814-9ED673D0DD6B}'  # Android ADB device interface GUID
function Log($m){ Add-Content -Path $result -Value $m; Write-Host $m }
Set-Content -Path $result -Value "fix_adb_driver started"

try {
    $dev = Get-PnpDevice -PresentOnly -ErrorAction Stop |
        Where-Object { $_.InstanceId -like 'USB\VID_18D1&PID_4EE2&MI_01\*' } | Select-Object -First 1
    if (-not $dev) {
        # fallback: any ADB-class interface (SubClass 42)
        $dev = Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -match 'ADB Interface' } | Select-Object -First 1
    }
    if (-not $dev) { Log "ERROR: ADB interface device not found. Re-plug glasses."; exit 10 }
    Log "Device: $($dev.InstanceId)"

    $key = "HKLM:\SYSTEM\CurrentControlSet\Enum\$($dev.InstanceId)\Device Parameters"
    if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
    New-ItemProperty -Path $key -Name 'DeviceInterfaceGUIDs' -Value @($ADB_GUID) -PropertyType MultiString -Force | Out-Null
    Log "Registered DeviceInterfaceGUIDs = $ADB_GUID"

    Log "Restarting interface..."
    Disable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Enable-PnpDevice  -InstanceId $dev.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Log "DONE. Interface restarted."
    exit 0
} catch {
    Log "EXCEPTION: $($_.Exception.Message)"
    exit 11
}
