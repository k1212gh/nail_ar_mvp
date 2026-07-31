#!/usr/bin/env python3
"""펜 가림 콘택트시트 — 여러 프레임의 [raw|penDim] 소형 비교를 한 장 그리드로.

여러 프레임을 한눈에 보고 실패 케이스(펜 미검출=FN, 과잉 가림=FP)를 빠르게 스캔한다.
web/pen_occlusion.py(라이브 단일소스)를 그대로 사용.

  python tools/pen_probe/contact_sheet.py --frames samples/pen --out sheet.jpg --cols 4 --every 6
"""
import argparse, glob, os, sys
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "web")); sys.path.insert(0, ROOT); os.chdir(ROOT)
import edge_serve as E  # noqa: E402
import pen_occlusion as PO  # noqa: E402

COLS = [(210, 90, 230), (240, 190, 90), (110, 210, 130), (90, 150, 240)]
CELL_H = 150   # 셀(프레임) 높이


def render_cell(im, nl):
    """한 프레임을 [raw | penDim] 두 패널로 좁게 렌더 → 손톱영역 크롭."""
    h, w = im.shape[:2]
    contours = [nd.get("contour") for nd in nl if nd.get("contour")]
    soft = PO.pen_soft_mask(im, contours)
    dcol = np.zeros((h, w, 3), np.float32); da = np.zeros((h, w), np.float32)
    for i, c in enumerate(contours):
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [np.array(c, np.int32).reshape(-1, 1, 2)], 255)
        mb = m > 0; dcol[mb] = COLS[i % len(COLS)]; da[mb] = 0.85
    occ = PO.apply_occlusion(im, dcol, da, soft)
    noocc = PO.apply_occlusion(im, dcol, da, np.zeros_like(soft))
    # 손톱 bbox 크롭
    xs = [p[0] for c in contours for p in c]; ys = [p[1] for c in contours for p in c]
    if xs:
        pad = 40
        x0, x1 = max(0, min(xs) - pad), min(w, max(xs) + pad)
        y0, y1 = max(0, min(ys) - pad), min(h, max(ys) + pad)
        noocc, occ = noocc[y0:y1, x0:x1], occ[y0:y1, x0:x1]
    pair = cv2.hconcat([cv2.resize(noocc, (int(noocc.shape[1] * CELL_H / noocc.shape[0]), CELL_H)),
                        cv2.resize(occ, (int(occ.shape[1] * CELL_H / occ.shape[0]), CELL_H))])
    # 가림된 디자인 픽셀 비율(진단): soft>0.3 인 디자인영역 비율
    dim_frac = float(((soft > 0.3) & (da > 0)).sum()) / max(1, (da > 0).sum())
    return pair, dim_frac


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True); ap.add_argument("--out", default="sheet.jpg")
    ap.add_argument("--cols", type=int, default=4); ap.add_argument("--every", type=int, default=6)
    ap.add_argument("--max", type=int, default=32)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.frames, "*.jpg")) + glob.glob(os.path.join(a.frames, "*.png")))[::a.every][:a.max]
    cells = []
    for f in files:
        im = cv2.imread(f)
        if im is None: continue
        nl = E._infer_yolo(im)
        if not nl: continue
        pair, dim = render_cell(im, nl)
        cv2.rectangle(pair, (0, 0), (pair.shape[1], 18), (0, 0, 0), -1)
        cv2.putText(pair, f"{os.path.basename(f)[:14]} dim={dim*100:.0f}%", (3, 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        cells.append(pair)
        print(f"ok {os.path.basename(f)} nails={len(nl)} dim={dim*100:.0f}%")
    if not cells:
        print("검출 프레임 없음"); return
    wmax = max(c.shape[1] for c in cells)
    cells = [cv2.copyMakeBorder(c, 2, 2, 2, wmax - c.shape[1] + 2, cv2.BORDER_CONSTANT, value=(40, 40, 40)) for c in cells]
    rows = [cv2.hconcat(cells[i:i + a.cols]) for i in range(0, len(cells), a.cols)]
    wfull = max(r.shape[1] for r in rows)
    rows = [cv2.copyMakeBorder(r, 0, 0, 0, wfull - r.shape[1], cv2.BORDER_CONSTANT, value=(40, 40, 40)) for r in rows]
    cv2.imwrite(a.out, cv2.vconcat(rows))
    print(f"=== {len(cells)}셀 → {a.out} (좌=가림전 / 우=penDim) ===")


if __name__ == "__main__":
    main()
