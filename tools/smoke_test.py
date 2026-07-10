"""헤드리스 스모크 테스트 — 폰을 꽂기 전에 코어 파이프라인이 실제로 로딩·동작하는지 확인.

카메라도 GUI 창도 필요 없다. 다음을 순서대로 검증한다.
  1) 코어 의존성 import (cv2 / numpy / mediapipe)
  2) MediaPipe 손 모델 다운로드 + HandLandmarker 생성 (가장 흔한 '폰에서 안 됨' 원인)
  3) 파이프라인이 빈 프레임 1장을 크래시 없이 처리
  4) 합성 손톱 마스크로 기하 산출(PCA 중심선/격자/프렌치/부착점) + 오버레이 렌더 경로

사용:  python tools/smoke_test.py
종료코드 0 = 전부 통과. 실패 항목은 [FAIL]로 표시되고 종료코드 1.
"""
from __future__ import annotations

import os
import sys
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 깨짐 방지
except Exception:  # noqa: BLE001
    pass

# 프로젝트 루트를 import 경로에 추가 (tools/ 하위에서 실행해도 동작)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASS, FAIL = "[PASS]", "[FAIL]"
results = []


def check(name, fn):
    try:
        info = fn()
        results.append((True, name, info or ""))
        print(f"{PASS} {name} {info or ''}")
        return True
    except Exception as e:  # noqa: BLE001
        results.append((False, name, repr(e)))
        print(f"{FAIL} {name}\n       {e}")
        traceback.print_exc()
        return False


def t_imports():
    import cv2, numpy, mediapipe  # noqa: F401
    return f"(opencv {cv2.__version__}, numpy {numpy.__version__}, mediapipe {mediapipe.__version__})"


def t_model_and_landmarker():
    """MediaPipe 모델 다운로드 + HandLandmarker 생성."""
    from config import HandConfig
    from src.hand_landmarks import HandLandmarkDetector
    det = HandLandmarkDetector(HandConfig())
    det._lazy_init()  # 모델 다운로드 + create_from_options
    ok = det._landmarker is not None
    det.close()
    if not ok:
        raise RuntimeError("HandLandmarker 생성 실패")
    return "(model loaded)"


def t_pipeline_blank_frame():
    """파이프라인이 빈 프레임을 크래시 없이 처리(손이 없으면 rois=[]가 정상)."""
    import numpy as np
    from config import AppConfig
    from src.pipeline import NailARPipeline
    pipe = NailARPipeline(AppConfig())
    frame = np.full((480, 640, 3), 30, np.uint8)
    out = pipe.process(frame, timestamp_ms=0, source_label="smoke", fps=0.0)
    pipe.close()
    if out is None or out.shape != (480, 640, 3):
        raise RuntimeError(f"출력 형상 이상: {None if out is None else out.shape}")
    return "(480x640 처리 OK)"


def t_geometry_synthetic_nail():
    """합성 손톱 마스크 → PCA 중심선/격자/프렌치/부착점 산출 + 오버레이."""
    import numpy as np
    import cv2
    from config import GeomConfig
    from src.geometry import compute_geometry
    from src import overlay
    from src.hand_landmarks import NailROI

    # 640x480 위에 기울어진 타원형 손톱 마스크
    mask = np.zeros((480, 640), np.uint8)
    center = (320, 240)
    cv2.ellipse(mask, center, (60, 95), 25, 0, 360, 255, -1)

    # ROI: 손톱 세로축이 대략 25도 방향이라고 가정
    ang = np.deg2rad(25 - 90)  # 타원 장축 방향
    axis = (float(np.cos(ang)), float(np.sin(ang)))
    roi = NailROI(finger="index", handedness="Right", center=center,
                  axis=axis, size=220.0, tip_xy=(360, 150), dip_xy=(300, 320))

    geom = compute_geometry(mask, roi, GeomConfig())
    if geom is None:
        raise RuntimeError("compute_geometry가 None 반환")
    n_grid, n_fr, n_at = len(geom.grid_lines), len(geom.french_curve), len(geom.attach_points)
    if n_grid == 0 or n_at == 0:
        raise RuntimeError(f"안내정보 비어있음 (grid={n_grid}, french={n_fr}, attach={n_at})")

    # 오버레이 렌더 경로(크래시 없이 그려지는지)
    frame = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    overlay.draw_mask(frame, mask)

    class _Cfg:  # draw_geometry가 참조하는 토글만
        show_centerline = show_grid = show_french = show_attach = True
    overlay.draw_geometry(frame, geom, geom.center, _Cfg())

    # 결과 저장(눈으로 확인용)
    out_path = os.path.join(ROOT, "samples", "smoke_overlay.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, frame)
    return (f"(angle={geom.angle_deg:.1f}deg len={geom.length:.0f} "
            f"grid={n_grid} french={n_fr} attach={n_at} -> {out_path})")


if __name__ == "__main__":
    print("=== nail_ar_mvp 스모크 테스트 (헤드리스) ===")
    t_imports_ok = check("1. core imports", t_imports)
    check("2. MediaPipe 손 모델 + HandLandmarker", t_model_and_landmarker)
    check("3. 파이프라인 빈 프레임 처리", t_pipeline_blank_frame)
    check("4. 합성 손톱 기하 + 오버레이", t_geometry_synthetic_nail)

    n_ok = sum(1 for ok, _, _ in results if ok)
    n = len(results)
    print(f"\n결과: {n_ok}/{n} 통과")
    sys.exit(0 if n_ok == n else 1)
