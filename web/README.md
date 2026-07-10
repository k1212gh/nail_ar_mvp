# Nail AR — 브라우저 온디바이스 버전 (설치 0)

폰 브라우저에서 **폰 카메라로 그 자리에서** 손톱에 별을 얹는다. Android Studio·앱 설치 불필요.
PC `--seg none` 로직(세그 없이 랜드마크로 손톱판 추정)을 MediaPipe JS로 그대로 옮긴 것.

| PC (Python) | 웹 (JS) |
|---|---|
| `hand_landmarks.py` | MediaPipe Tasks `HandLandmarker`(WASM, GPU 델리게이트) |
| `geometry.py geometry_from_roi` | `app.js` nailsFrom() — 동일 비율(0.72 / 0.55 / 0.75) |
| `design_overlay.py` | `app.js` drawStar() — canvas 회전·스케일 |

## 두 가지 버전
- `/` (index.html, app.js) — **랜드마크 추정** 배치(가볍고 빠름, 근사)
- `/yolo.html` (yolo.js) — **실제 손톱 인식**(YOLOv8-seg ONNX를 onnxruntime-web/WebGPU로 실행, 별을 진짜 손톱 마스크에 클리핑). PC `--seg yolo`와 같은 모델·디코드.

## 실행
1. PC에서:
   ```powershell
   python web\serve.py
   ```
   → `https://<PC-IP>:8443` 주소가 출력됨(폰과 같은 Wi-Fi).
   - **실제 손톱 인식**은 `https://<PC-IP>:8443/yolo.html` 로 접속.
   - 첫 로드 시 모델 46MB 다운로드 + WebGPU 컴파일로 10~30초 걸림(처음만).
   - 처음엔 자체서명 인증서를 자동 생성한다(`cert.pem`/`key.pem`).
   - **Windows 방화벽 팝업이 뜨면 "액세스 허용"**(안 그러면 폰이 접속 못 함).
2. **폰 브라우저**(Chrome 등)에서 그 주소 접속 →
   - 인증서 경고: **고급 → 계속/방문**(자체서명이라 정상)
   - **카메라 권한 허용**
3. 손톱이 카메라를 향하게 비추면 손톱마다 별. **화면 탭 = 별 on/off**, 하단 슬라이더 = 크기, 버튼 = 카메라 전환.

## 튜닝 (PC와 동일 값)
- `app.js`: `CENTER_RATIO`(0.72) / `LEN_RATIO`(0.55) / `WID_RATIO`(0.75) / `designScale`(0.85)
- 디자인 교체: `web/star.png` 를 다른 투명 PNG로

## 의존성/주의
- MediaPipe JS·WASM는 jsDelivr CDN에서 로드 → **폰에 인터넷 필요**(첫 로드). 모델·별은 로컬 서버에서.
- **별이 거꾸로/틀어지면**: `app.js` drawStar()의 `Math.atan2(n.ax, -n.ay)` 부호를 뒤집어 본다(기기 좌표계 차이).
- 카메라가 안 잡히면: 다른 앱이 카메라 점유 중인지 확인, HTTPS로 접속했는지 확인(http는 카메라 차단).
- 한계는 PC `--seg none`과 동일: 손톱 외곽 정밀 클리핑·곡면 없음(랜드마크 추정 배치). 정밀화는 손톱 세그 모델 단계.
