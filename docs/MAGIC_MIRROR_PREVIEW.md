# 매직미러 프리뷰(경로 C) + 카드 스케일 — 구현 현황과 남은 일

작성 2026-07-14. 이 문서는 **왜 매직미러 프리뷰로 갔는지**, **PC측에서 무엇이 구현·검증됐는지**,
**안경 켜지면 할 device 작업**을 정리한다. 물리 근거는 [AR_REGISTRATION_RESEARCH.md](AR_REGISTRATION_RESEARCH.md),
전략 배경은 메모리 `nailar-nearfield-ost-impossible` · `patent-vs-x3-preview-conflict`.

## 0. 결론 — 왜 경로 C

딥리서치 2건 + Grok 삼각검증으로, X3에서 "실물 손톱 위 선명 정합"은 물리 3벽(VAC 3.08D · 가산형
occlusion 불가 · 오프로드 지연 70~100ms)으로 **불가**. 세 경로 중 **C(매직미러 프리뷰)** 만 세 벽을
모두 회피한다 — 합성된 손+디자인을 **4m 패널에서 거울처럼 보므로** 눈에 0지연 실물 기준이 없어
고스트가 없고, 전부 4m라 흐림 없고, 디지털 합성이라 불투명. 단 "미리보기"라 특허 신규성(#1 미리보기
아님·#3 가림)은 X3로 실증 불가 → 제품/특허 트랙 분리(메모리 `patent-vs-x3-preview-conflict`).

프리뷰는 "사진 그대로"가 아니라 **손톱 3D 포즈에 곡면 메시 워핑 + 불투명 + 실물크기 크롭·확대 +
정지 시만 렌더**한 스마트 미러다.

## 1. PC측 구현·검증 완료 (이 저장소)

| 기능 | 파일 | 상태 |
|---|---|---|
| ISO 카드(85.6×54mm) 검출 → mm/px·손톱 실치수·solvePnP 거리 | [src/card_scale.py](../src/card_scale.py) | ✅ 테스트 5/5 |
| 카드 실측 → 깊이-파이프라인 mm 추정 보정계수 k(비순환) | [src/card_calib.py](../src/card_calib.py) | ✅ 테스트 6/6 |
| 렌더 게이팅용 손 정지 판정(칼만 속도) | [src/tracking.py](../src/tracking.py) `speed()` | ✅ 테스트 3/3 |
| 에지 서버 연동 | [web/edge_serve.py](../web/edge_serve.py) | ✅ 문법검증 |
| 실사진 카드 검출 검증 도구 | [tools/card_probe.py](../tools/card_probe.py) | ✅ 스모크 |

### 에지 서버 API 추가분 (`POST /infer`)
- `?card=1` → 응답에 `"card": {"found","mmPerPx","longPx","corners"}` + 손톱마다 `"lenMm","widMm"`.
- `?calib=1[&reset=1]` → 카드+손 동시 프레임에서 보정계수 k 누적 → 20개 모이면 `camera_calib.json` 기록.
  서버 시작 시 자동 로드해 mm 추정을 k 로 보정. 응답 `"calib": {"count","need","done","k","msg"}`.
- 모든 손톱에 `"speed"`(px/frame), `"stable"`(속도 ≤ `NAIL_STABLE_PX`, 기본 3.0) 추가 → 클라가
  **정지 시만 렌더**(이중상 억제)에 사용.

### 사용 흐름
1. 카드를 손톱 옆(같은 거리)에 대고 `?calib=1` 로 20프레임 → `camera_calib.json` 생성(1회).
2. 이후 `?card=1` 로 실치수 확인, 또는 카드 없이 보정된 mm 사용.
3. 실사진 검증: `python tools/card_probe.py <손+카드.jpg>`.

## 2. 안경 켜지면 할 device 작업 (turnkey)

C 프리뷰의 **표시부는 이미 있음**: 안경 앱 MirrorMesh 모드(피드 ON + 곡면 메시 디자인 ON,
`NailARController.cs`, ShareCamera로 안경 카메라 취득). 남은 건 PC 신호를 표시에 반영:

1. **실물크기 크롭·확대** — 서버 `card.mmPerPx`(또는 `camera_calib.json`)로 프리뷰 줌 계산
   ([src/card_scale.py](../src/card_scale.py) `lifesize_zoom(mm_per_px, panel_px_per_mm)`). `panel_px_per_mm`
   은 X3 디스플레이 기하(FOV~30°, 640px/eye, 가상영상 4m)에서 산출 — **on-device 실측 튜닝 필요**.
2. **렌더 게이팅** — 응답 `nail.stable == false`(손 이동 중)면 디자인을 흐리게/숨김 → 이중상 회피.
3. **손톱 mm 표시**(선택) — `nail.lenMm/widMm` 로 핏/측정 UX.

### 남은 실측·검증 (device 필요)
- 카드 검출 실환경 강건성(광택 반사·피부 배경·조명) — `card_probe.py`로 실사진 튜닝.
- 안경 카메라 고정초점(~50cm)에서 카드/손톱 선명도 — 팔 뻗어 ~50cm가 실용적인지.
- `panel_px_per_mm` 실측(무엇을 "실물크기"로 볼지 UX 결정 포함).

## 3. 보류(R&D) — 경로 B 자산
`src/eye_geometry.py`·`web/eye_reg.py`·`src/monitor_calib.py`·`face_landmarker.task` 는 시스루 눈-정합용
(경로 B). VAC 벽으로 제품 경로엔서 보류하되 삭제하지 않고 R&D로 보존.
