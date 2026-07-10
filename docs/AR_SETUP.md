# AR 글래스 셋업 & 보안 툴킷 — 통합 가이드

> RayNeo X3 연결 + Tvini 3대 기능(APK 설치·화면미러 / 원격 데스크톱 / 폰 화면공유)을
> **모두 오픈소스·로컬·감사가능**한 스택으로 대체한다. 작성 2026-07-01 (자율 세션).
> 도구 위치: [tools/ar_helper/](../tools/ar_helper/). 상위 계획: [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md).

---

## 0. 보안 원칙 (왜 Tvini를 그대로 안 쓰나)

Tvini의 세 기능(Helper=APK설치/미러, Remote Desktop, Phone share)은 전부 **유명 오픈소스
도구를 얇게 감싼 닫힌 바이너리**다. 화면공유=화면 전체 접근, APK설치=임의 코드 설치라는
**최고 권한**을 닫힌·미서명 소프트웨어에 주는 것이 위험의 핵심이다. 그래서 우리는
**원본 오픈소스를 로컬에서 직접** 쓴다.

| 항목 | Tvini (닫힌 바이너리) | 우리 스택 (오픈소스·로컬) |
|---|---|---|
| APK 설치 + 미러 | Tvini Helper | **scrcpy + adb** (Genymobile) |
| 원격 데스크톱 | Tvini Remote Desktop (QR/클라우드?) | **Sunshine(호스트) + Moonlight(안경)** — LAN 암호화 |
| 폰 → 안경 | Tvini Phone (QR 페어링) | **ScreenStream**(폰 LAN 서버) → 안경 브라우저 |
| 소스 감사 | ❌ 불가 | ✅ 전부 공개 |
| 데이터 경로 | 불투명(릴레이 가능) | USB / 내 LAN 만, 클라우드 0 |
| 설치 출처 | 그들 서버 APK | winget(해시검증) / GitHub(체크섬) |

---

## 1. 설치된 도구 (완료)

- **scrcpy 4.0 + adb 37.0.0** — `winget install Genymobile.scrcpy` (해시 검증됨).
  경로 자동 해석: [tools/ar_helper/adb_env.ps1](../tools/ar_helper/adb_env.ps1).
- 별도 PATH 설정 불필요 — 헬퍼가 winget 설치 경로를 스스로 찾는다.

---

## 2. 안경 연결 (RayNeo X3)

### 2.1 안경에서 ADB 켜기 (한 번만)
1. 안경 착용 → **Settings → General → About Device** 하이라이트
2. 터치패드 **왼쪽으로 10회 스와이프** → 상단에 중국어 + `adb` 표시되면 ON
   - **开**(=열림/ON) vs **关**(=닫힘/OFF). 다시 10회 하면 꺼짐.
3. (선택) **Settings → App Lab Features → App Lab** 켜기 (사이드로드 앱이 메뉴에 보임)

### 2.2 Windows USB 드라이버 수정 (필수 — 진단 완료)
**증상:** ADB는 켜졌는데(=Windows에 `ADB Interface`가 뜸) `adb devices`가 빈 목록.
**원인:** RayNeo는 USB에서 MTP+ADB 복합장치로 뜨는데, Windows가 자동 바인딩한 WinUSB로는
adb(libusb)가 ADB 엔드포인트를 못 연다 (`ADB interface missing endpoints`). macOS엔 없는
Windows 전용 문제.
**해결(다운로드 없음):** ADB 표준 인터페이스 GUID를 장치에 등록 → **레거시 백엔드**(adb 37은
`ADB_LIBUSB=0`이면 `usb_windows.cpp` 백엔드를 씀 — 검증됨)가 인식.
```
tools\ar_helper\Fix-ADB-Driver-ADMIN.cmd   ← 더블클릭 후 UAC "예"
```
이후 `adb devices`에 기기가 뜨면 성공. `unauthorized`면 안경에서 "USB 디버깅 허용" 팝업 수락.
> 헬퍼는 `adb_env.ps1`에서 **`ADB_LIBUSB=0`을 자동 설정**하므로 수정 후 모든 명령이 일관되게
> 기기를 본다. (stale 서버가 있으면 한 번 `adb kill-server` 후 재시도.)

**플랜 B (GUID 등록이 안 먹힐 때):** Google USB Driver 설치 후 장치관리자에서 `ADB Interface`를
그 드라이버로 지정(`Update driver → Browse → Have Disk → android_winusb.inf`, VID_18D1 포함).
**플랜 C:** WiFi ADB(아래 2.3).

### 2.3 폴백 — WiFi ADB (USB가 계속 막힐 때)
안경·PC를 같은 WiFi에. `tools\ar_helper\AR-Helper.cmd connect` → IP 입력, 또는 mDNS 탐색.
(주의: 클래식 adb는 최초 `adb tcpip 5555`에 USB가 필요. Android 11+ 무선 디버깅이 있으면
`adb pair`로 USB 없이 가능.)

---

## 3. Task2-1 — 보안 APK 설치기 + 화면 미러 (Tvini Helper 대체)

**런처:** [tools/ar_helper/AR-Helper.cmd](../tools/ar_helper/AR-Helper.cmd) (더블클릭 = 메뉴)

| 기능 | 명령 | 비고 |
|---|---|---|
| 기기 목록 | `AR-Helper.cmd devices` | USB+WiFi |
| 화면 미러 | `AR-Helper.cmd mirror` | scrcpy, 창 닫으면 종료 |
| **APK 설치** | `AR-Helper.cmd install "C:\app.apk"` | `adb install -r -t`. **미러 창에 APK 드래그&드롭도 설치됨** (Tvini와 동일 UX) |
| 화면 녹화 | `AR-Helper.cmd record` | logs/rec_*.mp4 |
| 기기 정보 | `AR-Helper.cmd info` | 모델/칩셋/카메라 |
| **무결성 검증** | `verify_apk.ps1 app.apk -Expected <sha256>` | 사이드로드 전 SHA-256 확인. 불일치=설치 차단 |

전부 로컬 adb/scrcpy 호출 — 감사 가능. 인터넷에서 아무것도 받지 않는다.
> **보안 자가감사(2026-07-01):** `tools/ar_helper/` 전 스크립트에 실제 네트워크 송신 **0건**
> (grep 확인). 유일한 네트워크 동작=winget 설치(해시검증). Moonlight/ScreenStream 등 외부 APK는
> `verify_apk.ps1`로 공식 릴리스 해시와 대조 후 설치.

---

## 4. Task2-2 — AR 원격 데스크톱 (Tvini Remote Desktop 대체)

PC 화면을 **내 LAN에서 암호화 스트리밍**해 안경에서 본다. 클라우드 릴레이 없음.

**설치:** [tools/ar_helper/setup_remote_desktop.ps1](../tools/ar_helper/setup_remote_desktop.ps1) (자가승격, UAC 승인)
1. Sunshine 설치(winget `LizardByte.Sunshine`) + 방화벽을 **Private 프로필만** 허용.
2. WebUI `https://localhost:47990`에서 계정 설정.
3. 안경에 **Moonlight** 사이드로드:
   - `github.com/moonlight-stream/moonlight-android/releases`에서 APK 받고 **체크섬 확인**
   - `AR-Helper.cmd install <moonlight.apk>`
4. Moonlight에서 이 PC를 LAN IP로 추가 → Sunshine이 보여주는 **PIN 입력** 페어링.
5. 스트리밍. AES 암호화 + 기기별 인증서, 화면은 LAN을 벗어나지 않음.

---

## 5. Task2-3 — 폰 → 안경 화면 공유 (Tvini Phone 대체)

둘 다 안드로이드이므로 **폰이 LAN 웹서버로 자기 화면을 방송 → 안경 브라우저로 시청**.

**권장: ScreenStream (오픈소스)** — `github.com/dkrivoruchko/ScreenStream`
- 폰에 ScreenStream 설치(Play/APK) → "Start" → 폰이 `http://<폰IP>:8080` 로 화면 방송(WebRTC/MJPEG).
- 안경 브라우저에서 그 URL 열기 → 폰 화면이 안경에 뜸. **LAN 전용, 클라우드 0, 오픈소스.**
- 핀/암호 옵션으로 접근 제한 가능.

**대안 A (PC 경유):** PC에서 `scrcpy`로 폰 미러 → 그 PC를 Sunshine으로 안경에 스트림. 지연↑.
**대안 B (유선):** 폰을 AR-Helper로 미러 녹화/전달 — 실시간성 낮음.

> Tvini의 QR 페어링 대신, 신뢰된 오픈소스 앱 + LAN URL로 동일 결과를 투명하게 얻는다.

---

## 6. 도수/초점 문제 (조사 완료)

**원인:** X3 Pro 가상화면은 **약 4m 고정(43")**. 근시안은 교정 없이 4m가 흐림 → 안경 벗으면 오버레이 뿌옇다. X3는 **디옵터 다이얼 없음**(웨이브가이드) → "초점 조정"이 아니라 **도수 렌즈**로 해결.

| 해결책 | 내용 |
|---|---|
| ⭐ 자석식 도수 인서트 | 코브릿지 자석 마운트. 근시 0~-10D, 난시 0~-2D, **단초점 원용**(평소 원거리 도수). RayNeo 공식/Lensology 주문 |
| 콘택트렌즈 | 즉시·저렴. 가상(4m)+실물 손톱(근거리) 동시 교정 |
| 안경 위 착용 | 가능하나 5분+ 불편, 비권장 |

**프로젝트 주의:** 실물 손톱 ~30cm vs 가상 오버레이 ~4m = **초점-폭주 불일치**가 도수와 별개로 존재.
원용 도수로 오버레이를 선명히 하고 근거리는 조절력으로 보는 조합 권장(노안 아니라면).

출처: RayNeo 도수 렌즈 페이지, Lensology X3 Pro 인서트, Tom's Hardware X3 Pro 리뷰.

---

## 7. 안경 도착 즉시 검증 — 2대 리스크 (연결되면 실행)

`IMPLEMENTATION_PLAN.md` Phase 2. 스크립트는 [tools/ar_helper/](../tools/ar_helper/)에 준비됨.

- **ⓐ 근거리 초점** — `capture_focus_test.ps1 -Torch`(연결 후). scrcpy **카메라 소스**로 안경
  후면 카메라를 직접 녹화 → `focus_analyze.py`가 프레임별 선명도 점수화(SHARP/BLURRY). `-LiveOnly`는 실시간 육안 확인.
- **ⓑ 고정 안정성** — `fixation_test.ps1`. scrcpy로 안경 화면 녹화 후 오브젝트 드리프트 검토(3DoF).
- 분기: 통과 → 글래스 카메라 캡처 / 실패 → **폰 카메라 캡처 + 글래스 표시** 폴백.

---

## 8. Android 테스트 앱 빌드 (사이드로드용 — 보류/절차만)

현 상태: JDK 24만 있음, **Android SDK·gradle·wrapper 없음**. winget ID는 모두 확인됨(2026-07-01).

**권장(가장 확실): Android Studio** — SDK·gradle·wrapper를 자동 처리.
```
winget install Google.AndroidStudio      # 이후 android/ 폴더 Open → Run ▶
```

**CLI 경로(고급):** 헬퍼 `setup_android_build.ps1 -Cli`(자가승격) 또는 수동:
1. `winget install EclipseAdoptium.Temurin.17.JDK` (AGP는 JDK24 미지원 가능 → 17 권장)
2. `winget install Google.AndroidCLI` (sdkmanager) + `winget install Google.PlatformTools`
3. `sdkmanager "platforms;android-34" "build-tools;34.0.0"` + `sdkmanager --licenses`
4. `ANDROID_HOME` 설정 → gradle wrapper 부트스트랩(Studio 없으면 gradle.org 배포판 필요) → `gradlew assembleDebug`
5. 산출 APK: `android/app/build/outputs/apk/debug/app-debug.apk` → `AR-Helper.cmd install <apk>`

> ⚠️ 자율세션에선 미실행(대용량 다운로드+UAC). wrapper 부트스트랩 마찰 때문에 **Android Studio 경로 권장.**

---

## 부록 — tools/ar_helper 파일 맵

| 파일 | 역할 |
|---|---|
| `adb_env.ps1` | winget scrcpy/adb 경로 해석(공용) |
| `AR-Helper.cmd` / `ar_helper.ps1` | **메인 런처**: 기기목록·미러·APK설치·녹화·WiFi·정보 |
| `device_info.ps1` | 모델/칩셋/RAM/카메라/사이드로드 여부 덤프 |
| `verify_apk.ps1` | 사이드로드 전 APK SHA-256 무결성 검증 |
| `capture_focus_test.ps1` / `focus_analyze.py` | 근거리 초점(ⓐ): 카메라 녹화→선명도 점수 |
| `fixation_test.ps1` | 고정 안정성(ⓑ): 화면 녹화→드리프트 검토 |
| `watch_device.ps1` | 연결될 때까지 폴링 후 알림 |
| `Fix-ADB-Driver-ADMIN.cmd` / `fix_adb_driver.ps1` | **USB 드라이버 수정**(관리자, ADB GUID 등록) |
| `setup_remote_desktop.ps1` | Sunshine 호스트 설치+방화벽(자가승격) |
