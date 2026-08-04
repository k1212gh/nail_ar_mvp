# 네일아트 보조 AR — MVP (PC Python 프로토타입)

손 영상에서 **손톱을 인식 → 외곽 분할 → 중심선·격자·프렌치 라인·부착점을 산출**해
실시간 오버레이로 그려주는 MVP. 계획서(`compass_artifact...md`)의 PC 프로토타입
단계(로드맵 0~6주)를 모듈형으로 구현했다.

## ✅ 모듈형 설계 — "변수 하나로 스마트글래스 전환"

카메라 종류는 파이프라인과 완전히 분리돼 있다. **`--source` 값 하나**만 바꾸면
폰·웹캠·파일·스마트글래스가 **똑같은 인식/정합/오버레이 코드**를 탄다.

```
                 ┌──────────────── 동일 파이프라인 ────────────────┐
입력 어댑터  →   손 랜드마크 → 손톱 세그 → 기하 산출 → 칼만 평활 → 오버레이
(video_source)   (hand_landmarks)(nail_seg)(geometry)  (tracking)  (overlay)

웹캠      --source 0
폰        --source http://192.168.0.10:4747/video      ← DroidCam/IP Webcam
파일      --source samples/hand.mp4
글래스    --source glasses --glasses-backend url|frame_dir|custom   ← XREAL Eye 등
```

`src/video_source.py`의 `build_source()`가 소스 결정의 **유일한 지점**이다.
새 하드웨어를 붙일 때 추가 작업은 어댑터 클래스 1개뿐, 호출부는 불변.

## 설치 & 실행

실제 시스템 = **글래스 앱(RayNeo X3)** 이 카메라 프레임을 **PC 에지 서버**로 보내고, PC가
YOLO+MediaPipe로 손톱을 검출해 돌려주면 앱이 오버레이한다. (`main.py`의 로컬 비디오 루프는
없어졌다 — 진입점은 에지 서버.)

```bash
pip install -r requirements.txt        # opencv, numpy, mediapipe, ultralytics
python web/edge_serve.py               # PC 에지 서버 (HTTPS :8443, YOLO+MediaPipe 검출)
# 글래스: Nail/ 유니티 프로젝트를 빌드·설치 (정본 = Nail/) 후 실행하면 :8443로 프레임 전송
```

- 검출 모델: MediaPipe `models/hand_landmarker.task`(자동 다운로드) + YOLO `models/nails_seg_s_yolov8_v1.pt`.
- 인증서: `certs/`(웹 루트 밖 — 개인키 유출 방지). 글래스는 `adb reverse tcp:8443 tcp:8443`로 터널.
- 브라우저 테스트: `https://<PC-IP>:8443/edge.html` (자체서명 경고 통과).

## 구조

| 파일 | 역할 |
|---|---|
| `config.py` | 모든 설정값(소스/세그/기하/추적). 데이터클래스 |
| `web/edge_serve.py` | **진입점** — HTTPS :8443, `POST /infer`(JPEG→손톱 기하 JSON) + 정적서빙 |
| `src/hand_landmarks.py` | MediaPipe 21 랜드마크 → 손톱 ROI 추정 |
| `src/yolo_nail_seg.py` | YOLOv8-seg 손톱 분할(에지 서버가 사용) |
| `src/nail_segmentation.py` | ROI 내 손톱 분할: `grabcut`(기본)/`color`/`external`(SAM·YOLO 후킹) |
| `src/geometry.py` | PCA 중심선·방향, 격자·프렌치 라인·부착점 산출 |
| `src/tracking.py` | 칼만 필터 평활·가림 보간 |
| `src/spaam.py` | SPAAM DLT 캘리브 솔버(카메라→눈 정합, 시스루 AR용) |
| `Nail/` | **정본 유니티 프로젝트**(RayNeo OpenXR 글래스 앱). `_archive/`는 죽은 사본 |

> 정리(2026-07-04): `main.py`·`src/video_source.py`·`src/metrics.py`는 제거/아카이브됨(`_archive/`).

## 세그멘테이션 교체 경로 (데이터가 쌓이면)

기본 `grabcut`은 **학습 데이터 0장으로 즉시 동작**한다. 계획서대로 SAM2/MobileSAM
자동 라벨 → YOLO11-seg 커스텀으로 올릴 때는 `--seg external` 로 두고:

```python
segmenter.set_external(my_yolo_or_sam_fn)   # fn(roi_crop_bgr, roi) -> mask
```

마스크만 반환하면 기하·추적·오버레이는 그대로 재사용된다.

## 스마트글래스(XREAL Eye 등) 이식 메모

- **그래픽 좌표는 이미 분리돼 있다.** `geometry.py` 산출물(선·점 좌표)을 글래스
  렌더러로 넘기면 되고, 글래스의 addition 디스플레이에선 검은 배경이 투명이 된다.
- **카메라 보정값**(`config.src.camera_matrix`)을 넣으면 정합 정확도가 올라간다.
  폰/글래스 공통 인터페이스(`VideoSource.intrinsics`).
- 계획서 경고대로 글래스의 **근거리 초점·작은 곡면 추적은 미확인**이므로,
  인식·추적은 이 폰 MVP 코드로 검증한 뒤 글래스는 **디스플레이 출력**으로만
  쓰는 아키텍처도 `--source glasses --glasses-backend custom` + `push_frame()`로
  바로 실험할 수 있다.

## 한계 (MVP)

- `grabcut`은 조명/배경에 민감하다 — 실데이터로 커스텀 세그 모델 교체가 정답.
- 추적은 칼만 평활 중심(MVP). 빠른 움직임엔 `tracking.py`의 KLT 광류 확장 지점을 채운다.
- 근접 초점은 폰 카메라/매크로렌즈 설정에 의존.

---

# 🔧 현재 진행 상황 & 노트북에서 이어하기 (2026-08)

> 이 섹션 = **지금 뭘 하고 있었는지 + 다른 PC(노트북)에서 이어받는 법.** 위쪽 MVP 문서는 초기 PC 프로토타입 기준이고, 실제 작업은 **RayNeo X3 안경 앱**으로 넘어와 있다.

## 지금 만들고 있는 것 — "손톱 그리기 가이드"

완성 디자인을 얹는 게 아니라, 네일 아티스트가 **직접 그릴 수 있게 손톱 위에 기준선을 안내**한다.
- **손톱 정중앙 십자선(crosshair)** — 시작점/끝점/중앙 기준. 렌더러 = [`Nail/Assets/Scripts/NailCenterDot.cs`](Nail/Assets/Scripts/NailCenterDot.cs).
- **매직미러 모드로 표시** — OST(시스루) 생화면은 4m 초점·시차 때문에 근거리 손톱 정합 불가(검증됨). 그래서 카메라 피드를 안경에 띄우고(**mode=4 = Enroll**) 그 위에 십자를 그림 → 시차 0.
- **정합의 핵심**: 피드와 십자가 **같은 canvas의 자식** → 둘이 같이 회전/스케일됨 → 십자는 카메라→눈 보정이 아니라 **rot=0 identity 매핑**이 맞다. (`push_calib ... rot=0 mirrorX=0 mirrorY=0 offsetX=0 offsetY=0`)
- **단안(mono=1)** 기본(근거리 복시 회피). 단, `screencap` 검증 시엔 **mono=0**(양안)이라야 화면이 캡처됨(단안은 3596B 검정으로 나옴).

## 최신 앱 = NailGuide (dev 빌드)

| 항목 | 값 |
|---|---|
| 패키지 | `com.DefaultCompany.NailGuide` |
| 빌드 | `CIBuild.BuildGuideDev` → `Nail/NailGuide_AUTO.apk` (~65MB, IL2CPP/ARM64, **dev=로그 나옴**) |
| define | `MIRROR_APP;GUIDE_APP` → 부팅 시 매직미러+루페+단안(left) |
| 안경 시리얼 | `006A5E5038F3297` (RayNeo X3, ARGF20) |

```bash
# 빌드 (노트북에 Unity 2022.3.36f1 필요)
"<Unity>/Unity.exe" -batchmode -quit -nographics -projectPath Nail \
  -executeMethod CIBuild.BuildGuideDev -logFile ng_build.log
```

## 노트북에서 이어하기 — 라이브 세팅 (USB 경로)

```bash
export ANDROID_SERIAL=006A5E5038F3297   # 안경 여러대/폰 동시연결 시 필수
export MSYS_NO_PATHCONV=1               # Git Bash에서 /sdcard 경로 안 깨지게

# 1) PC 에지 서버 — YOLO 검출 (NAIL_MODE=yolo 필수! 기본 hands면 손톱검출 안 함)
NAIL_MODE=yolo python web/edge_serve.py     # :8443 infer, :8080 monitor(/last.jpg,/stats.json), :8444 socket

# 2) 안경 설치 + USB 터널 (터널은 주기적으로 끊김 → 검출 멈추면 재실행)
adb install -r Nail/NailGuide_AUTO.apk
adb reverse tcp:8443 tcp:8443; adb reverse tcp:8080 tcp:8080; adb reverse tcp:8444 tcp:8444

# 3) 설정 push — 매직미러 + rot=0 identity (단안=mono1, 캡처검증=mono0)
python web/push_calib.py pkg=com.DefaultCompany.NailGuide \
  mode=4 mono=1 guide=0 rot=0 mirrorX=0 mirrorY=0 offsetX=0 offsetY=0 \
  useSocket=0 edgeUrl=https://127.0.0.1:8443/infer

# 4) 실행 + 검증
adb shell monkey -p com.DefaultCompany.NailGuide -c android.intent.category.LAUNCHER 1
curl -s http://127.0.0.1:8080/stats.json      # {"nails":N,...} frames 증가 = 정상
curl -s http://127.0.0.1:8080/last.jpg -o cam.jpg   # 카메라가 실제로 뭘 보는지
adb exec-out screencap -p > screen.png              # 안경 화면(mono=0일 때만 유효)
```

**검출이 되려면 카메라가 손톱을 봐야 한다.** 안경 카메라는 착용자가 보는 앞쪽을 찍으므로, **손을 얼굴 앞으로 들거나(손톱이 카메라를 향하게)** 책상 위 손을 내려다봐야 함. (빨간 펜 등은 손톱으로 오검출됨.)

## 펜 가림(occlusion) 상태

- **PC 매직미러 데모 = 완성**: `NAIL_OCC_DEMO=1 NAIL_MODE=yolo python web/edge_serve.py` → 모니터 피드에서 검은펜/금속브러시가 디자인을 뚫고 보임([`web/pen_occlusion.py`](web/pen_occlusion.py)). **빨강은 채도 높아 잘 안 뚫림.**
- **안경 가림 = 절반(스캐폴딩)**: PC가 `occMask`를 /infer 응답에 실어보내고(`NAIL_OCC_MASK=1`) [`EdgeClient.cs`](Nail/Assets/Scripts/EdgeClient.cs)가 파싱까지는 함. **하지만 안경에서 그 마스크로 오버레이/십자를 실제로 뚫는 소비 코드가 아직 없음** → 미완.

## 무선화 로드맵 (목표 = PC/USB 없이)

현재는 안경↔PC USB(adb reverse). 목표는 **폰 온디바이스 추론 + 안경 WiFi 중계**:
- 폰 앱 "Nail Edge Server"(`com.example.nailar`, onnx/소켓 :8444)가 YOLO 추론.
- 안경은 WiFi로 폰에 붙어 검출 수신. DHCP IP 불안정 → **클라우드 IP discovery**(폰이 바뀐 IP 보고 → 안경이 받아 직접 연결) 구상.
- 원격 모니터: 오라클 릴레이(`161.33.176.78:8090/monitor`) — 안경/PC가 프레임 push해야 켜짐. 관련: [`web/relay_compose_push.py`](web/relay_compose_push.py)(PC 컴포지터), [`Nail/Assets/Scripts/RelayPusher.cs`](Nail/Assets/Scripts/RelayPusher.cs)(안경 직접 송출), [`docs/GLASSES_DIRECT_RELAY.md`](docs/GLASSES_DIRECT_RELAY.md).

## 아직 안 끝난 것 (다음 할 일)

1. **십자-손톱 정합 하드웨어 검증** — 손톱이 프레임에 안 들어와 아직 육안 확인 못 함. 손톱 대고 `screencap`(mono=0)으로 십자가 손톱에 붙는지 확인.
2. **십자 가시성** — "얇은 선"이 손톱 크기로 축소되면 사라져서 선 7px(화면 ~2.5px)+중앙점으로 키움(커밋 `94ce0d3`). 실제 손톱에서 재확인 필요.
3. **카드 스케일 실물크기** — 카드(알려진 크기)로 거리·비율 1회 자동조정 → 슬라이더 미세조정 → 이후 고정(네일아트는 거리 이동 적음).
4. **검출 파이프라인 불안정** — adb reverse 터널 드랍/프레임 정지 반복. 재설정 순서: reverse 재실행 → 앱 재시작 → edge_serve 재기동 → 안경 리부팅.
5. **펜 가림 안경측 배선** — occMask 소비 코드(십자/오버레이를 마스크로 알파컷).

## 핵심 파일 (이번 작업)

| 파일 | 역할 |
|---|---|
| [`Nail/Assets/Scripts/NailCenterDot.cs`](Nail/Assets/Scripts/NailCenterDot.cs) | 손톱 중앙 십자선 렌더(런타임 스프라이트, overlay와 동일 calib) |
| [`Nail/Assets/Scripts/NailARController.cs`](Nail/Assets/Scripts/NailARController.cs) | 모드/설정 적용, NailCenterDot 코드배선(씬 편집 0) |
| [`web/push_calib.py`](web/push_calib.py) | 안경 config(`nail_calib.json`) adb push |
| [`web/edge_serve.py`](web/edge_serve.py) | PC 에지 서버(YOLO 검출, occ 마스크/데모) |
| `Nail/Assets/Editor/CIBuild.cs` | `BuildGuideDev`(NailGuide dev) / `BuildAndroid`(release) |
