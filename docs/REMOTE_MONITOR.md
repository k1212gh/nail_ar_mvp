# 원격 모니터 (오라클 클라우드 릴레이)

사장님이 **원격에서** 실시간 모니터(카메라+검출 오버레이)를 보게 하는 릴레이. 로컬은 아웃바운드만
하므로 NAT/방화벽 뒤에서도 동작한다.

```
[PC 에지서버 /monitor(8080)] --GET /last.jpg--> [relay_push.py(로컬)] --POST /push--> [오라클 VM cloud_relay.py] <--GET /monitor-- [사장님 브라우저]
```

- `web/cloud_relay.py` — 오라클 VM에서 실행(표준 라이브러리만, 의존성 0). 토큰 인증.
- `web/relay_push.py` — 로컬 PC에서 실행. 로컬 모니터 최신 프레임을 릴레이로 POST.
- 로컬 검증 완료: push(정상)=200 / push(오토큰)=403 / frame(정상)=200 / frame(오토큰)=403 / monitor=200.

## 1. 오라클 VM 준비
1. **인바운드 포트 개방**: 오라클 콘솔 → VCN → Security List → Ingress에 TCP `8090` 허용(0.0.0.0/0 또는 사장님 IP만).
2. **VM 방화벽**: `sudo firewall-cmd --add-port=8090/tcp --permanent && sudo firewall-cmd --reload`
   (Ubuntu/iptables면 `sudo iptables -I INPUT -p tcp --dport 8090 -j ACCEPT`)
3. Python3 있는지 확인(`python3 --version`).

## 2. 릴레이 실행 (오라클 VM)
```bash
scp web/cloud_relay.py ubuntu@<오라클공인IP>:~/         # 로컬에서 업로드
ssh ubuntu@<오라클공인IP>
PUSH_TOKEN='길고랜덤한값1' VIEW_TOKEN='길고랜덤한값2' RELAY_PORT=8090 python3 cloud_relay.py
#   (백그라운드 상시: nohup … & 또는 systemd 서비스로)
```

## 3. 로컬 푸셔 실행 (PC — 모니터가 프레임 만드는 그 PC)
```powershell
# 먼저 edge_serve.py(모니터) 가 돌고 있어야 함(안경/폰 프레임이 흘러 /last.jpg 생성)
$env:RELAY_URL="http://<오라클공인IP>:8090"; $env:PUSH_TOKEN="길고랜덤한값1"; $env:PUSH_FPS="5"
.\.venv\Scripts\python.exe web\relay_push.py
```

## 4. 사장님 시청
```
http://<오라클공인IP>:8090/monitor?token=길고랜덤한값2
```
이 링크만 전달. VIEW 토큰만 알려주고 PUSH 토큰은 비밀로.

## ⚠️ 보안
- 토큰이 URL에 실려 **HTTP만이면 도청 위험**. 실제 운영은 앞단에 **HTTPS**(caddy 한 줄 리버스프록시 권장):
  `caddy reverse-proxy --from https://<도메인> --to localhost:8090` (도메인+인증서 자동).
- 토큰은 길고 랜덤하게(`openssl rand -hex 16`). 데모 끝나면 릴레이 종료.
- 카메라 실시간 영상 노출임을 인지하고, 뷰 링크는 사장님에게만.

## 튜닝
- `PUSH_FPS`(기본 5) — 업로드 대역폭/부드러움 조절. 모니터용이라 3~8이면 충분.
- 프레임 스테일 판정 `MAX_AGE`(relay 15초) — 로컬 끊기면 사장님 화면에 '대기/끊김' 표시.
- 폰이 서버인 경우: 폰엔 웹 모니터가 없음 → PC 에지서버 경유 모니터를 소스로 쓰거나, 폰앱에 모니터/푸시 추가(후속).
