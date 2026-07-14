"""card_scale 단위테스트 — 합성 이미지 라운드트립(하드웨어·네트워크 불요).

정면 카드 스케일 정확도, 손톱 mm 환산, 실물크기 줌, 기울인 카드 검출, solvePnP 거리 복원.
실행: python tests/test_card_scale.py   (또는 pytest)
"""
import os
import sys

import numpy as np
import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.card_scale import (            # noqa: E402
    detect_card, nail_mm, lifesize_zoom, card_pose,
    CARD_LONG_MM, CARD_SHORT_MM, CARD_ASPECT,
)


def _draw_card(w=640, h=480, long_px=240.0, top_left=(120, 150)):
    """검은 배경에 흰 카드 사각형(정면). 반환 (img, long_px, short_px)."""
    short_px = long_px / CARD_ASPECT
    img = np.zeros((h, w, 3), np.uint8)
    x0, y0 = top_left
    x1, y1 = int(round(x0 + long_px)), int(round(y0 + short_px))
    cv2.rectangle(img, (x0, y0), (x1, y1), (255, 255, 255), -1)
    cv2.rectangle(img, (x0, y0), (x1, y1), (180, 180, 180), 2)   # 에지 뚜렷하게
    return img, float(long_px), float(short_px)


def test_detect_frontal_scale():
    img, L, Sh = _draw_card(long_px=240.0)
    card = detect_card(img)
    assert card is not None, "정면 카드 미검출"
    assert abs(card["long_px"] - L) / L < 0.06, card["long_px"]
    assert abs(card["aspect"] - CARD_ASPECT) < 0.1, card["aspect"]
    exp = 0.5 * (CARD_LONG_MM / L + CARD_SHORT_MM / Sh)
    assert abs(card["mm_per_px"] - exp) / exp < 0.06, (card["mm_per_px"], exp)


def test_nail_mm_realistic():
    img, L, Sh = _draw_card(long_px=240.0)
    card = detect_card(img)
    lm, wm = nail_mm(34.0, 22.0, card["mm_per_px"])   # 240px 카드 → 손톱 34px ≈ 12mm
    assert 8.0 < lm < 18.0, lm
    assert 5.0 < wm < 16.0, wm


def test_lifesize_zoom():
    assert abs(lifesize_zoom(0.4, 2.0) - 0.8) < 1e-9


def test_detect_tilted():
    img, L, Sh = _draw_card(long_px=260.0, top_left=(80, 120))
    h, w = img.shape[:2]
    s = 260.0 / CARD_ASPECT
    src = np.float32([[80, 120], [340, 120], [340, 120 + s], [80, 120 + s]])
    dst = src + np.float32([[25, 10], [-25, 10], [0, 0], [0, 0]])   # 상단을 안쪽으로 → 원근 기울임
    warped = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h))
    card = detect_card(warped)
    assert card is not None, "기울인 카드 미검출"
    assert abs(card["aspect"] - CARD_ASPECT) < 0.20, card["aspect"]


def test_card_pose_distance():
    f_px, w, h, dist = 900.0, 640, 480, 0.40   # 40cm
    obj = np.array([[-CARD_LONG_MM / 2, -CARD_SHORT_MM / 2, 0],
                    [ CARD_LONG_MM / 2, -CARD_SHORT_MM / 2, 0],
                    [ CARD_LONG_MM / 2,  CARD_SHORT_MM / 2, 0],
                    [-CARD_LONG_MM / 2,  CARD_SHORT_MM / 2, 0]], np.float64) / 1000.0
    K = np.array([[f_px, 0, w / 2], [0, f_px, h / 2], [0, 0, 1]], np.float64)
    proj, _ = cv2.projectPoints(obj, np.zeros((3, 1)), np.array([[0.], [0.], [dist]]),
                                K, np.zeros((5, 1)))
    pose = card_pose({"corners": proj.reshape(4, 2).astype(np.float32)}, f_px, w, h)
    assert pose is not None and abs(pose["dist_m"] - dist) < 0.01, pose


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
