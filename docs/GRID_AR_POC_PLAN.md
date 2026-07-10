# 손톱 격자 AR PoC — 작업 계획 (사장님 신규 MVP)

작성: 2026-07-03. 요구: **시스루 AR**로 손톱마다 **정중앙 기준 모눈(격자)** 표시, 멀티 손톱.
근거 조사: 병렬 리서치 3건(손톱 중심 검출 / 단안 OST 근거 / 격자 안정화) + 로컬 실측 2건.
한계 전제: `docs/LIMITATIONS_FOR_DEEP_RESEARCH.md`.

---

## 0. 핵심 설계 결정 (근거 요약)

### 결정 1 — **단안(한쪽 눈) 렌더**가 시스루 격자의 정공법
- Condino et al., IEEE TBME 2020: 손 뻗는 거리 OST 가이드 작업에서 **단안 vs 양안: 정확도·피로·워크로드 차이 없음**. VAC는 양안에서만 발생 → 단안은 복시·수렴충돌을 구조적으로 제거.
- 벤더 전원이 우리 작업거리 금지: HoloLens "40cm 미만 렌더 금지", Magic Leap 2 "0.37m 미만 흐림·복시·구역질", XREAL ~2m+. **25–40cm 양안 콘텐츠는 업계 표준 위반** — 단안이 유일한 합법 경로.
- 남는 건 조절 흐림(4m 초점 vs 30cm 손, ~3D defocus): **굵고 성긴 중간대비 선**으로 완화(Bayle 2021), 우세안에 표시(Laramee 2002), 정적 배경 권장.
- 기대 정합: 단안 SPAAM ~20점 정렬로 **x/y 2–4mm** (Azimi 2017; Condino 최대 5.9mm). 서브-mm는 광학 추가(Pisa 확대경) 없인 불가 — PoC 지표를 여기에 맞춘다.

### 결정 2 — 격자는 **"≈1mm" 메트릭 격자** (핀홀 공식)
- `cell_px = f_px × 0.001 / distM` (f_px = 0.86×640). distM은 MediaPipe world-landmark 크로스핸드 스팬.
- 단안 거리추정 오차 문헌치 ~5% (ARKit 350–400mm 스윗스팟 3.8%) → **1회 개인 보정**(신용카드 85.6mm 또는 실측 손톱폭)으로 바이어스 제거, 라벨은 "≈1mm".
- distM은 위치보다 훨씬 강하게 스무딩(1€ mincutoff 0.1 또는 >5% 변화시만 갱신) → 격자가 "숨쉬지" 않게.

### 결정 3 — 안정화는 **1€ 필터 + 80ms 상한 예측** (검증된 레시피)
- 손톱별 중심(px)+손가락 각도에 1€ 필터: `mincutoff 0.5–1.0, beta 0.007, dcutoff 1.0` (Casiez 튜닝 절차). MediaPipe 프로덕션 패턴 채용: 검출 손실 시 200–300ms 홀드 후 페이드+필터 리셋, 각도 2–3° 히스테리시스.
- 파이프라인 age(프레임 타임스탬프→표시)를 실측해 등속 외삽으로 보상하되 **80ms 상한**(Azuma: 그 이상 예측은 오차 폭증). 100ms+는 예측이 아니라 파이프라인 단축으로.
- 세계앵커 vs head-locked: 30cm 손 대상은 **검출-락(매 프레임 검출 따라감)이 SLAM 앵커보다 안정**(Scargill 2021).

### 결정 4 — 검출: **Phase 1은 현행 MediaPipe 중심, Phase 2에 세그 정밀화**
- 실측(오늘, RTX 4070 SUPER): 사전학습 YOLOv8s-seg 손톱 가중치(HF mnemic) = **7.0ms/frame**이지만 우리 640×400 글래스 프레임에서 **5개 중 0–1개만 검출** — 매니큐어 클로즈업 학습의 도메인 갭. 그대로는 못 씀.
- 경로: ① 지금 있는 MediaPipe 랜드마크 중심(이미 동작, 유저 확인 "검출 자체는 잘 됨")으로 격자 PoC 완성 → ② SAM 자동라벨(TIP 랜드마크를 포인트 프롬프트로) + Roboflow 3.6k(CC BY 4.0)로 우리 도메인 파인튠 → 마스크 무게중심 = 진짜 손톱판 중앙 (ModiFace 29.8ms/94.5 mIoU, 네일로봇 0.3mm이 이 레시피의 상한 증명). GPU 예산 7ms라 여유.

---

## 1. 단계별 계획

### P0. 스테레오 경로 규명 (반나절, **최우선 관문**)
미해결 의문 A4: Unity 헤드카메라 stereoEnabled=false → 런타임이 center-eye를 좌우로 복제하는 정황(z=2~4m에서도 좌우 시차 0 실측).
- [ ] depthM 스윕(0.3/1/2/4/100) × 프레임버퍼 캡처 → 좌/우 절반 내 패널 x위치 픽셀 측정: **시차가 변하는가?**
- [ ] Screen-space 오버레이 캔버스로 **왼쪽 절반(0–640px)에만** 격자를 그려 형이 확인: **한쪽 눈에만 보이는가?** (프레임버퍼 좌우분할 발견을 역이용한 단안 렌더 후보 1)
- [ ] 안 되면: per-eye 카메라(targetEye), unity_StereoEyeIndex 셰이더 분기, RayNeo API 순서로 시도.
- 판정: 단안 주입 가능 → P2 진행 / 전부 복제 → 단안은 물리 가림(한쪽 렌즈 캡)으로 데모하고 RayNeo에 문의.

### P1. 격자 렌더러 (반나절, P0와 병렬 가능)
- [ ] `NailGridRenderer.cs` 신규 + **모드 5 'ARGrid'** 추가(기존 모드 시스템에): 손톱별 십자선+N×N 모눈, 축=손가락 방향(ex,ey), 스케일=결정 2 공식.
- [ ] 격자 텍스처는 런타임 생성(중앙 십자 굵게, 모눈 얇게, 중간대비 시안색) — Bayle 권고 반영.
- [ ] 1€ 필터 이식(중심/각도/distM 별도 파라미터) — 서버 응답은 현행 그대로(cx,cy,ex,ey,len,wid,distM 이미 있음).
- [ ] calib 노브: `gridCells, cellMm, gridAlpha, gridRotDeg` (재빌드 없이 튜닝).
- 완료 기준: 미러 모드에서 격자가 손톱 5개에 안정적으로 붙음(지터 육안 무감지) — 미러에서 먼저 검증 후 AR로.

### P2. 단안 시스루 + SPAAM 정렬 (반나절)
- [ ] P0 확정 경로로 격자를 우세안에만 렌더(형 우세안 hole-in-card 테스트 30초).
- [ ] SPAAM 정렬 UX: 화면 크로스헤어에 실물 마커(펜 끝)를 ~20자세로 맞추고 탭 → 대응쌍 수집 → `src/spaam.py`(구현·자체검증 완료) DLT로 P행렬 → 오버레이 매핑에 적용.
- 완료 기준: 30cm 정지 손에서 격자 중심오차 ≤ 4mm (Azimi 수준).

### P3. 손톱판 중심 정밀화 (1일, 병렬 가능)
- [ ] SAM 자동라벨 파이프라인: 글래스로 녹화한 우리 프레임 수백 장 + TIP 프롬프트 → 마스크 → 검수.
- [ ] YOLOv8n-seg 파인튠(우리 라벨 + Roboflow 3.6k 혼합) → ONNX/TensorRT.
- [ ] 서버에 nail-seg 경로 추가(랜드마크 크롭→세그→무게중심), MediaPipe 중심과 A/B(엄지 개선 확인).

### P4. 평가·데모 (반나절)
- [ ] 지표 실측: 중심오차 mm(정지 손, 자로 검증) / 지터 px RMS / E2E 지연 ms / 락온 시간 s.
- [ ] 특허 PoC 데모 영상: 미러 모드(선명) + 단안 시스루 모드(진짜 AR) 2벌.

## 2. 리스크와 대비
| 리스크 | 대비 |
|---|---|
| P0에서 눈별 주입 전부 불가(완전 모노 복제) | 물리 가림 단안 데모 + RayNeo 문의; 매직미러는 항상 fallback |
| 4m 초점 흐림으로 격자 판독 불가 | 셀 크기↑(2–3mm), 선 굵게, 십자만 표시 모드 |
| distM 오차로 mm 스케일 신뢰 부족 | 개인 보정 + "≈1mm" 라벨 + 지표에 오차 명시 |
| WiFi adb/MCP 불안정 | 작업 전 재연결 체크리스트(무선디버깅 토글, MCP /mcp 재연결); USB 드라이버 fix는 관리자 1회 |

## 3. 레퍼런스 (조사 전문)
- 단안/VAC/벤더/SPAAM/근거리 레티클: Condino TBME 2020 · Bayle PLoS One 2021 · Laramee TOCHI 2002 · Kramida TVCG 2016 · Hoffman JoV 2008 · MS Comfort · ML2 Comfort · XREAL · Tuceryan Presence 2002 · Azimi arXiv:1703.05834 · Ferrari TVCG 2022(확대경 서브mm)
- 안정화/격자: Casiez 1€ CHI 2012 · MediaPipe LandmarksSmoothing · Azuma 1995(80ms) · Gül MM2020(엣지 예측) · Scargill 2021(앵커 드리프트) · ARKit 거리오차 Sensors 2023(~5%) · Amprimo 2024(world landmark 스케일 약함) · ARShoe MM2021(포즈 스무딩)
- 손톱 검출: ModiFace CVPRW2019(29.8ms) · NailNet bioRxiv 2024(IoU .953) · NAILS Sensors 2024 · Roboflow nails_segmentation 3.6k CC-BY · HF mnemic/nails_seg_yolov8(**우리 프레임 실측: 도메인 갭, 파인튠 필수**) · Grounded-SAM-2(오프라인 라벨용) · 네일로봇 US9959462(0.3mm 레시피)
