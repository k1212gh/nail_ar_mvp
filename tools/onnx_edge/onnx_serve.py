"""torch-free 에지 서버 — onnxruntime 손톱검출을 안경 소켓 프로토콜로 서빙.

web/edge_serve.py 의 소켓 경로(8444)와 100% 동일한 와이어 프로토콜:
  요청:  [4B big-endian total][1B flags][JPEG]     (total = 1 + JPEG길이, flags bit0 = wantCard)
  응답:  [4B big-endian len][JSON len바이트]        JSON = {"ok",​"w","h","ms","nails":[...]}

= 루트 B(Termux 파이썬 에지서버) 그 자체이자, 루트 A(네이티브 Kotlin)가 미러링할 서버 로직.
안경은 push_calib 로 sockHost=<이 머신 IP> 만 지정하면 그대로 붙는다(코드 변경 0).

실행:  python tools/onnx_edge/onnx_serve.py            (기본 0.0.0.0:8444, CPU)
       NAIL_EP=cpu|dml python tools/onnx_edge/onnx_serve.py   (윈도우 GPU는 onnxruntime-directml 필요)
"""
from __future__ import annotations
import json
import os
import socket
import socketserver
import struct
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from onnx_infer import OnnxNailSeg  # noqa: E402

PORT = int(os.environ.get("NAIL_SOCK_PORT", "8444"))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL = os.environ.get("NAIL_ONNX", os.path.join(ROOT, "web", "nails_seg.onnx"))

_EP = {"cpu": ["CPUExecutionProvider"],
       "dml": ["DmlExecutionProvider", "CPUExecutionProvider"]}.get(
    os.environ.get("NAIL_EP", "cpu").lower(), ["CPUExecutionProvider"])
SEG = OnnxNailSeg(MODEL, providers=_EP)
_LOCK = __import__("threading").Lock()


def _recv_n(sock, n):
    buf = b""
    while len(buf) < n:
        c = sock.recv(n - len(buf))
        if not c:
            return None
        buf += c
    return buf


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
        peer = self.client_address[0]
        print(f"[onnx-serve] 접속: {peer}")
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
            _flags, body = payload[0], payload[1:]
            img = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                res = {"ok": False, "err": "decode 실패"}
            else:
                h, w = img.shape[:2]
                t0 = time.perf_counter()
                with _LOCK:
                    nails = SEG.infer(img)
                res = {"ok": True, "w": w, "h": h,
                       "ms": round((time.perf_counter() - t0) * 1000, 1), "nails": nails}
            out = json.dumps(res).encode("utf-8")
            try:
                self.request.sendall(struct.pack(">I", len(out)) + out)
            except Exception:
                break
        print(f"[onnx-serve] 종료: {peer}")


class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ip = _lan_ip()
    print("=" * 56)
    print("  torch-free 손톱검출 에지 서버 (onnxruntime)")
    print(f"  소켓:  {ip}:{PORT}   (EP={_EP[0]})")
    print(f"  안경:  push_calib  useSocket=1 sockHost={ip} sockPort={PORT}")
    print("  종료: Ctrl+C")
    print("=" * 56)
    srv = _Server(("0.0.0.0", PORT), _Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[onnx-serve] 종료")
