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
