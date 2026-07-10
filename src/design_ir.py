"""Design IR — 임의 복잡 디자인을 정규 손톱 UV의 레이어드 표현으로 (DESIGN_WARP §2.2).

런타임은 IR + bake된 UV 아틀라스(BGRA)만 소비한다. 별 PNG는 1장짜리 IR(T-0)로 흡수해
기존 동작을 보존한다(fit_mode=stretch).

좌표 규약(warp_spec과 일치): u=0 좌측…u=1 우측 / v=0 뿌리…v=1 팁.
아틀라스 행 r = v*(H-1) (행0=v0=뿌리=위). T-0 래스터는 레거시(이미지 top=팁) 정합을 위해
flip_v=True 로 적재(별은 상하대칭이라 무관, 비대칭 디자인은 팁 방향 보존).
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

import cv2
import numpy as np


# ---------------------------------------------------------------- IR 구성/로드
def wrap_raster_as_ir(image_path: str, fit_mode: str = "stretch") -> dict:
    """단일 래스터(별 등) → T-0 IR. 기존 동작 100% 보존용."""
    return {
        "schema": "nail-design/1",
        "uv_template": "square",
        "fit_mode": fit_mode,
        "_legacy_t0": True,
        "layers": [{
            "id": "base", "role": "color_region", "type": "raster",
            "src": image_path, "uv": [0, 0, 1, 1], "flip_v": True,
            "blend": "normal", "opacity": 1.0,
        }],
        "anchors": [],
    }


def load_design_ir(spec, fit_mode: str = "stretch") -> Optional[dict]:
    """spec = .json IR 경로 | 래스터 이미지 경로 | IR dict → IR dict."""
    if isinstance(spec, dict):
        return spec
    if not spec:
        return None
    ext = os.path.splitext(spec)[1].lower()
    if ext == ".json":
        with open(spec, encoding="utf-8") as f:
            return json.load(f)
    return wrap_raster_as_ir(spec, fit_mode=fit_mode)        # 래스터 → T-0


# ---------------------------------------------------------------- 색/벡터 유틸
def _hex_bgr(s: str):
    s = s.lstrip("#")
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    return (b, g, r)


def _parse_path_uv(d: str):
    """아주 작은 SVG path 파서 (M/L/Q, UV 절대좌표). 폴리라인 점열 반환."""
    toks = re.findall(r"[MLQ]|-?\d*\.?\d+", d)
    pts, i = [], 0
    cur = (0.0, 0.0)
    while i < len(toks):
        c = toks[i]
        if c == "M":
            cur = (float(toks[i + 1]), float(toks[i + 2])); pts.append(cur); i += 3
        elif c == "L":
            cur = (float(toks[i + 1]), float(toks[i + 2])); pts.append(cur); i += 3
        elif c == "Q":
            qx, qy = float(toks[i + 1]), float(toks[i + 2])
            ex, ey = float(toks[i + 3]), float(toks[i + 4])
            for k in range(1, 13):
                t = k / 12.0
                mt = 1 - t
                x = mt * mt * cur[0] + 2 * mt * t * qx + t * t * ex
                y = mt * mt * cur[1] + 2 * mt * t * qy + t * t * ey
                pts.append((x, y))
            cur = (ex, ey); i += 5
        else:
            i += 1
    return pts


def _uv_to_px(u, v, W, H, flip_v=False):
    vv = (1.0 - v) if flip_v else v
    return int(round(u * (W - 1))), int(round(vv * (H - 1)))


# ---------------------------------------------------------------- atlas bake
def _over(dst_bgra, src_bgra):
    """src(BGRA) over dst(BGRA), straight alpha. 제자리."""
    sa = src_bgra[:, :, 3:4].astype(np.float32) / 255.0
    da = dst_bgra[:, :, 3:4].astype(np.float32) / 255.0
    oa = sa + da * (1 - sa)
    out_rgb = (src_bgra[:, :, :3].astype(np.float32) * sa +
               dst_bgra[:, :, :3].astype(np.float32) * da * (1 - sa))
    np.divide(out_rgb, np.where(oa > 1e-6, oa, 1.0), out=out_rgb)
    dst_bgra[:, :, :3] = np.clip(out_rgb, 0, 255).astype(np.uint8)
    dst_bgra[:, :, 3] = np.clip(oa[:, :, 0] * 255.0, 0, 255).astype(np.uint8)


def bake_uv_atlas(ir: dict, size: int = 512, assets_dir: str = "") -> np.ndarray:
    """IR → 정규 UV 아틀라스(BGRA, size×size). color_region/vector를 단일 아틀라스로 통합.

    DESIGN_WARP §5(C-1): 장식용 벡터(프렌치 등)도 같은 아틀라스에 supersample bake 해
    seam 없이 1회 워핑. decoration_3d/text는 별도 경로(여기서 제외).
    그라데이션은 PC에선 아틀라스 bake(웹은 analytic) — 모아레/밴딩은 mesh 단계 mip/INTER_AREA로 완화.
    """
    SS = 2                                   # supersample (벡터 AA)
    W = H = size * SS
    atlas = np.zeros((H, W, 4), np.uint8)
    for layer in ir.get("layers", []):
        role = layer.get("role")
        typ = layer.get("type")
        opacity = float(layer.get("opacity", 1.0))
        lay = np.zeros((H, W, 4), np.uint8)
        if typ == "raster":
            src = layer["src"]
            if assets_dir and not os.path.isabs(src):
                src = os.path.join(assets_dir, src)
            img = cv2.imread(src, cv2.IMREAD_UNCHANGED)
            if img is None:
                continue
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
            elif img.shape[2] == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
            u0, v0, u1, v1 = layer.get("uv", [0, 0, 1, 1])
            x0, x1 = int(u0 * W), int(u1 * W)
            y0, y1 = int(v0 * H), int(v1 * H)
            tw, th = max(1, x1 - x0), max(1, y1 - y0)
            rs = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)
            if layer.get("flip_v"):
                rs = cv2.flip(rs, 0)         # 이미지 top=팁(레거시 정합)
            lay[y0:y0 + th, x0:x0 + tw] = rs
        elif typ == "gradient":
            stops = layer.get("stops", [["#ffffff", 0.0], ["#000000", 1.0]])
            axis = layer.get("axis", "v")
            grad = _render_gradient(H, W, stops, axis)
            lay = grad
        elif typ in ("vector",) or role in ("french_boundary", "line", "outline"):
            pts = _parse_path_uv(layer.get("path", ""))
            if len(pts) >= 2:
                col = _hex_bgr(layer.get("stroke", "#ffffff"))
                wpx = max(1, int(layer.get("width_uv", 0.03) * H))
                poly = np.array([_uv_to_px(u, v, W, H) for (u, v) in pts], np.int32)
                bgr = np.zeros((H, W, 3), np.uint8)        # 연속 배열에 그린 뒤 복사
                am = np.zeros((H, W), np.uint8)
                cv2.polylines(bgr, [poly], False, col, wpx, cv2.LINE_AA)
                cv2.polylines(am, [poly], False, 255, wpx, cv2.LINE_AA)
                lay[:, :, :3] = bgr
                lay[:, :, 3] = am
        else:
            continue                          # text/decoration_3d 등은 별도 경로
        if opacity < 1.0:
            lay[:, :, 3] = (lay[:, :, 3].astype(np.float32) * opacity).astype(np.uint8)
        _over(atlas, lay)
    if SS > 1:
        atlas = cv2.resize(atlas, (size, size), interpolation=cv2.INTER_AREA)
    return atlas


def _render_gradient(H, W, stops, axis):
    out = np.zeros((H, W, 4), np.uint8)
    s = sorted(stops, key=lambda x: x[1])
    cols = np.array([_hex_bgr(c) for c, _ in s], np.float32)
    pos = np.array([p for _, p in s], np.float32)
    t = (np.linspace(0, 1, W if axis == "u" else H)).astype(np.float32)
    b = np.interp(t, pos, cols[:, 0])
    g = np.interp(t, pos, cols[:, 1])
    r = np.interp(t, pos, cols[:, 2])
    line = np.stack([b, g, r, np.full_like(b, 255)], 1).astype(np.uint8)
    if axis == "u":
        out[:, :, :] = line[None, :, :]
    else:
        out[:, :, :] = line[:, None, :]
    return out


def layers_by_role(ir: dict, role: str):
    return [L for L in ir.get("layers", []) if L.get("role") == role]
