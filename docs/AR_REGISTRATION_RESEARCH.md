# 손톱 AR 정합(registration) 연구 — 논문·코드 조사 및 결론

작성: 자율 세션 2026-07-03. 대상 기기: **RayNeo X3 (Pro)** — 양안 광학 시스루(OST) 웨이브가이드, 가상영상 초점면 **~4m 고정**, 월드 방향 RGB 카메라 1개, **아이트래킹 없음**. 목표: 검출된 손톱 위에 디자인을 AR로 얹기.

---

## 0. 결론 먼저 (TL;DR)

1. **RayNeo X3에서 "코앞 손(20~30cm) 실제 손톱에 픽셀을 정합하는 진짜 시스루 AR"은 소프트웨어로 불가능하다.** 기기의 **4m 고정 초점면**이 물리적 벽. 두 가지가 동시에, 각각 치명적:
   - **시차 정합오차** ‖E‖ ≈ O′·|p_z/d_focal − 1|. 30cm/4m → 계수 0.93. 아이트래킹이 없어 눈 위치 불확실 O′≈3~10mm → 오차 **3~9mm가 떠다님**(손톱 폭 ≈10mm의 절반 이상). SPAAM도 "못 보는 눈"은 추적 못 함.
   - **폭주-초점 충돌(VAC)** ≈ **3디옵터** @30cm (편안 한계 ±0.3D의 ~10배) → 흐림 + 복시. 소프트웨어로 해결 불가(가변초점 광학 필요).
2. **네일 트라이온 상용 제품(YouCam Nails, ModiFace/L'Oréal, Snap)은 전부 "매직미러" 방식** — 카메라 영상에 2D 오버레이를 그려 **화면으로** 본다. **아무도 시스루 눈-정합을 안 한다.** 우리가 벽에 부딪힌 이유가 이것.
3. **X3에서 실현 가능한 최선 = 매직미러 모드**: 카메라로 손을 잡아 디자인을 합성한 화면을 **편안한 중간거리 패널(~2~4m, X3의 강점)** 로 보여준다. 선명·단일·안정. 정합/시차/VAC 문제를 회피하면서 "내 손톱에 이 디자인 어때?"의 가치는 그대로.
4. **진짜 시스루 정합이 꼭 필요하면** → (a) 폰/태블릿 비디오 시스루 앱(업계 표준), 또는 (b) **작업거리에 맞는 짧은 초점(~30cm) OST-HMD**. 4m 초점의 X3는 원거리 콘텐츠(플로팅 스크린/내비)용이다.

---

## 1. 왜 근거리 시스루 AR이 X3에서 안 되는가 (물리)

### 1.1 시차(parallax) 정합오차 — Cutolo et al. 2020

- **Cutolo, Cattari, Fontana, Ferrari — "Optical See-Through HMDs With Short Focal Distance: Conditions for Mitigating Parallax-Related Registration Error", Frontiers in Robotics and AI 7:572001 (2020).**
  https://www.frontiersin.org/articles/10.3389/frobt.2020.572001/full · https://pmc.ncbi.nlm.nih.gov/articles/PMC7806030/
- **Ferrari, Cattari, Condino, Cutolo — "Optical Rules to Mitigate the Parallax-Related Registration Error…", MTI 8(1):4 (2024).** https://www.mdpi.com/2414-4088/8/1/4

핵심 식 (눈이 보정 위치에서 벗어났을 때의 측면 정합오차):

```
‖E‖ ≈ O′ · | p_z / d_focal − 1 |
```
- **O′** = 눈 동공이 보정 위치에서 벗어난 반경(mm) = 아이트래킹 없을 때의 눈위치 불확실도.
- **d_focal** = 디스플레이 초점(콜리메이션) 거리. X3 = **~4m = 400cm** (고정, 소프트웨어로 변경 불가).
- **p_z** = 얹으려는 실제 물체 깊이.

성질: **물체가 초점면에 있으면 오차 0**, 초점면에서 멀수록 O′에 비례해 선형 증가.

**우리 케이스 정량** (d_focal=400cm, p_z=30cm → 계수 |30/400−1| = 0.925):

| 눈위치 불확실 O′ | 30cm에서 정합오차 | 각크기 | 손톱(≈11mm) 대비 |
|---|---|---|---|
| 3mm (낙관) | 2.8mm | 0.5° | 25% |
| 5mm (현실, 무 아이트래킹) | **4.6mm** | 0.9° | **42%** |
| 10mm (안경 재착용/미끄러짐) | 9.2mm | 1.8° | 84% |

→ 5mm 불확실만으로 오차 **~4.6mm**, 게다가 안경이 흔들릴 때마다 **떠다닌다.** 손톱 폭이 10mm인데 오차가 그 절반. 참고로 짧은초점(33cm) 디스플레이면 같은 5mm가 0.45mm(계수 0.09)로 **10배 유리** — 순전히 초점거리 차이.

### 1.2 폭주-초점 충돌(VAC)

초점(조절)은 디스플레이가 4m(0.25D)로 고정. 폭주(vergence)는 실제 손 거리가 결정:

| 손 거리 | 폭주 요구 | VAC = |폭주−0.25D| | 판정 |
|---|---|---|---|
| 20cm | 5.0D | **4.75D** | 심각 |
| 30cm | 3.33D | **3.08D** | 심각 |
| 100cm | 1.0D | 0.75D | 여전히 불편 |

편안영역 ≈ ±0.3~0.5D, 눈 초점심도 ≈ 0.3D (Shibata 2011). **30cm에서 ~3D = 편안 한계의 6~10배.** 4m 초점에서 VAC를 0.3D 밑으로 낮추려면 물체가 **~1.8m보다 멀어야** 함. 30cm는 불가능 → 눈이 손과 오버레이를 동시에 초점 못 맞춤(하나 보면 다른 게 흐림) + 스테레오가 융합범위(Panum) 밖으로 나가 **복시**. 망막-광학 영역이라 **렌더링으로 해결 불가.**

참고: Wang 2021 VAC 리뷰 https://www.sciencedirect.com/science/article/pii/S2666950121001061 · Shibata 2011 https://pmc.ncbi.nlm.nih.gov/articles/PMC3369815/

### 1.3 확인된 하드웨어 사실
RayNeo X3/X3 Pro = 양안 웨이브가이드, **~4m 고정 가상영상**(원거리 플로팅 스크린용). 근거리 수작업(peripersonal) 정합의 정반대 설계.
https://www.rayneo.com/blogs/news/optical-waveguide · https://www.rayneo.com/blogs/news/prescription-smart-glasses-2026-vision-guide

---

## 2. 그럼에도 시스루 정합을 한다면 — 캘리브레이션(SPAAM 계열)

x/y(측면)만은 SPAAM으로 잡을 수 있다(깊이 z와 VAC 흐림은 못 잡음). X3에 쓸 수 있는 건 **아이트래킹 불필요한 수동 SPAAM 계열**뿐(INDICA-full/CIC 등 아이트래킹 자동법은 전부 불가).

### 2.1 공통 수학 — DLT로 3×4 투영행렬 P 풀기
눈+디스플레이를 핀홀 카메라로 보고, 3D 월드점 → 2D 디스플레이 픽셀 매핑 P(11 DOF)를 추정.
```
s·[u,v,1]ᵀ = P·[X,Y,Z,1]ᵀ
```
대응쌍 i마다 2식:
```
행A: [ 0, 0, 0, 0,  −X,−Y,−Z,−1,   vX, vY, vZ, v ]
행B: [ X, Y, Z, 1,   0, 0, 0, 0,  −uX,−uY,−uZ,−u ]
```
N개 쌓아 (2N×12) A → **A p = 0**. Hartley 정규화(2D 중심0·평균거리√2, 3D 중심0·평균거리√3) 후 **SVD의 최소특이값 우특이벡터** = p → reshape(3×4) → 역정규화. **최소 6쌍**(실전 15~25). 필요시 RQ분해로 K,[R|t].

### 2.2 방법별 요약
- **SPAAM** (Tuceryan/Genc/Navab, Presence 2002): 크로스헤어 1픽셀 ↔ 고정 3D점을 머리 움직여 정렬, ≥6쌍, DLT. 아이트래커 불필요. 사용자 부담 큼. https://direct.mit.edu/pvar/article/11/3/259/18409/
- **Stereo SPAAM** (Genc/Sauer, ISAR 2000): 양안 동시 3D 타겟 정렬 → 깊이 일관성↑. 양안 X3에 적합. IPD 제약 추가 가능. https://ieeexplore.ieee.org/document/880940/
- **Easy SPAAM / SPAAM2** (ISMAR 2002): 하드웨어 내재파라미터는 고정, **눈 위치만** 변함 → 오프라인 1회 풀 SPAAM + 온라인 **2~4쌍**으로 눈이동(Δx,Δy,Δz) 갱신. https://www.researchgate.net/publication/3981798
- **DRC** (Owen, ISMAR 2004): 디스플레이 모델(지그로 오프라인) + 눈 모델(온라인, 0~수쌍) 분리. https://ieeexplore.ieee.org/document/1383044/
- **D-SPAAM** (Moser/Swan): 재착용 강건성 평가 — SPAAM과 유의차 없음(작은 흔들림엔 강건).
- **★ Bare-hand rotation-constrained** (Hu, Cutolo, Rodriguez y Baena 2021, arXiv 2108.10603): 재착용 시 눈은 ~2cm 이동하나 가상영상이 멀어 **회전은 거의 안 변함 → translation-only 3-DOF** 갱신. **단 1회 정렬로 ~10 arcmin**, 손끝법보다 우수. **우리 세팅에 가장 근접.** https://arxiv.org/abs/2108.10603

### 2.3 손끝 기반 사용자 캘리브 (아이트래커 없을 때 우리 방식)
- Moser & Swan, "user-centric OST-HMD calibration using Leap Motion", 3DUI 2016. https://ieeexplore.ieee.org/document/7460047/ — 손끝/스타일러스를 3D 참조점으로 SPAAM 대응 수집. **스타일러스가 맨손끝보다 정확**(맨손끝 노이즈 큼).
- 절차: 한쪽 눈만 크로스헤어 표시(다른 눈 블랙) → 사용자가 **손끝**을 크로스헤어에 맞춤 → 확정 시 (픽셀[u,v] ↔ MediaPipe 3D[X,Y,Z]) 1쌍. 화면 여러 위치 + **여러 깊이**로 6쌍 이상.
- 노이즈 대응: **2D 방향(bearing)은 신뢰, 깊이는 불신**(카메라 1개) → 손 거리를 자세마다 바꿔 기하로 깊이 모호성 해소; RANSAC; 프레임 다중평균; DLT 후 **LM 비선형 정련**.

### 2.4 기대 정확도
좋은 SPAAM으로 **x/y ~0.2~0.5°**, **깊이 z는 약축**(눈점 오차 ~5cm, "물체가 더 가깝게 보임" 편향). = X3에선 x/y는 개선돼도 §1의 시차 떠다님 + VAC 흐림은 남는다.

---

## 3. 업계는 어떻게 하나 — 전부 "매직미러"

- **ModiFace/L'Oréal, "Nail Polish Try-On", CVPRW 2019** (arXiv 1906.02222, https://ar5iv.labs.arxiv.org/html/1906.02222): 듀얼 MobileNetV2로 손톱 세그+방향장 회귀. **렌더 레시피(우리가 훔칠 것)**: ① 손톱 **DIP→TIP 축**에 정렬한 쿼드, ② 그라디언트로 가짜 하이라이트, ③ **손톱 마스크를 끝쪽으로 늘려 생손톱(밝은 자유연) 가림**, ④ 색 블렌드. iOS CoreML + 브라우저 TF.js, **온디바이스 미러**, 33fps.
- **YouCam Nails(Perfect Corp)** / **ModiFace**(5cm~0.5m, 온디바이스) / **Snap Lens "Nails Try-On"**(온디바이스 3D 핸드+세그) — **전부 카메라영상 위 2D 오버레이를 화면으로.** 시스루 눈-정합은 아무도 안 함(사용자가 화면을 보니 캘리브 불필요).

**함의:** X3에서 "진짜 시스루 정합"을 고집하는 건 업계 누구도 안 하는 어려운 길이고, 물리적으로도 X3엔 불가. **미러 방식이 정답.**

---

## 4. 우리 프로젝트 권장 구현

### 4.1 (권장) 매직미러 모드 — X3에서 실제로 작동
- 카메라 피드를 **편안한 중간거리 패널(~2~4m, 초점면)** 로 표시 → 선명·단일·안정(시차/VAC 회피).
- 그 위에 디자인을 **카메라 좌표(rot=0)로 합성** → 화면 속 손톱에 정확히 얹힘(내가 스크린샷으로 검증 가능).
- 카메라 90° 세로장착 → **피드를 −90° 회전해 똑바로** 표시(사용자 "누워있음" 해소).
- ModiFace 렌더 레시피(방향정렬 쿼드 + 끝쪽 늘림 + 하이라이트) 적용.
- 손가락 폄(PIP 각도) 필터로 **주먹일 땐 안 뜨게**(서버 구현 완료).
- 절대거리(distM)로 디자인 크기만 비례(깊이 z는 패널 고정).

### 4.2 (선택) 진짜 시스루 정합 — 한계 감수 시
Stereo-SPAAM 오프라인 1회 + Hu/Cutolo translation-only 온라인 2~4쌍. **x/y는 개선되나 흐림·복시는 하드웨어라 남음.** 도수 콘택트/인서트로 근시 보정은 별개(있어도 4m-30cm VAC는 그대로).

### 4.3 (정공법) 하드웨어 교체
폰/태블릿 비디오시스루(업계표준) 또는 짧은초점(~30cm) OST-HMD.

---

## 5. 재사용 오픈소스 코드

| 리포 | 언어 | 용도 |
|---|---|---|
| https://github.com/fatihksubasi/spaam | Python(numpy/scipy) | **가장 깔끔한 DLT/SVD SPAAM.** 우리 PC 서버에 바로 이식(대응쌍 → 3×4 P). |
| https://github.com/YutaItoh/HMD-Calibration | MATLAB(MIT) | DLT + **INDICA_Full/Recycle**(눈이동 갱신 템플릿). |
| https://github.com/krm104/AndroidSPAAM | Java/C++ | 양안 SPAAM 앱(Moverio) — 눈별 블랭킹/크로스헤어/탭기록 상호작용 패턴. |
| https://github.com/doughtmw/display-calibration-hololens | Unity C# | HoloLens 눈별 레티클 정렬 씬 + off-axis frustum — **Unity 경로면 이걸.** |
| https://github.com/keijiro/HandPoseBarracuda | Unity C#(Apache) | MediaPipe Hands 온디바이스(ONNX) — 지연 줄이려 검출을 안경으로 옮길 때. |
| https://github.com/kinivi/hand-gesture-recognition-mediapipe | Python | 손가락 폄/굽힘 상태 분류 참고. |

---

## 6. MediaPipe 손톱 쿼드 + 폄 필터 (구현 메모)

- 손톱 = **DIP↔TIP** 사이. 쿼드: `axis=normalize(TIP−DIP)`, `center≈DIP+0.6·(TIP−DIP)`, `len=|TIP−DIP|`, `wid≈0.62·len`, 옆축 `side=normalize(cross(axis, DIP−PIP))`. 카메라 향하게 빌보드 + 장축은 axis 고정.
- **폄 판정(PIP 각도, 3D, 시점무관)**: PIP에서 (PIP→MCP)와 (PIP→TIP) 각도 >150° = 폄. 엄지는 (MCP2,IP3,TIP4). **`src/hand_landmarks.py`에 구현 완료**(`extended` 필드), 서버 `NAIL_EXTENDED` 필터.
- 인덱스: thumb(2,3,4) index(5,6,7,8) middle(9,10,11,12) ring(13,14,15,16) pinky(17,18,19,20).

---

## 7. 전체 참고문헌
- Cutolo 2020 (시차) https://www.frontiersin.org/articles/10.3389/frobt.2020.572001/full
- Ferrari 2024 (광학규칙) https://www.mdpi.com/2414-4088/8/1/4
- Grubert/Itoh/Moser/Swan, OST 캘리브 서베이 (IEEE TVCG 2018) https://arxiv.org/pdf/1709.04299
- SPAAM https://direct.mit.edu/pvar/article/11/3/259/18409/ · Stereo SPAAM https://ieeexplore.ieee.org/document/880940/
- SPAAM2 https://www.researchgate.net/publication/3981798 · DRC https://ieeexplore.ieee.org/document/1383044/
- Hu/Cutolo bare-hand https://arxiv.org/abs/2108.10603 · Moser Leap 3DUI2016 https://ieeexplore.ieee.org/document/7460047/
- INDICA 평가(Moser 2015) https://pubmed.ncbi.nlm.nih.gov/26357099/ · CIC https://pubmed.ncbi.nlm.nih.gov/26357098/
- ModiFace 네일 CVPRW2019 https://arxiv.org/abs/1906.02222 · Wang VAC 2021 https://www.sciencedirect.com/science/article/pii/S2666950121001061 · Shibata 2011 https://pmc.ncbi.nlm.nih.gov/articles/PMC3369815/
- 코드: fatihksubasi/spaam, YutaItoh/HMD-Calibration, krm104/AndroidSPAAM, doughtmw/display-calibration-hololens, keijiro/HandPoseBarracuda
</content>
