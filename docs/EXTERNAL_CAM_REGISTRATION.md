# 외부캠 복합 자동정합 (External-Camera Assisted OST Registration)

작성: 2026-07-11. 목표: **아이트래킹 없는 RayNeo X3에서, 외부 카메라(노트북 웹캠/폰)로 사용자 눈을
밖에서 측정해 손톱 AR 디자인의 위치정합을 사람별·자동으로** 맞춘다. 수동 SPAAM 없이.

> **한 줄 결론:** 위치(x/y) 정합은 이 방식으로 **자동화 가능**하다(외부캠 = 외장 아이트래커).
> 단 **흐림/복시(VAC)** 는 X3의 4m 고정초점 광학이라 이 방법으로도 남는다 —
> [AR_REGISTRATION_RESEARCH.md](AR_REGISTRATION_RESEARCH.md) §1.2 참조. "정확한 위치 + 흐림" 이 상한.

> **자매 문서:** [MONITOR_CALIBRATION.md](MONITOR_CALIBRATION.md) — 노트북 **모니터**를 정밀 기준물로 쓴
> 수동·고정밀 **기기상수 1회 보정**. 이 문서의 웹캠 자동추적이 그 위에서 사람별로 돈다.

---

## 1. 왜 외부캠이 문제를 푸는가

근거리 OST 시차 정합오차: `‖E‖ ≈ O′·|p_z/d_focal − 1|` ([연구문서](AR_REGISTRATION_RESEARCH.md) §1.2).
- **미지수는 눈 위치 O′.** X3는 아이트래킹이 없어 이걸 모른다 → SPAAM으로 수동 추정(사람마다·재착용마다).
- **외부캠이 홍채를 봐서 눈 3D를 직접 측정** → O′를 관측값으로 대체 → 위치정합 자동.
- 이건 X3에서 불가하다던 자동 아이트래킹(INDICA류)을 **외장 트래커로 대체**하는 정공법.

**남는 벽(이 방식으로도 못 넘음):** 폭주-초점 충돌(VAC) ≈ 3D @30cm. 4m 고정초점 광학이라
디자인(4m 초점)과 실제 손톱(30cm)이 동시에 선명할 수 없음 → 흐림+복시. 위치를 옮겨도 광학은 안 바뀜.
가변초점/편광선택 광학(하드웨어)만이 해결. **그래서 목표는 "정확한 위치", 흐림은 감수.**

## 2. 좌표계 & 수학 (구현: [src/eye_geometry.py](../src/eye_geometry.py), 단위테스트 [tests/test_eye_geometry.py](../tests/test_eye_geometry.py) 9/9)

| 프레임 | 정의 |
|---|---|
| **W** 웹캠 | 외부 웹캠 광심 원점. 픽셀+깊이가 여기서 나옴. |
| **H** 머리 | FaceLandmarker 머리포즈로 W와 연결(회전 R). |
| **Gc** 안경카메라 | 안경 월드카메라. 안경 안착점(코받침)+기기오프셋으로 위치. |
| **D** 디스플레이 | 앱이 그리는 정규화 좌표. f_disp[px]로 각↔px. |

**단계:**
1. **눈 3D (홍채 메트릭 앵커):** 홍채 지름 실측 11.7mm → 깊이 `Z = f_w · 0.0117 / d_iris_px`,
   `X,Y = (u−cx)Z/f_w, (v−cy)Z/f_w`. → 눈 위치 `eye_W`.
2. **안경카메라 3D:** 안경 안착점(코받침 랜드마크 168)을 같은 핀홀로 역투영 → `mount_W`,
   `gcam_W = mount_W + R·(기기오프셋 gcam_d)`. (오프셋은 눈이 아닌 안경 고정점 기준이라 기기상수)
3. **baseline:** `b = Rᵀ·(eye_W − gcam_W)` 의 좌우/상하 성분[m]. **사람마다 눈 위치가 다르면 b가 달라짐 → 사람별 정합.**
4. **시차모델 계수:** `B = f_disp · b` (px·m), `A = 광축정렬 상수(px)`.
   앱은 손 깊이 d마다 `offset(d) = A + B/d` 로 디자인 위치를 보정.
   → **d가 변해도(손을 당기고 밀어도) 앱이 프레임마다 자동 정합.** (부호/축은 §4 캘리브로 확정)

> 핵심: 앱 `NailMeshRenderer` 에 이미 `offset(d)=A+B/d` 모델이 있고 런타임(pAx/pAy/pBx/pBy)으로
> 조정됨. 우리는 **외부캠으로 A,B를 측정해 채워넣기만** 하면 됨 → **Unity 재빌드 불필요(정적/준라이브).**

## 3. 아키텍처

```
[노트북 웹캠] → web/eye_reg.py ──(nail_calib.json: meshParallaxOn,pAx..pBy)──▶ [NailMesh 앱]
   (얼굴/홍채)     FaceLandmarker                adb push (~1.2Hz)              offset(d)=A+B/d
                  → eye_geometry → A,B                                          ↑ 손 깊이 d
[안경 카메라] ──USB(adb reverse)──▶ web/edge_serve.py (손톱 검출) ──▶ [NailMesh 앱] 손톱 위치+d
```
- **eye_reg.py**(신규): 웹캠→눈→A/B→push. edge_serve.py 와 **동시 구동**(둘은 독립).
- **edge_serve.py**: 안경 카메라 프레임→손톱 위치·깊이(distM). 기존 그대로.
- **NailMesh 앱**(mode=ARMesh): 곡면 디자인 + `offset(d)=A+B/d` 로 정합.

## 4. 1회 캘리브(사람 무관, 기기/광학 상수) — 물리 세션 필요

측정 자동화되는 건 **눈 위치**뿐이고, 아래 상수는 안경/앱 좌표계 정렬용으로 1회 잡는다:
1. **웹캠 화각** `--hfov` (기본 60°): 정밀시 체스보드. 깊이 절대스케일에 영향.
2. **안경카메라 오프셋** `--gcam-dy/-dz` (코받침→월드카메라, 기본 −10/+12mm): X3 실측/스펙으로.
3. **디스플레이 화각** `--disp-hfov` (기본 27°): A/B의 px 스케일.
4. **축 부호** `--sign-x/-y`, **상수항** `--ax/--ay`: 안경 화면에서 디자인이 손톱에 오도록 1회 정렬.
   절차: 손을 고정(≈30cm) → sign/ax·ay를 조금씩 바꿔 push → 디자인이 손톱에 얹히는 값 확정.

이 상수는 사람이 바뀌어도 유지된다(눈 위치만 자동 재측정). → **다음 사람은 그냥 쓰면 자동 정합.**

## 5. 업데이트 속도 — 정적 vs 라이브

- **정적/준라이브(지금, 재빌드 없음):** `nail_calib.json` 폴링 = **0.7s(≈1.4Hz).**
  머리를 크게 안 움직이면 충분(손 깊이 적응은 앱 안에서 프레임마다 자동). 머리 급속 이동엔 지연.
- **완전 라이브(머리 움직여도):** 보정이 디스플레이 프레임레이트로 갱신돼야 함. **권장 경로:**
  안경은 이미 매 프레임 edge_serve 로 사진 보내고 손톱 좌표 받음(~15-20fps 실시간 채널).
  eye_reg 가 계산한 A,B(또는 눈-보정 화면좌표)를 **edge_serve 응답 JSON에 실어** 보내고,
  앱이 그 값을 쓰게 하면 폴링 병목 없음. → **§6 Unity 패치 필요(데스크톱 빌드).**

## 6. 완전 라이브용 Unity 패치 (데스크톱 빌드 대상, 이 노트북엔 Unity 없음)

**서버측(이 노트북서 가능):** edge_serve 가 eye_reg 의 최신 A,B를 공유메모리/파일로 받아
`/infer` 응답에 `"reg": {"Ax":..,"Ay":..,"Bx":..,"By":..}` 로 동봉.

**앱측(C#, `NailMeshRenderer`/`EdgeClient`) — 최소 변경:**
```csharp
// EdgeClient: 응답 파싱에 reg 필드 추가 → NailMeshRenderer 로 전달
if (resp.reg != null) {
    meshR.parallaxEnable = true;
    meshR.parallaxA = new Vector2(resp.reg.Ax, resp.reg.Ay);
    meshR.parallaxB = new Vector2(resp.reg.Bx, resp.reg.By);   // 프레임마다 갱신 = 라이브
}
```
`NailMeshRenderer.OffsetFor(distM)=parallaxA+parallaxB/distM` 는 그대로 활용(이미 존재).
→ 파일폴링(1.4Hz) 대신 **매 프레임 갱신**. 빌드: `CIBuild.BuildMesh`(IL2CPP/ARM64, Unity 2022.3.36f1).

## 7. 정확도 예산 (예상)

| 오차원 | 크기 | 결과 x/y 정합오차(30cm) |
|---|---|---|
| 홍채 깊이(11.7mm 개인차 ±0.5mm) | ~4% 깊이 | 소 (baseline z 성분에만) |
| 웹캠 화각 미보정(±5°) | ~9% 스케일 | 중 → 체스보드로 축소 |
| 안경카메라 오프셋 상수(±3mm) | 고정편향 | A 로 흡수(1회 정렬) |
| 머리 급속이동(1.4Hz 지연) | 속도의존 | 정적자세면 무시, 이동시 큼 → §6 라이브로 해결 |

이론상 좋은 캘리브로 **x/y ~0.3~0.7°**(연구문서 SPAAM 수준)이나 **자동·사람별**이 이점.
**흐림/복시는 불변**(하드웨어).

## 8. 향후: 재착용 slip 완전 보상 (마커 방식)

안경에 ArUco/AprilTag 마커를 붙여 웹캠이 **안경 자체를 독립 추적**하면, 안경이 미끄러져
눈-안경 관계가 변해도 gcam_W를 직접 관측 → §2의 코받침 근사 없이 정밀. (현재는 코받침 랜드마크로 근사.)

## 9. 파일

| 파일 | 역할 | 상태 |
|---|---|---|
| [src/eye_geometry.py](../src/eye_geometry.py) | 기하 수학 코어(순수) | ✅ 완료·테스트 9/9 |
| [tests/test_eye_geometry.py](../tests/test_eye_geometry.py) | 단위테스트 | ✅ |
| [web/eye_reg.py](../web/eye_reg.py) | 웹캠 런타임(측정→push) | ✅ 코드완료, 물리검증 대기 |
| edge_serve `/infer` reg 동봉 | 라이브 루프 서버측 | ⏳ §6 |
| Unity `NailMeshRenderer` reg 수신 | 라이브 루프 앱측 | ⏳ 데스크톱 빌드 |
| models/face_landmarker.task | FaceLandmarker 모델(3.7MB) | ✅ 다운로드됨 |
