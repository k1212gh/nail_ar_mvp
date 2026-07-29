"""원격 모니터 릴레이 — 오라클 클라우드 VM(공인 IP)에서 실행.

로컬(PC/폰)이 최신 프레임을 여기로 POST(아웃바운드) → 사장님은 브라우저로 시청.
NAT/방화벽 뒤에서도 됨(로컬은 아웃바운드만). 표준 라이브러리만 사용 → VM에 Python만 있으면 실행.

실행(오라클 VM):
  PUSH_TOKEN=xxxx VIEW_TOKEN=yyyy RELAY_PORT=8090 python3 cloud_relay.py
  - 오라클 '보안 목록' + VM 방화벽(iptables/firewalld)에서 RELAY_PORT 인바운드 개방
사장님 시청:  http://<오라클공인IP>:8090/monitor?token=<VIEW_TOKEN>
로컬 푸시:    relay_push.py 가 /push?token=<PUSH_TOKEN> 로 전송

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
#s{padding:8px;font-size:16px;color:#0ff}img{max-width:100%;height:auto}</style>
</head><body><div id=s>연결 중…</div><img id=v>
<script>
const T="__TOKEN__",v=document.getElementById('v'),s=document.getElementById('s');
let ok=0,fail=0;
v.onload=()=>{ok++;s.textContent='LIVE  frames:'+ok;setTimeout(next,50);};
v.onerror=()=>{fail++;s.textContent='대기/끊김… (재시도 '+fail+')';setTimeout(next,700);};
function next(){v.src='/frame?token='+T+'&t='+Date.now();}
next();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
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
    print(f"[relay] :{PORT}  view=/monitor?token={VIEW_TOKEN}  push=/push?token={PUSH_TOKEN}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
