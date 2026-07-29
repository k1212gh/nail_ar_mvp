# 폰 온디바이스 에지 서버 (루트 A) — 구현계획 & 결과

> 2026-07 노트북 세션. 목표: **PC가 하던 YOLO 손톱검출 서버 역할을 폰이 온디바이스로** 수행 →
> 안경이 WiFi로 폰에 붙어 검출을 받는다. 노트북 없이 폰만으로 안경 데모.

## 1. 목표와 아키텍처

```
  [RayNeo X3 안경]                      [폰: 갤럭시 S22 Ultra / SD8 Gen1]
   카메라 프레임(JPEG)  ── WiFi 소켓 ──▶  EdgeServer(:8444)
                                            └▶ NailOnnx  ── onnxruntime-android(NNAPI)
                                                 letterbox→YOLOv8-seg→NMS→마스크→PCA
   손톱 오버레이 렌더  ◀── JSON(nails) ──────────┘
```

- 안경은 이미 **LAN 소켓 접속 지원**: `push_calib useSocket=1 sockHost=<폰IP> sockPort=8444` → 코드 변경 0.
- 폰이 무거운 Python(torch/ultralytics)을 돌릴 필요 없음 — **ONNX + onnxruntime-android** 로 대체.
- **NNAPI EP** 로 Snapdragon Hexagon NPU / Adreno GPU 가속.

## 2. 왜 루트 A인가 (다른 루트 대비)

| 루트 | 방식 | 성능 | 결론 |
|---|---|---|---|
| A. 네이티브(onnxruntime-android + NNAPI) | Kotlin 앱 | 폰 NPU → 실시간급 | **채택** |
| B. Termux + Python onnxruntime | 파이썬 | CPU ~2-4fps | 프로토타입엔 OK (본 세션에서 검증본 구현) |
| C. torch/ultralytics 이식 | — | — | ❌ 안드 torch 비현실적 |

## 3. 프로토콜 (web/edge_serve.py 소켓 경로와 100% 동일)

```
요청:  [4B big-endian uint32 total][1B flags][JPEG]     total = 1 + JPEG길이,  flags bit0 = wantCard
응답:  [4B big-endian uint32 len ][JSON(UTF-8) len바이트]
JSON:  {"ok":true,"w":W,"h":H,"ms":M,
        "nails":[{"cx","cy","ex","ey","len","wid","contour":[[x,y],...]}, ...]}
```
안경측 클라이언트: `Nail/Assets/Scripts/EdgeClient.cs` 의 `EdgeSocketClient`.

## 4. 검출 파이프라인 (web/yolo.js 검증본과 동일)

`nails_seg.onnx` — 입력 `images[1,3,640,640]`, 출력 `output0[1,37,8400]`, `output1[1,32,160,160]`.

1. **letterbox** 640 (비율유지, 회색114 패딩), RGB, /255, CHW
2. **추론** onnxruntime
3. **디코드**: output0에서 score≥0.20 후보 → **NMS**(IoU 0.5, 최대 12)
4. **마스크**: 각 후보의 32계수 · 프로토(output1) → sigmoid>0.5 (박스영역 한정)
5. **기하(PCA)**: 마스크 픽셀 주성분 → 중심(방향박스 중점)·주축(ex,ey)·길이·폭
6. **컨투어**: 마스크 픽셀 볼록껍질 → 원본좌표 폴리곤 (안경 렌더는 기하값 위주, 컨투어는 모니터/펜가림용)
7. 160-space → 원본좌표 역-레터박스 변환

## 5. 구현물

### 네이티브 앱 (루트 A) — `android/` 앱에 에지서버 모드 추가
| 파일 | 역할 |
|---|---|
| `android/app/src/main/java/com/example/nailar/edge/NailOnnx.kt` | onnxruntime-android 세션(NNAPI) + letterbox + YOLOv8-seg 후처리 (§4 전부) |
| `.../edge/EdgeServer.kt` | ServerSocket(8444) + §3 와이어 프로토콜 + JSON 직렬화 |
| `.../edge/EdgeServerActivity.kt` | 시작/중지 UI, 폰 IP·backend·fps 표시 |
| `res/layout/activity_edge.xml` | 레이아웃 |
| `app/build.gradle.kts` | `com.microsoft.onnxruntime:onnxruntime-android:1.20.0` + `noCompress "onnx"` |
| `AndroidManifest.xml` | `EdgeServerActivity` 런처 등록 ("Nail Edge Server") |
| `assets/nails_seg.onnx` | 모델(45MB, **gitignore** — `web/nails_seg.onnx` 복사) |

### torch-free 파이썬 검증본 (루트 B이자 네이티브의 레퍼런스)
| 파일 | 역할 |
|---|---|
| `tools/onnx_edge/onnx_infer.py` | §4 파이프라인의 파이썬 구현. `--frames` 로 캡처 이미지 일괄 테스트 |
| `tools/onnx_edge/onnx_serve.py` | §3 소켓 서버(torch 없이). 안경이 그대로 붙음 |

## 6. 테스트 결과 (캡처 이미지 — 네이티브가 미러링하는 동일 파이프라인)

> 네이티브 Kotlin은 이 환경에서 폰 실행이 불가하므로, **동일 로직의 파이썬 onnxruntime 구현**을
> 안경으로 실제 캡처한 프레임에 돌려 검증했다(Kotlin은 이 로직을 1:1 이식).

- **onnx forward**: 입력 640² → output0[1,37,8400]+output1[1,32,160,160], torch 없이 정상.
- **캡처 프레임 일괄**(299장): **손톱 검출 192장(64%)**, 평균 320ms(노트북 CPU, 초반 100장은 손 없는 인형이라 실제 손 프레임 검출률은 더 높음). 컨투어·중심·주축 오버레이가 ultralytics 경로와 육안상 동일.
- **소켓 왕복**(onnx_serve): 안경 프로토콜대로 프레임 전송→JSON 수신 정상.
  예) raw_205 → `ok=True 640x400 nails=2 contour_pts=20`, raw_104 → nails=4, raw_248 → nails=3.

### 네이티브 빌드 결과 — **성공** ✅

- gradle 8.10.2 + AGP 8.5.2 + Kotlin 1.9.24 (JDK17), SDK android-34, 이 노트북에서 CLI 빌드.
- `BUILD SUCCESSFUL` → **`app-debug.apk` 174MB** 산출. **Kotlin 구현이 컴파일·통합 검증됨.**
- **onnxruntime-android 정상 통합**: `libonnxruntime.so` / `libonnxruntime4j_jni.so` 가 APK에 패키징됨(NNAPI EP 포함).
- 첫 빌드에서 `EdgeServerActivity`의 `R` import 누락 1건만 있었고 수정 후 통과.
- 폰 실기기 **설치·실행·온디바이스 실측 완료** → §7 참조. `adb install -r` → "Nail Edge Server" 실행, 서버가 8444 리슨, `adb forward` 왕복으로 검출·지연 측정(노트북과 동일 검출).

## 7. 온디바이스 실측 (갤럭시 S22 Ultra / SD8 Gen1, 640², adb forward 왕복)

폰에 실제 설치·실행하고, `adb forward tcp:9444 tcp:8444` 로 폰 서버에 붙어 캡처 프레임을 보내 측정.
검출 결과는 노트북과 **동일**(raw_205→nails=2, raw_104→4, raw_248→3 …) — 파이프라인 온디바이스 정상.

| EP | 지연 | fps | 비고 |
|---|---|---|---|
| **CPU (기본 채택)** | **~479 ms** | **~2.1** | 최고. onnxruntime 기본 CPU |
| XNNPACK | ~573 ms | ~1.7 | 이 모델엔 이득 없음 |
| NNAPI | ~1425 ms | ~0.7 | **오히려 느림** — YOLOv8-seg 미지원 op 폴백/분할 오버헤드 |

> 결론: **NNAPI/XNNPACK는 이 모델에 도움 안 됨 → 기본 EP를 CPU로 설정.** (런타임 `--es ep` 로 전환 가능)

## 8. 해상도·conf 최적화 (실시간화) — 노트북 CPU 실측(캡처 299장)

| 입력 | conf | 검출률 | 노트북 CPU | 폰 CPU |
|---|---|---|---|---|
| 640² | 0.20 | 64% | 254ms (3.9fps) | **479ms 실측 (2.1fps)** |
| 416² | 0.20 | 48% | 104ms (9.6fps) | ~200ms (투영) |
| 320² | 0.20 | 45% | 65ms (15fps) | ~120ms (투영) |
| **320²** | **0.08** | **56%** | **62ms (16fps)** | **134ms 실측 (7.5fps)** ⭐ |

> 폰(S22 Ultra) 실측: 640 CPU 479ms → **320@0.08 CPU 134ms = 약 3.6배↑, 7.5fps 달성.**
> 검출 트레이드는 실재(작은 손톱 놓침) — 실제 시연은 손이 가까워 손톱이 커서 더 유리.

- 손톱이 작아 해상도에 민감 — 416은 중간이득 없음. **320 + conf 0.08 이 실시간 스윗스팟**:
  640 대비 검출 64→56%, **속도 4배**, 오탐 폭증 없음(문틀 오탐 오히려 감소). 컨투어는 80²라 약간 거침.
- 실제 시연은 손을 가까이·정지시켜 손톱이 크므로 320 검출률은 이 수치보다 나을 것.
- **앱 전환은 재빌드 불필요**(assets에 320 동봉): `--es model nails_seg_320.onnx --ef conf 0.08`
- 재export: `python tools/onnx_edge/export_320.py` (imgsz만 바꿔 320/416/512 생성).

### INT8 양자화 시도 결과 — 현재 비적합(기록)

`tools/onnx_edge/quantize_int8.py` 로 640 모델을 캡처 프레임 80장 캘리브레이션해 시도:

| 방식 | 검출 | 노트북 CPU 속도 |
|---|---|---|
| 정적(static, QDQ per-channel) | **0%** (검출헤드 양자화로 출력 붕괴) | 476ms |
| 동적(dynamic, weight-only) | 35%(부분) | **10348ms (0.1fps!)** — conv엔 안티패턴 |

- **onnxruntime CPU에선 INT8이 답이 아님**: 정적=정확도 붕괴, 동적=치명적 저속.
- 제대로 하려면 (1) **검출헤드 노드 제외(혼합정밀)** 로 정확도 복구 + (2) **NNAPI/QNN** 등 int8 가속
  백엔드 — 별도 과제. 우선순위 낮음(320@0.08로 이미 실시간 달성).

**추가 증분(우선순위순):** ① 320@0.08 채택(완료) · ② 손정지 게이팅/예측으로 체감 개선 ·
③ (여력 시) INT8 혼합정밀 + QNN EP.

## 9. 빌드 / 실행

```
# 1) 모델을 assets로 (45MB, gitignore)
copy web\nails_seg.onnx android\app\src\main\assets\nails_seg.onnx

# 2) 빌드 (Android Studio에서 android/ 열고 Run  또는  CLI)
#    JAVA_HOME=<Android Studio>\jbr,  ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk
gradle -p android assembleDebug        # → app/build/outputs/apk/debug/app-debug.apk
adb install -r app-debug.apk

# 3) 폰에서 "Nail Edge Server" 실행 → [시작] → 화면의 sockHost IP 확인

# 4) 안경을 그 폰 서버로 지정 (PC에서 push_calib, 또는 안경앱 튜너)
python web\push_calib.py pkg=<안경앱> useSocket=1 sockHost=<폰IP> sockPort=8444
```

## 10. 남은 일 / 다음 증분

- [ ] 폰 실기기에서 **NNAPI fps 실측** (예상 실시간급).
- [ ] 안경 ↔ 폰서버 **엔드투엔드** (안경 프레임 → 폰검출 → 안경 렌더) 실검증.
- [ ] 필요 시 **QNN EP**(Hexagon 직결) 또는 **320² 재export** 로 추가 가속.
- [ ] `wantCard`(신용카드 스케일) 등 부가 필드는 현재 미구현 — 데모에 필요하면 추가.
- [ ] 펜 가림(soft penDim)은 안경(Unity)·폰(JS)·이 서버 어디서 마스크를 만들지 확정 후 연결.
