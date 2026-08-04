"""데모 피더 — 카메라(또는 샘플 이미지)를 edge_serve /infer 로 POST.
edge_serve가 YOLO 검출 후 모니터(/last.jpg)를 갱신 → relay_push가 오라클로 송출.

  CAM=0            카메라 인덱스 (기본 0). FEED_IMG 지정 시 그 이미지를 반복 송출.
  FEED_IMG=path    카메라 대신 정적 이미지 루프 (검출 확실히 보장용)
  INFER_URL=https://127.0.0.1:8443/infer
  FEED_FPS=5
"""
import os, sys, time, ssl, urllib.request
import cv2

CAM = os.environ.get("CAM", "0")
URL = os.environ.get("INFER_URL", "https://127.0.0.1:8443/infer")
FPS = float(os.environ.get("FEED_FPS", "5"))
IMG = os.environ.get("FEED_IMG", "")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def frames():
    if IMG:
        im = cv2.imread(IMG)
        if im is None:
            print("이미지 열기 실패:", IMG); sys.exit(1)
        print(f"[feed] 정적 이미지 루프: {IMG} {im.shape}")
        while True:
            yield im.copy()
    else:
        idx = int(CAM)
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print(f"카메라 인덱스 {idx} 열기 실패"); sys.exit(2)
        print(f"[feed] 카메라 {idx} 열림")
        while True:
            ok, f = cap.read()
            if not ok:
                time.sleep(0.1); continue
            yield f


period = 1.0 / max(0.1, FPS)
sent = err = 0
tlog = 0.0
for f in frames():
    t0 = time.time()
    try:
        ok, jpg = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 80])
        req = urllib.request.Request(URL, data=jpg.tobytes(),
                                     headers={"Content-Type": "image/jpeg"}, method="POST")
        urllib.request.urlopen(req, timeout=4, context=ctx).read()
        sent += 1
    except Exception as e:
        err += 1
        if time.time() - tlog > 3:
            print("feed err:", e); tlog = time.time()
    if time.time() - tlog > 3:
        print(f"[feed] sent={sent} err={err}"); tlog = time.time()
    dt = period - (time.time() - t0)
    if dt > 0:
        time.sleep(dt)
