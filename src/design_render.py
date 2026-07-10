"""디자인 렌더러(PC consumer) — WarpSpec/NailSurface 정점을 깐다 (DESIGN_WARP §3.2).

- plane/tilt: 4코너 homography(cv2.warpPerspective). plane은 레거시 design_overlay.apply 와
  기하 동일 → 별 회귀 PSNR 게이트 통과.
- mesh/mesh_shaded: 정점 그리드를 삼각형 래스터화해 역UV맵 생성 후 cv2.remap 1회(셀 수 무관).
공통: ROI 한정 워핑(레거시 최적화 보존) → 마스크 클립 + 페더 → 알파 합성(제자리).
"""
from __future__ import annotations

import numpy as np
import cv2

from .design_ir import load_design_ir, bake_uv_atlas
from .surface import (params_from_mask, params_from_landmarks, choose_tier,
                      build_nail_surface, surface_normal_shade, ParamSmoother)


# --------------------------------------------------------------- ROI/삼각형
def _roi_from_screen(screen, w, h, pad=2):
    xs = screen[..., 0]
    ys = screen[..., 1]
    x0 = max(0, int(np.floor(xs.min())) - pad)
    y0 = max(0, int(np.floor(ys.min())) - pad)
    x1 = min(w, int(np.ceil(xs.max())) + pad)
    y1 = min(h, int(np.ceil(ys.max())) + pad)
    return x0, y0, x1, y1


def _raster_tri(mx, my, ox, oy, a, b, c, ta, tb, tc, Wt):
    """삼각형 (a,b,c)=screen, (ta,tb,tc)=uv 를 map_x/map_y(ROI 로컬)에 채움."""
    rh, rw = mx.shape
    minx = max(int(np.floor(min(a[0], b[0], c[0]))), ox)
    maxx = min(int(np.ceil(max(a[0], b[0], c[0]))), ox + rw - 1)
    miny = max(int(np.floor(min(a[1], b[1], c[1]))), oy)
    maxy = min(int(np.ceil(max(a[1], b[1], c[1]))), oy + rh - 1)
    if minx > maxx or miny > maxy:
        return
    denom = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(denom) < 1e-9:
        return
    gx, gy = np.meshgrid(np.arange(minx, maxx + 1), np.arange(miny, maxy + 1))
    gxf = gx.astype(np.float32)
    gyf = gy.astype(np.float32)
    w0 = ((b[1] - c[1]) * (gxf - c[0]) + (c[0] - b[0]) * (gyf - c[1])) / denom
    w1 = ((c[1] - a[1]) * (gxf - c[0]) + (a[0] - c[0]) * (gyf - c[1])) / denom
    w2 = 1.0 - w0 - w1
    inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
    if not inside.any():
        return
    u = w0 * ta[0] + w1 * tb[0] + w2 * tc[0]
    v = w0 * ta[1] + w1 * tb[1] + w2 * tc[1]
    # 클립하지 않음 — uv∉[0,1](fit=contain 여백)은 remap BORDER_CONSTANT로 투명 처리.
    sx = u * (Wt - 1)
    sy = v * (Wt - 1)
    ly = (gy - oy)[inside]
    lx = (gx - ox)[inside]
    mx[ly, lx] = sx[inside]
    my[ly, lx] = sy[inside]


def _fit_scale(mode, a_nail, a_des):
    """fit_mode + 손톱비율(a_nail=width/length) + 디자인비율(a_des) → uv 인셋 (su, sv).

    stretch=(1,1)(현동작). contain=디자인 비율 보존하며 손톱 박스 안에 맞춤(여백).
    cover=비율 보존하며 박스 채움(넘침 크롭).
    """
    if mode == "stretch" or a_des <= 0 or a_nail <= 0:
        return 1.0, 1.0
    r = a_des / a_nail
    if mode == "contain":
        # 손톱이 디자인보다 넓으면(r<1) 가로 인셋, 좁으면 세로 인셋
        return (r, 1.0) if r < 1.0 else (1.0, 1.0 / r)
    if mode == "cover":
        return (1.0, 1.0 / r) if r < 1.0 else (r, 1.0)
    return 1.0, 1.0


def _apply_fit_uv(uv, su, sv):
    if su == 1.0 and sv == 1.0:
        return uv
    out = uv.copy()
    out[..., 0] = 0.5 + (uv[..., 0] - 0.5) / su
    out[..., 1] = 0.5 + (uv[..., 1] - 0.5) / sv
    return out


def _warp_color_region(frame, atlas, surface, mask, dcfg, shade=None, fit=(1.0, 1.0)):
    """atlas(BGRA)를 surface로 워핑해 frame 위 합성(제자리). ROI 한정. fit=uv 인셋."""
    h, w = frame.shape[:2]
    scr = surface.screen
    x0, y0, x1, y1 = _roi_from_screen(scr, w, h)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    sub_w, sub_h = x1 - x0, y1 - y0
    Wt = atlas.shape[0]
    su, sv = fit

    if surface.tier in ("plane", "tilt"):
        # 4코너 homography. src(atlas) 코너에 fit 인셋 적용(범위 밖=투명 여백).
        def ax(u):
            return (0.5 + (u - 0.5) / su) * (Wt - 1)

        def ay(v):
            return (0.5 + (v - 0.5) / sv) * (Wt - 1)
        src = np.float32([[ax(0), ay(0)], [ax(1), ay(0)], [ax(0), ay(1)], [ax(1), ay(1)]])
        dst = scr.reshape(-1, 2).astype(np.float32) - np.float32([x0, y0])
        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(atlas, M, (sub_w, sub_h),
                                     flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_CONSTANT,
                                     borderValue=(0, 0, 0, 0))
    else:
        # mesh: 삼각형 래스터 → 역UV맵 → remap 1회
        map_x = np.full((sub_h, sub_w), -1.0, np.float32)
        map_y = np.full((sub_h, sub_w), -1.0, np.float32)
        ny, nx = surface.grid
        uv = _apply_fit_uv(surface.uv, su, sv)
        for iy in range(ny):
            for ix in range(nx):
                p00, p10 = scr[iy, ix], scr[iy, ix + 1]
                p11, p01 = scr[iy + 1, ix + 1], scr[iy + 1, ix]
                t00, t10 = uv[iy, ix], uv[iy, ix + 1]
                t11, t01 = uv[iy + 1, ix + 1], uv[iy + 1, ix]
                _raster_tri(map_x, map_y, x0, y0, p00, p10, p11, t00, t10, t11, Wt)
                _raster_tri(map_x, map_y, x0, y0, p00, p11, p01, t00, t11, t01, Wt)
        cover = map_x >= 0
        warped = cv2.remap(atlas, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        warped[~cover] = 0
        if shade is not None:
            # 법선 음영을 격자→ROI로 보간해 RGB에 곱(0199)
            sh = cv2.resize(shade, (sub_w, sub_h), interpolation=cv2.INTER_LINEAR)
            warped[:, :, :3] = np.clip(
                warped[:, :, :3].astype(np.float32) * sh[:, :, None], 0, 255).astype(np.uint8)

    alpha = warped[:, :, 3].astype(np.float32) / 255.0 * float(dcfg.alpha)
    if getattr(dcfg, "clip_to_mask", True) and mask is not None:
        m = (mask[y0:y1, x0:x1] > 0).astype(np.float32)
        if getattr(dcfg, "feather", 0) > 0:
            k = int(dcfg.feather) * 2 + 1
            m = cv2.GaussianBlur(m, (k, k), 0)
        alpha = alpha * m
    a = alpha[:, :, None]
    sub = frame[y0:y1, x0:x1].astype(np.float32)
    rgb = warped[:, :, :3].astype(np.float32)
    frame[y0:y1, x0:x1] = (rgb * a + sub * (1.0 - a)).astype(np.uint8)


# --------------------------------------------------------------- 엔진
class DesignEngine:
    """IR 로드 + atlas bake(1회) + 프레임마다 surface 워핑. design_overlay.apply 대체."""

    def __init__(self, dcfg, atlas_size=512):
        self.dcfg = dcfg
        self.ir = load_design_ir(dcfg.image_path,
                                 fit_mode=getattr(dcfg, "fit_mode", "stretch"))
        self.atlas = None
        if self.ir is not None:
            import os
            assets = os.path.dirname(os.path.abspath(dcfg.image_path)) \
                if isinstance(dcfg.image_path, str) and dcfg.image_path.endswith((".png", ".jpg")) else ""
            self.atlas = bake_uv_atlas(self.ir, size=atlas_size, assets_dir=assets)
            # UV공간 페더(B-2): 디자인 자체 알파 경계를 UV에서 흐림 → 곡률 무관 균일.
            fuv = float(getattr(dcfg, "feather_uv", 0.0))
            if fuv > 0 and self.atlas is not None:
                k = max(1, int(fuv * atlas_size)) * 2 + 1
                self.atlas[:, :, 3] = cv2.GaussianBlur(self.atlas[:, :, 3], (k, k), 0)
        self.smoother = ParamSmoother()
        self._a_des = self._design_aspect()

    def _design_aspect(self):
        if self.ir is None:
            return 0.0
        return float(self.ir.get("aspect_hint", 0.0)) or 0.0

    def ok(self):
        return self.atlas is not None

    def render(self, frame, geom, mask, center, key=None, fps=None,
               z_tip=None, z_dip=None, dt=1.0 / 30):
        """손톱 하나에 디자인 합성. z_*가 있으면 랜드마크 tilt, 없으면 마스크(tilt=0)."""
        if self.atlas is None:
            return
        d = self.dcfg
        if z_tip is not None and z_dip is not None:
            params = params_from_landmarks(geom, d, z_tip, z_dip, center=center)
        else:
            params = params_from_mask(geom, d, center=center)
        if key is not None:
            params = self.smoother.smooth(key, params, dt=dt)
        tier = choose_tier(params, want=getattr(d, "warp_tier", "auto"), fps=fps)
        grid = getattr(d, "mesh_grid", (10, 8))
        surface = build_nail_surface(params, tier, grid)
        shade = None
        if tier == "mesh_shaded":
            shade = surface_normal_shade(params, surface.ny, surface.nx)
        # fit_mode: 손톱비율 대비 디자인 비율 보존(contain/cover). stretch=현동작.
        fit_mode = self.ir.get("fit_mode", getattr(d, "fit_mode", "stretch"))
        a_nail = float(geom.width) / max(float(geom.length), 1e-6)
        fit = _fit_scale(fit_mode, a_nail, self._a_des)
        _warp_color_region(frame, self.atlas, surface, mask, d, shade=shade, fit=fit)
