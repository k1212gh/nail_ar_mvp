"""대상 간 전사 (특허 청구항 30/32/33) — 손톱1 디자인을 손톱2 형상에 맞게 이식.

같은 워핑 엔진 재사용: UV가 공통 교환공간이라
  손톱1 화면 → (언워프) 정규 UV 아틀라스  → (워핑) 손톱2 화면.
좌우 손톱은 u→1-u 미러(청구항 30/31). anchors가 있으면 정규화 TPS로 미세보정(청구항 32),
외삽 폭주를 막기 위해 λ 정규화 + UV 경계 클램프(비판 F-1).
"""
from __future__ import annotations

import numpy as np
import cv2

from .surface import params_from_mask, build_nail_surface
from .design_render import _warp_color_region


def capture_nail_atlas(frame, geom, mask, dcfg, size=384, fine=(28, 24)) -> np.ndarray:
    """손톱1 화면 영역을 정규 UV 아틀라스(BGRA)로 언워프 캡처.

    surface(uv→screen)를 아틀라스 해상도로 보간해 frame을 역샘플. 마스크 안만 알파 1.
    """
    params = params_from_mask(geom, dcfg)
    surf = build_nail_surface(params, "mesh", fine)
    scr = surf.screen.astype(np.float32)                 # (ny+1,nx+1,2) uv→screen
    big = cv2.resize(scr, (size, size), interpolation=cv2.INTER_LINEAR)
    map_x = np.ascontiguousarray(big[:, :, 0])
    map_y = np.ascontiguousarray(big[:, :, 1])
    bgr = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    m = cv2.remap(mask, map_x, map_y, cv2.INTER_NEAREST,
                  borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    atlas = np.dstack([bgr, m]).astype(np.uint8)
    return atlas


def _tps_warp_atlas(atlas, src_uv, dst_uv, lam=0.5):
    """정규화 TPS로 atlas를 src_uv→dst_uv 대응에 맞춰 미세 워핑(없으면 항등)."""
    if not src_uv or not dst_uv or len(src_uv) < 3:
        return atlas
    tps = cv2.createThinPlateSplineShapeTransformer(lam)
    H, W = atlas.shape[:2]
    s = np.array([[u * (W - 1), v * (H - 1)] for u, v in src_uv], np.float32).reshape(1, -1, 2)
    d = np.array([[u * (W - 1), v * (H - 1)] for u, v in dst_uv], np.float32).reshape(1, -1, 2)
    matches = [cv2.DMatch(i, i, 0) for i in range(len(src_uv))]
    tps.estimateTransformation(d, s, matches)
    out = tps.warpImage(atlas)
    return out


def transfer_design(frame2, captured_atlas, geom2, mask2, dcfg,
                    mirror=False, tier="auto", fps=None,
                    src_anchors=None, dst_anchors=None):
    """캡처한 손톱1 디자인 아틀라스를 손톱2에 렌더(제자리). mirror=좌우 u→1-u."""
    atlas = captured_atlas
    if mirror:
        atlas = cv2.flip(atlas, 1)                       # u → 1-u
    if src_anchors and dst_anchors:
        atlas = _tps_warp_atlas(atlas, src_anchors, dst_anchors)
    params = params_from_mask(geom2, dcfg)
    from .surface import choose_tier
    t = choose_tier(params, want=tier, fps=fps)
    grid = getattr(dcfg, "mesh_grid", (10, 8))
    surf = build_nail_surface(params, t, grid)
    _warp_color_region(frame2, atlas, surf, mask2, dcfg)
