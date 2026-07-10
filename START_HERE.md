# ▶ 복귀 시 여기부터 (2026-07-01 자율세션 결과)

안경 연결까지 **딱 한 단계(관리자 1클릭)**만 남았고, 나머지(보안 툴킷·초점 테스트·문서)는
전부 준비·검증 완료했다. 전체 요약: [SESSION_2026-07-01](SESSION_2026-07-01_안경연결_보안툴킷.md) ·
가이드: [docs/AR_SETUP.md](docs/AR_SETUP.md).

## 1️⃣ 안경 USB 연결 마무리 (관리자 1클릭)
```
tools\ar_helper\Fix-ADB-Driver-ADMIN.cmd   ← 더블클릭 → UAC "예"
```
- 화면에 기기가 `device`로 뜨면 성공. `unauthorized`면 안경에서 "USB 디버깅 허용" 수락.
- 안 되면: `adb kill-server` 후 재실행 → 그래도 안 되면 docs/AR_SETUP §2.2 플랜B/C.
- (원인은 이미 규명됨: Windows 복합USB 문제. adb 레거시 백엔드로 우회하도록 다 세팅해둠.)

## 2️⃣ 연결 후 원커맨드 (실측 + 초점테스트까지)
```
powershell -ExecutionPolicy Bypass -File tools\ar_helper\first_connect.ps1
```
연결 확인 → 모델·칩셋·카메라 덤프 → (원하면) 근거리 초점 테스트까지 한 흐름.
개별로: `AR-Helper.cmd info` (실측) · `AR-Helper.cmd mirror` (화면 미러).

## 3️⃣ 근거리 초점 테스트 (특허 리스크 ⓐ)
```
powershell -ExecutionPolicy Bypass -File tools\ar_helper\capture_focus_test.ps1 -Torch
```
손톱을 20→30→40cm로 천천히. 스크립트가 가장 선명한 프레임을 점수화(SHARP/BLURRY)한다.
SHARP → 글래스 카메라 사용 / BLURRY → 폰 카메라 폴백.

## 🖐️ 네일-AR 앱 (자율세션 신규 — 안경에서 작동 검증됨)
손톱 검출 → 곡면 디자인 오버레이. **결과: [docs/GLASSES_APP_RESULTS.md](docs/GLASSES_APP_RESULTS.md).**
> ⚠️ 안경이 절전(Doze)이면 앱이 안 보임 → **안경을 쓰거나** 데모 스크립트가 자동으로 깨움.
```
# 정지 손사진에 디자인 입히기 (안정 데모)
powershell -File tools\build\run_glasses_demo.ps1 -Mode image
# 최종 제품 경로: PC/폰 프레임 → 안경이 검출+표시 (별 터미널에 프레임서버 먼저)
python tools\build\frame_server.py --image samples\focus_test\hand_small.jpg   # 또는 --webcam 0
powershell -File tools\build\run_glasses_demo.ps1 -Mode network
```
- 발견: **안경은 서드파티 카메라 차단** + 근거리 초점 약함 → **캡처=폰/PC, 표시=안경** 확정.
- 재빌드: `tools\build\build_app.ps1` (포터블 JDK17+Gradle+SDK, 관리자 불필요).
- **폰 라이브**: 폰 USB 연결 → `AR-Helper.cmd install <apk>` → 후면 카메라로 실시간(안경 아님).

## 그 외 (준비됨)
- **APK 설치:** `AR-Helper.cmd install "경로\app.apk"` (또는 미러 창에 드래그&드롭)
- **원격 데스크톱:** `tools\ar_helper\setup_remote_desktop.ps1` (Sunshine+Moonlight, LAN 암호화)
- **폰→안경 화면:** docs/AR_SETUP §5 (ScreenStream)
- **도수/초점:** 자석 도수 인서트(원용) 또는 콘택트 — docs/AR_SETUP §6
- **Android 앱 빌드:** JDK17+SDK 필요 — docs/AR_SETUP §8 (자율세션에선 보류)

> 질문 있던 것: **안경 ADB는 이미 켜져 있음**(Windows에 ADB Interface가 뜬 게 증거).
> 한자 ON/OFF 구분 = **开(ON)** vs **关(OFF)**.
