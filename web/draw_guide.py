"""그리기 가이드 — 손톱 위에 '시작점→경로→끝점'을 그려 네일 아티스트의 붓질을 안내한다.

완성 디자인을 덮어씌우는 대신(OST 안경은 시차로 정밀정합 불가), 어디서 시작해 어디로 그으라는
**대략적 획 가이드**를 보여준다. 이건 안경의 근본한계(4m 시차)에 강하다 — 픽셀 정합이 아니라
'이 손톱의 이 근방에서 이 방향으로'면 충분하기 때문. [[nailar-nearfield-ost-impossible]]

손톱 기하(edge_serve._infer_yolo): cx,cy(중심) · ex,ey(장축 단위벡터) · len,wid · contour.
로컬좌표 (v: 장축 -0.5~0.5, u: 폭 -0.5~0.5) → 이미지좌표로 매핑해 프리셋 획을 그린다.

  from draw_guide import render_guides
  out = render_guides(frame_bgr, nails, preset="french")   # french|stripe|diagonal|vgrad
"""
from __future__ import annotations
import cv2
import numpy as np

START_BGR = (90, 205, 90)     # 시작점(초록)
END_BGR = (70, 70, 235)       # 끝점(빨강)
PATH_BGR = (235, 225, 70)     # 경로(청록)


def _axes(nd):
    c = np.array([nd["cx"], nd["cy"]], np.float32)
    a = np.array([nd.get("ex", 0.0), nd.get("ey", 1.0)], np.float32)
    n = np.linalg.norm(a)
    a = a / n if n > 1e-6 else np.array([0.0, 1.0], np.float32)
    p = np.array([-a[1], a[0]], np.float32)     # 폭 방향(장축에 수직)
    return c, a, p, float(nd.get("len", 40.0)), float(nd.get("wid", 30.0))


def _pt(c, a, p, L, W, v, u):
    return c + v * L * a + u * W * p


def stroke_points(nd, preset):
    """프리셋별 획 경로(로컬→이미지 점열). 첫 점=시작, 끝 점=끝."""
    c, a, p, L, W = _axes(nd)
    if preset == "stripe":                       # 중앙 세로 스트라이프(뿌리→팁)
        return [_pt(c, a, p, L, W, t, 0.0) for t in np.linspace(-0.34, 0.42, 24)]
    if preset == "french":                       # 프렌치 스마일 라인(팁쪽 곡선)
        out = []
        for t in np.linspace(-1, 1, 30):
            u = 0.43 * t
            v = 0.30 - 0.16 * (1 - t * t)        # 가운데가 뿌리쪽으로 옴폭(스마일)
            out.append(_pt(c, a, p, L, W, v, u))
        return out
    if preset == "diagonal":                     # 대각선 획
        return [_pt(c, a, p, L, W, -0.3 + 0.72 * s, -0.36 + 0.72 * s) for s in np.linspace(0, 1, 24)]
    if preset == "vgrad":                        # V자(양끝→중앙 아래) — 브이 프렌치
        left = [_pt(c, a, p, L, W, 0.34 - 0.30 * s, -0.42 + 0.42 * s) for s in np.linspace(0, 1, 14)]
        right = [_pt(c, a, p, L, W, 0.04 + 0.30 * s, 0.0 + 0.42 * s) for s in np.linspace(0, 1, 14)]
        return left + right
    return []


def _dashed(out, pts, color, thick=2, dash=2):
    for i in range(0, len(pts) - 1, dash):
        cv2.line(out, tuple(pts[i]), tuple(pts[min(i + 1, len(pts) - 1)]), color, thick, cv2.LINE_AA)


def render_guides(frame_bgr, nails, preset="french", show_labels=True):
    """손톱마다 시작점(초록)·끝점(빨강)·경로(청록 점선) 가이드를 그린다."""
    out = frame_bgr.copy()
    for nd in nails:
        if not nd.get("contour"):
            continue
        pts = stroke_points(nd, preset)
        if len(pts) < 2:
            continue
        ipts = [tuple(np.round(p).astype(int)) for p in pts]
        r = max(3, int(float(nd.get("wid", 30)) * 0.09))
        _dashed(out, ipts, PATH_BGR, thick=max(2, r // 2))
        for pt, col in ((ipts[0], START_BGR), (ipts[-1], END_BGR)):
            cv2.circle(out, pt, r, col, -1, cv2.LINE_AA)
            cv2.circle(out, pt, r, (255, 255, 255), 1, cv2.LINE_AA)
        if show_labels:
            cv2.putText(out, "S", (ipts[0][0] + r, ipts[0][1] - r), cv2.FONT_HERSHEY_SIMPLEX, 0.4, START_BGR, 1, cv2.LINE_AA)
            cv2.putText(out, "E", (ipts[-1][0] + r, ipts[-1][1] - r), cv2.FONT_HERSHEY_SIMPLEX, 0.4, END_BGR, 1, cv2.LINE_AA)
    return out
