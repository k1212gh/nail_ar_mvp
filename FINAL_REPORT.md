# A3 복잡 디자인 곡면·기울기 워핑 엔진 — 최종 보고서

작성: 2026-06-24 (자율 개발 세션). 설계 SoT=`DESIGN_WARP.md`, 일지=`DEVLOG.md`, 로드맵=`PATENT_IMPLEMENTATION.md`.

## 0. 목표와 결과 한 줄
**별 PNG 한 장이 아니라 임의의 복잡한 네일 디자인이, 손톱이 정면이면 중앙에·돌아가면 원근으로 기울고 곡면을 따라 휘어 입혀지는 엔진**을 만들고, 특허 청구항 8·10·11·19·30·32·33을 실시했다.
→ **PC 엔진 + PC↔웹 공유수학: 완성·검증 완료.** 웹 GPU 렌더러: 구현·로직검증 완료(실기기 GL 동작은 검증 대기). **기존 동작 회귀 0.**

## 1. 만든 것 (아키텍처)
```
디자인 = 정규 손톱 UV의 레이어드 IR ──bake──▶ UV 아틀라스(BGRA)
                                                     │
손톱(마스크/랜드마크) ─▶ SurfaceParams ─[warp_spec]─▶ WarpSpec(정점 uv→screen)
                          (P0-1: 마스크는 tilt=0)          │ (py/js 비트동일)
                                                     ├─ PC: cv2.remap / warpPerspective
                                                     └─ 웹: WebGL2 메시 / canvas2D 폴백
```
- **공유 수학(데이터 계약):** `spec/warp_spec.py` ↔ `web/warp_spec.mjs` 순수함수 미러. 곡률(반원기둥)·기울기(평면내축 Rodrigues + 약투영)·plane/tilt/mesh tier를 한 함수로.
- **표면추정:** `src/surface.py` — 마스크 경로(tilt 금지, 곡률 prior), 랜드마크 경로(z차→tilt), One-Euro 시간필터.
- **디자인 IR/bake:** `src/design_ir.py` — 별 T-0 래퍼(fit_mode=stretch), 그라데이션/벡터/래스터 멀티레이어 → 단일 아틀라스.
- **렌더러(PC):** `src/design_render.py` — role 디스패치, plane=homography·mesh=삼각형 remap, fit_mode(stretch/contain/cover), UV 페더, ROI 최적화. `pipeline.py`에 드롭인.
- **전사:** `src/transfer.py` — 언워프 캡처 → 손톱2 워핑 + 좌우 미러 + 정규화 TPS.
- **렌더러(웹):** `web/warp_gl.js`(WebGL2 텍스처드 메시·mipmap) + `web/design_render.js`(GPU 정책·폴백) + `web/yolo.js` 옵트인(`?engine=1`).

## 2. 검증 결과 (실측)
| 항목 | 게이트 | 결과 | 파일 |
|---|---|---|---|
| 공유수학 py↔js 패리티 | 오차<1e-4 | **0.00e+00** (596정점 비트동일) | `spec/test_parity.py` |
| 별 회귀(레거시 vs 신규 plane) | PSNR>45dB | **47.3~49.7 dB** | `spec/test_regression_star.py` |
| tilt: 마스크 대칭 / 랜드마크 사다리꼴 | 대칭=0, tip>root | **0.000 / 0.186(tip192.9>root160.2)** | `spec/test_warp_tilt_curve.py` |
| 곡률0 == 평면 | PSNR>40 | **94.0 dB** | 〃 |
| 곡률 압축(반원기둥) | 가장자리<능선 | **0.60** | 〃 |
| 곡면 가장자리 누출 | <1% | **0.00%** | 〃 |
| 복잡디자인(그라데이션+프렌치+꽃) | 누출·렌더 | **누출 0px, atlas 100%** | `spec/test_complex_design.py` |
| fit_mode(길쭉 손톱) | 비율보존 | **stretch 0.43(손톱) / contain 1.00(디자인)** | 〃 |
| per-nail 클립 | 옆손톱 0 | **0px** | 〃 |
| 전사 라운드트립 / 미러 | 충실·반전 | **26.1dB / u 0.42→0.58** | `spec/test_transfer.py` |
| 웹 비-GL 로직 | 전부 | **13/13** | `web/test_web_logic.mjs` |
| 파이프라인 무결성 | 스모크 | **4/4** | `tools/smoke_test.py` |

**시각화:** `samples/a3_warp_demo.png`(plane·tilt·mesh), `a3_complex_demo.png`(복잡디자인 평면·곡면), `a3_atlas.png`(베이크된 UV 아틀라스), `a3_transfer_demo.png`(손톱간 전사).

## 3. 시도·개선·롤백 로그 (핵심 분기)
1. **WarpSpec 데이터 공유 결정** — 코드 트랜스파일(cv2↔canvas 비대칭) 대신 순수함수 미러+골든. → py↔js 비트동일 달성. 현 design_overlay↔yolo.js 수학 분기 문제를 구조적으로 해결.
2. **🔴 약투영 부호 롤백** — 초기 `k=f/(f+z)`는 "tip이 카메라로 올수록 축소"되는 역방향. → `k=f/(f-z)`로 교정(가까울수록 확대). 동시에 tilt 회전축을 월드→**로컬 s축**으로 수정.
3. **코너 순서 통일** — plane/tilt 4코너를 `[TL,TR,BR,BL]`→격자 행우선 `[TL,TR,BL,BR]`로. 렌더 정합 불변(패리티·회귀 재통과), 디버그 와이어프레임 정상화.
4. **🔴 P0-1 강제(설계 비판 반영)** — mono 마스크 tilt 추정은 원리적 불가(aspect↔손톱비율↔가림 구분불가, 앞/뒤 부호 미해결) → 마스크 경로 tilt=0, tilt는 랜드마크 z 전용. 방향성 디자인(프렌치/글자) 가짜 떨림 차단.
5. **🔴 벡터 레이어 OpenCV 버그** — 슬라이스 뷰(비연속)에 polylines → 에러. 연속 배열에 그린 뒤 복사로 수정.
6. **🔴 전사 비대칭 프로브 2회 교정** — 알파(전체손톱=대칭) 측정 0.50 → saliency(고주파) → 경계 고주파 희석 → 알파 침식(내부만)으로 좌측 0.42 확정.
7. **fit_mode를 uv 인셋으로** — 정사각 디자인을 손톱비율로 늘리지 않게(원형 모티프 안 찌그러짐). remap BORDER로 여백 투명.
8. **P0-2 GPU 정책** — ORT WebGPU와 충돌 피해 별도 WebGL2 + 컨텍스트 lost→canvas2D 강등 + 옵트인(레거시 불변).

## 4. 특허 청구항 커버리지
| 청구항 | 구현 | 검증 |
|---|---|---|
| 8 (확대/축소/회전/이동/굽힘/비선형) | tier별 변환 + 곡률 z + 메시 | ✅ |
| 9 (아핀/투시/호모/비선형) | plane/tilt/mesh | ✅ |
| 10 (곡면/메시 표면추정) | 반원기둥 NailSurface | ✅(curve0==plane, 압축0.60) |
| 11 (곡률/법선/관찰방향 보정) | 약투영 foreshortening + 법선음영 | ✅(tilt 사다리꼴) |
| 19 (프렌치/장식 등 안내요소) | role=vector/decoration | ✅(복잡디자인) |
| 30/31 (전사·대칭) | 캡처→워핑 + u→1-u | ✅(전사·미러) |
| 32/33 (대응점·표면좌표) | anchors TPS(λ) / UV 교환 | ✅(구현, anchors 미세보정) |

## 5. 정직한 한계 (PoC 인정)
- **웹 GPU 실동작 미검증:** 브라우저/폰 없는 환경 → WebGL 런타임·ORT WebGPU 공존·모바일 컨텍스트 lost는 **실기기 검증 필요**. 코드·정책·폴백은 구현됨, 공유수학·로직은 검증됨.
- **mono 마스크 tilt 포기:** 원리적 한계(P0-1). 기울기는 랜드마크(app.js) 경로 전용.
- **글자·진짜 3D 보석:** 미구현(stretch goal). 현재 국소아핀/데칼 근사 경로만 설계.
- **전사 TPS:** 외삽 방지 위해 UV 항등+미세보정으로 한정(대규모 비선형 전사는 추가 작업).
- **성능:** PC mesh는 ROI 비례로 충분. 웹 mesh fps·고해상 메모리는 실기기 측정 필요.

## 6. 다음 단계 (권장 순서)
1. **웹 실기기 스파이크(P0-2 결판):** `?engine=1`로 폰에서 WebGL2+ORT 공존·fps·컨텍스트 lost 측정. 막히면 WebGPU 렌더 통일 검토.
2. **랜드마크 tilt 실연결:** app.js MediaPipe z를 `params_from_landmarks`에 주입(현재 인터페이스 준비됨).
3. **A1/A2 추적·스무딩:** 멀티 손톱 ID 매칭으로 곡률·tilt 값 안정화(엔진의 ParamSmoother와 연계).
4. **디자인 입력 UI:** 임의 디자인 업로드/생성형 → IR. atlas는 PC bake 재사용.

## 7. 파일 인덱스
- **공유수학:** `spec/warp_spec.py`, `web/warp_spec.mjs`, `spec/test_parity.py`(+`_parity_node.mjs`)
- **PC 엔진:** `src/surface.py`, `src/design_ir.py`, `src/design_render.py`, `src/transfer.py`, `config.py`(DesignConfig), `src/pipeline.py`(드롭인)
- **웹 엔진:** `web/warp_gl.js`, `web/design_render.js`, `web/yolo.js`(옵트인), `web/test_web_logic.mjs`
- **테스트:** `spec/test_*.py`(5), `web/test_web_logic.mjs`
- **문서:** `DESIGN_WARP.md`(설계), `DEVLOG.md`(일지), `PATENT_IMPLEMENTATION.md`(로드맵), 본 `FINAL_REPORT.md`
- **시각화:** `samples/a3_*.png`(4)
