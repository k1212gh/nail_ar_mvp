# 모니터 기반 다거리 4점 SPAAM 정합 보정 (Monitor-Fiducial OST Calibration)

작성: 2026-07-11. 대상 기기: **RayNeo X3** — 양안 OST 웨이브가이드, 가상영상 초점면 **~4m 고정**,
월드 RGB 카메라 1개, **아이트래킹 없음**([AR_REGISTRATION_RESEARCH.md](AR_REGISTRATION_RESEARCH.md) §1.3).

> **한 줄 결론:** 노트북 **모니터**(물리치수 기지)를 정밀 평면 기준물로 써서, 여러 거리에서 4모서리를
> AR 크로스헤어에 맞추면 **눈↔안경카메라 기하 전체(스케일+오프셋)** 를 푼다 → 손톱이 "덜 벌어지는"
> 다중손톱 스케일 오정합까지 교정. **단, 정합 위치는 잡아도 VAC 흐림은 4m 고정초점 광학이라 못 잡는다**
> ([AR_REGISTRATION_RESEARCH.md](AR_REGISTRATION_RESEARCH.md) §1.2). 이것이 하드웨어 상한이다.

이 문서는 [EXTERNAL_CAM_REGISTRATION.md](EXTERNAL_CAM_REGISTRATION.md)(웹캠 **자동** 눈추적)의
**자매 시스템**이다. 관계는 명확하다:

| 시스템 | 방식 | 무엇을 잡나 | 빈도 |
|---|---|---|---|
| **모니터 보정** (이 문서) | 수동, 고정밀, 기지치수 평면 기준물 | **기기/광학 상수**(camera↔display 스케일·f_disp·A·gcam 오프셋·축부호) | **1회** |
| **웹캠 보정** ([자매 문서](EXTERNAL_CAM_REGISTRATION.md)) | 자동, 홍채 3D 측정 | **사람별 눈 위치**(→ B) | 사람마다·프레임마다 |

모니터 보정이 **한 번** 기기상수를 못박으면, 웹캠 자동추적이 그 위에서 **사람별**로 눈을 재는 구조(§6).

---

## 1. 개요 & 아이디어 출처

**사용자 제안:** "노트북 **모니터는 물리 크기를 정확히 안다**. 그러면 화면에 네 모서리 마커를 띄우고,
안경 AR 화면의 크로스헤어를 **여러 알려진 거리에서** 각 모서리에 맞추면, 눈-카메라 기하를 역산할 수 있지
않나?" — 즉 **모니터 = 정밀 평면 기준물(planar fiducial)**.

이것이 **"모니터 기반 다거리 4점 SPAAM"** 이다:

- **4점** = 모니터 네 모서리(치수 기지 → 카메라 프레임 3D를 PnP로 확정).
- **다거리** = 노트북을 2~3개 거리에 두고 반복(단일 평면 축퇴 해소, §2c).
- **SPAAM** = (디스플레이 크로스헤어 픽셀 ↔ 모서리 3D) 대응쌍을 DLT로 풀어 눈↔디스플레이 투영행렬 P
  추정([src/monitor_calib.py](../src/monitor_calib.py), [연구문서](AR_REGISTRATION_RESEARCH.md) §2).

기존 손끝 SPAAM([연구문서](AR_REGISTRATION_RESEARCH.md) §2.3)과의 결정적 차이: 참조 3D점이
**노이즈 큰 맨손끝**이 아니라 **치수를 아는 강체 평면의 모서리**다 → 3D 참조가 훨씬 정확하고,
카메라 PnP로 4점을 한꺼번에 얻어 대응 수집이 빠르다. (Moser & Swan 2016도 "스타일러스가
맨손끝보다 정확"이라 했다 — 모니터는 그보다도 강체·기지치수라 상위.)

---

## 2. 왜 되는가 (수식)

핀홀로 본 **눈+디스플레이**를, 카메라 프레임의 3D점 → 디스플레이 픽셀로 보내는 3×4 투영행렬 P로 모델링:

```
s·[u,v,1]ᵀ = P·[X,Y,Z,1]ᵀ ,   P ∈ ℝ³ˣ⁴  (11 DOF)
```
(u,v)=디스플레이 픽셀(우리가 크로스헤어를 그린 곳), (X,Y,Z)=카메라 프레임의 모니터 모서리 3D.

### (a) 객관항 — PnP로 4모서리의 카메라프레임 3D (눈 무관)

모니터의 물리 모서리 좌표는 기지(예: 폭 W_mm·높이 H_mm 로 `(0,0),(W,0),(W,H),(0,H)`, 평면 Z=0).
안경 월드카메라가 이 4모서리를 **픽셀로 검출** → `solvePnP` → 카메라↔모니터 포즈 `(R, t)`.
각 모서리의 **카메라 프레임 3D**:
```
X_cam^(i) = R · X_monitor^(i) + t        (i = 1..4)
```
**순수 컴퓨터비전 — 눈이 개입 안 함.** (구현: [src/monitor_calib.py](../src/monitor_calib.py) `camera_pose_from_corners`.)

### (b) 주관항 — 사용자가 크로스헤어를 모서리에 정렬 (눈에서 본 것)

한쪽 눈(주시안)으로 OST 디스플레이를 보며, **알려진 디스플레이 픽셀** `u=(crossX, crossY)` 에 그려진
크로스헤어가 특정 모니터 모서리에 겹치도록 정렬(머리 미세이동). 정렬 확정 순간:
```
대응쌍  u=(crossX, crossY) [display px]   ↔   X_cam^(i) [그 순간 PnP로 잰 모서리 3D]
```
이 대응은 **주관적**(눈 위치에 의존) — 바로 여기에 미지의 눈 위치가 들어온다.
앱에서 크로스헤어는 캔버스-로컬 픽셀 `(crossX, crossY)` 에 정확히 서고
([NailARController.cs:374-399](../Nail/Assets/Scripts/NailARController.cs#L374) `SetCross`),
정렬 시점의 모서리 3D는 PnP가 그 프레임에서 준다.

### (c) ≥6 대응 · ≥2 거리 → DLT → 눈 위치 → (A,B)

대응 N개(≥6)를 [src/monitor_calib.py](../src/monitor_calib.py) `solve_eye_in_camera` 에 넣어 DLT+SVD로 P 추정
(Hartley 정규화 → `A p = 0` 의 최소특이벡터 → 역정규화).

**P에서 눈 위치 뽑기:** 눈-디스플레이 핀홀의 카메라중심 C(=**눈 위치**, 카메라 프레임)는 P의 영공간:
```
P·[C;1] = 0  →  P=[M|p₄] 이면  C = −M⁻¹·p₄        (눈 3D, 카메라 프레임)
```
baseline `b = (C_x, C_y)` [m] → 시차모델 계수 (자매 문서·[eye_geometry.py:116](../src/eye_geometry.py#L116) `parallax_AB` 와 **동일 출력**):
```
B = f_disp · b   (px·m),     A = M 에서 나오는 광축정렬 상수(px)
offset(d) = A + B/d          (앱 NailMeshRenderer, 런타임 pAx/pAy/pBx/pBy)
```
`f_disp` = 디스플레이 초점[px] = (Wd/2)/tan(dispHFOV/2) ([eye_geometry.py:63](../src/eye_geometry.py#L63) `f_display_px`).
(구현: [src/monitor_calib.py](../src/monitor_calib.py) `solve_eye_in_camera` → `eye_to_AB`.)

### 왜 "여러 거리"가 필수인가 — 단일 평면 축퇴 (사용자의 "거리별로" 통찰)

모든 대응 3D점이 **한 평면**에 있으면(= 모니터를 한 거리에만 두면 4모서리가 전부 그 평면 위) DLT가
**축퇴**한다. 평면상의 점들은 3D→2D 투영을 8-DOF **호모그래피**까지밖에 못 구속한다 — 나머지, 특히
**눈의 광축방향 깊이(z)** 와 전역 스케일이 자유. `P·[X,Y,0,1]` 에서 3열이 곱해지지 않아 P의 한 열이
관측에 안 잡히기 때문이다.

→ 노트북을 **2~3개 거리**에 두면 4모서리가 서로 다른 평면에 퍼져 3D 부피를 채우고, 축퇴가 깨져
눈 깊이까지 확정된다. 이것이 사용자가 말한 **"거리별로"** 의 정확한 이유다. 같은 원칙이
[monitor_calib.py](../src/monitor_calib.py)("여러 깊이에 퍼진 3D 대응점")과 손끝 SPAAM
("손 거리를 자세마다 바꿔 기하로 깊이 모호성 해소", [연구문서](AR_REGISTRATION_RESEARCH.md) §2.3)에도 있다.

---

## 3. 오늘 문제와의 연결 — "손톱이 덜 벌어짐"(스케일)

이 보정은 **눈↔디스플레이 투영 전체 P**(스케일+오프셋)를 푼다. 여기가 핵심이다.

| 방식 | 자유도 | 무엇을 맞추나 | 다중손톱 |
|---|---|---|---|
| **전역 A+B/d 오프셋만** | 2D 평행이동 1개 | 주어진 깊이에서 **모든 손톱을 같은 벡터로 이동** | **~1개(중앙) 손톱만** 맞음 |
| **전체 투영 P** (모니터 보정) | 스케일 + 오프셋 + 깊이시차 | **각 손톱의 3D를 각자의 디스플레이 픽셀로** | **모든 손톱 동시** |

**왜 전역 오프셋으론 "덜 벌어짐"이 남나:** 손가락을 펴 손톱이 시야에 퍼지면, 각 손톱이 필요로 하는
보정량이 **위치마다 다르다**(시차 + 카메라FOV↔디스플레이FOV 스케일 차이). 전역 평행이동은 이 **스케일**을
못 건드려서, 중앙 손톱을 맞추면 바깥 손톱이 안쪽으로 몰린다 = **"손톱이 덜 벌어짐"**.

전체 P는 `calibScale`(카메라↔디스플레이 FOV 비율, [NailARController.cs:174](../Nail/Assets/Scripts/NailARController.cs#L174)
`calibScale`) + `calibOffset`/A + 깊이시차 B/d 로 **분해**되어, 각 손톱을 제 위치로 보낸다.
즉 모니터 보정은 **(A,B)뿐 아니라 스케일까지** 산출 → 오늘의 다중손톱 정합오류를 정면으로 푼다.
(단일점 A+B/d만 주는 자매 웹캠 시스템 대비, 모니터 보정의 추가 가치가 바로 이 스케일.)

---

## 4. 무재빌드 구현 (이 노트북 한 대로 전 루프)

앱은 이미 **런타임 보정**을 지원한다 → **Unity 재빌드 불필요**:

- **Calib 크로스헤어가 런타임 이동 가능:** `crossX/crossY` 를 `nail_calib.json` 으로 push하면 앱이
  **0.7초 폴링**([NailARController.cs:158](../Nail/Assets/Scripts/NailARController.cs#L158) `WaitForSeconds(0.7f)`)으로
  반영, 크로스헤어를 그 캔버스-로컬 좌표에 세운다([NailARController.cs:229-236](../Nail/Assets/Scripts/NailARController.cs#L229)).
  `NailMode.Calib` 는 시스루 + 크로스헤어 하나만 표시([NailARController.cs:324-328](../Nail/Assets/Scripts/NailARController.cs#L324)).
- **결과 적용도 런타임:** `offsetX/offsetY/scale`([NailARController.cs:173-175](../Nail/Assets/Scripts/NailARController.cs#L173))
  과 mesh 시차 `pAx/pAy/pBx/pBy`, `meshParallaxOn`([NailARController.cs:221-225](../Nail/Assets/Scripts/NailARController.cs#L221))
  전부 push로 반영.
- **모니터 검출도 이 노트북:** 안경 카메라가 노트북 화면의 4모서리를 본다 → 노트북이 곧 기준물.

### 절차 (계획 런타임 [web/monitor_calib_run.py](../web/monitor_calib_run.py))

1. **모니터 패턴 표시** — 노트북 전체화면에 4모서리 마커(고대비, 물리 폭·높이 mm 입력). 화면이 기준물.
2. **PnP** — 안경 카메라 프레임에서 4모서리 픽셀 검출 → `camera_pose_from_corners` → `(R,t)` →
   4모서리의 **카메라프레임 3D** `X_cam^(i)`.
3. **Calib 모드 진입** — 안경을 `NailMode.Calib` 로(크로스헤어만, 시스루). `web/push_calib.py` 로 push.
4. **정렬·기록 (4모서리 × 각 거리):** 각 모서리에 대해
   `push_calib.py crossOn=1 crossX=.. crossY=..` → 사용자가 주시안으로 크로스헤어를 그 모서리에 정렬 →
   조작자가 기록: `(crossX, crossY) ↔ 그 순간 PnP의 X_cam^(i)`.
5. **거리 반복** — 노트북을 2~3개 거리(예: 40 / 55 / 70cm)로 옮겨 2~4를 반복(**단일평면 축퇴 해소**, §2c).
   → 총 대응 ≥6(실전 12~24).
6. **풀기** — 수집 대응 → [src/monitor_calib.py](../src/monitor_calib.py) `solve_eye_in_camera` → 눈 3D →
   `eye_to_AB` → `(A,B)` + `calibScale`/`calibOffset`. 재투영 RMS(`residual_px`)로 품질 확인.
7. **결과 push** — `push_calib.py meshParallaxOn=1 pAx=.. pAy=.. pBx=.. pBy=.. scale=.. offsetX=.. offsetY=..`
   → 앱이 다음 폴링에 적용. **Unity 빌드 0회.**

> 주의: 현재 [web/push_calib.py](../web/push_calib.py) 의 `BASE` 사전에는 `pAx/pAy/pBx/pBy/meshParallaxOn`
> 키가 아직 없다(C# 쪽은 지원). `monitor_calib_run.py` 가 이 키들을 직접 써서 `nail_calib.json` 을 쓰거나
> `push_calib.py` 의 `BASE` 를 확장해야 한다 — 사소한 추가.

---

## 5. 정직한 한계

| 한계 | 내용 |
|---|---|
| **VAC 흐림이 정밀도 상한 (하드웨어 벽)** | 크로스헤어는 X3 **4m 고정 초점면**에 그려지고, 모니터는 ~50cm. 눈이 모니터 모서리에 초점을 맞추면 크로스헤어가 **흐려진다**. VAC = \|1/0.5 − 0.25\| ≈ **1.75D @50cm**(편안 ±0.3D의 ~6배; 30cm면 ~3D, [연구문서](AR_REGISTRATION_RESEARCH.md) §1.2). 정렬 불확실 ≈ 동공(4mm)×1.75D ≈ **0.007rad ≈ 0.4°** 흐림디스크 → 완벽한 솔버라도 사람이 흐린 십자를 선명한 모서리에 맞추는 정밀도가 상한. **소프트웨어로 못 넘음**(가변초점 광학 필요). |
| **여전히 수동·세션성** | 사람이 물리 정렬해야 함. 안경이 얼굴에서 크게 미끄러지면 눈-안경 관계가 변해 재보정 필요(눈 성분). **기기/광학 상수는 사람 무관·1회**로 남지만(§6), 그 상수 추출 세션 자체는 수동. |
| **단일평면 축퇴** | 한 거리만 쓰면 눈 깊이 미구속(§2c) → **≥2 거리 필수**. |
| **모서리 검출은 조명 의존** | 저조도·화면 반사·글레어·저대비면 PnP가 흔들려 X_cam 이 부정확. 안정 검출엔 적정 조명·대비 필요. |

**요약:** 위치(x/y)·스케일 정합은 자동화·정밀화 가능. **흐림/복시(VAC)는 불변** — 자매 문서와 동일한 하드웨어 상한.

---

## 6. 통합 "노트북 보정 스테이션"

노트북 한 대가 **두 역할**을 동시에 한다:

- **기지치수 기준물** = 노트북 **화면**(모니터 보정: 수동, 고정밀, 기기상수 1회).
- **아이트래커** = 노트북 **웹캠**(웹캠 보정: 자동, 사람별 눈추적, [자매 문서](EXTERNAL_CAM_REGISTRATION.md)).

**분업:** 모니터 보정이 **사람 무관 기기/광학 상수**(camera↔display 스케일·`f_disp`·A·`gcam` 오프셋·축부호 —
[자매 문서](EXTERNAL_CAM_REGISTRATION.md) §4가 지금은 `--hfov`·`--gcam-dy/dz`·`--disp-hfov`·`--sign`·`--ax/ay`
**기본값으로 추정만** 하던 값들)를 **정밀 1회 측정**해 못박는다. 그러면 웹캠 자동추적은 이 상수를 상수로 두고
**사람별 눈 위치만** 자동으로 재서 `B = f_disp·b` 를 프레임마다 채운다.

```
┌──────────────────────── 노트북 보정 스테이션 (한 대) ────────────────────────┐
│                                                                              │
│  [노트북 화면] ── 4모서리 패턴(기지 mm) ──▶ [안경 카메라] ──PnP──▶ 모서리 3D(cam) │
│       │  (수동·고정밀·1회)                                          │           │
│       │                                        [Calib 크로스헤어] ◀─┘ 사용자 정렬 │
│       │                                                (crossX/crossY push)     │
│       ▼                                                                         │
│  monitor_calib.py:  SPAAM DLT(다거리) → 눈 3D → 【기기/광학 상수】               │
│       │              calibScale · f_disp · A · gcam오프셋 · 축부호               │
│       ▼   (1회 확정, 사람 무관)                                                  │
│  ┌───────────────────────── 상수를 eye_geometry 설정에 주입 ─────────────────┐  │
│  │                                                                          │  │
│  │  [노트북 웹캠] ──홍채 3D──▶ eye_reg.py(자동·사람별) ── b ──▶ B = f_disp·b   │  │
│  │       (매 사람·매 프레임)         EXTERNAL_CAM_REGISTRATION.md              │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                      ▼                                           │
│                      nail_calib.json {meshParallaxOn, pAx..pBy, scale, offset}   │
│                                      │  adb push (0.7s 폴링)                     │
│                                      ▼                                           │
│                        [NailMesh 앱]  offset(d)=A+B/d  (재빌드 0)                │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **모니터 보정(이 문서):** 수동·고정밀·**1회** → 기기상수 확정.
- **웹캠 보정([자매 문서](EXTERNAL_CAM_REGISTRATION.md)):** 자동·사람별 → 그 상수 위에서 눈만 추적.
- 두 산출물 모두 결국 **동일한 `(A,B)` + 스케일**([eye_geometry.py](../src/eye_geometry.py))로 앱에 push.

---

## 7. ④ 라이브 루프 + Unity 패치 스펙 (per-nail 투영)

지금까지의 push(0.7s 폴링, [NailARController.cs:158](../Nail/Assets/Scripts/NailARController.cs#L158))는
**전역 A+B/d 하나**를 보낸다 → 머리 정지 시 충분하나, **모든 손톱을 동시에** 각자 위치로 맞추려면
**per-nail 투영**이 필요하다(§3). 그러려면 서버가 손톱마다 P를 적용해 보정좌표를 실어 보내고, 앱이 그걸 쓴다.
자매 문서 [§6](EXTERNAL_CAM_REGISTRATION.md) 의 라이브 패치를 그대로 확장한다.

**서버측 ([web/edge_serve.py](../web/edge_serve.py), 이 노트북서 가능):** `/infer` 응답
([edge_serve.py:125](../web/edge_serve.py#L125) `{"ok","w","h","ms","nails":[...]}`, 각 nail은
[edge_serve.py:102-111](../web/edge_serve.py#L102) `cx,cy,...,distM,...`)에 per-nail 보정을 동봉.
모니터 보정이 준 P를 각 손톱의 3D(`cx,cy` + `distM` 역투영)에 적용:

```jsonc
// (A) 전역 reg 블록 — 자매 문서 §6 형태(모든 손톱 공통 A,B)
"reg": {"Ax":.., "Ay":.., "Bx":.., "By":.., "scale":..}
// (B) per-nail 보정 — 손톱마다 P로 계산한 최종 디스플레이 오프셋(스케일까지 흡수)
"nails":[ {"cx":.., "cy":.., "distM":.., "ox":.., "oy":..}, ... ]   // ox,oy = 이 손톱의 보정 오프셋(px)
```

**앱측 (C#, `EdgeClient`/`NailMeshRenderer`) — 최소 변경 (자매 문서 §6 재사용):**
```csharp
// EdgeClient: 응답 파싱에 reg / per-nail 필드 추가
if (resp.reg != null) {                              // (A) 전역
    meshR.parallaxEnable = true;
    meshR.parallaxA = new Vector2(resp.reg.Ax, resp.reg.Ay);
    meshR.parallaxB = new Vector2(resp.reg.Bx, resp.reg.By);   // 프레임마다 갱신 = 라이브
    meshR.calibScale = resp.reg.scale;                          // ★ 스케일까지 실어 다중손톱 정합
}
// (B) per-nail: NailMeshRenderer.SetResults 가 각 nail.ox/oy 를 그 손톱 오프셋으로 직접 사용
//     → 전역 calibOffset+A+B/d 대신 손톱별 값 → 모든 손톱 동시 정합
```
- `NailMeshRenderer.OffsetFor(distM)=parallaxA+parallaxB/distM` 는 그대로 활용(이미 존재, 자매 문서 §6).
- **왜 per-nail이 결정타:** 전역 A+B/d는 한 점(≈1개 손톱)만 정합(§3). P를 손톱마다 적용해야 **스케일**이
  반영돼 **모든 손톱이 동시에** 제자리로 벌어진다. 모니터 보정이 P(스케일 포함)를 주는 이유가 이것.
- **빌드:** 이 노트북엔 Unity 없음 → C# 변경은 Unity **2022.3.36f1** 있는 데스크톱에서
  `CIBuild.BuildMesh`(IL2CPP/ARM64)로 빌드(자매 문서 §6과 동일 경로).

---

## 8. 파일 / 상태

| 파일 | 역할 | 상태 |
|---|---|---|
| [src/monitor_calib.py](../src/monitor_calib.py) | 수학 코어: `camera_pose_from_corners`(4모서리 PnP) · `solve_eye_in_camera`(다거리 SPAAM DLT) · `eye_to_AB`(눈→A,B) | ✅ 완료·테스트 12/12 |
| [web/monitor_calib_run.py](../web/monitor_calib_run.py) | 런타임 루프: 패턴 표시 → PnP → 크로스헤어 push → 정렬 기록 → solve → A,B push | ✅ 완료·구조검증 |
| [tests/tests_monitor_calib.py](../tests/tests_monitor_calib.py) | monitor_calib 합성 라운드트립 테스트 | ✅ 12/12 |
| [src/eye_geometry.py](../src/eye_geometry.py) | 시차 `offset(d)=A+B/d`·`parallax_AB`·`f_display_px`(모니터 보정과 **동일 출력**) | ✅ 완료·테스트 9/9 |
| [web/push_calib.py](../web/push_calib.py) | `nail_calib.json` adb push(크로스헤어·A/B·scale) | ✅ 존재(pAx..pBy 키 추가 필요, §4 주의) |
| [Nail/Assets/Scripts/NailARController.cs](../Nail/Assets/Scripts/NailARController.cs) | Calib 크로스헤어 런타임(crossX/crossY, 0.7s 폴링) + pAx..pBy/scale 적용 → **무재빌드 지원** | ✅ 존재 |
| [docs/EXTERNAL_CAM_REGISTRATION.md](EXTERNAL_CAM_REGISTRATION.md) | 자매 시스템(웹캠 자동 눈추적) | ✅ |
| [docs/AR_REGISTRATION_RESEARCH.md](AR_REGISTRATION_RESEARCH.md) | 물리 한계·SPAAM 수학 근거 | ✅ |
| edge_serve `/infer` reg/per-nail 동봉 | 라이브 루프 서버측(§7) | ⏳ |
| Unity `NailMeshRenderer`/`EdgeClient` reg 수신 | 라이브 루프 앱측(§7) | ⏳ 데스크톱 빌드(2022.3.36f1) |
| [docs/MONITOR_CALIBRATION.md](MONITOR_CALIBRATION.md) | 본 문서 | ✅ |
