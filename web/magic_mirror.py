"""매직미러 렌더러 — 카메라 프레임의 손톱에 디자인을 얹고 펜 가림까지 적용한 합성 결과.

안경 OST(광학투과)는 물리한계로 근거리 정합이 어렵다(docs/DEEP_RESEARCH_NEARFIELD_OST). 그래서
업계처럼 **카메라 영상 위에 디자인을 합성해 화면으로 보여주는 매직미러**가 현실적 정답이며, 이 경로에선
**펜 가림이 즉시 적용된다**(PC/폰이 그리므로). web/pen_occlusion.py(가림)와 짝을 이룬다.

  from magic_mirror import render
  out = render(frame_bgr, nails, occlude=True)   # nails = edge_serve._infer_yolo 결과
"""
from __future__ import annotations
import cv2
import numpy as np
import pen_occlusion as PO

# 젤 네일 느낌의 팔레트(BGR). 손톱마다 순환.
PALETTE = [(200, 90, 235), (235, 180, 90), (110, 205, 130), (90, 150, 240), (150, 120, 240), (210, 210, 120)]
BASE_ALPHA = 0.88


def _design_layer(shape, nails):
    """손톱마다 세로 그라데이션(젤 느낌) 디자인 색 + 알파 레이어 생성."""
    h, w = shape[:2]
    dcol = np.zeros((h, w, 3), np.float32)
    da = np.zeros((h, w), np.float32)
    for i, nd in enumerate(nails):
        cont = nd.get("contour")
        if not cont:
            continue
        m = np.zeros((h, w), np.uint8)
        pts = np.array(cont, np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(m, [pts], 255)
        mb = m > 0
        if not mb.any():
            continue
        c = np.array(PALETTE[i % len(PALETTE)], np.float32)
        # 세로 그라데이션: 위(팁)는 밝게, 아래(뿌리)는 짙게 — 젤 광택 느낌
        ys, xs = np.where(mb)
        y0, y1 = ys.min(), ys.max()
        t = (ys - y0) / max(1, (y1 - y0))            # 0(위)~1(아래)
        shade = (0.75 + 0.45 * (1 - t))[:, None]     # 위 1.2배~아래 0.75배
        dcol[ys, xs] = np.clip(c[None, :] * shade, 0, 255)
        da[mb] = BASE_ALPHA
    return dcol, da


def _warp_texture_onto_nail(tex, contour, h, w):
    """디자인 텍스처를 손톱 방향(minAreaRect)에 맞춰 원근 워핑 + 손톱모양 마스크. (dcol조각, mask) 반환."""
    pts = np.array(contour, np.float32).reshape(-1, 2)
    rect = cv2.minAreaRect(pts)                       # (center,(w,h),angle) — 손톱 방향 사각
    box = cv2.boxPoints(rect).astype(np.float32)       # 4모서리(시계/반시계)
    th, tw = tex.shape[:2]
    src = np.array([[0, 0], [tw - 1, 0], [tw - 1, th - 1], [0, th - 1]], np.float32)
    M = cv2.getPerspectiveTransform(src, box)
    warped = cv2.warpPerspective(tex, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [np.array(contour, np.int32).reshape(-1, 1, 2)], 255)
    return warped, m > 0


def render_textured(frame_bgr, nails, design_tex, occlude=True, pen_dim=0.15, gloss=True):
    """카탈로그 디자인 이미지(design_tex, BGR)를 각 손톱에 입혀 미리보기. occlude면 펜 지나는 곳 투명."""
    if not nails:
        return frame_bgr.copy()
    h, w = frame_bgr.shape[:2]
    dcol = np.zeros((h, w, 3), np.float32)
    da = np.zeros((h, w), np.float32)
    for nd in nails:
        cont = nd.get("contour")
        if not cont:
            continue
        warped, mb = _warp_texture_onto_nail(design_tex, cont, h, w)
        if not mb.any():
            continue
        col = warped.astype(np.float32)
        if gloss:  # 세로 광택(젤 느낌): 위 밝게
            ys, xs = np.where(mb)
            y0, y1 = ys.min(), ys.max()
            t = (ys - y0) / max(1, (y1 - y0))
            col[ys, xs] *= (0.85 + 0.4 * (1 - t))[:, None]
        dcol[mb] = np.clip(col[mb], 0, 255)
        da[mb] = BASE_ALPHA
    if occlude:
        contours = [nd.get("contour") for nd in nails if nd.get("contour")]
        soft = PO.pen_soft_mask(frame_bgr, contours)
        return PO.apply_occlusion(frame_bgr, dcol, da, soft, pen_dim=pen_dim)
    a3 = da[..., None]
    return np.clip(frame_bgr.astype(np.float32) * (1 - a3) + dcol * a3, 0, 255).astype(np.uint8)


def render(frame_bgr, nails, occlude=True, pen_dim=0.15):
    """손톱에 디자인 합성. occlude=True면 펜/도구가 지나는 부분의 디자인을 투명하게(펜이 비침)."""
    if not nails:
        return frame_bgr.copy()
    dcol, da = _design_layer(frame_bgr.shape, nails)
    if occlude:
        contours = [nd.get("contour") for nd in nails if nd.get("contour")]
        soft = PO.pen_soft_mask(frame_bgr, contours)
        return PO.apply_occlusion(frame_bgr, dcol, da, soft, pen_dim=pen_dim)
    # 가림 없음: 디자인이 펜까지 덮음
    a3 = da[..., None]
    return np.clip(frame_bgr.astype(np.float32) * (1 - a3) + dcol * a3, 0, 255).astype(np.uint8)
