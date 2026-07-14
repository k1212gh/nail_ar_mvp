"""NailTracker 속도(렌더 게이팅) 단위테스트.

정지한 손톱 → 속도≈0(stable), 등속 이동 손톱 → 속도 큼(not stable).
실행: python tests/test_tracking_speed.py   (또는 pytest)
"""
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import TrackConfig            # noqa: E402
from src.tracking import NailTracker      # noqa: E402


def _g(cx, cy, finger="index", hand="Right"):
    return SimpleNamespace(center=(cx, cy), finger=finger, handedness=hand)


def test_still_is_low_speed():
    trk = NailTracker(TrackConfig())
    for _ in range(10):
        trk.smooth(_g(100.0, 100.0))
    assert trk.speed(_g(100.0, 100.0)) < 1.0


def test_moving_is_high_speed():
    trk = NailTracker(TrackConfig())
    for i in range(10):
        trk.smooth(_g(100.0 + i * 12.0, 100.0))   # 프레임당 +12px
    assert trk.speed(_g(220.0, 100.0)) > 5.0


def test_speed_unknown_key_zero():
    trk = NailTracker(TrackConfig())
    assert trk.speed(_g(0.0, 0.0, finger="pinky")) == 0.0


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
