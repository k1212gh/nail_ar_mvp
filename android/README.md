# Nail AR — 안드로이드 온디바이스 앱 (별 오버레이 테스트)

PC 파이프라인(`../`)을 폰에서 직접 돌리는 네이티브 앱. 후면 카메라로 손을 비추면
손톱 위에 **별 이미지를 증강**한다. PC 모듈과 1:1로 대응한다.

| PC (Python) | 안드로이드 (Kotlin) | 역할 |
|---|---|---|
| `src/video_source.py` | `camera/CameraController.kt` | 입력(CameraX Preview+Analysis) |
| `src/hand_landmarks.py` | `vision/HandNailDetector.kt` | MediaPipe 손→손톱 ROI |
| `src/geometry.py`(일부) | `vision/NailRoi.kt` | 손톱 중심·축·크기 |
| `src/design_overlay.py`+`overlay.py` | `render/OverlayView.kt` | 별 합성(아핀) |
| `main.py`+`pipeline.py` | `MainActivity.kt` | 오케스트레이션 |

## 빌드 / 실행
1. **Android Studio**(Koala 이상 권장)에서 `android/` 폴더를 **연다**(Open).
   - Gradle Wrapper jar는 포함하지 않았다 → Studio가 동기화 시 자동 생성/다운로드.
   - (CLI로 하려면 gradle 설치 후 `gradle wrapper` 한 번 실행 → `./gradlew assembleDebug`.)
2. 폰을 USB로 연결(개발자모드+USB 디버깅) → Run ▶.
3. 첫 실행 시 **카메라 권한 허용**. 손을 후면 카메라에 비추면 손톱에 별이 뜬다.
4. **화면 탭** = 별 on/off.

> 손 모델(`assets/hand_landmarker.task`, 7.5MB)과 별(`assets/designs/star.png`)은
> 이미 포함되어 있어 오프라인으로 바로 동작한다.

## 동작 방식 = PC `--seg none`
세그멘테이션 없이 **손 랜드마크로 손톱판 크기·위치를 추정**해 별을 얹는다(맨손톱은
피부와 색이 같아 세그가 불안정하므로). PC `geometry_from_roi`와 **동일 비율**:
- 손톱 세로 = 끝마디(TIP–DIP) × **0.55**, 가로 = 세로 × **0.75**, 중심 = DIP→TIP **0.72** 지점
- `OverlayView.designScale = 0.85` 가 그 위에 곱해짐

## 디자인 바꾸기 / 튜닝
- 이미지: `app/src/main/assets/designs/star.png` 를 다른 투명 PNG로 교체
- 별 크기: `render/OverlayView.kt` 의 `designScale`(0.85)
- 손톱 비율: `vision/HandNailDetector.kt` 의 `nailLengthRatio / widthRatio / nailCenterRatio`
  (PC와 같은 값 → 한쪽에서 맞춘 값을 그대로 옮기면 됨)

## 현재 한계 (다음 증분)
이 앱은 **랜드마크 기반 배치(아핀)** 까지다. PC의 `--seg none` 경로와 동일하다.
- **손톱 외곽 마스크 클리핑 없음**: 별이 손톱 정확한 외곽으로 잘리지 않고, TIP/DIP로
  추정한 손톱 영역에 얹힌다. → PC `nail_segmentation.py` 이식 또는 온디바이스 세그 추가 시 해결.
- **곡면 워핑 없음**(평면): 특허 청구항 10·도 5. remap 기반 곡면 매핑이 다음 증분.
- **회전 부호**: `OverlayView.drawStar()`의 각도(`atan2(ax,-ay)`)는 첫 실기 테스트에서
  별이 거꾸로/틀어지면 부호만 뒤집으면 된다(기기 좌표계 확인용 주석 있음).
- **좌표 매핑**: 세로(portrait)+후면 카메라 기준 fillCenter 가정. 가로/전면 전환 시 보정 필요.

## 검증 포인트
- 손을 돌리면 별이 손톱을 **따라 도는가**(방향 추적).
- 손가락별로 **각각** 뜨는가(다중 손톱).
- 근거리에서 손톱이 **검출되는가**(초점·조명 영향) — HUD의 `nails:` 수로 확인.
