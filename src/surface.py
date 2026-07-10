"""표면 추정 — geom/랜드마크 → SurfaceParams → NailSurface 메시 (DESIGN_WARP §2.3, §4).

핵심 원칙(P0-1): **mono 마스크 경로는 tilt를 추정하지 않는다.** 단일 실루엣에서
aspect 변화는 tilt·손톱비율·부분가림과 구분 불가하고 앞/뒤 부호는 원리적으로 못 푼다.
따라서 `params_from_mask`는 tilt_deg=0 고정(곡률 prior는 허용). tilt는 랜드마크 z가 있는
`params_from_landmarks`에서만 산출한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from spec.warp_spec import build_warp_spec


# --------------------------------------------------------------------------
# SurfaceParams: build_warp_spec(py/js)가 그대로 소비하는 plain dict.
# --------------------------------------------------------------------------
def params_from_geom(geom, dcfg, center=None, tilt_deg=0.0,
                     tilt_axis=(1.0, 0.0), curv_half_angle=None):
    """NailGeometry + DesignConfig → SurfaceParams dict.

    center=None 이면 geom.center, 아니면 외부에서 평활된 중심(sc)을 우선.
    curv_half_angle=None 이면 dcfg.curve 사용(0=평면).
    """
    cx, cy = (geom.center if center is None else center)
    curv = float(dcfg.curve if curv_half_angle is None else curv_half_angle)
    feather_uv = float(getattr(dcfg, "feather_uv", 0.0))
    if feather_uv <= 0.0 and getattr(dcfg, "feather", 0) > 0:
        # 레거시 px 페더 → UV폭 근사(손톱 길이 대비). 곡률 무관 균일 페더(B-2).
        feather_uv = float(dcfg.feather) / max(float(geom.length), 1.0)
    return {
        "center_px": [float(cx), float(cy)],
        "axis_major": [float(geom.axis_major[0]), float(geom.axis_major[1])],
        "axis_minor": [float(geom.axis_minor[0]), float(geom.axis_minor[1])],
        "length": float(geom.length), "width": float(geom.width),
        "scale": float(dcfg.scale), "along": float(dcfg.along),
        "tilt_deg": float(tilt_deg),
        "tilt_axis": [float(tilt_axis[0]), float(tilt_axis[1])],
        "curv_half_angle": curv, "persp_f": 0.0,
        "feather_uv": feather_uv, "alpha": float(dcfg.alpha),
    }


def params_from_mask(geom, dcfg, center=None, curv_half_angle=None):
    """마스크/YOLO 경로 — tilt 항상 0 (P0-1). 곡률은 표준모델 prior로 허용."""
    return params_from_geom(geom, dcfg, center=center, tilt_deg=0.0,
                            curv_half_angle=curv_half_angle)


def tilt_from_landmark_depth(z_tip, z_dip, length, axis_major):
    """랜드마크 z(상대깊이) 차 → out-of-plane tilt_deg + tilt_axis.

    tip이 카메라 쪽(z 큼)이면 +, 멀어지면 -. axis_minor 둘레로 기울어지므로
    tilt_axis = axis_minor 방향(major에 수직). length로 정규화해 각도화.
    """
    dz = float(z_tip - z_dip)
    if length < 1e-6:
        return 0.0, (1.0, 0.0)
    # dz/length ≈ tan(theta) (약투영). 부호 보존(+면 tip이 카메라 쪽).
    theta = math.degrees(math.atan2(dz, max(length * 1e-3, 1e-6)))
    theta = max(-60.0, min(60.0, theta))
    # 회전축 = 로컬 s축(minor) = (1,0). tip/root가 깊이로 기울어 foreshorten.
    return theta, (1.0, 0.0)


def params_from_landmarks(geom, dcfg, z_tip, z_dip, center=None,
                          curv_half_angle=None):
    """랜드마크 경로 — z차로 tilt 산출(P0-1 예외: 랜드마크는 깊이 단서 보유)."""
    tilt_deg, tilt_axis = tilt_from_landmark_depth(
        z_tip, z_dip, geom.length, geom.axis_major)
    return params_from_geom(geom, dcfg, center=center, tilt_deg=tilt_deg,
                            tilt_axis=tilt_axis, curv_half_angle=curv_half_angle)


def choose_tier(params, want="auto", fps=None):
    """SurfaceParams + (옵션)fps → 렌더 tier. 폴백 사다리(DESIGN_WARP §7)."""
    has_tilt = abs(params.get("tilt_deg", 0.0)) > 0.5
    has_curv = (params.get("curv_half_angle", 0.0) or 0.0) > 1e-3
    if want != "auto":
        return want
    if fps is not None and fps < 8:
        return "plane"                       # 저fps 강등
    if has_curv:
        return "mesh"
    if has_tilt:
        return "tilt"
    return "plane"


# --------------------------------------------------------------------------
# NailSurface: 정규 UV 격자 위 표면 메시 (PC consumer가 cv2.remap에 쓸 numpy).
# --------------------------------------------------------------------------
@dataclass
class NailSurface:
    tier: str
    grid: tuple            # (ny, nx)
    uv: np.ndarray         # (ny+1, nx+1, 2) f32  정규 텍스처좌표 [0,1]
    screen: np.ndarray     # (ny+1, nx+1, 2) f32  프레임 픽셀좌표
    feather_uv: float
    alpha: float
    params: dict

    @property
    def ny(self):
        return self.grid[0]

    @property
    def nx(self):
        return self.grid[1]


def build_nail_surface(params, tier="plane", grid=(8, 6)) -> NailSurface:
    """SurfaceParams → NailSurface. plane/tilt는 4코너(1x1), mesh는 grid."""
    spec = build_warp_spec(params, tier, grid)
    ny, nx = spec["grid"]
    uv = np.array(spec["uv"], np.float32).reshape(ny + 1, nx + 1, 2)
    screen = np.array(spec["screen"], np.float32).reshape(ny + 1, nx + 1, 2)
    return NailSurface(tier=spec["tier"], grid=(ny, nx), uv=uv, screen=screen,
                       feather_uv=spec["feather_uv"], alpha=spec["alpha"],
                       params=params)


def surface_normal_shade(params, ny, nx, light=(0.0, 0.0, 1.0)):
    """mesh_shaded용 — 정규 UV 격자에서 로컬 3D(곡률/tilt 적용 전 z_curv 기준) 법선·음영.

    반환 shade: (ny+1, nx+1) f32, 0.6~1.0. 능선 밝고 가장자리 어둠(0199 법선 음영).
    곡률이 0이면 전부 1.0(평면).
    """
    cha = (params.get("curv_half_angle", 0.0) or 0.0)
    W = params["width"] * params.get("scale", 1.0)
    L = params["length"] * params.get("scale", 1.0)
    shade = np.ones((ny + 1, nx + 1), np.float32)
    if cha <= 1e-6:
        return shade
    lx, ly, lz = light
    ln = math.sqrt(lx * lx + ly * ly + lz * lz) or 1.0
    lx, ly, lz = lx / ln, ly / ln, lz / ln
    for iy in range(ny + 1):
        for ix in range(nx + 1):
            u = ix / nx
            phi = (u - 0.5) * 2.0 * cha
            # 반원기둥 표면 법선(가로방향 성분 = sin(phi), 깊이성분 = cos(phi))
            nxv = math.sin(phi)
            nzv = math.cos(phi)
            d = max(0.0, nxv * lx + nzv * lz)
            shade[iy, ix] = 0.6 + 0.4 * d
    return shade


# --------------------------------------------------------------------------
# One-Euro 필터 — tilt_deg/curv 등 추정 스칼라 시간 평활 (G-3).
# --------------------------------------------------------------------------
class OneEuro:
    """1D One-Euro 필터. 느릴 땐 부드럽게, 빠를 땐 지연 적게."""

    def __init__(self, min_cutoff=1.0, beta=0.02, dcutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.dcutoff = dcutoff
        self._x = None
        self._dx = 0.0

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, dt):
        if dt <= 0:
            dt = 1e-3
        if self._x is None:
            self._x = x
            return x
        dx = (x - self._x) / dt
        a_d = self._alpha(self.dcutoff, dt)
        self._dx = a_d * dx + (1 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        a = self._alpha(cutoff, dt)
        self._x = a * x + (1 - a) * self._x
        return self._x


class ParamSmoother:
    """손톱 key별 SurfaceParams 스칼라 평활(tilt_deg·curv·center). confidence 게이팅."""

    _FIELDS = ("tilt_deg", "curv_half_angle")

    def __init__(self):
        self._f = {}

    def smooth(self, key, params, dt=1.0 / 30):
        filt = self._f.setdefault(key, {k: OneEuro() for k in self._FIELDS})
        out = dict(params)
        for k in self._FIELDS:
            out[k] = float(filt[k](float(params.get(k, 0.0)), dt))
        return out
