<#
  run_glasses_demo.ps1 — one command to show the nail-AR app on the glasses.
  Modes:
    -Mode image    (default) static hand image -> detect -> curved design overlay
    -Mode network  PC frame_server + adb reverse -> glasses fetch/detect/render (product path)
    -Mode camera   local camera (works on a PHONE, not the glasses)
  Options: -Image <hand.jpg>  -Webcam <id>  -Guide
  Prereq: app installed (build_app.ps1 + deploy_app.ps1) and device connected.
#>
param(
  [ValidateSet('image','network','camera')][string]$Mode = 'image',
  [string]$Image = 'c:\Users\k1212\Desktop\Toy\nail_ar_mvp\samples\focus_test\hand_small.jpg',
  [int]$Webcam = -1,
  [switch]$Guide
)
. "c:\Users\k1212\Desktop\Toy\nail_ar_mvp\tools\ar_helper\adb_env.ps1"
$pkg='com.example.nailar'; $filesDir="/sdcard/Android/data/$pkg/files"
$guideJson = if ($Guide) { 'true' } else { 'false' }

# keep glasses display awake (else app renders 0-size)
& $ADB shell input keyevent KEYCODE_WAKEUP 2>$null
& $ADB shell svc power stayon true 2>$null | Out-Null
& $ADB shell mkdir -p $filesDir 2>$null

switch ($Mode) {
  'image' {
    & $ADB push "$Image" "$filesDir/nail_input.jpg" 2>&1 | Select-String 'pushed'
    "{`"showGuide`":$guideJson,`"designScale`":1.7}" | Set-Content -Encoding ascii "$env:TEMP\cfg.json"
    & $ADB push "$env:TEMP\cfg.json" "$filesDir/nailar_config.json" 2>&1 | Out-Null
  }
  'network' {
    Write-Host "Start the PC frame server in another terminal, e.g.:" -ForegroundColor Yellow
    if ($Webcam -ge 0) { Write-Host "  python tools\build\frame_server.py --webcam $Webcam" }
    else { Write-Host "  python tools\build\frame_server.py --image `"$Image`"" }
    & $ADB reverse tcp:8080 tcp:8080 2>&1 | Out-Null
    "{`"frameUrl`":`"http://127.0.0.1:8080/frame.jpg`",`"showGuide`":$guideJson,`"designScale`":1.7}" |
      Set-Content -Encoding ascii "$env:TEMP\cfg.json"
    & $ADB push "$env:TEMP\cfg.json" "$filesDir/nailar_config.json" 2>&1 | Out-Null
  }
  'camera' {
    # no config / no nail_input -> app uses local camera (phone only; glasses block camera)
    "{`"showGuide`":$guideJson}" | Set-Content -Encoding ascii "$env:TEMP\cfg.json"
    & $ADB push "$env:TEMP\cfg.json" "$filesDir/nailar_config.json" 2>&1 | Out-Null
  }
}

& $ADB shell am force-stop $pkg 2>$null
& $ADB shell am start -n "$pkg/.MainActivity" 2>&1 | Select-Object -First 1
Write-Host "launched ($Mode). Screenshot: AR-Helper.cmd ... or deploy_app screenshot." -ForegroundColor Green
