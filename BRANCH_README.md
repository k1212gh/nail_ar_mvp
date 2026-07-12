# 브랜치: `feat/ost-registration-and-electron-station`

> 작성 2026-07-13. 이 문서는 **이 브랜치가 왜 갈라졌고, 무엇을·왜 만들었는지**를 서사로 정리한다.
> main 은 "안경 데모가 도는가"를 검증하는 상태였고, 이 브랜치는 그 위에서 나온
> **"디자인이 실제 손톱에 안 맞는다"는 문제 하나**를 파고들다 여러 산출물로 번졌다.

---

## 0. 왜 이 브랜치가 갈라졌나 (한 문단)

노트북에서 안경 데모를 살려 파이프라인이 도는 걸 확인한 뒤(main), 실사용에서 **"곡면 디자인이 실제 손톱 위치에 안 얹힌다"** 는 문제가 드러났다. 이걸 "매번 손으로 맞추는 게 아니라 **자동으로** 맞추자"로 파고들었고, 그 과정에서 (1) 왜 근본적으로 어려운지의 물리, (2) 자동 정합을 위한 **외부캠 눈추적**, (3) 고정밀 보정을 위한 **모니터 기반 SPAAM**, (4) 이 모든 걸 사장님도 버튼으로 굴리게 하는 **Electron 컨트롤 스테이션**, (5) 안경 앱의 **매직미러 모드 + 빌드 시스템 수정**까지 나왔다. main 을 어지럽히지 않으려 브랜치로 분리했다.

관련 세션 맥락: [SESSION_2026-07-11_데모준비_깃업로드.md](SESSION_2026-07-11_데모준비_깃업로드.md), 물리 근거: [docs/AR_REGISTRATION_RESEARCH.md](docs/AR_REGISTRATION_RESEARCH.md).

---

## 1. 출발점 — "디자인이 손톱에 안 맞는다"

- 안경(RayNeo X3 Pro)은 **광학 시스루(OST)**. 카메라가 손톱을 검출(PC edge_serve)하고, 안경이 그 위에 디자인을 그린다.
- 그런데 **디자인이 실제 손톱에서 어긋나** 보인다. "손으로 offset을 맞추면 되지 않나?" → **그건 사람마다·매번 해야 해서 제품이 아니다.** 그래서 **자동 정합**을 목표로 삼았다.

## 2. 물리 현실부터 직시 (왜 자동이 어려운가)

[docs/AR_REGISTRATION_RESEARCH.md](docs/AR_REGISTRATION_RESEARCH.md) 의 결론(이 브랜치의 전제):

- X3는 **가상영상 초점 4m 고정 + 아이트래킹 없음**.
- **시차 정합오차** = 눈 위치를 모르니 재착용마다 ~4.6mm 떠다님(손톱 폭의 ~42%).
- **폭주-초점 충돌(VAC)** 30cm에서 ~3디옵터 → 흐림·복시. **소프트웨어로 못 고침.**
- 업계(YouCam·ModiFace·Snap)는 전부 **매직미러**(카메라 영상 위 2D 합성, 화면으로 봄) — 아무도 시스루 눈-정합을 안 한다.

→ **결론: "자동·정확·선명"을 다 잡는 건 이 하드웨어론 불가. 위치(x/y)는 자동화 가능하지만 흐림은 하드웨어 벽.** 그래서 두 갈래를 동시에 팠다: **(A) 위치 자동정합 R&D**, **(B) 흐림 없는 정답 = 매직미러**.

## 3. (A) 외부캠 복합 자동정합 — 위치 자동화

**아이디어:** X3에 없는 아이트래킹을 **노트북 웹캠으로 대체**. 웹캠이 얼굴 홍채를 봐서 눈 3D를 측정 → 눈-카메라 baseline b → 앱의 깊이적응 시차모델 `offset(d)=A+B/d` 의 (A,B)를 자동으로 채운다.

| 파일 | 역할 | 상태 |
|---|---|---|
| [src/eye_geometry.py](src/eye_geometry.py) | 기하 코어(홍채 11.7mm 메트릭 → 눈3D → baseline → A,B) | 단위테스트 [tests/test_eye_geometry.py](tests/test_eye_geometry.py) 9/9 |
| [web/eye_reg.py](web/eye_reg.py) | 웹캠 런타임(FaceLandmarker → 측정 → adb push) | 라이브 검증: 검지 손톱이 눈측정만으로 자동 정합됨(=코어 검증) |
| [models/face_landmarker.task](models/face_landmarker.task) | MediaPipe FaceLandmarker 모델(홍채+머리포즈) | 3.7MB, turnkey 위해 포함 |

설계: [docs/EXTERNAL_CAM_REGISTRATION.md](docs/EXTERNAL_CAM_REGISTRATION.md). **한계: 위치는 잡아도 VAC 흐림은 불변.**

## 4. (A') 모니터 기반 다거리 4점 SPAAM — 고정밀 1회 보정

**사용자 아이디어:** 노트북 **모니터(물리 크기 기지)** 를 정밀 평면 기준물로 삼아, 안경 크로스헤어를 여러 거리에서 4모서리에 맞추면 눈-카메라 기하 **전체(스케일+오프셋)** 를 푼다. → "손톱이 덜 벌어짐"(스케일 오정합)까지 교정.

| 파일 | 역할 | 상태 |
|---|---|---|
| [src/monitor_calib.py](src/monitor_calib.py) | PnP(4모서리) + SPAAM DLT(다거리) + 눈→A,B | 단위테스트 [tests/tests_monitor_calib.py](tests/tests_monitor_calib.py) 12/12(합성 눈오차 0.03mm) |
| [web/monitor_calib_run.py](web/monitor_calib_run.py) | 런타임(패턴표시·모서리검출·크로스헤어·기록·솔브) | 서브커맨드 CLI |

설계: [docs/MONITOR_CALIBRATION.md](docs/MONITOR_CALIBRATION.md). **웹캠 자동추적(3)과 모니터 보정(4)이 "노트북 = 보정 스테이션"으로 통합**된다.

## 5. (B) 매직미러 — 흐림 없는 정답 (안경 앱 재빌드)

물리적으로 시스루 정합은 흐림이 남으므로, **매직미러**(카메라 피드 위에 디자인 합성 → 먼 패널로 봄, VAC 없음)가 X3에서 가장 깨끗한 데모다. 기존 안경 앱엔 "피드 ON + 디자인 ON" 모드가 없어 **Unity 소스에 새 모드를 추가하고 재빌드**했다.

- [Nail/Assets/Scripts/NailARController.cs](Nail/Assets/Scripts/NailARController.cs): **`MirrorMesh` 모드 추가**(피드 ON + 곡면 메시 디자인 ON + 시차 OFF). `nail_calib.json` 에 `mode=5` push 로 진입.
- [Nail/Assets/Editor/CIBuild.cs](Nail/Assets/Editor/CIBuild.cs): **빌드 시스템 수정 + `BuildMirror` 추가.**
  - 배치빌드가 SDK/target/cmdline-tools 때문에 계속 실패 → **임베디드/사용자 SDK 경로 명시, target SDK 30(RayNeo 요구) + platform-30 있는 사용자 SDK, `cmdline-tools/latest` 처리** 를 코드에서 자동 설정.
  - `BuildMirror` = 기존 `NailMesh` 를 **덮어쓰지 않는 별도 패키지 `com.DefaultCompany.NailMirror`**(side-by-side). 뭐가 잘못돼도 원래 앱은 멀쩡하게.
- 산출물 `NailMirror_AUTO.apk`(gitignore, 18MB)를 안경에 설치 → `mode=5` → 매직미러 동작 확인.
  - **교훈(현장 함정):** RayNeo 카메라 HAL이 **앱을 빠르게 여닫으면 "serious error"로 멈춘다.** 복구 = **안경 재부팅 1회 후 단일 실행**. 앱/빌드는 정상, 카메라만 리셋하면 됨.

## 6. Electron 컨트롤 스테이션 — 왜 만들었나

위 파이프라인(edge_serve·eye_reg·monitor_calib·adb)을 **CLI 여러 개로 손수 굴리는 건 사장님/현장 데모에 부적합**하다. 그래서 **"서버는 그대로 두고 껍데기만"** — Python 백엔드는 손대지 않고, **Electron + React UI** 로 감쌌다.

| 파일 | 역할 |
|---|---|
| [electron/main.js](electron/main.js) · [electron/preload.js](electron/preload.js) | Electron 메인 + 안전한 IPC 브리지 |
| [electron/backend.js](electron/backend.js) | child_process 로 python 서버/eye_reg·adb 오케스트레이션(**서버 코드 무수정**) |
| [electron/renderer/](electron/renderer/) | React(무빌드 UMD+htm) UI: 상태판·서버/안경 제어·**모니터 보정 마법사**·라이브 프리뷰·로그 |

- **버튼으로**: 에지서버 on/off, 안경 연결(reverse+wake+앱), 눈추적 on/off, 모니터 4점 보정.
- `npm start`(개발) 또는 **패키징(.exe, Electron 포함 완전 독립)** 으로 배포. `backend.js` 가 repo 를 자동 탐색(`NAIL_REPO` 로 override 가능).
- **안경 앱(Unity)은 대체하지 않음** — Electron 은 PC측 컨트롤러/캘리브/매직미러 역할.

## 7. 곁다리 버그 수정 (fresh-clone·환경 함정)

- [web/serve.py](web/serve.py): 자체서명 인증서 생성 시 **`certs/` 폴더가 없으면 먼저 생성**(fresh clone 에서 서버가 안 켜지던 버그).
- [src/tracking.py](src/tracking.py): 칼만 `float(1원소배열)` → **numpy 2.x 호환**(`[i,0]` 인덱싱). 손 잡히는 순간 서버가 죽던 버그.
- [.gitignore](.gitignore): `.venv/`·`electron/node_modules/`·임시 json·Unity IDE 파일·**중첩 중복 클론 `/nail_ar_mvp/`** 제외.

---

## 8. 빠른 사용

```powershell
# 1) (한 번) 클린 venv + 의존성  (이 노트북은 anaconda base가 mediapipe와 충돌 -> 별도 venv 필수)
py -3.11 -m venv .venv
$env:PYTHONUTF8=1; .venv\Scripts\python -m pip install -r requirements.txt

# 2) 데모: Electron 스테이션 (권장)
cd electron; npm install; npm start      # 버튼으로 서버·안경·보정 제어

#    또는 CLI 로 직접
.venv\Scripts\python web\edge_serve.py    # 터미널1: 에지서버(반드시 이 venv 파이썬)
adb reverse tcp:8443 tcp:8443             # 터미널2: 안경 연결
adb shell monkey -p com.DefaultCompany.NailMirror -c android.intent.category.LAUNCHER 1

# 3) 자동정합(선택): 웹캠 눈추적
.venv\Scripts\python web\eye_reg.py --package com.DefaultCompany.NailMirror

# 4) 안경 앱 재빌드(Unity 2022.3.36f1 필요): 매직미러 별도앱
"<Unity>\Editor\Unity.exe" -batchmode -nographics -quit -projectPath Nail -executeMethod CIBuild.BuildMirror -buildTarget Android -logFile -
```

## 9. 상태 요약

| 영역 | 상태 |
|---|---|
| 외부캠 눈추적 코어 | ✅ 테스트 9/9, 라이브 검증 |
| 모니터 4점 보정 코어 | ✅ 테스트 12/12 |
| 매직미러 모드 + 빌드 | ✅ NailMirror APK 빌드·설치·구동 확인(카메라 리셋 후) |
| Electron 스테이션 | ✅ 실행·패키징 확인 |
| 버그 수정 | ✅ serve.py·tracking.py·gitignore |
| 남은 것 | 모니터보정 물리세션 정밀화, per-nail 라이브 루프(Unity 패치) — 문서에 스펙 있음 |
