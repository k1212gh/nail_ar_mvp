# 안경 앱 — 자율 개발 결과 (2026-07-01)

> 목표: **손톱 검출 → 디자인 AR 오버레이 앱을 빌드해 RayNeo X3 Pro에 탑재.**
> 결과: **✅ 달성.** 무(無)에서 빌드 툴체인 세팅 → 네이티브 APK 빌드 → 안경 배포 →
> 손톱 5개 검출 + 곡면 디자인 오버레이를 **안경에서 렌더·스크린샷 검증.**
> 상세 세션: [SESSION_2026-07-01](../SESSION_2026-07-01_안경연결_보안툴킷.md).

## 1. 기기 실측 (RayNeo X3 Pro)
| 항목 | 값 |
|---|---|
| 모델/코드명 | ARGF20 / MercuryLiteXR, RayNeoX3Pro |
| SoC / RAM | Qualcomm(`neo`=AR1 Gen1) / ~4GB |
| OS / ABI | Android 12 (SDK32) / arm64-v8a |
| 디스플레이 | 1280×480, 60Hz, density 160, **FLAG_SECURE** |
| 카메라 | id0 back 4032×3024(12MP), id1 back 640×480, fps15/24/30, zoom1–8× |

## 2. 플랫폼 제약 (실측으로 확정 — 아키텍처 결정 요인)
1. **서드파티 카메라 차단** — 사이드로드 앱의 Camera2가 `ERROR_CAMERA_DISABLED`(센서프라이버시 OFF·appops allow에도 불변). 시스템 앱(`com.leiniao.camera`)만 카메라 가능.
2. **고정초점 ~50cm+** — 손톱 작업거리 20~40cm는 SOFT(흐림). (초점 판정기 `focus_analyze.py`로 확인.)
3. **디스플레이가 idle 시 Dozing** — 안경을 안 쓰면 화면 OFF → **앱 뷰가 0크기로 렌더 안 됨.** `input keyevent WAKEUP` + `svc power stayon true`로 깨우면 정상.
4. **FLAG_SECURE 디스플레이** — 보안 창은 캡처 차단. 단, 일반 앱 창은 **깨어있을 때** screencap 가능.
5. **RayNeo 앱 관리(Mercury/BackgroundAppManager)** — 서드파티 앱을 특수 창으로 다룸. `am start`로 포그라운드 가능.

**→ 확정 아키텍처:** 캡처·인식은 **폰/PC**, 안경은 **표시 전용.** (특허 청구항 41/42 연산배치와 부합. 계획서 Phase 2 폴백 채택.)

## 3. 빌드 툴체인 (유저 스코프, 관리자 불필요) — 재현 가능
`C:\Users\k1212\android-buildkit\` 에 포터블 설치:
- **JDK 17**(Temurin), **Gradle 8.9**, **Android SDK**(cmdline-tools + platform-34 + build-tools 34).
- 스크립트: [tools/build/setup_buildkit.ps1](../tools/build/setup_buildkit.ps1) (다운로드+SDK+라이선스), [build_app.ps1](../tools/build/build_app.ps1), [deploy_app.ps1](../tools/build/deploy_app.ps1).
- 라이선스는 해시 파일 직접 기록으로 무인 수락.
- **결과 APK:** `android/app/build/outputs/apk/debug/app-debug.apk` (~58MB, CameraX 1.3.4 + MediaPipe tasks-vision 0.10.14 + hand_landmarker.task).

## 4. 앱 — 두 모드
- **IMAGE MODE** (글래스 시연/검증): 앱 외부폴더 `nail_input.jpg`가 있으면 그 정지영상으로
  MediaPipe 손 검출 → 손톱 ROI → **곡면(반원기둥 mesh) 디자인 오버레이**. 카메라 차단 우회 + screencap 검증 가능.
  주입: `adb push <hand.jpg> /sdcard/Android/data/com.example.nailar/files/nail_input.jpg`.
- **CAMERA MODE**: 후면 카메라 라이브(폰에서 동작; 글래스는 카메라 차단으로 미동작).
- 코드: `render/OverlayView.kt`(디자인/안내선/곡면 mesh `drawBitmapMesh`), `vision/HandNailDetector.kt`(+`detectImage` IMAGE 러닝모드), `MainActivity.kt`(모드 분기).
- 디자인 에셋: [tools/build/gen_nail_design.py](../tools/build/gen_nail_design.py) — 손톱형(타원 알파) french/floral/dots PNG 생성.

## 5. 검증 결과 (안경 실기)
- HUD: **`IMAGE: nails 5  det 537ms  1080x1440`** — MediaPipe가 손톱 5개를 537ms에 검출.
- 5개 손톱 각각에 **손톱형(타원 알파) 디자인**이 **곡면(반원기둥 mesh)+3D 음영(가장자리 어둡게)**으로 얹힘.
- **손가락별 다른 디자인**(프렌치/플로럴/도트 순환) = 실제 네일아트 느낌.
- 증거: `samples/app_design_v5*.png`(광택+프렌치 스마일라인 개선·최종), `app_design_v4*`(per-finger), v2/v3(중간).
- **디자인 품질 개선(자율 루프)**: `gen_nail_design.py`에 광택 하이라이트(shiny) + 깔끔한 프렌치 스마일라인 추가 → 실제 반짝이는 네일아트 느낌. 안경 검증 완료.
- **= 특허 핵심(인식→안내정보 생성→정합 표시)을 타겟 하드웨어에서 실증.**

## 5b. 폰 라이브 경로 (같은 APK, 카메라 모드)
안경은 카메라 차단이지만 **일반 안드로이드 폰(갤S22 등)은 CAMERA MODE로 실시간 동작**한다
(입력폴더에 nail_input.jpg 없으면 자동 카메라 모드). 폰 USB 연결 후:
```
tools\ar_helper\AR-Helper.cmd install android\app\build\outputs\apk\debug\app-debug.apk
```
→ 후면 카메라로 손톱 실시간 검출+디자인 오버레이(좋은 초점). 안경=표시, 폰=캡처의
"라이브" 실증은 다음 증분(폰 캡처 → 에지 → 안경 표시 네트워크).

## 5c. ✅ 최종 아키텍처 실증 — NETWORK MODE (M8)
**"외부 캡처 → 안경 표시"** 제품 경로를 실기 검증. 안경은 카메라만 막혔지 **연산은 가능**하므로,
외부(폰/PC)가 프레임만 제공하고 안경이 검출+렌더한다.
- **PC 프레임 서버**: [tools/build/frame_server.py](../tools/build/frame_server.py) — `/frame.jpg` 서빙(정지이미지 또는 웹캠).
- **USB 터널**: `adb reverse tcp:8080 tcp:8080` → 안경이 `http://127.0.0.1:8080/frame.jpg` 접속(WiFi 불필요).
- **안경 앱 NETWORK MODE**: 설정파일 `nailar_config.json`의 `frameUrl` 있으면 프레임 폴링 → MediaPipe 검출 → 곡면 디자인 렌더. (Android12 평문차단 → `usesCleartextTraffic=true` 필요.)
- **검증 결과**: HUD `NET: nails 5  506ms/frame  #11` — 연속 루프로 프레임 수신·검출·오버레이. 증거 `samples/app_network2.png`.
- **라이브 검증 완료**: `frame_server.py --webcam 0`로 PC 웹캠 스트림 → 안경 HUD `NET: nails 0  358ms/frame  #15`(연속 프레임 수신·처리, ~3fps). 웹캠 앞에 손 없어서 nails 0일 뿐, **라이브 파이프라인 end-to-end 작동.** 손을 웹캠/폰 카메라에 대면 실시간 네일-AR. 원커맨드: `tools/build/run_glasses_demo.ps1 -Mode network`.
- 설정파일 예: `{"frameUrl":"http://127.0.0.1:8080/frame.jpg","showGuide":false,"designScale":1.7}` (3모드 우선순위: network > image(nail_input.jpg) > camera).

## 6. 남은 개선(다음 증분)
- 정밀 손톱 외곽 클리핑(현재 타원 근사) — 온디바이스 세그(YOLOv8-seg 이식) 또는 PC 에지 오프로드.
- **라이브 경로**: 폰 카메라 캡처 → (에지) 인식·워프 → 안경 표시(네트워크). = 최종 사용형.
- 청구항 24(가림 보정)/30(전사)/14(결과검출) 앱 반영.
- 초점-폭주(가상4m vs 실물30cm) UX, 도수 인서트.

## 7. 함께 설치된 것 (요청)
- **NewPipe**(유튜브, OSS) · **Fennec**(파이어폭스, OSS) — 안경에서 네이티브 실행. 조작은 안경 터치패드 또는 PC scrcpy.
- 알림 브리지: [tools/notify/](../tools/notify/) (텔레그램 양방향 — 토큰 주면 작동).
