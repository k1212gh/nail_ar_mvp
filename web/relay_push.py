"""로컬 푸셔 — 로컬 모니터의 최신 프레임을 오라클 릴레이로 POST(아웃바운드).

기본 소스는 PC 에지서버 모니터(edge_serve.py)의 /last.jpg. 표준 라이브러리만 사용.

실행(로컬 PC):
  RELAY_URL=http://<오라클IP>:8090 PUSH_TOKEN=xxxx python web/relay_push.py
  (선택) MON_SRC=http://127.0.0.1:8080/last.jpg  PUSH_FPS=5
"""
import os
import time
import urllib.request

SRC = os.environ.get("MON_SRC", "http://127.0.0.1:8080/last.jpg")
RELAY = os.environ.get("RELAY_URL", "").rstrip("/")
TOKEN = os.environ.get("PUSH_TOKEN", "changeme-push")
FPS = float(os.environ.get("PUSH_FPS", "5"))


def main():
    if not RELAY:
        raise SystemExit("RELAY_URL 환경변수 필요 (예: http://<오라클IP>:8090)")
    print(f"[push] {SRC}  ->  {RELAY}/push  @ {FPS}fps")
    url = f"{RELAY}/push?token={TOKEN}"
    period = 1.0 / max(0.1, FPS)
    sent, err, last_log = 0, 0, 0.0
    while True:
        t0 = time.time()
        try:
            jpg = urllib.request.urlopen(SRC, timeout=3).read()
            if jpg:
                req = urllib.request.Request(url, data=jpg,
                                             headers={"Content-Type": "image/jpeg"}, method="POST")
                urllib.request.urlopen(req, timeout=3).read()
                sent += 1
        except Exception as e:
            err += 1
            if time.time() - last_log > 3:
                print("push err:", e); last_log = time.time()
        if time.time() - last_log > 5:
            print(f"[push] sent={sent} err={err}"); last_log = time.time()
        dt = period - (time.time() - t0)
        if dt > 0:
            time.sleep(dt)


if __name__ == "__main__":
    main()
