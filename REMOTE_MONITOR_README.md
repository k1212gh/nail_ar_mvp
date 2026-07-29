# 폰 온디바이스 에지서버 + 원격 모니터 — 진행 인수인계

> 브랜치 `feat/phone-edge-remote-monitor` (base: `feat/pen-occlusion` → 원류 main)
> 노트북 세션 기록. **다른 PC/사장님 환경에서 이어서 작업하기 위한 문서.**
> 상세 문서: [docs/PHONE_EDGE_SERVER_PLAN.md](docs/PHONE_EDGE_SERVER_PLAN.md) · [docs/REMOTE_MONITOR.md](docs/REMOTE_MONITOR.md)

---

## 0. 한 줄 요약
- **폰이 안경의 YOLO 손톱검출 에지서버가 될 수 있음을 실증**(온디바이스, torch 없이). 실시간급 7.5fps.
- **사장님 원격 시청 릴레이**를 구현·로컬검증 완료. **남은 것: 실제 오라클 VM에 배포**(미완).

---

## 1. base 브랜치 이후 진행사항 (커밋 순)

| 커밋 | 내용 |
|---|---|
| `18c35af` | **폰 온디바이스 에지서버(루트 A)** — 네이티브 Kotlin(NailOnnx/EdgeServer/Activity) + onnxruntime-android, 안경 소켓 프로토콜 동일 |
| `bec1475` | 온디바이스 EP 실측 + **CPU 기본 채택**(NNAPI가 이 모델엔 3배 느림), `--es ep`·`--ez autostart` |
| `366013d` | **실시간화** — 320²/416² 재export + 해상도/conf 자동적응 |
| `2dadd82` | **온디바이스 320@0.08 실측 = 134ms(7.5fps)** (640은 479ms) |
| `715823d` | INT8 양자화 시도 → **CPU엔 비적합** 결론 기록 |
| `ce67f04` | **원격 모니터 릴레이**(오라클) — cloud_relay.py + relay_push.py |

### 1-A. 폰 온디바이스 에지서버 (루트 A) — **완료·실증**
- **무엇**: PC가 하던 YOLO 손톱검출을 폰이 온디바이스로 수행 → 안경이 WiFi로 폰에 붙어 검출을 받음.
- **핵심**: torch/ultralytics 없이 **ONNX + onnxruntime-android**. 후처리(letterbox→NMS→마스크→PCA)는
  `web/yolo.js` 검증본을 Kotlin/파이썬으로 1:1 이식.
- **온디바이스 실측 (갤럭시 S22 Ultra, 640²):**
  | EP | 지연 | fps |
  |---|---|---|
  | CPU(기본) | 479ms | 2.1 |
  | XNNPACK | 573ms | 1.7 |
  | NNAPI | 1425ms | 0.7 (역효과) |
- **해상도 최적화**: 320@conf0.08 → **폰 134ms(7.5fps)**, 검출률 64→56%(작은손톱 놓침). 실시간 채택.
- **INT8**: 정적=검출0%(헤드붕괴), 동적=0.1fps(conv 안티패턴) → CPU엔 부적합. (혼합정밀+NNAPI/QNN은 별도 과제)
- **안경↔폰 엔드투엔드 실증**: 안경(NailMesh)→WiFi→폰서버 → `nails=4 @137ms(7fps)` 확인.
  ⚠️ 연속 스트림은 **안경 착용**(XR 세션 활성) 필요 + 이 공유기 DHCP가 안경 IP를 자주 바꿈(폰은 고정 권장).
- **앱 조작**: `adb shell am start -n com.example.nailar/.edge.EdgeServerActivity --es model nails_seg_320.onnx --ef conf 0.08 --es ep cpu --ez autostart true`
- **안경 지정**: `ANDROID_SERIAL=<안경> python web/push_calib.py pkg=com.DefaultCompany.NailMesh useSocket=1 sockHost=<폰IP> sockPort=8444`

### 1-B. 원격 모니터 릴레이 — **구현·로컬검증 완료 / 배포 미완**
`web/cloud_relay.py`(오라클), `web/relay_push.py`(로컬). 로컬 검증: push/frame=200, 오토큰=403, monitor=200.

---

## 2. ★ 끝내지 못한 것 — 오라클 클라우드 원격 실시간 시청 환경 구축

**목표**: 다른 공간의 사장님이 브라우저로 실시간 모니터(카메라+검출)를 보게 함.

**구조** (로컬은 아웃바운드만 → NAT/방화벽 뒤에서도 동작):
```
PC 에지서버 /monitor(/last.jpg)  →  relay_push.py(로컬)  →  [오라클 VM: cloud_relay.py]  →  사장님 브라우저 /monitor
```

**구현·검증된 것 ✅**
- `web/cloud_relay.py` — 릴레이(엔드포인트 `/push`·`/monitor`·`/frame`·`/healthz`, PUSH/VIEW 토큰 분리, 표준라이브러리만)
- `web/relay_push.py` — 로컬 최신프레임 → 릴레이 POST(FPS 조절)
- 노트북에서 push→시청 왕복 + 토큰 인증(오토큰 403) 전부 통과, 브라우저 시청 확인

**끝내지 못한 것 ⛔ (다음에 이걸 하면 됨)**
1. **실제 오라클 VM에 배포** — cloud_relay.py 업로드 후 상시 실행(systemd/nohup). *접속정보(공인IP·SSH키)가 없어 미실행.*
2. **오라클 인바운드 포트 개방** — 콘솔 Security List Ingress + VM 방화벽에서 릴레이 포트(예 8090) TCP 허용.
3. **HTTPS** — 토큰이 URL에 실려 HTTP만이면 도청 위험. 앞단에 caddy/nginx 리버스프록시로 HTTPS 권장.
4. **소스 확정** — 지금 모니터는 **PC 에지서버**가 생성. 폰이 서버인 구성이면 폰엔 웹모니터가 없어 (a)PC경유 or (b)폰앱에 모니터/푸시 추가 필요.

**재개 방법 (오라클 VM 준비되면)**
```bash
# [오라클 VM] 포트 개방 후
scp web/cloud_relay.py ubuntu@<오라클IP>:~/
ssh ubuntu@<오라클IP> "PUSH_TOKEN=$(openssl rand -hex 16) VIEW_TOKEN=$(openssl rand -hex 16) RELAY_PORT=8090 nohup python3 cloud_relay.py &"
# [로컬 PC] edge_serve.py(모니터) 실행 중인 상태에서
RELAY_URL=http://<오라클IP>:8090  PUSH_TOKEN=<위 PUSH>  python web/relay_push.py
# [사장님]  http://<오라클IP>:8090/monitor?token=<위 VIEW>
```
자세한 절차·보안: [docs/REMOTE_MONITOR.md](docs/REMOTE_MONITOR.md)

---

## 3. 파일 지도
| 파일 | 역할 |
|---|---|
| `android/app/src/main/java/com/example/nailar/edge/` | 폰 네이티브 에지서버(NailOnnx·EdgeServer·EdgeServerActivity) |
| `tools/onnx_edge/onnx_infer.py` · `onnx_serve.py` | torch-free 추론 레퍼런스 + 소켓서버(루트 B) |
| `tools/onnx_edge/export_320.py` · `quantize_int8.py` | 320 재export · INT8 양자화(시도) |
| `web/cloud_relay.py` · `web/relay_push.py` | **원격 모니터 릴레이 + 푸셔** |
| `web/nails_seg.onnx` (640) · `web/nails_seg_320.onnx`(gitignore) | 손톱 세그 모델 |
| `docs/PHONE_EDGE_SERVER_PLAN.md` · `docs/REMOTE_MONITOR.md` | 상세 계획/배포 문서 |

## 4. 다음 할 일
- [ ] **오라클 VM에 릴레이 배포**(위 재개 방법) + HTTPS → 사장님 원격 시청 완성 ← *이게 미완의 핵심*
- [ ] 안경↔폰 연속 스트림 안정화(안경 착용 + 폰 고정IP/핫스팟)
- [ ] (여력) 폰앱에 웹모니터/푸시 내장 → 폰서버 구성에서도 원격시청
- [ ] (여력) INT8 혼합정밀 + QNN EP로 640 정확도 유지한 가속
- [ ] 펜 가림 soft penDim B단계(브러시 도착 후) — 별도 브랜치 `feat/pen-occlusion`
