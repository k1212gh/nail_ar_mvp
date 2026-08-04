"""컴포지터 v3 — 안경 AR(screenrecord) + 검출뷰, 병렬 큐 푸시로 인터넷 지연 겹치기.

소스: AR(screenrecord→ffmpeg 스레드) · DET(edge_serve 폴링 스레드) 각각 최신프레임 유지.
합성 스레드가 큐에 넣고, N개 워커가 keep-alive 연결로 동시에 오라클에 POST → 지연(160ms) 겹쳐 fps↑.
큐는 최신 우선(꽉 차면 오래된 것 버림) — 라이브 모니터라 신선도 우선.

  RELAY_URL, PUSH_TOKEN 필수. ADB, FFMPEG. COMPOSE_FPS(20), WORKERS(4), JPEG_Q(72), PANEL_H(440).
"""
import os, time, threading, subprocess, queue
from urllib.parse import urlparse
import http.client
import numpy as np, cv2, urllib.request

ADB = os.environ.get("ADB", "adb")
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
DET_URL = os.environ.get("DET_URL", "http://127.0.0.1:8080/last.jpg")
RELAY = os.environ.get("RELAY_URL", "").rstrip("/")
TOKEN = os.environ.get("PUSH_TOKEN", "")
COMPOSE_FPS = float(os.environ.get("COMPOSE_FPS", "20"))
WORKERS = int(os.environ.get("WORKERS", "4"))
JPEG_Q = int(os.environ.get("JPEG_Q", "72"))
AR_H = int(os.environ.get("PANEL_H", "440"))
AR_W = int(AR_H * 640 / 480)
if not RELAY:
    raise SystemExit("RELAY_URL 필요")
u = urlparse(RELAY)
HOST, PORT = u.hostname, (u.port or 80)
PATH = f"/push?token={TOKEN}"

latest = {"ar": None, "det": None, "arn": 0, "lock": threading.Lock()}
q = queue.Queue(maxsize=6)
stat = {"sent": 0, "err": 0}


def read_exact(f, n):
    b = b""
    while len(b) < n:
        c = f.read(n - len(b))
        if not c:
            return None
        b += c
    return b


def ar_thread():
    fb = AR_W * AR_H * 3
    while True:
        adb_p = ff = None
        try:
            adb_p = subprocess.Popen(
                [ADB, "exec-out", "screenrecord", "--output-format=h264",
                 "--time-limit", "170", "--bit-rate", "8M", "-"], stdout=subprocess.PIPE)
            ff = subprocess.Popen(
                [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "h264", "-i", "-",
                 "-vf", f"crop=iw/2:ih:0:0,scale={AR_W}:{AR_H}",
                 "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                stdin=adb_p.stdout, stdout=subprocess.PIPE)
            adb_p.stdout.close()
            while True:
                buf = read_exact(ff.stdout, fb)
                if buf is None:
                    break
                img = np.frombuffer(buf, np.uint8).reshape(AR_H, AR_W, 3)
                with latest["lock"]:
                    latest["ar"] = img; latest["arn"] += 1
        except Exception as e:
            print("ar err:", e, flush=True)
        finally:
            for p in (ff, adb_p):
                try: p and p.kill()
                except Exception: pass
        time.sleep(0.3)


def det_thread():
    while True:
        try:
            b = urllib.request.urlopen(DET_URL, timeout=2).read()
            im = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
            if im is not None:
                with latest["lock"]:
                    latest["det"] = im
        except Exception:
            pass
        time.sleep(0.03)


def push_worker():
    conn = None
    while True:
        jpg = q.get()
        for _ in range(2):
            try:
                if conn is None:
                    conn = http.client.HTTPConnection(HOST, PORT, timeout=5)
                conn.request("POST", PATH, body=jpg,
                             headers={"Content-Type": "image/jpeg", "Connection": "keep-alive"})
                conn.getresponse().read()
                stat["sent"] += 1
                break
            except Exception:
                try: conn.close()
                except Exception: pass
                conn = None
                stat["err"] += 1
        q.task_done()


def panel(im, txt, color):
    if im is None:
        im = np.zeros((AR_H, AR_H, 3), np.uint8)
        cv2.putText(im, "(connecting...)", (14, AR_H // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 255), 2)
    else:
        h, w = im.shape[:2]
        im = cv2.resize(im, (max(1, int(w * AR_H / h)), AR_H))
    cv2.rectangle(im, (0, 0), (im.shape[1], 28), (0, 0, 0), -1)
    cv2.putText(im, txt, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return im


threading.Thread(target=ar_thread, daemon=True).start()
threading.Thread(target=det_thread, daemon=True).start()
for _ in range(WORKERS):
    threading.Thread(target=push_worker, daemon=True).start()

print(f"[v3] compose{COMPOSE_FPS}fps workers={WORKERS} q{JPEG_Q} -> {RELAY}", flush=True)
period = 1.0 / COMPOSE_FPS
tlog = time.time(); last_sent = 0; last_arn = 0
while True:
    t0 = time.time()
    with latest["lock"]:
        ar = None if latest["ar"] is None else latest["ar"]
        det = None if latest["det"] is None else latest["det"]
        arn = latest["arn"]
    frame = cv2.hconcat([panel(ar, "GLASSES AR (real render)", (0, 255, 120)),
                         panel(det, "YOLO DETECT", (0, 200, 255))])
    ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q])
    b = jpg.tobytes()
    try:
        q.put_nowait(b)
    except queue.Full:
        try: q.get_nowait()
        except Exception: pass
        try: q.put_nowait(b)
        except Exception: pass
    now = time.time()
    if now - tlog >= 3:
        dt = now - tlog
        print(f"[v3] push={(stat['sent']-last_sent)/dt:.1f}fps AR입력={(arn-last_arn)/dt:.1f}fps err={stat['err']} qsize={q.qsize()} bytes={len(b)}", flush=True)
        tlog = now; last_sent = stat["sent"]; last_arn = arn
    dt = period - (time.time() - t0)
    if dt > 0:
        time.sleep(dt)
