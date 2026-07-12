"""eye_geometry 단위테스트 — 하드웨어 없이 수학만 검증."""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from src import eye_geometry as EG


def approx(a, b, tol=1e-6):
    assert abs(a - b) <= tol, f"{a} != {b} (tol {tol})"


def test_focal():
    cfg = EG.EyeRegConfig(webcam_hfov_deg=60.0)
    # f = (640/2)/tan(30°) = 320/0.57735 = 554.26
    approx(cfg.f_webcam_px(640), 320.0 / math.tan(math.radians(30)), 1e-4)


def test_iris_center_diameter():
    # 중심(100,100), 반경 10px 원 위 4점 → 지름 20
    pts = np.zeros((478, 2))
    pts[468] = [100, 100]
    pts[469] = [100, 90]; pts[470] = [100, 110]; pts[471] = [90, 100]; pts[472] = [110, 100]
    c, d = EG.iris_center_and_diameter(pts, EG.IRIS_R)
    approx(c[0], 100); approx(c[1], 100); approx(d, 20.0, 1e-9)


def test_eye_depth_from_iris():
    cfg = EG.EyeRegConfig(webcam_hfov_deg=60.0)
    f = cfg.f_webcam_px(640)
    # 이미지 중심의 홍채, 지름 20px → Z = f·0.0117/20
    eye = EG.eye_position_webcam(np.array([320.0, 240.0]), 20.0, 640, 480, cfg)
    approx(eye[0], 0.0, 1e-9); approx(eye[1], 0.0, 1e-9)
    approx(eye[2], f * EG.IRIS_DIAMETER_M / 20.0, 1e-9)
    # 지름 절반(10px) → 깊이 2배 (선형 역비례)
    eye2 = EG.eye_position_webcam(np.array([320.0, 240.0]), 10.0, 640, 480, cfg)
    approx(eye2[2], 2 * eye[2], 1e-9)


def test_eye_lateral_offset():
    # 홍채가 이미지 오른쪽(+u)에 있으면 눈 X(+오른쪽)도 +
    cfg = EG.EyeRegConfig(webcam_hfov_deg=60.0)
    eye = EG.eye_position_webcam(np.array([420.0, 240.0]), 20.0, 640, 480, cfg)
    assert eye[0] > 0, "오른쪽 홍채인데 X 양수 아님"


def test_baseline_measured():
    # 눈과 안경카메라 위치를 직접 주면 b = (eye-gcam) 카메라축 성분
    eye = np.array([0.00, -0.010, 0.40])       # 눈
    gcam = np.array([0.00,  0.005, 0.42])       # 안경카메라(눈보다 아래·앞)
    b = EG.baseline_eye_minus_gcam(eye, gcam, np.eye(3))
    approx(b[0], 0.0); approx(b[1], -0.015)     # eye_y - gcam_y = -0.010-0.005


def test_baseline_is_per_person():
    # 사람이 달라 눈 위치가 다르면 baseline 도 달라야(사람별 정합의 근거)
    gcam = np.array([0.0, 0.0, 0.42])
    b1 = EG.baseline_eye_minus_gcam(np.array([0.00, -0.010, 0.40]), gcam, np.eye(3))
    b2 = EG.baseline_eye_minus_gcam(np.array([0.02, -0.005, 0.40]), gcam, np.eye(3))
    assert not np.allclose(b1, b2), "눈 위치 다른데 baseline 동일 — 측정 반영 안 됨"


def test_parallax_direction_and_magnitude():
    cfg = EG.EyeRegConfig(display_px_w=1280.0, display_hfov_deg=27.0)
    b = np.array([0.0, 0.018])
    Ax, Ay, Bx, By = EG.parallax_AB(b, cfg)
    fdisp = cfg.f_display_px()
    approx(Bx, 0.0); approx(By, fdisp * 0.018, 1e-6)
    # 깊이 커질수록 오프셋 작아짐(시차 1/d) — 정합 방향성의 핵심
    o30 = EG.offset_at_depth((Ax, Ay, Bx, By), 0.30)
    o60 = EG.offset_at_depth((Ax, Ay, Bx, By), 0.60)
    assert abs(o30[1]) > abs(o60[1]) > 0, "가까울수록 오프셋 커야(시차)"
    approx(o30[1], 2 * o60[1], 1e-6)          # d 절반 → 오프셋 2배


def test_zero_baseline_zero_parallax():
    cfg = EG.EyeRegConfig(Ax_px=5, Ay_px=-3)
    ab = EG.parallax_AB(np.array([0.0, 0.0]), cfg)
    approx(ab[2], 0.0); approx(ab[3], 0.0)
    o = EG.offset_at_depth(ab, 0.3)
    approx(o[0], 5); approx(o[1], -3)


def test_full_pipeline_realistic():
    # 얼굴 ~45cm, 홍채 오른쪽 약간 위 + 코받침 중앙, 현실값이 나오나
    cfg = EG.EyeRegConfig()
    f = cfg.f_webcam_px(640)
    diam = f * EG.IRIS_DIAMETER_M / 0.45      # 45cm에 해당하는 홍채 지름 px
    out = EG.full_pipeline(np.array([340.0, 225.0]), diam, np.array([320.0, 245.0]), 0.45,
                           640, 480, np.eye(3), cfg)
    assert 0.35 < out["eye_W"][2] < 0.55, f"눈 깊이 비현실적: {out['eye_W'][2]}"
    off = EG.offset_at_depth(out["AB"], 0.30)
    assert abs(off[0]) < 2000 and abs(off[1]) < 2000, f"오프셋 폭주: {off}"
    print(f"  [현실체크] 눈={out['eye_W'].round(3)}m gcam={out['gcam_W'].round(3)}m "
          f"b={out['baseline_xy'].round(4)}m AB={tuple(round(x,1) for x in out['AB'])} "
          f"off@30cm={tuple(round(x,1) for x in off)}px")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t(); passed += 1; print(f"[PASS] {t.__name__}")
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
