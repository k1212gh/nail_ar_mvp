"""A3-1.5 tilt + A3-2 곡률 검증 + 시각화.

검증:
  T1 tilt(랜드마크): tip이 카메라 쪽이면 tip 폭 > root 폭(원근 사다리꼴). 마스크 경로는 tilt=0(대칭).
  C1 curve0 == plane: mesh(curv=0)이 plane과 PSNR>40.
  C2 곡률 압축: mesh(curv>0)에서 가장자리 s간격 < 능선 부근(반원기둥).
  C3 가장자리 누출: 곡률 워핑 디자인이 마스크(+페더) 밖으로 새는 비율 <1%.
시각화: 별을 plane/tilt/mesh로 렌더한 비교 PNG + 메시 와이어프레임.
"""
import math
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import DesignConfig, GeomConfig                         # noqa: E402
from src.geometry import compute_geometry                           # noqa: E402
from src.surface import (params_from_mask, params_from_landmarks,   # noqa: E402
                         build_nail_surface)
from src.design_render import DesignEngine, _warp_color_region      # noqa: E402


def synth_nail(W, H, cx, cy, al, aw, ang):
    mask = np.zeros((H, W), np.uint8)
    cv2.ellipse(mask, (cx, cy), (aw, al), ang, 0, 360, 255, -1)
    geom = compute_geometry(mask, None, GeomConfig())
    return mask, geom


def _edge_w(screen):
    s = screen
    root_w = np.hypot(*(s[0, 1] - s[0, 0]))
    tip_w = np.hypot(*(s[1, 1] - s[1, 0]))
    return tip_w, root_w


def psnr(a, b):
    mse = np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2)
    return float("inf") if mse < 1e-9 else 10 * math.log10(255 * 255 / mse)


def draw_wire(img, surface, color=(0, 255, 0)):
    s = surface.screen
    ny, nx = surface.grid
    for iy in range(ny + 1):
        for ix in range(nx + 1):
            p = tuple(np.round(s[iy, ix]).astype(int))
            if ix < nx:
                q = tuple(np.round(s[iy, ix + 1]).astype(int))
                cv2.line(img, p, q, color, 1, cv2.LINE_AA)
            if iy < ny:
                q = tuple(np.round(s[iy + 1, ix]).astype(int))
                cv2.line(img, p, q, color, 1, cv2.LINE_AA)


def main():
    W, H = 420, 460
    cx, cy = W // 2, H // 2
    mask, geom = synth_nail(W, H, cx, cy, 150, 95, 0)
    dcfg = DesignConfig()
    dcfg.scale = 0.92

    # ---- T1: tilt(랜드마크) 사다리꼴 ----
    pm = params_from_mask(geom, dcfg)
    pl = params_from_landmarks(geom, dcfg, z_tip=0.12, z_dip=0.0)   # tip이 카메라 쪽
    s_mask = build_nail_surface(pm, "tilt", (1, 1)).screen
    s_tilt = build_nail_surface(pl, "tilt", (1, 1)).screen
    tw_m, rw_m = _edge_w(s_mask)
    tw_t, rw_t = _edge_w(s_tilt)
    asym_m = abs(tw_m - rw_m) / ((tw_m + rw_m) / 2)
    asym_t = abs(tw_t - rw_t) / ((tw_t + rw_t) / 2)
    print(f"T1 tilt: tilt_deg={pl['tilt_deg']:.1f}  마스크 비대칭={asym_m:.3f}(≈0)  "
          f"랜드마크 tip폭={tw_t:.1f} root폭={rw_t:.1f} 비대칭={asym_t:.3f}")
    assert asym_m < 1e-3, "마스크 경로는 tilt=0(대칭)이어야"
    assert tw_t > rw_t and asym_t > 0.03, "tip이 카메라쪽이면 tip폭>root폭(사다리꼴)"

    # ---- C1: curve0 == plane ----
    star = os.path.join(ROOT, "samples", "star.png")
    dplane = DesignConfig(); dplane.image_path = star; dplane.scale = 0.92; dplane.warp_tier = "plane"
    dmesh0 = DesignConfig(); dmesh0.image_path = star; dmesh0.scale = 0.92; dmesh0.warp_tier = "mesh"; dmesh0.curve = 0.0
    bg = np.full((H, W, 3), 60, np.uint8)
    fp = bg.copy(); DesignEngine(dplane).render(fp, geom, mask, geom.center)
    fm = bg.copy(); DesignEngine(dmesh0).render(fm, geom, mask, geom.center)
    p01 = psnr(fp, fm)
    print(f"C1 curve0==plane: PSNR(plane vs mesh-curv0) = {p01:.1f} dB (>40)")
    assert p01 > 40, f"curv0 mesh가 plane과 달라짐 ({p01:.1f}dB)"

    # ---- C2: 곡률 압축(반원기둥) ----
    pc = params_from_mask(geom, dcfg, curv_half_angle=0.9)
    sc = build_nail_surface(pc, "mesh", (10, 8)).screen
    top = sc[0]                                       # 뿌리행 정점들의 화면 x투영(가로)
    # 보조축(minor) 투영 좌표로 s간격 측정
    vx, vy = geom.axis_minor
    proj = top[:, 0] * vx + top[:, 1] * vy
    gaps = np.abs(np.diff(proj))
    edge_gap = (gaps[0] + gaps[-1]) / 2
    center_gap = gaps[len(gaps) // 2]
    print(f"C2 곡률 압축: 가장자리 s간격={edge_gap:.2f} < 능선 s간격={center_gap:.2f} "
          f"(비={edge_gap / center_gap:.2f})")
    assert edge_gap < center_gap * 0.85, "반원기둥이면 가장자리가 더 압축돼야"

    # ---- C3: 가장자리 누출 ----
    dcurv = DesignConfig(); dcurv.image_path = star; dcurv.scale = 1.0
    dcurv.warp_tier = "mesh"; dcurv.curve = 0.9; dcurv.feather = 3
    fc = bg.copy()
    DesignEngine(dcurv).render(fc, geom, mask, geom.center)
    changed = np.any(fc != bg, axis=2)
    mask_dil = cv2.dilate(mask, np.ones((2 * dcurv.feather + 3,) * 2, np.uint8))
    leak = int((changed & (mask_dil == 0)).sum())
    inside = int((changed & (mask > 0)).sum())
    ratio = leak / max(inside, 1)
    print(f"C3 누출: 마스크(+페더) 밖 변경 {leak}px / 안 {inside}px = {ratio*100:.2f}% (<1%)")
    assert ratio < 0.01, f"가장자리 누출 {ratio*100:.2f}%"

    # ---- 시각화 ----
    def panel(title, dc, wire_params=None, wire_tier="plane"):
        f = bg.copy()
        cv2.ellipse(f, (cx, cy), (95, 150), 0, 0, 360, (90, 90, 90), -1)  # 손톱 음영
        DesignEngine(dc).render(f, geom, mask, geom.center)
        if wire_params is not None:
            draw_wire(f, build_nail_surface(wire_params, wire_tier,
                      (10, 8) if wire_tier.startswith("mesh") else (1, 1)))
        cv2.putText(f, title, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return f

    d_pl = DesignConfig(); d_pl.image_path = star; d_pl.scale = 0.92; d_pl.warp_tier = "plane"
    d_ti = DesignConfig(); d_ti.image_path = star; d_ti.scale = 0.92; d_ti.warp_tier = "tilt"
    d_me = DesignConfig(); d_me.image_path = star; d_me.scale = 0.92; d_me.warp_tier = "mesh"; d_me.curve = 0.9
    p_pl = panel("plane", d_pl, params_from_mask(geom, d_pl), "plane")
    # tilt 시각화는 랜드마크 z 주입
    eng_ti = DesignEngine(d_ti)
    f_ti = bg.copy(); cv2.ellipse(f_ti, (cx, cy), (95, 150), 0, 0, 360, (90, 90, 90), -1)
    eng_ti.render(f_ti, geom, mask, geom.center, z_tip=0.12, z_dip=0.0)
    draw_wire(f_ti, build_nail_surface(params_from_landmarks(geom, d_ti, 0.12, 0.0), "tilt", (1, 1)))
    cv2.putText(f_ti, "tilt(landmark)", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    p_me = panel("mesh(curve)", d_me, params_from_mask(geom, d_me, curv_half_angle=0.9), "mesh")

    combo = np.hstack([p_pl, f_ti, p_me])
    out = os.path.join(ROOT, "samples", "a3_warp_demo.png")
    cv2.imwrite(out, combo)
    print(f"\n시각화 저장: {out}")
    print("ALL A3-1.5/A3-2 CHECKS OK")


if __name__ == "__main__":
    main()
