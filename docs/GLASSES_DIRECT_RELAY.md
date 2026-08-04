# 안경 직접 중계 — PC 없이 안경이 원격 모니터로 송출

기존 경로는 안경 화면을 **PC가 대신 캡처해서** 릴레이로 올렸다.

```
[기존]  안경 --USB--> PC (adb screenrecord + web/relay_compose_push.py) --인터넷--> 릴레이 --> 사장님
[직접]  안경 --WiFi--> 릴레이 --> 사장님                                (PC가 사슬에서 빠짐)
```

구현: `Nail/Assets/Scripts/RelayPusher.cs` (안경 앱 안), 설정은 `nail_calib.json` 으로 주입.

---

## 1. 무엇을 보내나

**전용 캡처 카메라**가 AR 캔버스(카메라 피드 + 손톱 오버레이)를 단안으로 RenderTexture에 다시 그린다.
`EdgeClient` 가 검출 서버로 보내는 것은 *카메라 원본*이라 오버레이가 없다 — 사장님이 봐야 하는 건
손톱 위에 디자인이 얹힌 화면이므로 캔버스를 통째로 그려야 한다.

> **왜 `ScreenCapture.CaptureScreenshotIntoRenderTexture` 가 아닌가 (삽질 기록)**
> 처음엔 그 API로 백버퍼를 잡았다. 송출은 12fps로 멀쩡히 되는데 **화면이 완전 검정으로만 나갔다.**
> 같은 순간 `adb shell screencap` 은 카메라 피드가 또렷이 찍혔으니, 안경 화면이 검은 게 아니라
> 그 API가 XR 스테레오 합성 결과를 못 가져오는 것이었다. AR 캔버스는 World Space(카메라 앞
> `m_Depth` 에 떠 있는 판)라서, 카메라를 하나 더 두고 그 캔버스를 단안으로 다시 그리면 XR 합성을
> 거치지 않고 같은 그림을 얻는다. 캡처 카메라는 `stereoTargetEye=None` 이라 안경 화면에는 끼어들지 않는다.

프레임당 처리는 **3단 파이프라인**이다. 각 단이 서로를 기다리지 않는다:

```
[메인]   전용 캡처 카메라가 AR 캔버스를 RenderTexture에 단안 렌더 (안경 화면엔 영향 없음)
         → AsyncGPUReadback → raw 복사(≈0.5ms)          ← GPU 스톨 없음
[인코더] RGB24 raw → JPEG                                ← X3에서 384x288 기준 20~65ms
[업로더] JPEG → keep-alive HTTP POST /push (스레드 3개)   ← 인터넷 왕복 90~160ms
```

단을 나눈 것은 실측 때문이다. 처음엔 인코딩을 메인 스레드에서 했고(5.6fps), 워커로 옮겨도
인코딩과 업로드가 한 스레드에서 직렬이라 **(인코딩 100ms + 왕복 100ms) = 4.6fps** 에 묶였다.
`web/relay_compose_push.py` 가 `WORKERS=4` 로 푼 것과 똑같은 문제 — 지연을 겹쳐야 fps가 산다.
3단으로 나눈 뒤 **12.1fps**(err=0).

큐는 최신 우선이다. 라이브 모니터라 **신선도가 우선**이므로 밀린 프레임은 버린다
(`relay_compose_push.py` 의 최신우선 큐와 같은 철학).

### 실측 (RayNeo X3, 매장 WiFi, 오라클 릴레이 RTT 42ms)

| 구성 | 결과 |
|---|---|
| 메인 스레드 인코딩, 640px | 5.6fps (enc 56~139ms가 렌더 루프를 잡음) |
| 워커 1개에서 인코딩+업로드 직렬, 640px | 4.6fps |
| **3단 파이프라인, 480px** | 9.2fps |
| **3단 파이프라인, 384px** | **12.1fps** ← 권장 |

## 2. 전제조건

| 조건 | 확인 방법 |
|---|---|
| 안경이 **WiFi에 연결**되어 인터넷이 됨 | `adb -s <안경> shell ip -o -f inet addr show` 에 `wlan0` 이 보여야 함 |
| 릴레이가 떠 있음 | `curl http://<릴레이IP>:8090/healthz` → `ok` |
| 릴레이 `PUSH_TOKEN` 을 앎 | VM에서 `docker inspect nail-relay` 의 env |

USB로만 연결된 상태(= `lo` 만 있는 상태)에서는 안경이 인터넷에 못 나가므로 이 기능은 동작하지 않는다.

## 3. 켜기

```bash
# 안경 WiFi가 꺼져 있으면 먼저 켠다 (저장된 매장 AP에 자동으로 붙는다)
adb -s <안경시리얼> shell svc wifi enable

python web/push_calib.py serial=<안경시리얼> pkg=com.DefaultCompany.NailGuide \
  relayOn=1 relayUrl=http://161.33.176.78:8090 relayToken=<PUSH_TOKEN> \
  relayFps=20 relayW=384 relayQ=68
```

**완전 무선**(PC를 아예 빼려면) 검출도 폰으로 넘긴다 — 위 인자에 다음을 덧붙인다:

```bash
  useSocket=1 sockHost=<폰IP> sockPort=8444
```

0.7초 안에 앱이 반영한다(재시작 불필요). 끄기는 `relayOn=0`.

> `serial=` 은 안경과 폰이 동시에 연결되어 있을 때 필수다. 없으면 adb가 대상을 못 고른다.
> 토큰은 로그에 `***` 로만 찍히지만, **기기의 `nail_calib.json` 에는 평문으로 남는다** (§5).

## 4. 옵션

| 키 | 기본 | 뜻 |
|---|---|---|
| `relayOn` | 0 | 1=송출, 0=중지 |
| `relayUrl` | — | `http://<릴레이IP>:8090` |
| `relayToken` | — | 릴레이 `PUSH_TOKEN` |
| `relayFps` | 12 | 송출 fps **목표**. 실제 fps는 인코딩 속도가 정한다(아래 `relayW` 참고) |
| `relayW` | 480 | 전송 가로 px (세로는 종횡비 유지). **fps를 지배하는 값** — 인코딩 비용이 픽셀 수에 비례한다 |
| `relayQ` | 70 | JPEG 품질 |
| `relayFlipY` | 0 | 화면이 거꾸로 보이면 1 (플랫폼별 RenderTexture 원점 차이 보정) |

출력 종횡비는 안경 한쪽 눈 기준(`Screen.width/2 : Screen.height`)이다. 사장님 모니터엔 한쪽 눈이면
충분하다 — PC 컴포지터가 ffmpeg `crop=iw/2:ih:0:0` 로 하던 것과 같은 판단이다.

**설정은 기기에 저장된다(PlayerPrefs).** `push_calib.py` 는 *모든* 필드를 leave 센티널로 채워 파일을
통째로 덮어쓰므로, 다른 용도로 calib를 한 번만 밀어도 `relayToken` 이 `""` 로 지워진다. 앱이 살아있는
동안은 `""`=leave 규약으로 버티지만 **재시작하면 중계가 죽는다**(실제로 겪었다). 그래서 마지막 설정을
기기에 남겨 재시작 후 복원한다. 토큰도 함께 남으므로 노출 수준은 calib 파일과 같다.

## 5. 한계 — 알고 쓸 것

- **YOLO 검출 패널이 사라진다.** 컴포지터가 붙이던 오른쪽 `YOLO DETECT` 패널은 PC에서 합성하던 것이라,
  안경 직접 송출에서는 안경 화면 하나만 나간다. 검출 화면까지 보려면 기존 PC 경로를 쓴다.
- **토큰이 기기에 평문으로 남는다.** `/sdcard/Android/data/<pkg>/files/nail_calib.json` 에 저장되고,
  릴레이도 HTTP(평문)다. `web/cloud_relay.py` 상단 주석과 같은 전제 — 실운영은 릴레이 앞단 HTTPS +
  토큰 회전이 필요하다.
- **안경이 인코딩·업로드를 떠안는다.** 발열과 배터리 소모가 늘어난다. `relayFps` / `relayW` 로 조절한다.
- **매장 WiFi 상행 대역폭을 쓴다.** 640px·q70·12fps 기준 대략 1~2 Mbps.

## 6. 문제 해결

로그(`adb -s <안경> logcat -s Unity`)에 5초마다 통계가 찍힌다:

```
[Relay] 12.1fps sent=830 err=0 drop=11 enc=59ms net=126ms 384x288@q68 up=3
```

`enc`(인코딩 ms)와 `net`(왕복 ms) 중 큰 쪽이 병목이다. `enc`가 크면 `relayW`를 낮추고,
`net`이 크면 업로드 스레드 수(`RelayPusher.workers`, 기본 3)를 늘린다.

| 증상 | 원인 |
|---|---|
| `[Relay] endpoint -> ... (token 비어있음!)` | `relayToken` 미설정 — 송출 자체를 시작하지 않는다 |
| `err` 만 계속 증가 | 토큰 불일치(릴레이가 403+close) 또는 안경이 릴레이에 도달 못 함 |
| `sent` 는 느는데 **화면이 완전 검정** | 프레임 크기를 보라. 384x288 기준 정상은 5~10KB, 2KB 근처면 단색이다. 캡처 카메라가 캔버스를 못 그리는 것(`Camera.main` 없음, 캔버스가 다른 레이어) — `[Relay] 캡처 카메라 생성` 로그가 떴는지 확인한다 |
| `sent` 는 느는데 모니터가 검음 | 다른 송출자(PC 컴포지터)가 같은 릴레이를 덮어쓰는 중일 수 있다 |
| 잘 되다가 앱 재시작 후 멎음 | 예전 버전의 증상. 지금은 PlayerPrefs로 복원된다(§4). `[Relay] 저장된 설정 복원` 로그 확인 |
| 로그가 아예 안 찍히고 프레임이 끊김 | **안경 화면이 꺼진(Dozing) 상태**다. Unity가 백그라운드에서 렌더를 멈추면 캡처할 백버퍼가 없다. `adb shell svc power stayon true` 로 화면을 유지한다 |
| 화면이 거꾸로 | `relayFlipY=1` |
| `drop` 이 `sent` 만큼 큼 | 상행 대역폭 부족 — `relayFps`/`relayW` 를 낮춘다 |
| `AsyncGPUReadback 미지원` 경고 | 동기 ReadPixels 폴백으로 동작(프레임 스톨). fps를 낮춰 쓴다 |

## 7. 관련 파일

- `Nail/Assets/Scripts/RelayPusher.cs` — 캡처·인코딩·업로드
- `Nail/Assets/Scripts/NailARController.cs` — `CalibData` 의 `relay*` 필드, 런타임 컴포넌트 생성
- `web/push_calib.py` — 설정 주입(`serial=`, `relay*`)
- `web/cloud_relay.py` — 릴레이(수신 `/push`, 시청 `/stream`)
- `web/relay_compose_push.py` — 기존 PC 경유 컴포지터(검출 패널 합성)
