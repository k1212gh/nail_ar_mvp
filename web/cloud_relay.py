"""원격 모니터 릴레이 — 오라클 클라우드 VM(공인 IP)에서 실행.

로컬(PC/폰)이 최신 프레임을 여기로 POST(아웃바운드) → 사장님은 브라우저로 시청.
NAT/방화벽 뒤에서도 됨(로컬은 아웃바운드만). 표준 라이브러리만 사용 → VM에 Python만 있으면 실행.

실행(오라클 VM):
  PUSH_TOKEN=xxxx VIEW_TOKEN=yyyy RELAY_PORT=8090 python3 cloud_relay.py
  - 오라클 '보안 목록' + VM 방화벽(iptables/firewalld)에서 RELAY_PORT 인바운드 개방
사장님 시청:  http://<오라클공인IP>:8090/monitor?token=<VIEW_TOKEN>
로컬 푸시:    relay_push.py 가 /push?token=<PUSH_TOKEN> 로 전송

시청 경로 2가지:
  /stream  — MJPEG multipart(한 커넥션으로 서버가 프레임을 밀어줌). 폴링 지연 없음 → 부드러움. (기본)
  /frame   — 단발 JPEG(폴링용, 호환/폴백).

⚠️ 토큰은 URL에 노출되므로 HTTP만으로는 도청 위험 → 실제 운영은 앞단에 HTTPS(caddy/nginx) 권장.
"""
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("RELAY_PORT", "8090"))
PUSH_TOKEN = os.environ.get("PUSH_TOKEN", "changeme-push")
VIEW_TOKEN = os.environ.get("VIEW_TOKEN", "changeme-view")
MAX_AGE = 15.0  # 초 — 이보다 오래된 프레임이면 '연결 끊김'으로 처리

_L = {"jpeg": b"", "ts": 0.0, "n": 0, "lock": threading.Lock()}

_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Nail-AR 원격 모니터</title>
<style>html,body{margin:0;background:#0c0c0c;color:#0f0;font-family:monospace;text-align:center}
#s{padding:6px;font-size:14px;color:#0ff}img{max-width:100%;height:auto}</style>
</head><body><div id=s>스트림 연결 중…</div><img id=v src="/stream?token=__TOKEN__">
<script>
const T="__TOKEN__",v=document.getElementById('v'),s=document.getElementById('s');
v.onload=()=>{s.textContent='LIVE (stream)';};
v.onerror=()=>{s.textContent='끊김 — 3초 후 재연결…';setTimeout(()=>{v.src='/stream?token='+T+'&t='+Date.now();},3000);};
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _q(self, key):
        return parse_qs(urlparse(self.path).query).get(key, [""])[0]

    def do_POST(self):
        if urlparse(self.path).path != "/push":
            self.send_error(404); return
        if self._q("token") != PUSH_TOKEN:
            self.send_error(403, "bad push token"); return
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n) if n else b""
        if not body:
            self.send_error(400, "empty"); return
        with _L["lock"]:
            _L["jpeg"], _L["ts"], _L["n"] = body, time.time(), _L["n"] + 1
        self._ok(b"ok", "text/plain")

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/monitor", "/"):
            if self._q("token") != VIEW_TOKEN:
                self.send_error(403, "token required"); return
            self._ok(_HTML.replace("__TOKEN__", VIEW_TOKEN).encode(), "text/html; charset=utf-8")
        elif p == "/stream":
            if self._q("token") != VIEW_TOKEN:
                self.send_error(403, "bad view token"); return
            self._stream()
        elif p == "/frame":
            if self._q("token") != VIEW_TOKEN:
                self.send_error(403, "bad view token"); return
            with _L["lock"]:
                jpg, age = _L["jpeg"], time.time() - _L["ts"]
            if not jpg or age > MAX_AGE:
                self.send_error(503, "no recent frame"); return
            self._ok(jpg, "image/jpeg")
        elif p == "/healthz":
            self._ok(b"ok", "text/plain")
        else:
            self.send_error(404)

    def _stream(self):
        # MJPEG multipart: 한 커넥션으로 새 프레임이 생길 때마다 밀어준다(폴링 RTT 제거).
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frameboundary")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        last_n = -1
        try:
            while True:
                with _L["lock"]:
                    jpg, n, ts = _L["jpeg"], _L["n"], _L["ts"]
                if n != last_n and jpg and (time.time() - ts) <= MAX_AGE:
                    last_n = n
                    self.wfile.write(b"--frameboundary\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg))
                    self.wfile.write(jpg)
                    self.wfile.write(b"\r\n")
                else:
                    time.sleep(0.004)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _ok(self, data, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"[relay] :{PORT}  view=/monitor?token={VIEW_TOKEN}  (stream+poll)  push=/push?token={PUSH_TOKEN}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
