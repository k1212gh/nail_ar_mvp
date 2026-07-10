@echo off
REM ============================================================================
REM  Fix-ADB-Driver-ADMIN.cmd  —  DOUBLE-CLICK THIS, then approve the UAC prompt.
REM  Fixes the Windows composite-USB issue so `adb` can see the RayNeo glasses.
REM  Registers the standard ADB WinUSB interface GUID (no downloads), restarts
REM  the interface, then verifies with the legacy adb backend.
REM ============================================================================
setlocal
REM --- self-elevate ---
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo Requesting administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo === Running driver fix (elevated) ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_adb_driver.ps1"

echo.
echo === Verifying adb detection (legacy backend) ===
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0adb_env.ps1'; $env:ADB_LIBUSB='0'; & $ADB kill-server; Start-Sleep 1; & $ADB start-server; Start-Sleep 2; & $ADB devices -l"

echo.
echo If a device with state 'device' or 'unauthorized' appears above, the fix worked.
echo (unauthorized -> accept the 'Allow USB debugging' prompt in the glasses)
echo If still empty, try ADB_LIBUSB=1 or use WiFi ADB (see docs/AR_SETUP.md).
echo.
pause
endlocal
