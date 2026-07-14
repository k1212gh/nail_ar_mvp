"""카드 실측 스케일로 깊이-파이프라인 mm 추정을 보정하는 순수 코어 (단위테스트 가능).

edge_serve 의 mm 추정은 `mm = 1000·distM / f_px` (핀홀 + 가정 초점거리/손 크기)로 나온다.
신용카드(실측 mm/px)를 손과 **같은 평면**에 함께 잡으면, 그 프레임의
  · 카드 실측 mm/px  vs  · 파이프라인 예측 mm/px
의 비 = **보정계수 k** 를 얻는다. 여러 프레임의 중앙값 k 를 camera_calib.json 에 저장하면,
런타임(카드 없이)에도 mm 추정을 k 로 곱해 실측에 맞춘다.

비순환성: 카드는 초점거리/손크기 가정과 **독립인 ground-truth** 라, k 는 그 가정들의 결합
오차를 흡수한다(순환 아님).
"""
from __future__ import annotations

import numpy as np


def pipeline_mm_per_px(dist_m: float, f_px: float) -> float:
    """깊이-파이프라인의 mm/px = 1000·distM / f_px (edge_serve enroll 과 동일식)."""
    if f_px <= 0.0:
        return 0.0
    return 1000.0 * float(dist_m) / float(f_px)


def scale_correction(card_mm_per_px: float, dist_m: float, f_px: float):
    """한 관측의 보정계수 k = 카드 실측 mm/px ÷ 파이프라인 예측 mm/px. 무효면 None."""
    pred = pipeline_mm_per_px(dist_m, f_px)
    if pred <= 1e-9 or card_mm_per_px <= 1e-9:
        return None
    return float(card_mm_per_px) / pred


def fold_correction(ratios) -> float:
    """관측 보정계수들의 중앙값(이상치에 강인). 유효값이 없으면 1.0(무보정)."""
    r = [x for x in ratios if x is not None and np.isfinite(x) and x > 0]
    return float(np.median(r)) if r else 1.0
