"""card_calib 단위테스트 — mm 보정계수 순수 로직.

실행: python tests/test_card_calib.py   (또는 pytest)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.card_calib import pipeline_mm_per_px, scale_correction, fold_correction  # noqa: E402


def test_pipeline_mm_per_px():
    assert abs(pipeline_mm_per_px(0.40, 900.0) - (1000 * 0.40 / 900.0)) < 1e-9
    assert pipeline_mm_per_px(0.40, 0.0) == 0.0        # f_px=0 방어


def test_scale_correction_value():
    # 카드 실측 0.5, 예측 0.4444 → k = 1.125
    k = scale_correction(0.5, 0.40, 900.0)
    assert abs(k - 0.5 / (1000 * 0.40 / 900.0)) < 1e-9


def test_scale_correction_identity():
    # 카드가 예측과 정확히 일치하면 k=1
    f_px, d = 900.0, 0.40
    pred = pipeline_mm_per_px(d, f_px)
    assert abs(scale_correction(pred, d, f_px) - 1.0) < 1e-9


def test_scale_correction_invalid():
    assert scale_correction(0.5, 0.0, 900.0) is None      # dist=0
    assert scale_correction(0.0, 0.40, 900.0) is None      # card=0


def test_fold_median_robust():
    # 이상치 5.0 이 있어도 중앙값은 안정
    assert abs(fold_correction([1.1, 1.2, 1.15, 5.0, None]) - 1.175) < 1e-6


def test_fold_empty_is_identity():
    assert fold_correction([]) == 1.0
    assert fold_correction([None, float("nan"), -1.0]) == 1.0


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
