#!/usr/bin/env python3
"""pen_occlusion 합성 회귀 테스트 — 실기기·YOLO 없이 알고리즘 불변식 검증.

두 가지 핵심 성질을 합성 이미지로 확인:
  A) 깨끗한 손톱(균일 색) → 가림 거의 0 (오탐 없음).
  B) 어두운 펜 줄무늬가 손톱을 가로지름 → 줄무늬 위는 가림>0, 줄무늬 밖 손톱은 ≈0.
실행: python tools/pen_probe/test_pen_occlusion.py   (pytest 불필요, 종료코드로 성패)
"""
import os, sys
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "web"))
import pen_occlusion as PO  # noqa: E402

NAIL = [[60, 40], [140, 40], [140, 160], [60, 160]]  # 사각 손톱 폴리곤
NAIL_BGR = (170, 190, 210)   # 밝은 살구/핑크 계열 손톱색


def _base():
    im = np.full((200, 200, 3), (120, 120, 120), np.uint8)   # 회색 배경
    cv2.fillPoly(im, [np.array(NAIL, np.int32).reshape(-1, 1, 2)], NAIL_BGR)
    return im


def _nail_mask():
    m = np.zeros((200, 200), np.uint8)
    cv2.fillPoly(m, [np.array(NAIL, np.int32).reshape(-1, 1, 2)], 255)
    return m > 0


def test_clean_no_occlusion():
    im = _base()
    # 약간의 카메라 노이즈(가림 아님)
    im = cv2.add(im, (np.random.RandomState(0).randn(200, 200, 3) * 3).astype(np.int16).clip(-255, 255).astype(np.uint8) if False else np.zeros_like(im))
    soft = PO.pen_soft_mask(im, [NAIL])
    inside = soft[_nail_mask()]
    assert inside.max() < 0.15, f"깨끗한 손톱에 오탐 가림 발생: max={inside.max():.3f}"
    print(f"  A) 깨끗한 손톱: 가림 max={inside.max():.3f} (<0.15) OK")


def test_pen_stripe_occludes():
    im = _base()
    # 어두운 펜 줄무늬(세로 30px, 손톱을 위-아래로 관통 → 경계 횡단 + 길쭉)
    cv2.rectangle(im, (95, 0), (125, 200), (30, 30, 30), -1)
    soft = PO.pen_soft_mask(im, [NAIL])
    nail = _nail_mask()
    stripe = np.zeros((200, 200), bool); stripe[:, 95:125] = True
    on_pen = soft[nail & stripe]
    off_pen = soft[nail & ~stripe]
    assert on_pen.mean() > 0.3, f"펜 줄무늬 위 가림 약함: mean={on_pen.mean():.3f}"
    assert off_pen.mean() < 0.1, f"펜 밖 손톱에 번짐: mean={off_pen.mean():.3f}"
    print(f"  B) 펜 줄무늬: 위 가림 mean={on_pen.mean():.3f}(>0.3), 밖 mean={off_pen.mean():.3f}(<0.1) OK")


def test_highlight_not_occluder():
    im = _base()
    # 손톱보다 밝은 스펙큘러 반점(하이라이트) → occluder 아님
    cv2.circle(im, (100, 100), 12, (245, 245, 245), -1)
    soft = PO.pen_soft_mask(im, [NAIL])
    assert soft[_nail_mask()].max() < 0.2, f"하이라이트를 가림으로 오탐: max={soft[_nail_mask()].max():.3f}"
    print(f"  C) 하이라이트 반점: 가림 max={soft[_nail_mask()].max():.3f} (<0.2) OK")


if __name__ == "__main__":
    print("pen_occlusion 합성 회귀 테스트")
    fails = 0
    for t in (test_clean_no_occlusion, test_pen_stripe_occludes, test_highlight_not_occluder):
        try:
            t()
        except AssertionError as e:
            fails += 1; print(f"  FAIL {t.__name__}: {e}")
    print("=== 통과 ===" if not fails else f"=== {fails}건 실패 ===")
    sys.exit(1 if fails else 0)
