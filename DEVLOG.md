# A3 워핑 엔진 — 개발일지 (DEVLOG)

각 결정·시도·검증·롤백을 시간순으로 기록. 설계 SoT=`DESIGN_WARP.md`, 로드맵=`PATENT_IMPLEMENTATION.md`.
범례: 🟢 채택/통과 · 🟡 부분/보류 · 🔴 실패→롤백 · 🔀 분기결정

---

## 2026-06-24 · A3 자율개발 착수 (분기점)
사용자 지시: 이 시점을 분기로 잡고 자율 진행, 각 결정/롤백 기록 후 최종 보고.
환경 제약(정직): 이 PC에서 **Python(cv2/numpy)·node 실행 가능, 브라우저/폰/실GPU 불가**. → PC 엔진·공유수학(py↔js 패리티)·합성 렌더는 실제 검증, 웹 GPU 실동작은 "기기 검증 대기"로 명시.

전략: DESIGN_WARP.md의 빌드 순서대로 A3-1(인프라+plane, 곡면0 현동작 재현) → A3-1.5 tilt(랜드마크) → A3-2 곡률 → A3-3 복잡디자인 → A3-4 전사. P0 게이트 준수.

### [A3-1] WarpSpec 공유 수학 (착수)
🔀 **결정: 코드 공유 대신 데이터(WarpSpec) 공유 + py/js 순수함수 미러 + 골든 패리티.**
근거: cv2↔canvas API 비대칭으로 트랜스파일은 깨짐. 순수 스칼라 수학만 미러하면 비트 동기 가능.

🔀 **결정: tilt를 평면내 축 Rodrigues 회전 + 약투영(k=f/(f+z))으로 통합.** plane은 tilt·curv 강제 0이라 k=1 → 회전된 직사각형(현 동작과 기하 동일). tier 하나(plane/tilt/mesh/mesh_shaded)로 4코너~격자 모두 표현.

🟢 **검증: WarpSpec py↔js 패리티 — 16케이스 596정점 최대오차 0.00e+00 (atol 1e-4).** `spec/warp_spec.{py,mjs}` 비트 동일. 한쪽 수정 시 다른 쪽 강제 실패하는 안전망 확보. (현 design_overlay.py↔yolo.js 수학 분기 문제의 구조적 해결.)
- 파일: `spec/warp_spec.py`, `web/warp_spec.mjs`, `spec/test_parity.py`, `spec/_parity_node.mjs`.

### [A3-1] 표면추정·IR·렌더러·통합
🔀 **P0-1 강제: `surface.params_from_mask`는 tilt_deg=0 고정.** tilt는 `params_from_landmarks`(z_tip-z_dip)에서만. 곡률 prior는 마스크 경로도 허용(표준모델). One-Euro 시간필터(`ParamSmoother`)로 tilt/curv 평활.
🔀 **좌표 규약 동결 + T-0 별 래퍼 flip_v.** atlas v=0=뿌리(행0), v=1=팁. 레거시는 이미지 top=팁이라 T-0 래스터는 `flip_v=True`로 적재(별 상하대칭이라 무관, 비대칭 디자인 팁방향 보존).
🔀 **렌더 분기: plane/tilt=warpPerspective(4코너, 레거시 정합) / mesh=삼각형 래스터→cv2.remap 1회.** ROI 한정 최적화 보존. mesh_shaded는 반원기둥 법선 음영(0199) RGB 곱.
🔀 **그라데이션 PC는 atlas bake(웹은 analytic 예약).** 밴딩은 atlas supersample+INTER_AREA로 완화. 완전 analytic은 웹 WebGL 단계에서.
🟢 **게이트1 — 별 회귀 PSNR(레거시 vs 신규 plane):** 3개 손톱 위치/각도에서 **47.3~49.7 dB (>45 통과).** 무한대 아닌 건 신규가 별을 512 atlas로 1회 리샘플 후 워핑하기 때문(설계상 허용).
🟢 **게이트2 — 파이프라인 드롭인:** `design_overlay.apply` → `DesignEngine.render`로 교체. 스모크 4/4 통과(import·빈프레임·기하 정상).
- 신설: `src/surface.py`, `src/design_ir.py`, `src/design_render.py`, `spec/test_regression_star.py`. 수정: `config.DesignConfig`(fit_mode/warp_tier/mesh_grid/feather_uv, curve=curv_half_angle), `src/pipeline.py`(드롭인).
- **A3-1 완료.** 곡면 0인데 새 데이터모델(IR/WarpSpec/Surface)이 현 동작 100% 재현하며 섬.

### [A3-1.5 tilt + A3-2 곡률]
🔴→🟢 **롤백/교정: 약투영 부호.** 초기 `k=f/(f+z)`는 tip이 카메라로 올수록 *축소*되는 역방향이었음. → `k=f/(f-z)`(z>0=카메라쪽=확대)로 교정. tilt 회전축도 월드 좌표 `(-uy,ux)`→**로컬 s축 `(1,0)`**으로 수정(tip/root가 깊이로 기울어 foreshorten).
🔀 **코너 순서 격자 행우선(TL,TR,BL,BR) 통일.** plane/tilt 1×1도 mesh와 같은 reshape(2,2) 정상 격자가 되게(렌더 정합 불변, 패리티·회귀 재통과). 디버그 와이어프레임 나비넥타이 → 정상 사각형.
🟢 **T1 tilt(랜드마크):** 마스크 경로 비대칭=0.000(P0-1 준수), 랜드마크 z주입 시 tip폭 192.9 > root폭 160.2(비대칭 0.186) = 원근 사다리꼴.
🟢 **C1 curve0==plane = 94.0 dB**(곡률0이 평면으로 자동 수렴). **C2 곡률 압축** 가장자리/능선 s간격 비 0.60(반원기둥). **C3 가장자리 누출 0.00%**(클립 정상).
🟢 **시각화 `samples/a3_warp_demo.png`:** plane(평면)·tilt(사다리꼴)·mesh(곡률격자에 별이 휨) 3분할. 사용자 요구("정면 중앙 / 돌아가면 사선·곡면") 충족 확인.
- 수정: `spec/warp_spec.{py,mjs}`(k, 코너), `src/surface.py`(tilt축), `src/design_render.py`(src 코너). 신설: `spec/test_warp_tilt_curve.py`. **A3-1.5+A3-2 완료.**

### [A3-3 복잡 디자인]
🔀 **fit_mode를 uv 인셋으로 구현(stretch/contain/cover).** 정사각 UV 디자인을 손톱 비율로 늘리지 않게 — contain은 디자인 비율 보존하며 박스 안에 맞춤(여백=remap BORDER 투명). plane은 src 코너 인셋, mesh는 uv 변환. _raster_tri 클립 제거(uv∉[0,1]=투명).
🔀 **UV공간 페더(feather_uv): atlas 알파를 UV에서 1회 blur** → 곡률 무관 균일 경계(B-2 처방).
🔴→🟢 **버그: 벡터 레이어 polylines가 슬라이스 뷰(비연속)에서 OpenCV 에러** → 연속 BGR/알파 캔버스에 그린 뒤 복사로 수정.
🟢 **복잡 IR(그라데이션 베이스 + 프렌치 벡터 + 꽃 래스터 3레이어) bake → atlas 100% 채움.** plane·mesh(곡률) 둘 다 누출 0px. 곡면에서 프렌치 라인·꽃·그라데이션이 **한 디자인으로 통째 휨**.
🟢 **fit_mode: 길쭉 손톱(비율0.42)에서 stretch 커버=0.43(손톱대로 늘어남) vs contain=1.00(정사각 디자인 비율 보존).** 원형 모티프 안 찌그러짐.
🟢 **per-nail 클립: 옆 손톱 침범 0px**(PC는 손톱별 mask 인자라 union 누출 G-2 구조적 비해당).
🟢 **시각화 `samples/a3_complex_demo.png`(+`a3_atlas.png`).** 별 PNG가 아닌 풀네일 디자인이 일반적으로 곡면 워핑됨 — 사용자 핵심 요구("복잡한 디자인에도 가능") 충족.
- 수정: `src/design_render.py`(fit/uv페더), `src/design_ir.py`(벡터 연속배열). 신설: `spec/test_complex_design.py`. **A3-3 완료.**

### [A3-4 전사 (청구항 30/32/33)]
🔀 **전사 = 같은 엔진 재사용.** 손톱1 화면 → 언워프(uv→screen surface를 atlas 해상도로 보간 후 `cv2.remap` 역샘플) → 정규 UV 아틀라스 캡처 → 손톱2 surface로 워핑. 좌우는 `cv2.flip`(u→1-u). anchors는 정규화 TPS(λ)로 미세보정(외삽 폭주 F-1 방지).
🔴→🟢 **검증 프로브 버그(엔진 아님):** 비대칭을 알파로 측정했으나 알파=전체 손톱(대칭) → 0.50. + 손톱 외곽 고주파가 대칭으로 희석. → saliency(원본-블러) + 알파 침식(내부만)으로 교정.
🟢 **라운드트립 PSNR 26.1dB**(언워프→리워프 충실), 꽃 무게중심 u=0.42(좌측 보존), **손톱2 전사 커버 33,717px**, **미러 u 0.42→0.58**(좌우 반전).
🟢 **시각화 `samples/a3_transfer_demo.png`:** 손톱1 디자인이 형상·각도 다른 손톱2에 자연 이식 + 캡처된 UV 아틀라스.
- 신설: `src/transfer.py`, `spec/test_transfer.py`. **A3-4 완료. PC 엔진 A3 전구간(청구항 8·10·11·19·30·32·33) 검증 완료.**

### [웹 측 + P0-2 GPU 정책]
🔀 **렌더 수학은 공유(warp_spec.mjs 패리티), 렌더러는 분기:** plane=canvas2D affine 폴백, tilt/mesh=WebGL2 텍스처드 메시(`warp_gl.js`). atlas mipmap+CLAMP(밴딩/모아레 B-1), premultiplied over.
🔀 **P0-2 정책 구현:** ORT가 WebGPU 점유 → 렌더는 **별도 WebGL2 컨텍스트**. WebGL2 미지원/`webglcontextlost` → **canvas2D plane 자동 강등**(곡면 포기, 동작 유지) + restore 재초기화. `?engine=1[&curve=]` **옵트인** — 기존 yolo.html 레거시 경로는 불변(회귀 0).
🟡 **검증 한계(정직):** 이 환경엔 브라우저/실GPU 없음 → WebGL 런타임·모바일 컨텍스트 공존은 **실기기 검증 대기**. 대신 (a) 공유수학 패리티 0.0, (b) node 로직 13/13(인덱스·params·tier·곡률압축), (c) 전 JS `node --check` 통과로 비-GL 부분 검증.
- 신설: `web/warp_gl.js`, `web/design_render.js`, `web/test_web_logic.mjs`. 수정: `web/yolo.js`(옵트인 분기, 레거시 불변).

### [현장 디버그 + 랜드마크 경로에 엔진 연결]
🔴 **증상: 폰 yolo.html에서 nails 0(best 0.00).** → 진단: ultralytics .pt ≡ onnx CPU 둘 다 동일(오버레이 이미지엔 0). **모델·변환 멀쩡, YOLO가 맨손톱/밝은 배경을 못 봄**(이 모델은 또렷한 손톱 전용). yolo_nail_detect.png에선 0.89~0.92로 정상 검출 확인.
🔀 **해결: 검출은 랜드마크 경로(`/` app.js, MediaPipe)가 맨손톱에 강인.** 사용자 환경에서 fps 14.9·nails 5 확인. + 디버그용 yolo.js에 `best 점수` HUD·`?conf=` 추가.
🟢 **A3 엔진을 랜드마크 경로에 연결** — app.js가 손가락 **z**로 tilt 산출(마스크 경로는 불가했던 진짜 기울기!) + 곡률 기본 0.55. 마스크 없는 경로라 엔진에 null-mask(흰 1×1) 지원 추가. WebGL2 실패 시 canvas2D(평면) 자동 폴백. `?flat`(옛 평면)·`?curve=`·`?notilt` 옵션.
- 수정: `web/app.js`(엔진 연결·z tilt), `web/design_render.js`(null mask), `web/yolo.js`(디버그 HUD). node 문법·로직 검증. **실기기 렌더는 사용자 확인 중.**

## ✅ 최종 상태 (2026-06-24)
PC 엔진 + 공유수학 **완성·검증**(테스트 5스위트 전부 PASS, 시각화 4종). 웹 엔진 **구현·로직검증**(실기기 GL 대기). 회귀 0(별 PSNR 47dB, 스모크 4/4).
- 테스트: `spec/test_parity.py`(0.0) · `test_regression_star.py`(47.3dB) · `test_warp_tilt_curve.py` · `test_complex_design.py` · `test_transfer.py` · `web/test_web_logic.mjs`(13/13).
- 시각화: `samples/a3_warp_demo.png`(plane/tilt/mesh) · `a3_complex_demo.png`(복잡디자인 평면/곡면) · `a3_atlas.png` · `a3_transfer_demo.png`.
- 상세 보고: `FINAL_REPORT.md`.
