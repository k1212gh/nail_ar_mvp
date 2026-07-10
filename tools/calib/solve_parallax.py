#!/usr/bin/env python3
"""solve_parallax.py — 거리적응 시차모델 offset(d)=A+B/d 를 2점 이상에서 최소제곱으로 풀이.

각 측정점: (distM, offX, offY) — 그 거리에서 디자인을 손톱에 맞추는 데 필요한 총 오프셋
(display px). 펜 포인팅/보고로 구한 값. offset = A + B*(1/d) 를 x,y 각각 1차 회귀.

사용:
  python tools/calib/solve_parallax.py d1 ox1 oy1  d2 ox2 oy2  [d3 ox3 oy3 ...]
출력: {"meshParallaxOn":1,"pAx":..,"pAy":..,"pBx":..,"pBy":..} (nail_calib.json 에 병합)
"""
import json
import sys

import numpy as np


def main():
    vals = [float(x) for x in sys.argv[1:]]
    if len(vals) < 6 or len(vals) % 3 != 0:
        raise SystemExit("입력: d ox oy 를 2세트 이상 (예: 0.25 -210 -14  0.40 -150 -8)")
    pts = np.array(vals, np.float64).reshape(-1, 3)
    d, ox, oy = pts[:, 0], pts[:, 1], pts[:, 2]
    # offset = A + B*(1/d) -> 설계행렬 [1, 1/d]
    X = np.column_stack([np.ones_like(d), 1.0 / d])
    (Ax, Bx), *_ = np.linalg.lstsq(X, ox, rcond=None)
    (Ay, By), *_ = np.linalg.lstsq(X, oy, rcond=None)
    calib = {"meshParallaxOn": 1,
             "pAx": round(float(Ax), 2), "pAy": round(float(Ay), 2),
             "pBx": round(float(Bx), 3), "pBy": round(float(By), 3)}
    print(json.dumps(calib, ensure_ascii=False))
    # 각 측정점 잔차(px) 리포트
    for i in range(len(d)):
        px = Ax + Bx / d[i]
        py = Ay + By / d[i]
        print(f"  d={d[i]:.3f}  fit=({px:6.1f},{py:6.1f})  meas=({ox[i]:6.1f},{oy[i]:6.1f})  "
              f"resid=({px-ox[i]:+5.1f},{py-oy[i]:+5.1f})", file=sys.stderr)


if __name__ == "__main__":
    main()
