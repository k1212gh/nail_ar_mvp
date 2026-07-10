#!/usr/bin/env python3
"""frame_server.py — serve camera frames to the glasses (NET MODE display client).

The glasses can't use their own camera (blocked), so an external source (this PC,
standing in for a phone) streams frames; the glasses fetch, detect, and render.
Reach it over USB with:  adb reverse tcp:8080 tcp:8080  -> glasses GET 127.0.0.1:8080/frame.jpg

Modes:
  --image PATH     serve a static JPEG (re-read each request; swap the file to change)
  --webcam [ID]    serve live frames from a PC webcam (needs a working cv2 camera)
Usage:
  python frame_server.py --image samples/focus_test/hand_small.jpg --port 8080
  python frame_server.py --webcam 0 --port 8080
"""
import argparse
import http.server
import threading
import time
import sys

_lock = threading.Lock()
_frame_jpeg = b""
_static_path = None


def _static_bytes():
    with open(_static_path, "rb") as f:
        return f.read()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/frame"):
            data = _static_bytes() if _static_path else _latest()
            if not data:
                self.send_response(503); self.end_headers(); return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"frame_server: GET /frame.jpg")

    def log_message(self, *a):
        pass


def _latest():
    with _lock:
        return _frame_jpeg


def _webcam_loop(cam_id):
    import cv2
    global _frame_jpeg
    cap = cv2.VideoCapture(cam_id, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cap.isOpened():
        print(f"webcam {cam_id} not opened", file=sys.stderr); return
    print(f"webcam {cam_id} streaming @ {int(cap.get(3))}x{int(cap.get(4))}...")
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05); continue
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if ok:
            with _lock:
                global _frame_jpeg
                _frame_jpeg = buf.tobytes()
        time.sleep(0.03)


def main():
    global _static_path
    ap = argparse.ArgumentParser()
    ap.add_argument("--image")
    ap.add_argument("--webcam", nargs="?", const=0, type=int)
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    if a.image:
        _static_path = a.image
        print(f"serving static image: {a.image}")
    elif a.webcam is not None:
        threading.Thread(target=_webcam_loop, args=(a.webcam,), daemon=True).start()
    else:
        print("need --image PATH or --webcam [ID]"); sys.exit(2)
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", a.port), Handler)
    print(f"frame_server on :{a.port}  (adb reverse tcp:{a.port} tcp:{a.port}; glasses GET http://127.0.0.1:{a.port}/frame.jpg)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
