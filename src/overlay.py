"""오버레이 렌더링 — 산출 기하를 프레임 위에 그린다 (OpenCV 드로잉).

스마트글래스로 옮길 때: 글래스는 보통 '실제 시야 위에 가상 그래픽'을 더하는
addition 디스플레이라 검은 배경이 투명이 된다. 그래서 그래픽 좌표(geom)만
글래스 렌더러로 넘기면 되고, 이 파일의 draw_* 함수들이 만드는 선/점 좌표가
그대로 재사용된다. (좌표 산출과 렌더 백엔드를 분리해 둔 이유)
"""
from __future__ import annotations

import cv2
import numpy as np

COLORS = {
    "roi":        (80, 80, 80),
    "mask":       (0, 200, 255),
    "centerline": (0, 255, 0),
    "minor":      (0, 180, 0),
    "grid":       (255, 180, 0),
    "french":     (255, 0, 255),
    "attach":     (0, 0, 255),
    "landmark":   (200, 200, 200),
    "ghost":      (120, 120, 120),
    "text":       (255, 255, 255),
}


def draw_landmarks(frame, rois, cfg):
    if not cfg.show_landmarks:
        return
    for roi in rois:
        cv2.circle(frame, _i(roi.tip_xy), 3, COLORS["landmark"], -1)
        cv2.circle(frame, _i(roi.dip_xy), 2, COLORS["landmark"], -1)


def draw_roi(frame, roi):
    box = roi.to_box_points().astype(np.int32)
    cv2.polylines(frame, [box], True, COLORS["roi"], 1, cv2.LINE_AA)


def draw_mask(frame, mask, alpha=0.35):
    color = np.zeros_like(frame)
    color[mask > 0] = COLORS["mask"]
    cv2.addWeighted(color, alpha, frame, 1.0, 0, frame)


def draw_geometry(frame, geom, smoothed_center, cfg):
    cx, cy = smoothed_center
    # 중심선(주축)
    if cfg.show_centerline:
        half = geom.length / 2.0
        ax, ay = geom.axis_major
        p1 = (cx - ax * half, cy - ay * half)
        p2 = (cx + ax * half, cy + ay * half)
        cv2.line(frame, _i(p1), _i(p2), COLORS["centerline"], 2, cv2.LINE_AA)
        # 가로 보조축
        bx, by = geom.axis_minor
        hw = geom.width / 2.0
        cv2.line(frame, _i((cx - bx * hw, cy - by * hw)),
                 _i((cx + bx * hw, cy + by * hw)), COLORS["minor"], 1, cv2.LINE_AA)
        cv2.circle(frame, _i((cx, cy)), 3, COLORS["centerline"], -1)
    # 격자
    if cfg.show_grid:
        for p1, p2 in geom.grid_lines:
            cv2.line(frame, _i(p1), _i(p2), COLORS["grid"], 1, cv2.LINE_AA)
    # 프렌치 라인
    if cfg.show_french and len(geom.french_curve) >= 2:
        pts = np.array([_i(p) for p in geom.french_curve], np.int32)
        cv2.polylines(frame, [pts], False, COLORS["french"], 2, cv2.LINE_AA)
    # 부착점
    if cfg.show_attach:
        for p in geom.attach_points:
            cv2.circle(frame, _i(p), 2, COLORS["attach"], -1)


def draw_ghost(frame, xy):
    cv2.circle(frame, _i(xy), 4, COLORS["ghost"], 1, cv2.LINE_AA)


def draw_hud(frame, fps, n_nails, source_label, seg_method):
    h = frame.shape[0]
    lines = [
        f"FPS: {fps:5.1f}   nails: {n_nails}",
        f"src: {source_label}   seg: {seg_method}",
        "[q]uit [m]ask [g]rid [f]rench [l]andmark [d]esign",
    ]
    y = 22
    for t in lines:
        cv2.putText(frame, t, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, t, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    COLORS["text"], 1, cv2.LINE_AA)
        y += 24


def draw_bench(frame, lines):
    """검증 계측 패널(우상단)."""
    w = frame.shape[1]
    y = 22
    for t in lines:
        cv2.putText(frame, t, (w - 360, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, t, (w - 360, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (120, 255, 120), 1, cv2.LINE_AA)
        y += 24


def _i(p):
    return (int(round(p[0])), int(round(p[1])))
