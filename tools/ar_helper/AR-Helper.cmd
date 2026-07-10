@echo off
REM Double-click launcher for the secure AR Helper (scrcpy/adb wrapper).
REM 100%% local + open-source. No cloud, no bundled APKs.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ar_helper.ps1" %*
endlocal
