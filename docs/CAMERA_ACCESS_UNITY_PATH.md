# 안경 카메라 접근 — 조사 결론 & Unity 경로 (2026-07-01)

> 질문: RayNeo X3 Pro **안경 카메라**를 우리 앱이 쓸 수 있나? 결론: **서드파티 앱은 정책
> 차단. 공식 경로 = Unity ARDK `ShareCamera`(권한 런타임 경유).**

## 1. 카메라 차단 — 확정된 사실
- 사이드로드 앱(일반 UID): Camera2 open 시 **`ERROR_CAMERA_DISABLED`**(정책 차단).
- shell UID(adb/scrcpy): 정책은 통과하나 `configureStreams: Broken pipe(-32)`.
- `SYSTEM_CAMERA` = role-managed, **화이트리스트 ~26개 시스템/RayNeo 앱**에만(우리 앱 불가).
- `pm grant`/`cmd role add`/`dpm`/appops/creator토글/센서프라이버시 — **전부 무효**.
- 부트로더 잠김(`oem_unlock=0`, `ro.debuggable=0`) → **루트 불가.**
- 패키지명 위장 = 화이트리스트 이름 전부 이미 설치됨 + `SYSTEM_CAMERA`가 signature 검사 → 불가.
- **→ 소프트웨어 우회 없음.** (공식 문서 "카메라는 네이티브로 됨"은 **공식 서명/화이트리스트 앱** 기준.)

## 2. 공식 경로 — Unity ARDK ShareCamera
- 문서(GitBook, 공개): `https://rayneo-en.gitbook.io/rayneo-devdoc`
- **`ShareCamera`**(Unity): 권한 있는 RayNeo 런타임이 카메라를 잡고 **Android 공유 텍스처(EGL/GL)**로 Unity에 프레임 전달.
  ```csharp
  m_Handler = ShareCamera.OpenCamera(XRCameraType, new XRResolution(w,h), rawImage, 30);
  XRResolution[] r = ShareCamera.getSupportResolutions(camType);  // X3pro RGB: 4032x3024~176x144
  ShareCamera.CloseCamera(m_Handler);
  ```
  주의: **동적 카메라 권한 요청 필수.** 초점은 고정(~50cm)이라 근접 손톱은 소프트.

## 3. 필요 스펙 (문서 확인)
| 항목 | 값 |
|---|---|
| Unity Editor | **2022.3.36f1** (changeset `95a4219250e5`; "c1"=Tuanjie 가능성, ARDK로 확인) |
| ARDK | **RayNeo OpenXR Unity ARDK 1.1.2** (`RayNeo OpenXR Unity ARDK.zip`, Feishu drive, md5 341130f1…) |
| 런타임 | **`RayNeoRuntime-release-platformKey-signed.apk`** 안경 설치 (Glass OS 25.8.29+) |
| 빌드 | IL2CPP / ARM64 / minSDK29 / targetSDK32 |

## 4. 스캐폴드 (작성·검증 완료) — [unity/](../unity/)
검출은 **기존 PC 에지 재활용**, Unity는 캡처+렌더만.
- `Assets/Scripts/NailARController.cs` — 권한 + ShareCamera + 캡처루프
- `Assets/Scripts/EdgeClient.cs` — `POST /infer`(HTTPS:8443, 자체서명 허용) → 손톱좌표
- `Assets/Scripts/NailOverlayRenderer.cs` — 손톱별 디자인 배치(fit/fill·회전)
- **에지 실동작 검증:** `web/edge_serve.py` 에 손 이미지 POST → `{"nails":[{"cx","cy","ex","ey","len","wid","contour"}]}` 정상(GPU, 115ms). C# 스키마 일치시킴.
- `README_UNITY.md` — 전체 셋업 절차.

## 5. 남은 일 (사용자)
1. Unity Hub GUI → **2022.3.36f1 + Android Build Support** 설치 (Hub CLI는 이 빌드에서 깨짐).
2. `RayNeo OpenXR Unity ARDK.zip` 다운 → 전달.
3. `RayNeoRuntime-...signed.apk` 안경 설치.
→ 이후: 프로젝트 생성 + ARDK 임포트 + 스캐폴드 드롭인 + `XRCameraType`등 확인 + 빌드/설치.

## 6. 대안(지금 되는 것)
폰/PC 카메라 → 안경 표시(네이티브 앱, `docs/GLASSES_APP_RESULTS.md`). 초점·화질 우위.

출처: [GitBook 개발문서](https://rayneo-en.gitbook.io/rayneo-devdoc) · Feishu 개발자 매뉴얼 · [Qualcomm X3 Pro 가이드](https://www.qualcomm.com/developer/project/get-started-with-rayneo-x3-pro-ar-development)
