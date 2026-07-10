<#
  setup_buildkit.ps1 — portable, user-scope (NO admin) Android build toolchain.
  Downloads + extracts JDK17, Gradle 8.9, Android cmdline-tools; installs SDK
  packages (platform-tools, android-34, build-tools 34) and accepts licenses.
  Logs each step so a background run can be monitored.
  Target for building android/ (AGP 8.5.2 -> needs Gradle 8.7+/JDK17/SDK34).
#>
$ErrorActionPreference = 'Continue'
$KIT = 'C:\Users\k1212\android-buildkit'
$LOG = "$KIT\setup.log"
New-Item -ItemType Directory -Force -Path $KIT | Out-Null
function Log($m){ $t=(Get-Date).ToString('HH:mm:ss'); "$t $m" | Tee-Object -FilePath $LOG -Append }

Log "=== buildkit setup start ==="

# --- 1) JDK 17 (Temurin) ---
$jdkZip = "$KIT\jdk17.zip"
if (-not (Test-Path "$KIT\jdk")) {
  Log "downloading JDK17..."
  curl.exe -sL -o $jdkZip "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse"
  Log "JDK17 zip: $((Get-Item $jdkZip -ErrorAction SilentlyContinue).Length) bytes"
  Expand-Archive -Path $jdkZip -DestinationPath "$KIT\jdk" -Force
  Log "JDK17 extracted"
}
$JAVA_HOME = (Get-ChildItem "$KIT\jdk" -Directory | Where-Object { $_.Name -like 'jdk*' } | Select-Object -First 1).FullName
Log "JAVA_HOME=$JAVA_HOME"

# --- 2) Gradle 8.9 ---
$gZip = "$KIT\gradle.zip"
if (-not (Test-Path "$KIT\gradle\gradle-8.9")) {
  Log "downloading Gradle 8.9..."
  curl.exe -sL -o $gZip "https://services.gradle.org/distributions/gradle-8.9-bin.zip"
  Log "gradle zip: $((Get-Item $gZip -ErrorAction SilentlyContinue).Length) bytes"
  Expand-Archive -Path $gZip -DestinationPath "$KIT\gradle" -Force
  Log "Gradle extracted"
}
$GRADLE = "$KIT\gradle\gradle-8.9\bin\gradle.bat"
Log "GRADLE=$GRADLE"

# --- 3) Android cmdline-tools ---
$ctZip = "$KIT\cmdtools.zip"
$SDK = "$KIT\android-sdk"
if (-not (Test-Path "$SDK\cmdline-tools\latest\bin\sdkmanager.bat")) {
  Log "downloading cmdline-tools..."
  curl.exe -sL -o $ctZip "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
  Log "cmdtools zip: $((Get-Item $ctZip -ErrorAction SilentlyContinue).Length) bytes"
  Expand-Archive -Path $ctZip -DestinationPath "$SDK\_tmp" -Force
  New-Item -ItemType Directory -Force -Path "$SDK\cmdline-tools\latest" | Out-Null
  Get-ChildItem "$SDK\_tmp\cmdline-tools\*" | Move-Item -Destination "$SDK\cmdline-tools\latest" -Force
  Remove-Item "$SDK\_tmp" -Recurse -Force -ErrorAction SilentlyContinue
  Log "cmdline-tools placed at cmdline-tools/latest"
}
$SDKMGR = "$SDK\cmdline-tools\latest\bin\sdkmanager.bat"

# --- 4) SDK packages + licenses ---
$env:JAVA_HOME = $JAVA_HOME
$env:ANDROID_HOME = $SDK
$env:ANDROID_SDK_ROOT = $SDK
Log "accepting licenses..."
$y = ("y`n" * 30)
$y | & $SDKMGR --sdk_root=$SDK --licenses 2>&1 | Select-Object -Last 2 | ForEach-Object { Log "lic: $_" }
Log "installing platform-tools, platforms;android-34, build-tools;34.0.0 ..."
& $SDKMGR --sdk_root=$SDK "platform-tools" "platforms;android-34" "build-tools;34.0.0" 2>&1 | Select-Object -Last 3 | ForEach-Object { Log "sdk: $_" }

# --- 5) record env for the build script ---
[pscustomobject]@{ JAVA_HOME=$JAVA_HOME; ANDROID_HOME=$SDK; GRADLE=$GRADLE } | ConvertTo-Json | Set-Content "$KIT\env.json"
Log "=== buildkit setup DONE ==="
