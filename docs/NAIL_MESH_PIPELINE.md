# 곡면 메쉬 네일 파이프라인 — "1회 측정 → 베이킹 → 런타임은 포즈만"

버튜버 리깅과 같은 구조: 무거운 작업(손톱 실측·디자인 분절/워프)은 오프라인에 1회,
런타임은 중심·축·거리만 갱신한다. 손톱별 반원기둥 메쉬에 베이킹 텍스처를 UV로 입히므로
기울기 투영·원근은 GPU가 처리하고, 광택 하이라이트가 손 움직임에 따라 흐른다.

## 사용 절차

1. **측정 (Enroll)** — 에지 서버 켠 상태에서:
   - 캘리브 파일로 진입: `{"mode":4}` → `adb push nail_calib.json /sdcard/Android/data/com.DefaultCompany.Nail/files/`
   - 거울 모드로 카메라 피드가 보인다. 손등을 15~50cm에서 천천히 움직이며 보여준다.
   - HUD에 손가락별 표본 수가 갱신됨: `[Right] T12 I40 M33 R28 P9 /40` → 5손가락 모두 40이면 DONE.
   - 서버가 `nail_profile.json`(프로젝트 루트)에 손가락별 중앙값(mm)을 기록한다.
   - 표본 리셋은 Enroll 모드 재진입(모드 바꿨다가 다시 4).

2. **베이킹** — PC에서:
   ```
   python tools/build/bake_nail_design.py --design french        # 프로파일 기반
   python tools/build/bake_nail_design.py --demo                 # 측정 전 표준치수 테스트
   ```
   `out/nail_bake/`에 손가락별 텍스처 10장 + `nail_bake.json` 생성.
   원리: 평면 디자인을 각 손톱의 원호 전개면(arc-length)으로 리샘플 → 메쉬에 감으면
   정면 모습이 원본과 일치. 곡률은 `--curve`(새그/폭, 기본 0.22).

3. **푸시 & 실행** (스코프드 스토리지 때문에 mkdir을 먼저 — 디렉토리째 push는 거부됨.
   shell이 만든 하위 디렉토리는 앱이 못 읽을 수 있으니 **chmod 777까지 필수**):
   ```
   adb shell mkdir -p /sdcard/Android/data/com.DefaultCompany.Nail/files/nail_bake
   adb push out/nail_bake/. /sdcard/Android/data/com.DefaultCompany.Nail/files/nail_bake/
   adb shell chmod 777 /sdcard/Android/data/com.DefaultCompany.Nail/files/nail_bake
   ```
   전용 앱(NailMesh_AUTO.apk, `CIBuild.BuildMesh`)은 켜자마자 ARMesh로 부팅(탭 순환 없음).
   패키지가 달라서 위 경로의 `com.DefaultCompany.Nail`을 `com.DefaultCompany.NailMesh`로 바꿔 푸시.
   첫 실행 시 CAMERA 권한 필요: `adb shell pm grant com.DefaultCompany.NailMesh android.permission.CAMERA`.
   화면이 Doze로 꺼진 채 실행하면 XR 초기화가 멈출 수 있음 → 깨우고(`adb shell input keyevent KEYCODE_WAKEUP`) 앱 재시작.
   앱에서 탭으로 ARMesh 모드 진입(순환: ARGrid → ARDesign → ARMesh) 또는 `{"mode":3}`.
   모드 진입 시 bake를 다시 읽는다. 실행 중 갱신은 `{"bakeReload":1}` (값을 바꿔 푸시).
   bake가 없으면 Resources 디자인 + 표준 치수로 폴백(바로 테스트 가능).

## 런타임 스케일 산식 (포즈만 계산)

- 서버 → `cx, cy, ex, ey, distM` (손가락 identity 포함)
- 예상 카메라 px: `lenPx = focalRatio(0.86)·imgW · lenMm/1000 / distM` — **프로파일 mm + 거리만 사용**
- 기울기(pitch): `acos(관측 len / 예상 len)` (전방단축), `tiltMax=40°` 클램프
- distM 없거나 bake 없으면 서버의 프레임별 px로 폴백

## 캘리브 노브 (nail_calib.json)

| 키 | 의미 |
|---|---|
| `mode` | 3=ARMesh, 4=Enroll |
| `meshGloss` / `meshGlossPow` | 광택 강도 / 하이라이트 예리함 (기본 0.9 / 28) |
| `meshTilt` | 1=전방단축 기울기 on, 0=off |
| `meshTiltSign` | ±1 기울기 방향 뒤집기 |
| `meshBulge` | ±1 볼록 방향(뷰어 쪽/반대) 뒤집기 |
| `meshCurve` | bake 없을 때 폴백 곡률 |
| `meshScale` | 메쉬 디자인 스케일 (overlay designScale와 별도) |
| `bakeReload` | 값을 바꿔 푸시하면 nail_bake 재로딩 |

공용 정렬 노브(offsetX/Y, scale, rot, designRot, smoothing, holdSec)는 스프라이트
오버레이와 메쉬에 **동일하게** 적용된다(같은 좌표 매핑 = SPAAM 캘리브 공유).

## 규약 (코드 간 일치해야 하는 것들)

- `focalRatio 0.86` = `config.py HandConfig.focal_ratio` (서버·Unity·베이커 공통)
- 디자인 PNG: 이미지 **상단 = 팁** (gen_nail_design.py french_tip 기준). Unity 텍스처 v=1 = 상단.
- 메쉬 UV: u = 호 길이 균등(베이커의 arc-length 리샘플과 일치), v = base 0 → tip 1
- curve = 새그/폭 비. 메쉬(NailMeshRenderer.BuildNailMesh)와 베이커(bake_one)가 같은 원호 수학 사용:
  `R=(a²+s²)/2s, θ0=asin(a/R)`

## 실기 확인 순서 (다음 세션)

1. `--demo` bake 푸시 → ARMesh 모드 → 메쉬 10개가 손톱 위에 뜨는지
2. 볼록/기울기 방향 확인 → 필요시 `meshBulge`/`meshTiltSign` 뒤집기
3. 광택 스윕 체감 → `meshGloss`/`meshGlossPow` 튜닝
4. Enroll 실측 → 재베이킹 → 스케일 정확도(미터법 격자와 교차 검증 가능)
