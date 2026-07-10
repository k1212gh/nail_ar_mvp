# 복잡 디자인 곡면·기울기 워핑 — 설계서 (DESIGN_WARP)

> **이 파일이 워핑 엔진의 단일 진실원천(SoT).** 상위 로드맵 `PATENT_IMPLEMENTATION.md`의 Phase A3가 이 문서를 가리킨다.
> 작성: 2026-06-24, 다관점 워크플로(설계 4안 → 종합 → 적대적 비판) 산출. 비판의 교정은 본문에 이미 반영됨.

## 0. 목표 한 줄
별 PNG 한 장이 아니라 **임의의 복잡한 네일 디자인**(그라데이션/패턴/꽃/프렌치/글자/3D 장식물)이, 손톱이 정면이면 중앙에 자연스럽게, 손가락이 돌아가면 원근으로 기울고 곡면 따라 휘어 보이게 — PC(OpenCV)와 웹(canvas/WebGL/WebGPU) 양쪽에서. 특허 청구항 8/10/11/19/30/33/36 실시.

## 1. 종합 결정 (4안 합류)
- **표현(C 채택):** 디자인 = "정규 손톱 UV에 정의된 **레이어드 IR**". 별 PNG는 1장짜리 IR로 흡수.
- **표면(A 채택):** 손톱 = **반원기둥 표준모델 + 2 스칼라(곡률반각·tilt) 피팅** 메시. 굽힘·foreshortening·법선음영을 자연 흡수.
- **공유(D 채택):** 코드가 아니라 **WarpSpec(정점 그리드 데이터)**를 PC·웹이 공유 + **골든테스트로 비트 동기**. 현 design_overlay.py↔yolo.js 수학 분기 문제의 구조적 해결.
- **렌더(B 절제):** CPU(remap/canvas)가 1급. WebGL/WebGPU 셰이더는 곡률·고해상이 필요한 상위 티어에서만 켜는 옵션.

## 2. 자료모델
### 2.1 정규 손톱 UV 템플릿 (모든 좌표의 교환공간)
```
u ∈ [0,1] 가로: u=0 좌측, u=0.5 능선(곡률 최고), u=1 우측  → axis_minor에 정렬
v ∈ [0,1] 세로: v=0 뿌리(큐티클), v=1 팁                  → axis_major(현 ey<0=tip)에 정렬
```
`uv_template = square|round|almond|stiletto` 프리셋. 디자인은 실손톱 모양을 모른 채 이 정사각 UV에만 그린다. = 특허 0203 "표준 손톱 형상모델" prior.

### 2.2 Design IR (design.json — 빌드타임 산출, 런타임은 IR + bake atlas만 소비)
```jsonc
{ "schema":"nail-design/1", "uv_template":"almond", "aspect_hint":0.72,
  "fit_mode":"stretch",            // ★ T-0(별) 기본 stretch=현동작; 신규디자인은 contain/cover
  "layers":[                       // z순서, role이 렌더경로 결정 (특허 0367)
    {"id":"base","role":"color_region","type":"raster","src":"base.png","uv":[0,0,1,1]},
    {"id":"grad","role":"color_region","type":"gradient","stops":[["#ff5ea2",0],["#ffd36b",1]],"axis":"v"},
    {"id":"fr","role":"french_boundary","type":"vector","path":"M0,.3 Q.5,.18 1,.3","width_uv":0.04},
    {"id":"txt","role":"text","type":"text","text":"LOVE","uv":[0.5,0.55],"keep_upright":true},
    {"id":"gem","role":"decoration_3d","type":"placement","uv":[0.5,0.85],"asset":"gem_round","size_mm":2.0}],
  "anchors":[{"id":"a0","uv":[0.5,0.95]},{"id":"a1","uv":[0.08,0.30]},{"id":"a2","uv":[0.92,0.30]}] }
```
role(특허 0367 직상속): `color_region`(채움/그라데이션/패턴/래스터) · `line/french_boundary/outline`(벡터) · `text` · `decoration_3d`(부착점+법선).
**별 흡수:** `image_path="star.png"` → `{layers:[{role:color_region,type:raster,src:star.png,uv:[0,0,1,1]}],fit_mode:"stretch"}`로 자동 래핑 → 현 동작 100% 보존.

### 2.3 NailSurface (표면 메시) / SurfaceParams (두 신호원 합류점)
```python
@dataclass
class NailSurface:           # 정규 UV 격자 위 표면 메시 (특허 0193)
    nx:int; ny:int
    uv:        np.ndarray    # (ny+1,nx+1,2) 정규 텍스처좌표 (src)
    screen_xy: np.ndarray    # (ny+1,nx+1,2) 프레임 픽셀좌표 (dst) ← 워핑 결과
    normal:    np.ndarray    # (ny+1,nx+1,3) 정점 법선 (0195, 음영)
    shade:     np.ndarray    # (ny+1,nx+1)   법선·관찰각 음영 (0199)
    params:    "SurfaceParams"
```
```jsonc
// SurfaceParams — 마스크/랜드마크/스테레오가 전부 같은 다운스트림으로 합류
{ "center_px":[cx,cy],"axis_major":[ux,uy],"axis_minor":[vx,vy],"length":L,"width":W,
  "tilt_axis":[tx,ty],"tilt_deg":0.0,        // ★ mono 마스크에선 항상 0 (§4.2 P0-1)
  "curv_half_angle":0.6,                       // config.curve 연결
  "curv_model":"standard","confidence":0.7,"view_dir":[0,0,-1] }
```

### 2.4 WarpSpec (PC/웹 공통 데이터 계약 — JSON 직렬화)
```jsonc
{ "tier":"mesh",            // plane|tilt|mesh|mesh_shaded
  "grid":[ny,nx],           // plane/tilt=[1,1](4점), mesh=[10,8]
  "uv":[[u,v],...], "screen":[[x,y],...],   // 정점 src/dst
  "shade":[s,...], "feather_uv":0.04, "alpha":1.0 }
```

## 3. 워핑 엔진 — 수학은 데이터로 공유
**순수함수 `build_warp_spec(params, tier, grid)`를 py/js에 미러**(라이브러리 호출 0, 입출력 plain number) → **골든 픽스처로 비트 동기**. consumer(렌더러)는 verts만 소비하므로 곡률식이 바뀌어도 consumer 불변.
```
spec/warp_spec.py  ─┐ 동일 수식 미러
spec/warp_spec.mjs ─┘  spec/fixtures/*.json(입력) → spec/golden/*.json(기대 WarpSpec)
                       test_parity.{py,mjs} 가 atol=1e-4 통과해야 머지
```
- **PC consumer** `src/design_render.py`: mesh=정점 barycentric으로 dense map 채워 `cv2.remap` 1회(셀 수 무관, ROI 픽셀 비례 — 현 design_overlay.py L58-63 ROI 보존). plane/tilt=4점 `warpPerspective`.
- **웹 consumer** `web/design_render.js`: 저티어=canvas `setTransform`(4점만; **canvas mesh 금지** ←삼각형 seam), 고티어=WebGL/WebGPU `drawElements`(곡률·고해상).
- ★ **골든은 2단:** verts(1e-4) + **렌더 출력 PSNR**(consumer 리샘플 차이 회귀 검출).

## 4. 곡률·기울기 — 핵심 교정(비판 반영)
### 4.1 반원기둥 곡률 모델 (curv_half_angle, config.curve 연결)
```
phi    = (u-0.5)*2*curv_half_angle
s_loc  = sin(phi)/sin(curv_half_angle)*(W/2)         # 가로 압축
z_curv = (cos(phi)-cos(curv_half_angle))*(W/2)       # 능선 융기
k      = persp_f/(persp_f+z)                          # 약투영 → foreshortening 자동
screen = center + axis_major*(t_loc*k) + axis_minor*(s_loc*k)
```
`curv_half_angle=0` → 평면(현 동작 자동 수렴).

### 4.2 ★ P0-1 — mono 마스크는 tilt를 추정하지 않는다 (원리적 한계)
- 단일 프레임 실루엣에서 **aspect(폭/길이) 변화 = 실제 tilt = 짧고 뚱뚱한 손톱 = 부분가림(엄지 측면)** 이 수학적으로 구분 불가. 앞/뒤 tilt 부호는 약투영 z↔-z 대칭이라 **원리적으로 못 푼다.**
- 별은 회전대칭이라 가짜 tilt가 안 보였지만, **방향성 디자인(프렌치/글자)은 매 프레임 가짜 tilt로 흔들린다.**
- **결론:** `yolo.html`(마스크) 경로 = **plane + 곡률 prior까지만**, `tilt_deg=0` 고정. tilt는 **`app.js` 랜드마크 z차(TIP·DIP·PIP)가 있을 때만** 활성. curvature는 표준모델 prior라 마스크에서도 OK.
- aspect_ref는 고정상수 금지 → **정면일 때 관측 aspect를 사용자/손가락별 EMA 온라인 캘리브레이션.**

### 4.3 시간 안정화 (G-3, A1/A2와 연계)
SurfaceParams(curv_half_angle, tilt_deg, center, 축)에 **One-Euro/EMA 필터 + confidence 게이팅** 필수. 추정 노이즈가 방향성 디자인을 떨리게 하므로 plane 단계부터 깐다.

## 5. 복잡디자인 처리 (별→풀네일) — 교정 반영
| 요소(0367) | 표현 | 처리 | 교정 |
|---|---|---|---|
| 그라데이션 | `type:gradient` | **analytic 유지(bake 금지)**, 셰이더 보간 | B-1 밴딩 원천 차단 |
| 패턴/꽃/래스터 | UV atlas bake | mesh 텍스처매핑 | **mipmap 필수**(모아레), atlas 최대변 1024 |
| 프렌치/윤곽 | vector | **장식용은 atlas에 함께 supersample bake**(C-1 seam 방지); 작업가이드선만 별도 polyline | |
| 글자 | text | mesh 국소평균 아핀 + 가독성 클램프 | **A3-3 stretch goal**(C-2) |
| 3D 장식물 | 부착점+asset | 법선음영+접지그림자 데칼 | 진짜 billboard는 **stretch goal**(C-3) |
| 반투명 | opacity+blend | alpha 프리멀티 z순 over | |
- **비율 보존:** UV 정사각 + fit_mode(stretch=별 기본 / contain·cover=신규) → 원형 꽃 안 찌그러짐(현 L68 강제늘림 해결).
- **페더:** 화면공간 아니라 **UV공간 폭**(SDF) → 곡률 무관 균일(B-2). 저티어 canvas에도 최소 마스크 blur(G-1).
- **per-nail 클립**(union 금지) → 인접 손톱 누출 방지(G-2).

## 6. 대상간 전사 (청구항 30/32/33)
UV가 공통 교환공간 → 손톱1 UV ↔ 손톱2 UV는 **항등**, anchors TPS는 **미세보정만**(regularization λ + UV경계 클램프로 외삽 폭주 방지, F-1). 캡처는 atlas로 굽지 말고 **surface1 파라미터와 함께 저장**해 1회 비선형 유지. 좌우 손톱 = `u→1-u` 미러. **A3-4(곡면 안정 후).**

## 7. 폴백 사다리 + fps
| Tier | 변환 | 단서 | 렌더러 | 발동 |
|---|---|---|---|---|
| T0 plane | affine 4점 | 현 보유 | PC warpPerspective / 웹 canvas | fps<8·GPU없음 |
| T1 tilt | perspective 4점 | tilt_deg(랜드마크) | 동일 4점 | fps≥8 |
| T2 mesh | N×M 곡률 | curv_half_angle | PC remap / 웹 GPU | fps≥15 |
| T3 mesh_shaded | mesh+음영 | 법선·관찰각 | PC remap+shade / 웹 frag | fps≥20 |
히스테리시스(fpsEma): <8 강등(5프레임 잠금), >18 손가락 정지 시 승급. **웹 ROI 타일 렌더**(풀프레임 designCv 폐기, D-3).

## 8. ★ P0 게이트 (곡면 코드 쓰기 전 결판)
1. **P0-1** mono 마스크 tilt 추정 안 함(§4.2). tilt=랜드마크 전용. 시간필터+confidence 동반.
2. **P0-2 웹 GPU 컨텍스트 정책:** `yolo.js:4` `ort.webgpu.bundle`이 WebGPU 점유 → "추론 WebGPU + 렌더 WebGL" 동시 점유는 모바일 컨텍스트 lost·GPU↔CPU 왕복. **(a) WebGPU로 렌더 통일 또는 (b) wasm추론+WebGL** 택1을 **실기기 스파이크로 검증** + 컨텍스트 lost 핸들러 + plane 폴백. 셰이더 `highp` + 정규화 좌표(D-2).
3. **P0-3 텍스처 파이프라인 기본값:** 그라데이션 analytic(bake 제외), atlas mipmap 강제, **T-0 별 래퍼 fit_mode=stretch**(현 출력 PSNR>45dB 회귀 가드, E-2).

## 9. 특허 청구항 매핑
| 청구항 | 요건 | 설계요소 |
|---|---|---|
| 8 | 확대/축소/회전/이동/굽힘/비선형 | build_warp_spec tier(굽힘=§4.1 z_curv) |
| 9 | 아핀/투시/호모그래피/비선형 | WarpSpec.tier |
| 10 | 평면/곡면/패치/메시 표면추정 | NailSurface, Planar↔HalfCylinder |
| 11 | 깊이/곡률/법선/관찰방향 보정 | SurfaceParams + normal/shade + 약투영 |
| 19 | 중심선/격자/프렌치/장식/붓경로/윤곽 | role 디스패치, geometry.py grid/french/attach 재사용 |
| 30/32/33 | 전사(이동·대칭·비선형/대응점/표면좌표) | UV 교환공간 + anchors TPS + u→1-u |
| 36 | 방법항(표면추정+곡률/법선 변형) | §4 파이프라인 |
| 0135 | 알고리즘 비한정 | surface_from_*/build_warp_spec/렌더러 교체 |

## 10. 빌드 계획 (비판 교정판 — A3-1을 "인프라+plane"으로 재정의)
- **A3-1 인프라+plane 정합 (곡면 0, 현 동작 100% 재현):**
  WarpSpec 계약 + `build_warp_spec` py/mjs 미러 + 골든테스트(plane만) + Design IR 스키마 + T-0 별 래퍼(fit_mode=stretch) + SurfaceParams 합류 + **One-Euro 시간필터 + confidence** + **웹 GPU 정책 P0-2 실기기 스파이크**.
  검증: star.png가 IR 경유로 현 출력 PSNR>45dB; py==js 골든 atol 1e-4; 컨텍스트 공존 초록불.
- **A3-1.5 tilt (랜드마크 전용):** `surface_from_landmarks`(z차→tilt_deg), tilt tier 4점. 마스크 경로엔 미적용.
- **A3-2 곡률+법선음영:** 선행=웹 마스크 디코드(yolo.js L127-132) 경감. HalfCylinderModel→mesh tier, PC remap/웹 GPU, shade, config.curve 연결. 검증: 곡률0=plane 수렴, 가장자리 누출<1%, 폰 mesh≥8fps.
- **A3-3 복잡디자인 수용:** SVG/layered→IR + bake_uv_atlas(그라데이션 제외) + role 디스패처 + fit_mode + UV-SDF 페더 + 웹 업로드 UI. 글자/보석=stretch.
- **A3-4 전사:** 캡처→언워프→IR 어댑터 + anchors TPS(λ) + u→1-u 미러.

## 11. 기존 코드 — 유지 / 리팩터 / 신설
- **유지:** geometry.py PCA·`_resolve_center`(OBB 투영 L88-92, SurfaceParams 좌표) · grid/french(bow)/attach(곡면 골격); design_overlay.py ROI(L58-63); yolo.js 추론·NMS·마스크디코드 골격(단 L127-132 경감); config 대부분.
- **리팩터:** design_overlay.py `apply()`(L34-88)→`render_design`+role 디스패처(시그니처 호환 드롭인); yolo.js `renderClippedStars`(L145-169)→`renderDesign`; `star.png` 하드코딩(L7/31-34)→IR 로드; `destination-in` 풀프레임(L160-167)→per-nail ROI + (고티어)셰이더 클립; config `DesignConfig.curve`(L65)→`curv_half_angle` 승격.
- **신설:** `spec/warp_spec.{py,mjs}`·`spec/surface.{py,mjs}`·`spec/fixtures|golden`·`spec/test_parity.{py,mjs}`; `src/surface.py`(NailSurface/HalfCylinder/Planar); `src/design_ir.py`·`web/design_ir.js`(IR/T-0래퍼/bake_uv_atlas); `src/design_render.py`·`web/design_render.js`; `web/warp_gl.js`(또는 WebGPU 통일).

## 12. 알려진 하드 리밋 (PoC에서 인정)
- mono 마스크: tilt(특히 앞/뒤 부호) 못 함 → plane+곡률까지.
- 글자·진짜 3D 보석: A3-3 stretch goal(국소아핀/데칼로 근사, 완전 3D 아님).
- 전사: TPS 외삽 불안정 → UV 항등 + 미세보정으로 한정.

## 13. 변경 로그
- 2026-06-24: 워크플로(설계4안→종합→적대비판)로 최초 작성. P0 3종·A3-1 재정의(인프라+plane) 확정.
