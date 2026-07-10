"""디자인 이미지 정합·합성 — 별 같은 샘플 이미지를 손톱 위에 자연스럽게 입힌다.

특허 청구항 8(디자인 원본을 손톱 크기·방향·형상에 맞게 변형)·청구항 9(투시/아핀 변환)에
해당하는 모듈. 손톱 기하(중심·세로축·가로축·길이·폭·마스크)를 받아 디자인 이미지를
손톱의 방향 박스에 사영(homography)하고, 손톱 마스크로 잘라 알파 합성한다.

"자연스러움"의 핵심 3가지를 여기서 처리한다.
  1) 크기·회전·위치: 손톱 세로축/길이·폭에 맞춤 (디자인이 손톱을 따라 돈다)
  2) 넘침 방지: 손톱 마스크로 클리핑 → 손톱 밖으로 안 삐져나감
  3) 가장자리 블렌딩: 마스크 경계를 페더(feather)해 경계가 튀지 않게

곡면(청구항 10, 도 5) 워핑은 다음 증분. 현재는 평면 아핀 + 마스크 클립 + 페더.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np


def load_design(path: str) -> Optional[np.ndarray]:
    """디자인 PNG를 BGRA로 로드. 알파 없으면 불투명 알파를 붙인다."""
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 2:  # 그레이
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    elif img.shape[2] == 3:  # BGR
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    return img


def apply(frame: np.ndarray, design_bgra: np.ndarray, geom, mask, center, cfg) -> None:
    """frame 위 손톱(geom/mask)에 design을 합성(제자리 수정)."""
    h, w = frame.shape[:2]
    dh, dw = design_bgra.shape[:2]
    if dh < 2 or dw < 2 or geom.length < 2 or geom.width < 2:
        return

    cx, cy = center
    ux, uy = geom.axis_major   # 손톱 끝(팁) 방향 단위벡터
    vx, vy = geom.axis_minor   # 가로 방향
    hl = geom.length / 2.0 * cfg.scale
    hw = geom.width / 2.0 * cfg.scale

    # 중심에서 팁(+)/뿌리(-) 방향으로 이동
    shift = geom.length / 2.0 * cfg.along
    cx += ux * shift
    cy += uy * shift

    def pt(a, b):  # a: 세로축(팁+), b: 가로축
        return [cx + ux * a + vx * b, cy + uy * a + vy * b]

    # 디자인 사각형(위=팁쪽) → 손톱 방향 박스
    dst = np.float32([pt(hl, -hw), pt(hl, hw), pt(-hl, hw), pt(-hl, -hw)])

    # 속도: 전체 프레임이 아니라 디자인이 닿는 ROI 박스 안에서만 워핑·합성
    pad = 2
    x0 = max(0, int(np.floor(dst[:, 0].min())) - pad)
    y0 = max(0, int(np.floor(dst[:, 1].min())) - pad)
    x1 = min(w, int(np.ceil(dst[:, 0].max())) + pad)
    y1 = min(h, int(np.ceil(dst[:, 1].max())) + pad)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return

    dst_local = dst - np.float32([x0, y0])
    src = np.float32([[0, 0], [dw, 0], [dw, dh], [0, dh]])
    M = cv2.getPerspectiveTransform(src, dst_local)

    sub_w, sub_h = x1 - x0, y1 - y0
    warped = cv2.warpPerspective(design_bgra, M, (sub_w, sub_h),
                                 flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=(0, 0, 0, 0))

    alpha = warped[:, :, 3].astype(np.float32) / 255.0 * float(cfg.alpha)
    if cfg.clip_to_mask and mask is not None:
        m = (mask[y0:y1, x0:x1] > 0).astype(np.float32)
        if cfg.feather > 0:
            k = int(cfg.feather) * 2 + 1
            m = cv2.GaussianBlur(m, (k, k), 0)
        alpha = alpha * m

    a = alpha[:, :, None]
    sub = frame[y0:y1, x0:x1].astype(np.float32)
    rgb = warped[:, :, :3].astype(np.float32)
    frame[y0:y1, x0:x1] = (rgb * a + sub * (1.0 - a)).astype(np.uint8)
