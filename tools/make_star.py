"""테스트용 별 디자인 PNG(RGBA) 생성 — samples/star.png.

손톱에 입혀 '자연스럽게 정합되나'를 보기 위한 샘플 이미지.
사용:  python tools/make_star.py        (samples/star.png 생성)
      python main.py --source 0 --design samples/star.png
"""
from __future__ import annotations

import math
import os

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "samples", "star.png")

S = 256
img = np.zeros((S, S, 4), np.uint8)
cx = cy = S / 2.0
R = S * 0.46      # 바깥 반지름
r = R * 0.42      # 안쪽 반지름

pts = []
for i in range(10):
    ang = -math.pi / 2 + i * math.pi / 5     # 위쪽 꼭짓점부터
    rad = R if i % 2 == 0 else r
    pts.append([cx + rad * math.cos(ang), cy + rad * math.sin(ang)])
poly = np.array([pts], np.int32)

# 금색 채움(BGRA) + 진한 외곽선
cv2.fillPoly(img, poly, (60, 190, 255, 255))
cv2.polylines(img, poly, True, (30, 110, 200, 255), 4, cv2.LINE_AA)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
cv2.imwrite(OUT, img)
print(f"별 디자인 저장: {OUT}  ({S}x{S}, RGBA)")
