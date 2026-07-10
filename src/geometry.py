"""기하 산출 — 손톱 마스크에서 중심점·중심축·격자·프렌치 라인·부착점 (계획서 A-3).

PCA로 손톱 세로 주축과 중심을 얻고, 그 로컬 좌표계 위에서 안내선을 만든다.
모든 산출물은 '전체 프레임 px 좌표'로 반환하므로 오버레이가 그대로 그린다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np


@dataclass
class NailGeometry:
    finger: str
    handedness: str
    center: tuple                      # 무게중심 (x, y)
    axis_major: tuple                  # 세로 주축 단위벡터(손톱 끝 방향)
    axis_minor: tuple                  # 가로 보조축 단위벡터
    angle_deg: float                   # 주축 방향각
    length: float                      # 세로 길이(px)
    width: float                       # 가로 폭(px)
    contour: np.ndarray                # 손톱 외곽 컨투어
    tip_point: tuple                   # 손톱 끝점
    grid_lines: List[tuple] = field(default_factory=list)      # [((x1,y1),(x2,y2))]
    french_curve: List[tuple] = field(default_factory=list)    # [(x,y), ...]
    attach_points: List[tuple] = field(default_factory=list)   # [(x,y), ...]


def geometry_from_roi(roi, length_ratio: float = 0.55, width_ratio: float = 0.75,
                      center_ratio: float = 0.72) -> "NailGeometry":
    """세그 없이 손 랜드마크(ROI)만으로 손톱 '판' 크기·위치를 추정 (--seg none).

    맨손톱은 피부와 색이 같아 세그가 불안정하므로 랜드마크로 추정한다. 단,
    손톱판은 손가락 끝마디(TIP-DIP 거리)보다 작으므로 비율로 줄여서 손톱 크기에 맞춘다.
      - length = 끝마디 길이 × length_ratio (손톱 세로, 끝마디의 ~55%)
      - width  = length × width_ratio       (손톱 가로)
      - center = DIP→TIP 의 center_ratio 지점(관절이 아닌 끝쪽 손톱판 위)
    """
    ax, ay = roi.axis
    tx, ty = roi.tip_xy
    dx, dy = roi.dip_xy
    seg = math.hypot(tx - dx, ty - dy)          # 손가락 끝마디 길이(투영)
    if seg < 1.0:
        seg = max(8.0, roi.size * 0.5)
    length = seg * length_ratio                  # 손톱 세로(끝마디보다 작게)
    width = length * width_ratio                 # 손톱 가로
    cx = dx + (tx - dx) * center_ratio           # 손톱 중심을 끝쪽으로
    cy = dy + (ty - dy) * center_ratio
    minor = (-ay, ax)
    angle = math.degrees(math.atan2(ay, ax))
    # 회전 사각형 근사 컨투어(부착점/마스크 대용은 비워둠)
    half_l, half_w = length / 2.0, width / 2.0
    box = np.array([
        [cx + ax * half_l + minor[0] * half_w, cy + ay * half_l + minor[1] * half_w],
        [cx + ax * half_l - minor[0] * half_w, cy + ay * half_l - minor[1] * half_w],
        [cx - ax * half_l - minor[0] * half_w, cy - ay * half_l - minor[1] * half_w],
        [cx - ax * half_l + minor[0] * half_w, cy - ay * half_l + minor[1] * half_w],
    ], dtype=np.int32)
    return NailGeometry(
        finger=roi.finger, handedness=roi.handedness, center=(cx, cy),
        axis_major=(ax, ay), axis_minor=minor, angle_deg=angle,
        length=length, width=width, contour=box, tip_point=(tx, ty))


def _resolve_center(contour, centroid, major, minor, mode):
    """작업 기준 중심 산출 (특허 청구항 2: 기하학적 중심 / 시각적 균형 중심).

    면적 무게중심(centroid)은 손톱이 비대칭이거나 일부만 보일 때(특히 엄지)
    넓은 뿌리쪽으로 쏠려 디자인이 정중앙에서 빗나간다. 그래서 기본은 'obb'.

    - "centroid": 면적 무게중심(구버전). 비대칭/부분 마스크에서 쏠림.
    - "obb": 주축 투영 min~max의 중점 = 방향 정렬 외접박스 중심(기본, 안전 폴백).
    - "ellipse": 손톱 외곽 타원 피팅 중심. 단, fitEllipse는 컨투어가 희소하거나
      길쭉하면 중심이 박스 밖으로 튀므로, 박스 안에 있을 때만 채택하고
      아니면 obb로 폴백한다.
    """
    if mode == "centroid":
        return centroid

    # obb 중심 + 주축/보조축 투영 범위 (항상 계산: 기본값이자 ellipse 안전망)
    pts = contour - np.array(centroid, np.float32)
    pj = pts[:, 0] * major[0] + pts[:, 1] * major[1]
    pn = pts[:, 0] * minor[0] + pts[:, 1] * minor[1]
    t_lo, t_hi = float(pj.min()), float(pj.max())
    s_lo, s_hi = float(pn.min()), float(pn.max())
    t_mid, s_mid = 0.5 * (t_lo + t_hi), 0.5 * (s_lo + s_hi)
    obb = (centroid[0] + major[0] * t_mid + minor[0] * s_mid,
           centroid[1] + major[1] * t_mid + minor[1] * s_mid)

    if mode == "ellipse" and len(contour) >= 5:
        (ex, ey), _axes, _ang = cv2.fitEllipse(contour.astype(np.float32))
        # 타원 중심을 로컬축에 투영해 방향 박스 안인지 검사 → 밖이면 obb로 폴백
        et = (ex - centroid[0]) * major[0] + (ey - centroid[1]) * major[1]
        es = (ex - centroid[0]) * minor[0] + (ey - centroid[1]) * minor[1]
        if t_lo <= et <= t_hi and s_lo <= es <= s_hi:
            return (float(ex), float(ey))
        return obb

    return obb  # 기본: obb (방향 박스 중심)


def _largest_contour(mask: np.ndarray) -> Optional[np.ndarray]:
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 10:
        return None
    return c.reshape(-1, 2).astype(np.float32)


def compute_geometry(mask: np.ndarray, roi, cfg) -> Optional[NailGeometry]:
    contour = _largest_contour(mask)
    if contour is None or len(contour) < 5:
        return None

    # --- PCA: 주축 + 무게중심 ------------------------------------------
    mean, eigvec, eigval = cv2.PCACompute2(contour, mean=np.empty((0)))
    centroid = (float(mean[0, 0]), float(mean[0, 1]))
    major = (float(eigvec[0, 0]), float(eigvec[0, 1]))
    minor = (float(eigvec[1, 0]), float(eigvec[1, 1]))

    # 주축이 손톱 끝(TIP) 방향을 향하도록 부호 정렬
    if roi is not None:
        ax, ay = roi.axis                     # ROI의 tip 방향 사용
        if major[0] * ax + major[1] * ay < 0:
            major = (-major[0], -major[1])
            minor = (-minor[0], -minor[1])
    else:
        if major[1] > 0:                      # ROI 없음(YOLO): 영상 위쪽을 tip으로 가정
            major = (-major[0], -major[1])
            minor = (-minor[0], -minor[1])
    angle_deg = math.degrees(math.atan2(major[1], major[0]))

    # --- 작업 기준 중심 선택 (청구항 2) — 무게중심 쏠림 보정 -------------
    center = _resolve_center(contour, centroid, major, minor,
                             getattr(cfg, "center_mode", "obb"))

    # --- 로컬 좌표 투영으로 길이/폭 추정 (선택된 중심 기준) --------------
    pts = contour - np.array(center, np.float32)
    proj_major = pts[:, 0] * major[0] + pts[:, 1] * major[1]
    proj_minor = pts[:, 0] * minor[0] + pts[:, 1] * minor[1]
    t_min, t_max = float(proj_major.min()), float(proj_major.max())
    s_min, s_max = float(proj_minor.min()), float(proj_minor.max())
    length = t_max - t_min
    width = s_max - s_min

    def local_to_px(t, s):
        return (center[0] + major[0] * t + minor[0] * s,
                center[1] + major[1] * t + minor[1] * s)

    tip_point = local_to_px(t_max, 0.0)

    geom = NailGeometry(
        finger=(roi.finger if roi is not None else "nail"),
        handedness=(roi.handedness if roi is not None else ""), center=center,
        axis_major=major, axis_minor=minor, angle_deg=angle_deg,
        length=length, width=width, contour=contour.astype(np.int32),
        tip_point=tip_point)

    # --- 격자선 (마스크로 클리핑) ---------------------------------------
    geom.grid_lines = _build_grid(mask, local_to_px, t_min, t_max, s_min, s_max, cfg)
    # --- 프렌치 라인 (끝에서 french_ratio 위치의 가로 곡선) -------------
    geom.french_curve = _build_french(mask, local_to_px, t_min, t_max,
                                       s_min, s_max, cfg)
    # --- 부착점 (외곽 등간격 샘플) --------------------------------------
    geom.attach_points = _build_attach_points(contour, cfg)
    return geom


def _clip_segment_to_mask(mask, p1, p2, samples=40):
    """선분을 마스크 내부 구간만 남겨 (시작,끝) 반환. 없으면 None."""
    h, w = mask.shape[:2]
    inside = []
    for i in range(samples + 1):
        t = i / samples
        x = p1[0] + (p2[0] - p1[0]) * t
        y = p1[1] + (p2[1] - p1[1]) * t
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < w and 0 <= yi < h and mask[yi, xi] > 0:
            inside.append((x, y))
    if len(inside) < 2:
        return None
    return inside[0], inside[-1]


def _build_grid(mask, local_to_px, t_min, t_max, s_min, s_max, cfg):
    lines = []
    # 가로선(주축을 따라 등분) — 세로 위치 t를 나눠 가로로 긋는다
    for r in range(1, cfg.grid_rows + 1):
        t = t_min + (t_max - t_min) * r / (cfg.grid_rows + 1)
        seg = _clip_segment_to_mask(mask, local_to_px(t, s_min), local_to_px(t, s_max))
        if seg:
            lines.append(seg)
    # 세로선(보조축을 따라 등분)
    for c in range(1, cfg.grid_cols + 1):
        s = s_min + (s_max - s_min) * c / (cfg.grid_cols + 1)
        seg = _clip_segment_to_mask(mask, local_to_px(t_min, s), local_to_px(t_max, s))
        if seg:
            lines.append(seg)
    return lines


def _build_french(mask, local_to_px, t_min, t_max, s_min, s_max, cfg):
    """손톱 끝(t_max)에서 french_ratio만큼 안쪽에 가로 곡선(스마일 라인)."""
    t = t_max - (t_max - t_min) * cfg.french_ratio
    curve = []
    n = 24
    bow = (t_max - t_min) * cfg.french_ratio * 0.5  # 끝 쪽으로 볼록
    h, w = mask.shape[:2]
    for i in range(n + 1):
        u = i / n
        s = s_min + (s_max - s_min) * u
        # 가운데가 손톱 끝 쪽으로 볼록한 포물선
        t_local = t + bow * (1 - (2 * u - 1) ** 2)
        x, y = local_to_px(t_local, s)
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < w and 0 <= yi < h and mask[yi, xi] > 0:
            curve.append((x, y))
    return curve


def _build_attach_points(contour, cfg):
    """외곽 컨투어를 등간격 샘플링한 장식 부착점."""
    n = max(4, cfg.attach_points_per_edge * 4)
    peri = cv2.arcLength(contour.astype(np.float32), True)
    if peri <= 0:
        return []
    approx = cv2.approxPolyDP(contour.astype(np.int32), 0.002 * peri, True).reshape(-1, 2)
    # 누적 호 길이 기준 등간격
    pts = approx.astype(np.float32)
    seg = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1]
    if total <= 0:
        return []
    out = []
    for i in range(n):
        d = total * i / n
        idx = int(np.searchsorted(cum, d) - 1)
        idx = max(0, min(idx, len(pts) - 1))
        nxt = (idx + 1) % len(pts)
        seg_len = seg[idx] if seg[idx] > 1e-6 else 1.0
        r = (d - cum[idx]) / seg_len
        x = pts[idx, 0] + (pts[nxt, 0] - pts[idx, 0]) * r
        y = pts[idx, 1] + (pts[nxt, 1] - pts[idx, 1]) * r
        out.append((float(x), float(y)))
    return out
