"""신용카드(ISO/IEC 7810 ID-1) 기준물로 이미지의 실치수 스케일(mm/px)을 구하는 순수 CV 코어.

목적: 카메라 프레임에 함께 잡힌 신용/체크/신분증 카드(**85.60 x 53.98 mm 규격 고정**)를 검출해
그 화면상 픽셀 크기로부터 mm/px 스케일을 역산한다. 카드가 손톱과 **같은 깊이 평면**에 있으면
손톱의 실치수(mm)를 초점거리/거리 가정 없이 바로 얻는다 (magic-mirror 실물크기 프리뷰용).

핵심 아이디어: 카드는 크기가 규격으로 확정 → 화면상 카드 픽셀폭을 재면 mm/px가 나온다.
  mm_per_px = 카드_실치수_mm / 카드_픽셀치수
카드가 기울면 원근으로 변의 픽셀길이가 달라지므로, 검출된 4모서리에서 마주보는 변의 평균
길이를 쓰고, 장변(85.6mm)/단변(53.98mm) 두 축의 mm/px를 각각 구해 평균한다.
(정밀 버전 = solvePnP로 카드 자세+거리까지 → card_pose. 카드 없이 손 거리로 크기 조절하는
깊이적응 캘리브에 씀.)

순수 CV·하드웨어 비의존 → 단위테스트 가능 (tests/test_card_scale.py).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import cv2

# ISO/IEC 7810 ID-1 (신용/체크/신분증 공통 규격) — 전 세계 고정
CARD_LONG_MM = 85.60
CARD_SHORT_MM = 53.98
CARD_ASPECT = CARD_LONG_MM / CARD_SHORT_MM   # ≈ 1.586


@dataclass
class CardConfig:
    aspect_tol: float = 0.20        # 종횡비 허용오차(원근·검출 오차 감안). |aspect-1.586| < tol
    min_area_frac: float = 0.01     # 프레임 대비 최소 카드 면적(너무 작으면 무시)
    max_area_frac: float = 0.90     # 최대(프레임 꽉 채운 오검출 방지)
    approx_eps_frac: float = 0.02   # approxPolyDP 근사 강도(둘레 대비)
    canny_lo: int = 50
    canny_hi: int = 150


def _order_corners(pts) -> np.ndarray:
    """4점을 TL,TR,BR,BL 순서로 정렬. (x+y 합·y-x 차로 코너 판별; 대략 수직인 카드 가정)."""
    pts = np.asarray(pts, np.float32).reshape(4, 2)
    s = pts.sum(axis=1)                    # x+y
    d = np.diff(pts, axis=1).ravel()       # y-x
    return np.array([pts[np.argmin(s)],    # TL: x+y 최소
                     pts[np.argmin(d)],    # TR: y-x 최소
                     pts[np.argmax(s)],    # BR: x+y 최대
                     pts[np.argmax(d)]],   # BL: y-x 최대
                    np.float32)


def _side_lengths(c: np.ndarray):
    """정렬된 4모서리(TL,TR,BR,BL) → (장변평균_px, 단변평균_px)."""
    tl, tr, br, bl = c
    horiz = 0.5 * (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl))   # 위·아래 변
    vert = 0.5 * (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr))    # 좌·우 변
    return float(max(horiz, vert)), float(min(horiz, vert))


def detect_card(img_bgr, cfg: CardConfig = CardConfig()):
    """이미지에서 ISO 카드 후보(가장 큰 유효 사각형)를 찾아 스케일 정보를 반환. 없으면 None.

    반환: {
      "corners":   (4,2) float, TL,TR,BR,BL,
      "long_px":   장변 픽셀길이,  "short_px": 단변 픽셀길이,  "aspect": long/short,
      "mm_per_px": 장·단변 두 축 mm/px의 평균,
      "area_frac": 프레임 대비 카드 면적 비,
    }
    """
    h, w = img_bgr.shape[:2]
    frame_area = float(h * w)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, cfg.canny_lo, cfg.canny_hi)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    best_area = -1.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < cfg.min_area_frac * frame_area or area > cfg.max_area_frac * frame_area:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, cfg.approx_eps_frac * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        corners = _order_corners(approx.reshape(4, 2))
        long_px, short_px = _side_lengths(corners)
        if short_px < 1e-3:
            continue
        aspect = long_px / short_px
        if abs(aspect - CARD_ASPECT) > cfg.aspect_tol:
            continue
        if area > best_area:
            best_area = area
            mm_per_px = 0.5 * (CARD_LONG_MM / long_px + CARD_SHORT_MM / short_px)
            best = {
                "corners": corners,
                "long_px": long_px, "short_px": short_px, "aspect": aspect,
                "mm_per_px": float(mm_per_px), "area_frac": float(area / frame_area),
            }
    return best


def nail_mm(len_px, wid_px, mm_per_px):
    """손톱 픽셀 치수 → mm (카드와 동일 깊이 평면 가정). 반환 (len_mm, wid_mm)."""
    return float(len_px) * float(mm_per_px), float(wid_px) * float(mm_per_px)


def lifesize_zoom(mm_per_px, panel_px_per_mm):
    """실물크기 프리뷰 배율. 카메라 이미지 mm/px 와 패널 px/mm 로 1:1 실물크기 줌 계수.

    panel_px_per_mm = 패널(가상화면)에서 1mm가 몇 px 인가(디스플레이 기하로 결정).
    zoom>1 이면 확대해야 실물크기. (프리뷰 크롭·스케일에 사용.)
    """
    return float(mm_per_px) * float(panel_px_per_mm)


def card_pose(card, f_px, img_w, img_h):
    """카드 4모서리 + 초점거리(px) → solvePnP(IPPE)로 카드까지 거리(m)·자세. 없으면 None.

    카드 없이 손 거리(distM)로 크기를 조절하는 **깊이적응 캘리브**용(초점거리 검증/보정).
    반환: {"dist_m": float, "rvec":(3,1), "tvec":(3,1)}.
    """
    if card is None:
        return None
    obj = np.array([[-CARD_LONG_MM / 2, -CARD_SHORT_MM / 2, 0.0],
                    [ CARD_LONG_MM / 2, -CARD_SHORT_MM / 2, 0.0],
                    [ CARD_LONG_MM / 2,  CARD_SHORT_MM / 2, 0.0],
                    [-CARD_LONG_MM / 2,  CARD_SHORT_MM / 2, 0.0]], np.float64) / 1000.0
    K = np.array([[f_px, 0.0, img_w * 0.5],
                  [0.0, f_px, img_h * 0.5],
                  [0.0, 0.0, 1.0]], np.float64)
    ok, rvec, tvec = cv2.solvePnP(obj, card["corners"].astype(np.float64), K,
                                  np.zeros((5, 1)), flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        return None
    return {"dist_m": float(np.linalg.norm(tvec)), "rvec": rvec, "tvec": tvec}
