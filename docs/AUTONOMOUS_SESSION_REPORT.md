# 자율 세션 보고서 — 손톱 AR 정합 연구·구현

세션: 2026-07-03 02:04 시작 (3시간 자율 지시). 지시: "이런 거 처리하는 레퍼런스 조사(모든 논문·코드) → 구현 → 보고. 목표 이룰 때까지 자율."

---

## 한 줄 결론

**형이 원한 "코앞 실제 손톱에 픽셀을 정합하는 진짜 시스루 AR"은 RayNeo X3에서 물리적으로 불가능함을 논문으로 확증했습니다.** 우리가 겪은 흐림·복시·떠다님은 버그가 아니라 **4m 고정 초점면**의 근본 한계. **업계 전체(YouCam/ModiFace/Snap)가 이걸 피해서 "매직미러"(카메라 영상+2D 오버레이를 화면으로)로 합니다.** → X3에서 실현 가능한 정답도 매직미러. 코드로 준비해뒀습니다(다음 빌드 1회 필요).

---

## 1. 조사 (4개 병렬 에이전트 → `docs/AR_REGISTRATION_RESEARCH.md`)

- **근거리 시차 물리(Cutolo 2020, Frontiers):** ‖E‖ ≈ O′·|p_z/d_focal−1|. X3(4m)에 30cm 손 → 계수 0.93. 무 아이트래킹이라 눈위치 불확실 5mm → **오차 4.6mm가 3~9mm 떠다님**(손톱폭의 절반↑). **VAC ≈ 3D**(편안한계의 10배) → 흐림+복시, 소프트웨어 해결 불가. → *진짜 시스루 근거리 AR 불가 확증.*
- **SPAAM 계열 캘리브(서베이 arXiv 1709.04299):** X3엔 **Stereo-SPAAM**(아이트래커 불필요)만 가능. x/y ~0.2~0.5°는 잡아도 **깊이 z·흐림은 못 잡음.** 코드 `fatihksubasi/spaam`(Python, 서버 이식용), `YutaItoh/HMD-Calibration`(MIT), Hu/Cutolo bare-hand translation-only(arXiv 2108.10603).
- **업계 제품:** 네일 트라이온 전부 **미러 방식·온디바이스.** ModiFace CVPRW2019(1906.02222) 렌더 레시피(DIP→TIP 축 쿼드 + 끝쪽 늘림 + 하이라이트).
- **MediaPipe:** 손가락 폄 = **PIP 각도법**(>150°) — 우리 코드에 반영.

## 2. 구현 (완료·검증)

### 서버(재빌드 불필요, 테스트 완료)
- **절대거리(distM):** MediaPipe World Landmarks(미터) + 핀홀로 카메라~손 거리 계산. `src/hand_landmarks.py`, 응답에 `distM`. 검증 OK.
- **손가락 폄 필터(주먹 제외):** PIP 3D 각도 >150°만. 검증: 편 손 유지, **타이핑 포즈 10→1개**로 걸러짐. `NAIL_EXTENDED=on`(기본).
- **손톱-향함(facing) 필터:** 손등이 카메라 향할 때만(옵션 `NAIL_FACING=back`, 기본 off).
- 파일: `src/hand_landmarks.py`, `web/edge_serve.py`.

### SPAAM 정합 솔버 (구현 + 자체검증 완료)
- `src/spaam.py` — 표준 DLT/SVD로 3×4 눈↔디스플레이 투영행렬 추정(Hartley 정규화 + SVD + 재투영).
  **자체테스트 PASS**: 합성 대응 30쌍 + 0.5px 정렬노이즈 → **재투영 RMS 0.344px**(정확 복원). `python src/spaam.py`.
- 용도: 진짜-시스루 정합의 x/y 개선(Stereo면 좌/우 각각 풀고 IPD 검증). **단 X3의 깊이·흐림·VAC는 못 잡음**(§1).

### 앱(코드 작성 완료 — **다음 빌드에 반영**, Unity 열려있어 자율빌드 불가)
- **매직미러용 `canvasRot`:** 캔버스(피드+오버레이) 통째 회전 → 세로 카메라를 똑바로. `Nail/Assets/Scripts/NailARController.cs`.
- (기존) distM 기반 동적깊이 + distScale, 스무딩/hold, 회전/미러/오프셋 — 전부 calib 실시간.
- `Nail/Assets/Editor/CIBuild.cs`: CLI 배치빌드 메서드(Unity 닫혀있을 때 `Unity.exe -batchmode -quit -projectPath Nail -executeMethod CIBuild.BuildAndroid`).

### 프리셋 calib (`tools/calib/`)
- `nail_calib_mirror.json` — **매직미러**(feed on, canvasRot=90, 4m 패널, 디자인 합성). *다음 빌드 후 사용.*
- `nail_calib_ar.json` — 진짜-AR 최선안(물리한계로 흐림/복시 예상).

## 3. 왜 자율 빌드를 못 했나
Unity Editor(pid 42380)가 **열려 있어 프로젝트 잠김** → 배치빌드 불가. Unity MCP도 이 세션에 미연결. **코드는 다 작성**해뒀고, 열린 에디터가 C# 변경을 자동 컴파일하므로, 형이 돌아와 **Build 1회**만 하면 매직미러가 반영됩니다. (그 Input Handling 다이얼로그 뜨면 Yes)

## 4. 형이 돌아오면 (권장 순서)

1. **결정:** 진짜 손 정합은 이 안경으론 불가(물리). **매직미러로 갈지** 정하기.
2. 매직미러면: Unity에서 **Build 1회** → 제가 설치 + `nail_calib_mirror.json` 푸시 → 카메라로 손+디자인이 **선명·단일**한 패널로 보임(주먹 땐 안 뜸). canvasRot(90/−90/180) 한 번 맞추면 똑바로.
3. 렌더 품질: 원하면 ModiFace 레시피(끝쪽 늘림·하이라이트) + 더 진한 디자인 에셋 추가.
4. 진짜 시스루 정합을 꼭 원하면: 도수 콘택트/인서트로 근시 보정(흐림 일부↓) + Stereo-SPAAM 캘리브(x/y만 개선, VAC는 남음). 또는 폰/태블릿 앱·짧은초점 HMD로 하드웨어 전환.

## 5. 오늘까지의 확정 성과 (재확인)
- ✅ 안경 자체 카메라 뚫기(ShareCamera + 런처 액티비티)
- ✅ MediaPipe 5손가락 + 칼만 추적(10ms) + 절대거리 + 폄/향함 필터
- ✅ 카메라→검출→오버레이 파이프라인 안경 실동작
- ✅ 근거리 시스루 AR 불가의 물리적 증명 + 실현가능 대안(매직미러) 설계·구현
- ⏸ 매직미러 최종 반영 = 형의 Build 1회 대기

*모든 파일 저장됨. 서버·무선 adb 유지 중.*
