"""torch-free YOLOv8-seg 손톱 추론 — onnxruntime 만으로 nails_seg.onnx 실행.

web/yolo.js(브라우저 검증본)의 letterbox→추론→NMS→마스크→PCA기하 를 그대로 파이썬으로 옮긴 것.
- 루트 B(Termux 파이썬 에지서버)의 추론 코어이자,
- 루트 A(네이티브 안드로이드 Kotlin)가 1:1로 미러링할 레퍼런스 파이프라인.

출력 손톱 스키마는 web/edge_serve.py 와 동일(cx,cy,ex,ey,len,wid,contour) → 안경이 그대로 파싱.
"""
from __future__ import annotations
import numpy as np
import cv2
import onnxruntime as ort

S = 640           # 모델 입력 정사각
NA = 8400         # 앵커 수
PH = PW = 160     # 마스크 프로토 해상도
PN = PH * PW
CONF = 0.20       # 신뢰도 임계(yolo.js 기본)
IOU = 0.5         # NMS IoU
MASK_THR = 0.5
MAXDET = 12


def _nms(boxes, scores, iou_thr, maxdet):
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0 and len(keep) < maxdet:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        w = np.clip(xx2 - xx1, 0, None)
        h = np.clip(yy2 - yy1, 0, None)
        inter = w * h
        ai = (boxes[i, 2] - boxes[i, 0]) * (boxes[i, 3] - boxes[i, 1])
        ar = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        iou = inter / np.maximum(ai + ar - inter, 1e-9)
        order = rest[iou <= iou_thr]
    return keep


def _pca(pts):
    """160-space 마스크 픽셀들 → 중심(방향박스 중점)·주축 단위벡터·길이·폭. (yolo.js pca 이식)"""
    m = pts.mean(axis=0)
    d = pts - m
    a = float((d[:, 0] * d[:, 0]).mean())
    b = float((d[:, 0] * d[:, 1]).mean())
    c = float((d[:, 1] * d[:, 1]).mean())
    tr, det = a + c, a * c - b * b
    l1 = tr / 2 + np.sqrt(max(0.0, tr * tr / 4 - det))
    ex, ey = b, l1 - a
    if abs(b) < 1e-6:
        ex, ey = (1.0, 0.0) if a >= c else (0.0, 1.0)
    L = np.hypot(ex, ey) or 1.0
    ex, ey = ex / L, ey / L
    if ey > 0:                       # 영상 위쪽을 tip으로
        ex, ey = -ex, -ey
    nx, ny = -ey, ex
    t = d[:, 0] * ex + d[:, 1] * ey
    su = d[:, 0] * nx + d[:, 1] * ny
    tmid, smid = (t.min() + t.max()) / 2, (su.min() + su.max()) / 2
    cx = m[0] + ex * tmid + nx * smid
    cy = m[1] + ey * tmid + ny * smid
    return {"mx": float(cx), "my": float(cy), "ex": float(ex), "ey": float(ey),
            "len": float(t.max() - t.min()), "wid": float(su.max() - su.min())}


class OnnxNailSeg:
    def __init__(self, model_path: str, providers=None, conf: float = CONF):
        self.conf = conf
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(
            model_path, sess_options=so,
            providers=providers or ["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name
        # 입력/출력 크기에서 차원 자동 도출 → 320²/640² 모두 대응
        ishape = self.sess.get_inputs()[0].shape        # [1,3,S,S]
        oshape = self.sess.get_outputs()[0].shape        # [1,37,NA]
        pshape = self.sess.get_outputs()[1].shape        # [1,32,PH,PW]
        self.S = int(ishape[-1]) if isinstance(ishape[-1], int) else 640
        self.NA = int(oshape[-1]) if isinstance(oshape[-1], int) else 8400
        self.PH = int(pshape[-2]) if isinstance(pshape[-2], int) else self.S // 4
        self.PW = int(pshape[-1]) if isinstance(pshape[-1], int) else self.S // 4
        self.PN = self.PH * self.PW

    def _letterbox(self, img):
        h, w = img.shape[:2]
        S = self.S
        r = min(S / w, S / h)
        nw, nh = round(w * r), round(h * r)
        px, py = (S - nw) // 2, (S - nh) // 2
        canvas = np.full((S, S, 3), 114, np.uint8)
        canvas[py:py + nh, px:px + nw] = cv2.resize(img, (nw, nh))
        ten = np.transpose(canvas[:, :, ::-1].astype(np.float32) / 255.0, (2, 0, 1))[None]
        return np.ascontiguousarray(ten), r, px, py

    def infer(self, img_bgr):
        """BGR 이미지 → 손톱 리스트(원본 좌표계). edge_serve 스키마와 동일."""
        S, PH, PW, PN = self.S, self.PH, self.PW, self.PN
        H, W = img_bgr.shape[:2]
        ten, r, px, py = self._letterbox(img_bgr)
        o0, o1 = self.sess.run(None, {self.inp: ten})
        o0 = o0[0]                       # (37, 8400)
        protos = o1[0].reshape(32, PN)   # (32, 25600)

        sc = o0[4]
        idx = np.where(sc >= self.conf)[0]
        if idx.size == 0:
            return []
        cx, cy, ww, hh = o0[0, idx], o0[1, idx], o0[2, idx], o0[3, idx]
        boxes = np.stack([cx - ww / 2, cy - hh / 2, cx + ww / 2, cy + hh / 2], axis=1)
        keep = _nms(boxes, sc[idx], IOU, MAXDET)

        nails = []
        for k in keep:
            gi = idx[k]
            coef = o0[5:37, gi]                       # (32,)
            x1, y1, x2, y2 = boxes[k]
            bx1, by1 = max(0, int(x1 // 4)), max(0, int(y1 // 4))
            bx2, by2 = min(PW - 1, int(np.ceil(x2 / 4))), min(PH - 1, int(np.ceil(y2 / 4)))
            logits = (coef @ protos).reshape(PH, PW)
            on = np.zeros((PH, PW), bool)
            reg = 1.0 / (1.0 + np.exp(-logits[by1:by2 + 1, bx1:bx2 + 1]))
            on[by1:by2 + 1, bx1:bx2 + 1] = reg > MASK_THR
            if on.sum() < 8:
                continue
            ys, xs = np.where(on)
            g = _pca(np.stack([xs, ys], axis=1).astype(np.float32))
            ocx = (g["mx"] * 4 - px) / r
            ocy = (g["my"] * 4 - py) / r

            # 원본 좌표계 컨투어 (160→640→언레터박스→원본)
            m640 = cv2.resize((on.astype(np.uint8) * 255), (S, S), interpolation=cv2.INTER_NEAREST)
            crop = m640[py:S - py, px:S - px]
            morig = cv2.resize(crop, (W, H), interpolation=cv2.INTER_NEAREST)
            cnts, _ = cv2.findContours(morig, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cont = []
            if cnts:
                cc = max(cnts, key=cv2.contourArea)
                peri = cv2.arcLength(cc, True)
                cc = cv2.approxPolyDP(cc, 0.012 * peri, True).reshape(-1, 2)
                cont = cc.astype(int).tolist()

            nails.append({
                "cx": round(float(ocx), 1), "cy": round(float(ocy), 1),
                "ex": round(float(g["ex"]), 4), "ey": round(float(g["ey"]), 4),
                "len": round(float(g["len"] * 4 / r), 1),
                "wid": round(float(g["wid"] * 4 / r), 1),
                "contour": cont,
            })
        return nails


if __name__ == "__main__":
    import argparse
    import glob
    import os
    import time
    ap = argparse.ArgumentParser(description="onnxruntime 손톱검출 테스트(캡처 프레임)")
    ap.add_argument("--model", default=os.path.join("web", "nails_seg.onnx"))
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", default="onnx_test_out")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--conf", type=float, default=CONF)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    seg = OnnxNailSeg(a.model, providers=["CPUExecutionProvider"], conf=a.conf)
    files = sorted(glob.glob(os.path.join(a.frames, "*.jpg")))
    if a.limit:
        files = files[:a.limit]

    tot, det_frames, tsum = 0, 0, 0.0
    for f in files:
        im = cv2.imread(f)
        if im is None:
            continue
        tot += 1
        t0 = time.perf_counter()
        nails = seg.infer(im)
        tsum += (time.perf_counter() - t0) * 1000
        if not nails:
            continue
        det_frames += 1
        vis = im.copy()
        for nd in nails:
            if nd["contour"]:
                cv2.polylines(vis, [np.array(nd["contour"], np.int32).reshape(-1, 1, 2)],
                              True, (0, 255, 0), 2)
            cx, cy = int(nd["cx"]), int(nd["cy"])
            tip = (int(cx + nd["ex"] * nd["len"] * 0.5), int(cy + nd["ey"] * nd["len"] * 0.5))
            cv2.circle(vis, (cx, cy), 3, (0, 0, 255), -1)
            cv2.line(vis, (cx, cy), tip, (255, 0, 255), 2)
        cv2.imwrite(os.path.join(a.out, "onnx_" + os.path.basename(f)), vis)

    print(f"프레임 {tot} | 손톱검출된 프레임 {det_frames} ({det_frames*100//max(1,tot)}%) "
          f"| 평균 {tsum/max(1,tot):.1f} ms ({1000/max(0.1,tsum/max(1,tot)):.1f} fps)")
    print(f"출력: {os.path.abspath(a.out)}")
