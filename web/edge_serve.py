"""에지 추론 서버 (Phase 0a) — HTTPS 정적 + POST /infer.

폰(또는 글래스)이 카메라 프레임(JPEG)을 보내면, PC가 YOLOv8-seg로 손톱을 인식하고
손톱별 기하(중심·축·길이·폭·외곽)를 JSON으로 돌려준다. 무거운 추론은 PC가 하므로
브라우저 ONNX(best 0.00) 문제를 우회하고, 글래스도 같은 방식으로 오프로드한다(특허 41/42).

실행:  python web/edge_serve.py
폰:    https://<PC-IP>:8443/edge.html   (정적 페이지가 /infer 로 프레임 전송)
"""
from __future__ import annotations

import collections
import functools
import http.server
import json
import os
import socket
import socketserver
import ssl
import struct
import sys
import threading
import time
import urllib.parse

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# ROOT(=src/config 용), HERE(=serve.py 용) 둘 다 경로에 보장 (어디서 실행해도 동작)
for _p in (ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import serve as S                       # 같은 폴더: 인증서·LAN IP 재사용
from config import GeomConfig
from src.geometry import compute_geometry
from src.log_setup import setup_logging
from src.yolo_nail_seg import YoloNailSegmenter
from src.card_scale import detect_card, nail_mm   # 신용카드 기준물 실치수 스케일
from src.card_calib import scale_correction, fold_correction   # 카드 실측 → mm 추정 보정

log = setup_logging("INFO", to_file=False)
PORT = 8443
_GEOM = GeomConfig()
_MODEL_PATH = os.path.join(ROOT, "models", "nails_seg_s_yolov8_v1.pt")
_seg: YoloNailSegmenter | None = None   # 지연 로드(첫 요청 때)


def _ensure_model():
    global _seg
    if _seg is None:
        log.info("YOLO 손톱 모델 로딩(에지)…")
        _seg = YoloNailSegmenter(_MODEL_PATH, conf=0.30, imgsz=640)
    return _seg


# --- MediaPipe hand-landmark + Kalman tracking (stable, all-5-fingers, temporal) ---
from config import HandConfig, TrackConfig            # noqa: E402
from src.hand_landmarks import HandLandmarkDetector    # noqa: E402
from src.tracking import NailTracker                   # noqa: E402
from src.geometry import geometry_from_roi             # noqa: E402

MODE = os.environ.get("NAIL_MODE", "hands")            # "hands" | "yolo"
FACING = os.environ.get("NAIL_FACING", "off")          # "off" | "back"(nails-only) | "palm"
EXTENDED = os.environ.get("NAIL_EXTENDED", "on")       # "on" = 편 손가락만(주먹 제외) | "off"
_STABLE_PX = float(os.environ.get("NAIL_STABLE_PX", "3.0"))   # 손 정지 판정 속도 임계(px/frame)
_hand: HandLandmarkDetector | None = None
_trk: NailTracker | None = None


def _ensure_hand():
    global _hand, _trk
    if _hand is None:
        hc = HandConfig()
        for p in (os.path.join(ROOT, "web", "hand_landmarker.task"),
                  os.path.join(ROOT, "models", "hand_landmarker.task")):
            if os.path.isfile(p):
                hc.model_path = p
                break
        log.info("MediaPipe HandLandmarker 로딩(에지): %s", hc.model_path)
        _hand = HandLandmarkDetector(hc)
        _trk = NailTracker(TrackConfig())
    return _hand, _trk


def _infer_hands(img) -> list:
    """MediaPipe로 손당 5손가락 손톱 ROI → 칼만 평활(이전 프레임 반영)."""
    det, trk = _ensure_hand()
    rois = det.detect(img, None)          # VIDEO 모드, 내부 추적, 5손가락/손
    nails, seen = [], set()
    for roi in rois:
        f = getattr(roi, "facing", 0.0)
        if FACING == "back" and f <= 0:   # 손톱(손등)이 카메라 향할 때만
            continue
        if FACING == "palm" and f >= 0:
            continue
        if EXTENDED == "on" and getattr(roi, "extended", 1.0) < 0.5:  # 굽힌 손가락(주먹) 제외
            continue
        geom = geometry_from_roi(roi)
        if geom is None:
            continue
        sx, sy = trk.smooth(geom)         # 칼만 시간융합(이전 결과로 가산)
        seen.add(trk._key(geom))
        spd = trk.speed(geom)             # 손 정지 판정용 속도(px/frame)
        ex, ey = geom.axis_major
        cont = []
        if getattr(geom, "contour", None) is not None:
            cont = np.array(geom.contour, np.int32).reshape(-1, 2).tolist()
        nails.append({
            "cx": round(float(sx), 1), "cy": round(float(sy), 1),
            "ex": round(float(ex), 4), "ey": round(float(ey), 4),
            "len": round(float(geom.length), 1), "wid": round(float(geom.width), 1),
            "finger": geom.finger, "hand": geom.handedness,
            "facing": round(float(f), 5),
            "distM": round(float(getattr(roi, "dist_m", 0.0)), 4),
            "extended": round(float(getattr(roi, "extended", 1.0)), 1),
            "speed": round(float(spd), 2),
            "stable": bool(spd <= _STABLE_PX),   # 렌더 게이팅: 손 정지 시만 True(이중상 억제)
            "contour": cont,
        })
    trk.predict_missing(seen)             # 가려진 손가락 예측기 진행
    return nails


def _infer_jpeg(buf: bytes, want_card: bool = False) -> dict:
    arr = np.frombuffer(buf, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return {"ok": False, "err": "decode 실패"}
    h, w = img.shape[:2]
    t0 = time.perf_counter()
    nails = _infer_hands(img) if MODE == "hands" else _infer_yolo(img)
    ms = (time.perf_counter() - t0) * 1000.0
    res = {"ok": True, "w": w, "h": h, "ms": round(ms, 1), "nails": nails}
    if want_card:
        _attach_card_scale(img, res)
    return res


def _attach_card_scale(img, res: dict) -> None:
    """프레임에 신용카드가 있으면 mm/px 스케일 + 손톱 실치수(mm)를 res 에 붙인다.

    카드가 손톱과 같은 깊이 평면에 있다고 가정(사용자가 손 옆/뒤에 카드를 댐) → 초점거리·거리
    가정 없이 실치수 확정. magic-mirror 실물크기 프리뷰(mmPerPx)와 손톱 mm 측정에 사용.
    """
    card = detect_card(img)
    if card is None:
        res["card"] = {"found": False}
        return
    mmpp = card["mm_per_px"]
    res["card"] = {"found": True, "mmPerPx": round(mmpp, 5),
                   "longPx": round(card["long_px"], 1),
                   "corners": card["corners"].astype(int).tolist()}
    for nd in res.get("nails", []):
        lm, wm = nail_mm(nd.get("len", 0.0), nd.get("wid", 0.0), mmpp)
        nd["lenMm"], nd["widMm"] = round(lm, 2), round(wm, 2)


# --- 손톱 프로파일 측정(enroll) — "1회 측정 -> 베이킹 -> 런타임은 포즈만" 파이프라인의 1단계.
# POST /infer?enroll=1[&reset=1] 동안 손가락별 실측(mm)을 누적하고, 표본이 8개를 넘긴
# 손가락부터 중앙값을 ROOT/nail_profile.json 에 계속 기록한다
# (tools/build/bake_nail_design.py 가 소비). 한 손 5손가락 모두 NEED개면 done.
ENROLL_NEED = int(os.environ.get("NAIL_ENROLL_NEED", "40"))
_FINGERS = ("thumb", "index", "middle", "ring", "pinky")
_ENROLL: dict = {}          # "hand:finger" -> [(len_mm, wid_mm), ...]


def _enroll_update(res: dict, reset: bool) -> dict:
    if reset:
        _ENROLL.clear()
    f_px = HandConfig().focal_ratio * res["w"]
    for nd in res.get("nails", []):
        d = float(nd.get("distM", 0.0))
        if not (0.10 <= d <= 0.60):        # 너무 멀면 mm/px 분해능 부족, 너무 가까우면 왜곡
            continue
        if float(nd.get("facing", 0.0)) <= 0.0:   # 손등(손톱)이 카메라를 향할 때만
            continue
        if float(nd.get("extended", 1.0)) < 0.5 or not nd.get("hand") or not nd.get("finger"):
            continue
        mm = _MM_K * 1000.0 * d / f_px     # px -> mm (핀홀; 카드 캘리브 보정 _MM_K)
        _ENROLL.setdefault(f"{nd['hand']}:{nd['finger']}", []).append(
            (float(nd["len"]) * mm, float(nd["wid"]) * mm))
    best_hand, best_min = None, -1
    for hand in ("Left", "Right"):
        cnts = [len(_ENROLL.get(f"{hand}:{f}", ())) for f in _FINGERS]
        if min(cnts) > best_min:
            best_hand, best_min = hand, min(cnts)
    if any(len(v) >= 8 for v in _ENROLL.values()):
        _write_profile()
    done = best_min >= ENROLL_NEED
    if best_hand and best_min >= 0:
        parts = " ".join(f"{f[0].upper()}{len(_ENROLL.get(best_hand + ':' + f, ()))}" for f in _FINGERS)
        msg = f"[{best_hand}] {parts} /{ENROLL_NEED}" + (" DONE" if done else "")
    else:
        msg = "손등을 카메라에 보여주세요 (15~50cm)"
    return {"active": True, "count": max(0, best_min), "need": ENROLL_NEED,
            "done": done, "msg": msg}


def _write_profile():
    nails = []
    for k in sorted(_ENROLL):
        v = _ENROLL[k]
        if len(v) < 8:
            continue
        hand, finger = k.split(":", 1)
        med = np.median(np.asarray(v, np.float32), axis=0)   # 중앙값 = 이상치에 강인
        nails.append({"hand": hand, "finger": finger,
                      "lenMm": round(float(med[0]), 2), "widMm": round(float(med[1]), 2),
                      "n": len(v)})
    prof = {"version": 1, "focalRatio": HandConfig().focal_ratio, "nails": nails}
    with open(os.path.join(ROOT, "nail_profile.json"), "w", encoding="utf-8") as fp:
        json.dump(prof, fp, ensure_ascii=False, indent=1)


# --- 카드 실측 스케일 보정 (camera_calib.json) — mm 추정 보정계수 k (1.0=무보정) ---
_CALIB_PATH = os.path.join(ROOT, "camera_calib.json")
_CALIB_NEED = int(os.environ.get("NAIL_CALIB_NEED", "20"))
_MM_K = 1.0
_CALIB_RATIOS: list = []


def _load_calib() -> float:
    """camera_calib.json 이 있으면 mm 보정계수를 로드(없으면 1.0)."""
    global _MM_K
    try:
        with open(_CALIB_PATH, encoding="utf-8") as fp:
            _MM_K = float(json.load(fp).get("mmScaleCorrection", 1.0))
    except Exception:
        _MM_K = 1.0
    return _MM_K


def _calib_update(res: dict, reset: bool) -> dict:
    """카드+손이 같이 잡힌 프레임에서 mm 보정계수를 누적 → 중앙값을 camera_calib.json 에 기록.

    카드(실측 mm/px)와 파이프라인 예측 mm/px 의 비 k 를 손톱마다 모아 중앙값을 취한다.
    카드는 초점거리/손크기 가정과 독립인 ground-truth 라 비순환(참고: src/card_calib.py)."""
    global _MM_K
    if reset:
        _CALIB_RATIOS.clear()
    card = res.get("card") or {}
    f_px = HandConfig().focal_ratio * res["w"]
    if card.get("found"):
        cmmpp = float(card.get("mmPerPx", 0.0))
        for nd in res.get("nails", []):
            d = float(nd.get("distM", 0.0))
            if d <= 0.05:
                continue
            k = scale_correction(cmmpp, d, f_px)
            if k is not None and 0.3 < k < 3.0:      # 비상식적 비율 배제
                _CALIB_RATIOS.append(k)
    n = len(_CALIB_RATIOS)
    k_med = fold_correction(_CALIB_RATIOS)
    if n > 0:
        _MM_K = k_med
    done = n >= _CALIB_NEED
    if done:
        with open(_CALIB_PATH, "w", encoding="utf-8") as fp:
            json.dump({"mmScaleCorrection": round(k_med, 5), "n": n,
                       "focalRatio": HandConfig().focal_ratio}, fp,
                      ensure_ascii=False, indent=1)
    msg = (f"카드+손 동시 노출 유지 — {n}/{_CALIB_NEED}" + (" DONE" if done else "")) if n \
        else "신용카드를 손톱 옆(같은 거리)에 대주세요"
    return {"active": True, "count": n, "need": _CALIB_NEED, "done": done,
            "k": round(k_med, 4), "msg": msg}


def _infer_yolo(img) -> list:
    nails = []
    for m in _ensure_model().detect_full(img):
        g = compute_geometry(m, None, _GEOM)
        if g is None:
            continue
        peri = cv2.arcLength(g.contour.astype(np.int32), True)
        cont = cv2.approxPolyDP(g.contour.astype(np.int32), 0.012 * peri, True).reshape(-1, 2)
        nails.append({
            "cx": round(g.center[0], 1), "cy": round(g.center[1], 1),
            "ex": round(g.axis_major[0], 4), "ey": round(g.axis_major[1], 4),
            "len": round(g.length, 1), "wid": round(g.width, 1),
            "contour": cont.astype(int).tolist(),
        })
    return nails


# ---------------------------------------------------------------------------
# 무선 모니터 — 같은 WiFi의 폰/노트북 브라우저로 실기기 카메라+검출을 실시간 확인.
# 안경은 HTTPS:8443(USB) 그대로, 모니터만 HTTP:8080 별도(인증서 경고 없음).
# ---------------------------------------------------------------------------
MON_PORT = int(os.environ.get("NAIL_MON_PORT", "8080"))
MON_ROT = os.environ.get("NAIL_MON_ROT", "cw")   # cw|ccw|none — 90° 장착 카메라 보기 보정(검출엔 무관)
_MON = {"jpeg": b"", "nails": 0, "ms": 0.0, "frames": 0,
        "times": collections.deque(maxlen=30), "lock": threading.Lock()}


def _mon_fps() -> float:
    t = _MON["times"]
    return (len(t) - 1) / (t[-1] - t[0]) if len(t) >= 2 and t[-1] > t[0] else 0.0


def _update_monitor(body: bytes, res: dict) -> None:
    """프레임에 손톱 외곽/중심을 그려 모니터용 JPEG로 보관 + 통계 갱신(매 프레임)."""
    try:
        im = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
        if im is None:
            return
        nl = res.get("nails", [])
        for nd in nl:
            cont = nd.get("contour")
            if cont:
                cv2.polylines(im, [np.array(cont, np.int32).reshape(-1, 1, 2)], True, (0, 255, 0), 2)
            cv2.circle(im, (int(nd.get("cx", 0)), int(nd.get("cy", 0))), 4, (0, 0, 255), -1)
        if MON_ROT == "cw":
            im = cv2.rotate(im, cv2.ROTATE_90_CLOCKWISE)       # 90° 장착 카메라를 세워서 보기(뷰 전용)
        elif MON_ROT == "ccw":
            im = cv2.rotate(im, cv2.ROTATE_90_COUNTERCLOCKWISE)
        cv2.putText(im, f"nails={len(nl)}  fps={_mon_fps():.1f}  ms={res.get('ms', 0)}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        ok, enc = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            with _MON["lock"]:
                _MON["jpeg"] = enc.tobytes()
                _MON["nails"], _MON["ms"] = len(nl), res.get("ms", 0.0)
                _MON["frames"] += 1
                _MON["times"].append(time.time())
    except Exception:
        pass


_MONITOR_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Nail-AR 모니터</title>
<style>html,body{margin:0;background:#0c0c0c;color:#0f0;font-family:monospace;text-align:center}
#s{padding:10px;font-size:20px;color:#0ff}img{max-width:100%;height:auto;image-rendering:auto}</style>
</head><body><div id=s>연결 중…</div><img id=v>
<script>
const v=document.getElementById('v'),s=document.getElementById('s');
v.onload=()=>setTimeout(next,60); v.onerror=()=>setTimeout(next,400);
function next(){v.src='/last.jpg?t='+Date.now();} next();
async function stat(){try{const j=await(await fetch('/stats.json')).json();
 s.textContent='nails='+j.nails+'  fps='+j.fps+'  ms='+j.ms+'  frames='+j.frames;}catch(e){s.textContent='서버 대기…';}}
setInterval(stat,500); stat();
</script></body></html>"""


class MonitorHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/monitor", "/monitor/"):
            return self._send(_MONITOR_HTML.encode("utf-8"), "text/html; charset=utf-8")
        if p == "/last.jpg":
            with _MON["lock"]:
                data = _MON["jpeg"]
            if not data:
                self.send_error(503, "no frame yet"); return
            return self._send(data, "image/jpeg")
        if p == "/stats.json":
            with _MON["lock"]:
                s = {"nails": _MON["nails"], "ms": _MON["ms"], "frames": _MON["frames"], "fps": round(_mon_fps(), 1)}
            return self._send(json.dumps(s).encode(), "application/json")
        self.send_error(404)

    def _send(self, data: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def _start_monitor():
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", MON_PORT), MonitorHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


# ---------------------------------------------------------------------------
# raw TCP 소켓 추론 (B') — 영구 연결로 프레임당 TLS 핸드셰이크를 제거해 지연↓/fps↑.
# 프로토콜(요청):  [4B total-len(BE)] [1B flags] [JPEG]    flags bit0 = want_card
# 프로토콜(응답):  [4B len(BE)] [JSON]
# 평문(LAN/USB 전용). HTTP /infer(8443)는 그대로 유지 — 소켓은 빠른 프리뷰 경로.
# ---------------------------------------------------------------------------
INFER_SOCK_PORT = int(os.environ.get("NAIL_SOCK_PORT", "8444"))
_INFER_LOCK = threading.Lock()   # MediaPipe/칼만은 스레드-비안전 → 추론 직렬화


def _recv_n(sock, n: int):
    buf = b""
    while len(buf) < n:
        c = sock.recv(n - len(buf))
        if not c:
            return None
        buf += c
    return buf


class _InferTCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        while True:
            hdr = _recv_n(self.request, 4)
            if hdr is None:
                break
            total = struct.unpack(">I", hdr)[0]
            if total < 1 or total > 20_000_000:
                break
            payload = _recv_n(self.request, total)
            if payload is None:
                break
            flags, body = payload[0], payload[1:]
            with _INFER_LOCK:
                res = _infer_jpeg(body, want_card=bool(flags & 1))
            _update_monitor(body, res)
            out = json.dumps(res).encode("utf-8")
            try:
                self.request.sendall(struct.pack(">I", len(out)) + out)
            except Exception:
                break


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _start_infer_socket():
    srv = _ThreadingTCPServer(("0.0.0.0", INFER_SOCK_PORT), _InferTCPHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        path, _, query = self.path.partition("?")
        if path != "/infer":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n)
            qs = urllib.parse.parse_qs(query)
            _calib = qs.get("calib", ["0"])[0] == "1"
            res = _infer_jpeg(body, want_card=(qs.get("card", ["0"])[0] == "1" or _calib))
            if res.get("ok") and qs.get("enroll", ["0"])[0] == "1":
                res["enroll"] = _enroll_update(res, qs.get("reset", ["0"])[0] == "1")
            if res.get("ok") and _calib:
                res["calib"] = _calib_update(res, qs.get("reset", ["0"])[0] == "1")
            log.info("infer bytes=%d nails=%d ms=%s", len(body), len(res.get("nails", [])), res.get("ms"))
            _update_monitor(body, res)   # WiFi 모니터용: 매 프레임 카메라+검출을 시각화해 보관
            out = json.dumps(res).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
        except Exception as e:  # noqa: BLE001
            log.exception("infer 오류")
            self.send_error(500, str(e))

    def end_headers(self):           # 폰 브라우저 JS 캐시 방지(수정 즉시 반영)
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):       # 접근로그 소음 억제
        pass


def main():
    ip = S.lan_ip()
    S.ensure_cert(ip)
    # 시작 시 모델 워밍업(첫 프레임 16초 지연 제거)
    log.info("모델 워밍업 중…")
    _ensure_model().detect_full(np.zeros((640, 640, 3), np.uint8))
    log.info("워밍업 완료")
    log.info("카드 mm 보정 로드: mmScaleCorrection=%.4f", _load_calib())
    http.server.SimpleHTTPRequestHandler.extensions_map.update(
        {".js": "text/javascript", ".mjs": "text/javascript"})
    handler = functools.partial(Handler, directory=HERE)
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(S.CERT, S.KEY)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    _start_monitor()        # WiFi 무선 모니터(HTTP)
    _start_infer_socket()   # raw TCP 소켓 추론(B') — 빠른 프리뷰 경로
    print("=" * 60)
    print("  에지 추론 서버 (PC가 인식, 폰은 렌더)")
    print(f"  폰 접속:  https://{ip}:{PORT}/edge.html")
    print(f"  ★ 무선 모니터(같은 WiFi 브라우저):  http://{ip}:{MON_PORT}/monitor")
    print(f"  소켓 추론(빠름):  {ip}:{INFER_SOCK_PORT}  (USB: adb reverse tcp:{INFER_SOCK_PORT})")
    print("  방화벽 팝업 뜨면 '액세스 허용'. 종료: Ctrl+C")
    print("=" * 60)
    log.info("무선 모니터: http://%s:%d/monitor  |  소켓: %s:%d", ip, MON_PORT, ip, INFER_SOCK_PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[edge] 종료")


if __name__ == "__main__":
    main()
