"""monitor_calib 단위테스트 — 하드웨어 없이 순수 수학만 검증.

test_eye_geometry.py 스타일: __main__ 에서 test_* 전부 실행, PASS/FAIL 출력, 실패시 비정상종료.
핵심은 solve_eye_in_camera 의 '합성 라운드트립': 알려진 눈 E_true + 알려진 P_true 로
대응을 생성 → 솔버가 E_true 를 mm 이내로 복원하는지 확인.
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from src import monitor_calib as MC
from src import eye_geometry as EG


def approx(a, b, tol=1e-6):
    assert abs(a - b) <= tol, f"{a} != {b} (tol {tol})"


def _make_P_true(E_true, cfg):
    """카메라중심이 E_true 인 알려진 3×4 투영 P_true (디스플레이 핀홀, 정사각픽셀).

    P = K[R|t], 카메라중심 C = -Rᵀt. R=I → t=-E_true → C=E_true.
    K: fx=fy=f_display_px, 주점=(display_px_w/2, display_px_h/2).
    """
    f = cfg.f_display_px()
    K = np.array([[f, 0, cfg.display_px_w / 2],
                  [0, f, cfg.display_px_h() / 2],
                  [0, 0, 1.0]], float)
    R = np.eye(3)
    t = -R @ np.asarray(E_true, float)
    P = K @ np.c_[R, t]
    return P, K


def _corr_from_P(P, cfg, depths, grid, noise_px=0.0, seed=0):
    """P_true 로 여러 거리의 3D 격자점을 디스플레이 norm 으로 투영 → 대응리스트."""
    rng = np.random.default_rng(seed)
    scale = np.array([cfg.display_px_w, cfg.display_px_h()], float)
    corr = []
    for z in depths:
        for (x, y) in grid:
            X = np.array([x, y, z], float)
            uvw = P @ np.append(X, 1.0)
            uv = uvw[:2] / uvw[2]
            if noise_px:
                uv = uv + rng.normal(0, noise_px, 2)
            corr.append((uv / scale, X))
    return corr


# --- 설정/초점 --------------------------------------------------------------
def test_f_glasses_cam_px():
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.5, monitor_h_m=0.3, glasses_cam_hfov_deg=66.0)
    approx(cfg.f_glasses_cam_px(1280), 640.0 / math.tan(math.radians(33.0)), 1e-4)


def test_f_display_px_matches_eye_geometry():
    # eye_geometry 와 동일한 f_disp 정의여야 (모델 일관성).
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.5, monitor_h_m=0.3,
                                display_px_w=1280.0, display_hfov_deg=27.0)
    eg = EG.EyeRegConfig(display_px_w=1280.0, display_hfov_deg=27.0)
    approx(cfg.f_display_px(), eg.f_display_px(), 1e-9)


def test_display_px_h_assumption():
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.5, monitor_h_m=0.3, display_px_w=1280.0)
    approx(cfg.display_px_h(), 1280.0 * 0.75, 1e-9)   # 4:3 가정 = 960


# --- PnP: 모니터 4모서리 → 3D --------------------------------------------
def test_camera_pose_from_corners_depth():
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.50, monitor_h_m=0.30,
                                glasses_cam_hfov_deg=66.0)
    img_w, img_h = 1280, 720
    f = cfg.f_glasses_cam_px(img_w)
    Z0 = 0.70                                          # 모니터를 0.70m 정면에
    W, H = cfg.monitor_w_m, cfg.monitor_h_m
    obj = np.array([[-W/2, -H/2, 0], [W/2, -H/2, 0], [W/2, H/2, 0], [-W/2, H/2, 0]], float)
    corners_px = []
    for (x, y, z) in obj:                              # R=I, t=(0,0,Z0)
        Xc = np.array([x, y, z + Z0])
        u = f * Xc[0] / Xc[2] + img_w / 2
        v = f * Xc[1] / Xc[2] + img_h / 2
        corners_px.append([u, v])
    corners_px = np.array(corners_px, float)

    res = MC.camera_pose_from_corners(corners_px, img_w, img_h, cfg)
    depths = res["corners_cam"][:, 2]
    for d in depths:
        assert abs(d - Z0) / Z0 < 0.01, f"복원 깊이 {d} vs {Z0} (>1%)"
    approx(res["t"][2], Z0, 0.01 * Z0)
    # 복원된 모서리 간 물리 폭/높이가 실제와 일치하는지(스케일 정합)
    cc = res["corners_cam"]
    approx(np.linalg.norm(cc[1] - cc[0]), W, 1e-3)     # TL-TR = 가로
    approx(np.linalg.norm(cc[2] - cc[1]), H, 1e-3)     # TR-BR = 세로


def test_camera_pose_tilted():
    # 기울어진(회전+병진) 모니터도 모서리 3D 를 정확히 복원하는지.
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.52, monitor_h_m=0.29, glasses_cam_hfov_deg=70.0)
    img_w, img_h = 1280, 720
    f = cfg.f_glasses_cam_px(img_w)
    K = np.array([[f, 0, img_w/2], [0, f, img_h/2], [0, 0, 1.0]], float)
    W, H = cfg.monitor_w_m, cfg.monitor_h_m
    obj = np.array([[-W/2, -H/2, 0], [W/2, -H/2, 0], [W/2, H/2, 0], [-W/2, H/2, 0]], float)
    import cv2
    rvec_true = np.array([0.15, -0.25, 0.05])
    R_true, _ = cv2.Rodrigues(rvec_true)
    t_true = np.array([0.05, -0.02, 0.65])
    cam = (R_true @ obj.T).T + t_true
    corners_px = (K @ cam.T).T
    corners_px = corners_px[:, :2] / corners_px[:, 2:3]

    res = MC.camera_pose_from_corners(corners_px, img_w, img_h, cfg)
    err = np.linalg.norm(res["corners_cam"] - cam, axis=1)
    assert err.max() < 1e-3, f"기울어진 모서리 3D 복원오차 {err.max()*1000:.3f}mm"


# --- 핵심: 합성 라운드트립 (눈위치 복원) --------------------------------
def test_solve_eye_roundtrip_exact():
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.50, monitor_h_m=0.30,
                                display_px_w=1280.0, display_hfov_deg=27.0)
    E_true = np.array([0.03, -0.01, 0.0])              # 카메라보다 3cm 오른쪽, 1cm 위
    P_true, _ = _make_P_true(E_true, cfg)
    depths = [0.4, 0.6, 0.8]                            # 3개 시뮬 모니터 거리
    grid = [(-0.12, -0.08), (0.12, -0.08), (0.12, 0.08), (-0.12, 0.08)]  # 모서리 4점
    corr = _corr_from_P(P_true, cfg, depths, grid)     # 12 대응
    assert len(corr) >= 8

    out = MC.solve_eye_in_camera(corr, cfg)
    err_mm = np.linalg.norm(out["eye_cam"] - E_true) * 1000.0
    assert not out["planar_warn"], "여러 거리인데 평면경고가 뜸"
    assert err_mm < 1.0, f"눈 복원오차 {err_mm:.4f}mm (>1mm)"
    assert out["residual_px"] < 1e-3, f"재투영 RMS {out['residual_px']:.2e}px 너무 큼"
    assert out["n"] == 12
    print(f"  [roundtrip-exact] n={out['n']} eye_err={err_mm:.6f}mm "
          f"residual={out['residual_px']:.3e}px eye={out['eye_cam'].round(5)}")


def test_solve_eye_roundtrip_noise():
    # 정렬노이즈 0.5px 하에서도 mm 급 복원 + 작은 잔차.
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.50, monitor_h_m=0.30,
                                display_px_w=1280.0, display_hfov_deg=27.0)
    E_true = np.array([0.031, -0.008, 0.004])
    P_true, _ = _make_P_true(E_true, cfg)
    depths = [0.35, 0.55, 0.75]
    # 거리마다 6점 격자 → 18 대응 (잘 조건화)
    grid = [(gx, gy) for gx in (-0.13, 0.0, 0.13) for gy in (-0.09, 0.09)]
    corr = _corr_from_P(P_true, cfg, depths, grid, noise_px=0.5, seed=7)

    out = MC.solve_eye_in_camera(corr, cfg)
    err_mm = np.linalg.norm(out["eye_cam"] - E_true) * 1000.0
    assert not out["planar_warn"]
    assert err_mm < 5.0, f"노이즈하 눈 복원오차 {err_mm:.3f}mm (>5mm)"
    assert out["residual_px"] < 3.0, f"노이즈하 재투영 RMS {out['residual_px']:.3f}px"
    print(f"  [roundtrip-noise] n={out['n']} noise=0.5px eye_err={err_mm:.3f}mm "
          f"residual={out['residual_px']:.3f}px")


def test_solve_eye_requires_six():
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.5, monitor_h_m=0.3)
    P_true, _ = _make_P_true(np.array([0.02, 0.0, 0.0]), cfg)
    corr = _corr_from_P(P_true, cfg, [0.5], [(-0.1, 0.0), (0.1, 0.0), (0.0, 0.1)])  # 3개
    try:
        MC.solve_eye_in_camera(corr, cfg)
        assert False, "대응 3개인데 예외 안 남"
    except ValueError:
        pass


def test_solve_eye_planar_warn():
    # 단일 거리(모든 3D 점 한 평면) → planar_warn True (P 는 반환).
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.5, monitor_h_m=0.3)
    E_true = np.array([0.03, -0.01, 0.0])
    P_true, _ = _make_P_true(E_true, cfg)
    grid = [(gx, gy) for gx in (-0.12, 0.0, 0.12) for gy in (-0.08, 0.0, 0.08)]  # 9점, z고정
    corr = _corr_from_P(P_true, cfg, [0.5], grid)
    out = MC.solve_eye_in_camera(corr, cfg)
    assert out["planar_warn"], "단일 평면인데 planar_warn 이 False"
    assert out["P"].shape == (3, 4)
    assert out["n"] == 9
    print(f"  [planar] planar_warn={out['planar_warn']} residual={out['residual_px']:.3e}px (낙관적일 수 있음)")


# --- eye_to_AB -------------------------------------------------------------
def test_eye_to_AB_sign_and_magnitude():
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.5, monitor_h_m=0.3,
                                display_px_w=1280.0, display_hfov_deg=27.0)
    eye = np.array([0.03, -0.01, 0.0])                 # 3cm 오른쪽, 1cm 위
    Ax, Ay, Bx, By = MC.eye_to_AB(eye, cfg)
    fd = cfg.f_display_px()
    approx(Ax, 0.0); approx(Ay, 0.0)
    approx(Bx, fd * 0.03, 1e-9)
    approx(By, fd * (-0.01), 1e-9)
    assert Bx > 0 and By < 0, "부호가 눈 위치 방향과 불일치"
    # 0.3m 깊이 오프셋 = Bx/0.3 (손 계산과 일치, 유한).
    off_x = Bx / 0.3
    approx(off_x, fd * 0.03 / 0.3, 1e-9)
    assert math.isfinite(off_x)
    print(f"  [eye_to_AB] fdisp={fd:.2f}px Bx={Bx:.3f} By={By:.3f} off_x@0.3m={off_x:.3f}px")


def test_eye_to_AB_consistent_with_parallax_AB():
    # eye_to_AB 는 eye_geometry.parallax_AB(sign=+1, A=0) 와 수치 일치해야.
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.5, monitor_h_m=0.3,
                                display_px_w=1280.0, display_hfov_deg=27.0)
    eg = EG.EyeRegConfig(display_px_w=1280.0, display_hfov_deg=27.0)
    eye = np.array([0.028, -0.012, 0.003])
    _, _, Bx, By = MC.eye_to_AB(eye, cfg)
    _, _, Bx2, By2 = EG.parallax_AB(eye[:2], eg)
    approx(Bx, Bx2, 1e-9); approx(By, By2, 1e-9)


# --- 파이프라인 통합: PnP → 눈복원 (모니터 물리 좌표 경유) --------------
def test_pipeline_pnp_then_eye():
    """PnP 로 얻은 3D 모서리를 SPAAM 에 넣어 눈을 복원하는 엔드투엔드 정합.

    카메라 프레임에서 여러 거리의 모니터를 세우고(모서리 3D 알려짐), 눈 E_true 핀홀로
    각 모서리를 디스플레이에 투영해 norm 을 만든 뒤, PnP 로 복원한 모서리 3D 와 짝지어
    solve_eye_in_camera 가 E_true 를 되찾는지 확인.
    """
    cfg = MC.MonitorCalibConfig(monitor_w_m=0.50, monitor_h_m=0.30,
                                glasses_cam_hfov_deg=66.0,
                                display_px_w=1280.0, display_hfov_deg=27.0)
    img_w, img_h = 1280, 720
    f = cfg.f_glasses_cam_px(img_w)
    K = np.array([[f, 0, img_w/2], [0, f, img_h/2], [0, 0, 1.0]], float)
    W, H = cfg.monitor_w_m, cfg.monitor_h_m
    obj = np.array([[-W/2, -H/2, 0], [W/2, -H/2, 0], [W/2, H/2, 0], [-W/2, H/2, 0]], float)

    E_true = np.array([0.032, -0.009, 0.0])
    P_true, _ = _make_P_true(E_true, cfg)
    scale = np.array([cfg.display_px_w, cfg.display_px_h()], float)

    corr = []
    for Z0 in (0.45, 0.65, 0.85):                       # 모니터를 3거리에
        cam = obj + np.array([0.0, 0.0, Z0])            # R=I, 정면
        cpx = (K @ cam.T).T
        cpx = cpx[:, :2] / cpx[:, 2:3]                  # 안경 카메라 픽셀
        res = MC.camera_pose_from_corners(cpx, img_w, img_h, cfg)
        cc = res["corners_cam"]                         # PnP 복원 3D
        for i in range(4):                              # 눈 핀홀로 디스플레이 norm
            uvw = P_true @ np.append(cam[i], 1.0)       # 참 3D 로 norm 생성
            uv = uvw[:2] / uvw[2]
            corr.append((uv / scale, cc[i]))            # (norm, PnP복원3D) 짝

    out = MC.solve_eye_in_camera(corr, cfg)
    err_mm = np.linalg.norm(out["eye_cam"] - E_true) * 1000.0
    assert not out["planar_warn"]
    assert err_mm < 2.0, f"엔드투엔드 눈 복원오차 {err_mm:.3f}mm"
    ab = MC.eye_to_AB(out["eye_cam"], cfg)
    print(f"  [pipeline] n={out['n']} eye_err={err_mm:.4f}mm residual={out['residual_px']:.3e}px "
          f"AB=({ab[0]:.1f},{ab[1]:.1f},{ab[2]:.1f},{ab[3]:.1f})")


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
