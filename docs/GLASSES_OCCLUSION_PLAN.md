# 안경 화면에 펜 가림 넣기 — 통합 계획 (빌드 전 설계)

> "펜이 여전히 가리는데?"에 대한 정확한 답 + 안경 실화면 적용 경로. 2026-07-31.
> **결론 먼저**: 가림은 **매직미러 모드에서만** 의미 있다. OST(광학투과) 모드엔 물리적으로 불가.

## 왜 OST(NailGuide)엔 가림을 못 넣나 (중요)

[[nailar-nearfield-ost-impossible]] / docs/DEEP_RESEARCH_NEARFIELD_OST 에서 확증:
- X3는 **4m 고정 초점면**에 디자인을 띄운다. 실제 손톱(30cm)과 **시차(parallax)로 3~9mm 어긋남.**
- 즉 카메라가 만든 펜 가림 마스크를 화면에 그려도, **눈으로 보는 실제 펜 위치와 안 맞아** 엉뚱한 데가 뚫린다.
- → **OST(진짜 시스루)에서 픽셀 정합 가림은 원천 불가.** 디자인 자체가 안 맞는데 가림만 맞출 순 없다.

## 그래서 가림이 되는 곳 = 매직미러 (카메라영상 위에 합성해서 화면으로)

카메라 좌표 = 디자인 좌표 = 가림 좌표가 **모두 한 화면(스크린 공간)** 이라 정확히 일치. 두 갈래:

### 경로 1 — PC/폰이 합성 (이미 구현됨, 재빌드 0) ✅
- `web/magic_mirror.py`가 카메라 프레임에 디자인+펜가림을 합성. **지금 작동**(before/after 영상 `_demo/`).
- 안경 앱 **NailMirror**가 이 합성뷰를 화면에 띄우거나, 원격 모니터가 이걸 송출하면 **가림이 그대로 보임.**
- **가장 빠른 실현**: 원격 모니터(사장님)를 magic_mirror 합성뷰로 → 재빌드 없이 가림 완성. (edge_serve `NAIL_OCC_DEMO=1`이 이미 이 경로 — magic_mirror 사용하도록 연결함.)

### 경로 2 — 안경 NailMirror 앱이 자체 합성 (재빌드 1회, 온디바이스)
안경이 스스로 카메라+디자인+가림을 그린다. 데이터/코드 경로:

**a) edge_serve가 가림 마스크를 검출응답에 동봉** (PC측, 검증 가능)
```
/infer 응답 nails[] 에 per-nail 추가:  "occ": "<base64 low-res soft mask, e.g. 24x24>"
또는 전역:  "occMask": {"w":80,"h":50,"data":"<base64 grayscale>"}
```
- pen_occlusion.pen_soft_mask() 결과를 80×50 등으로 축소 → grayscale JPEG/base64. 소켓 부담 작음(수 KB).
- `web/edge_serve.py` /infer 직렬화부 + `EdgeClient.cs` 파서에 필드 추가.

**b) 안경 셰이더가 스크린공간 가림 마스크 샘플** (Unity측, **빌드 검증 필요**)
`Nail/Assets/Resources/NailBakedGloss.shader` frag 수정(초안):
```hlsl
// Properties에 추가:  _OccTex ("Occlusion", 2D) = "black" {}
// vert: o.scrPos = ComputeScreenPos(o.pos);   (v2f에 float4 scrPos 추가)
// frag 마지막:
//   half occ = tex2D(_OccTex, i.scrPos.xy / i.scrPos.w).r;  // 카메라=스크린 공간
//   c.a *= (1.0 - occ * 0.85);                                // 펜 지나는 곳 디자인 투명
```
- `NailMeshRenderer.cs`가 매 프레임 occMask를 Texture2D로 업로드해 material `_OccTex`에 세팅.
- **전제**: NailMirror(매직미러)라 디자인이 손톱의 스크린 위치에 그려짐 → 카메라공간 마스크와 일치.
  OST(NailGuide)에선 위 §때문에 적용해도 안 맞음 → **NailMirror 전용.**

## 권장 실행 순서

1. **[재빌드 0, 지금] 원격 모니터를 magic_mirror 합성뷰로** → 사장님 화면에 펜 가림 즉시. (edge_serve 연결 완료)
2. **[재빌드 1회] 안경 NailMirror 온디바이스 가림**: 경로 2(a)+(b). edge_serve/EdgeClient 파서는 내가 미리
   짜둘 수 있음(검증가능). 셰이더/렌더러는 Unity 빌드 1회 필요(형 도움).
3. **[불가] OST NailGuide 가림** — 물리한계. 시도 말 것. OST는 "대략 위치" 가이드용으로만.

## 지금 내가 미리 할 수 있는 것 (빌드 없이 검증)
- [x] **edge_serve /infer에 occMask 동봉** — `NAIL_OCC_MASK=1`이면 `res["occMask"]={w,h,jpg(base64)}`.
  검증: vf_076 → 96×128 마스크 **base64 676B**, 디코드 max=79, JSON 총 1993B. (비용: pen_soft_mask 추가연산 → fps↓, 기본 off.)
- [x] **EdgeClient.cs 파서** — `[Serializable] OccMask{w,h,jpg}` + `InferResult.occMask`. JsonUtility 호환·하위호환(컴파일은 Unity서 확인).
- [x] magic_mirror 합성뷰(경로1) — 완료.
- **남은 것(형 Unity, ~30분)**: NailBakedGloss.shader에 `_OccTex` 샘플(위 초안) + NailMeshRenderer가
  `occMask.jpg → Texture2D.LoadImage → material._OccTex` 업로드. **NailMirror 씬에서만**(OST 아님).
