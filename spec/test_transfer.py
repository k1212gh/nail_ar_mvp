"""A3-4 전사 검증 — 손톱1 디자인을 형상 다른 손톱2에 이식 + 좌우 미러 (청구항 30~33)."""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import DesignConfig, GeomConfig                 # noqa: E402
from src.geometry import compute_geometry                   # noqa: E402
from src.design_render import DesignEngine                  # noqa: E402
from src.transfer import capture_nail_atlas, transfer_design  # noqa: E402


def synth_nail(W, H, cx, cy, al, aw, ang=0):
    mask = np.zeros((H, W), np.uint8)
    cv2.ellipse(mask, (cx, cy), (aw, al), ang, 0, 360, 255, -1)
    return mask, compute_geometry(mask, None, GeomConfig())


def content_centroid_u(atlas):
    """아틀라스 '특징'(고주파=꽃/라인) 무게중심의 u(0~1). 그라데이션 베이스는 무시.

    알파(전체 손톱)는 대칭이라 무의미 → saliency(원본-블러)로 모티프 위치를 잡는다.
    """
    bgr = atlas[:, :, :3]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blur = cv2.GaussianBlur(gray, (51, 51), 0)
    inner = cv2.erode(atlas[:, :, 3], np.ones((31, 31), np.uint8))  # 경계 고주파 제외
    sal = np.abs(gray - blur) * (inner > 0)
    if sal.sum() < 1:
        return 0.5
    xs = np.arange(atlas.shape[1])
    return float((sal.sum(0) * xs).sum() / sal.sum() / (atlas.shape[1] - 1))


def main():
    W, H = 480, 460
    # 손톱1: 좌측에 꽃을 둔 비대칭 디자인 (전사·미러 판별용)
    flower = os.path.join(ROOT, "samples", "flower.png")
    ir1 = {"schema": "nail-design/1", "aspect_hint": 0.72, "fit_mode": "stretch",
           "layers": [
               {"id": "g", "role": "color_region", "type": "gradient",
                "stops": [["#ff5ea2", 0.0], ["#ffd36b", 1.0]], "axis": "v"},
               {"id": "fl", "role": "color_region", "type": "raster", "src": flower,
                "uv": [0.05, 0.30, 0.42, 0.62], "flip_v": False}]}  # 좌측

    m1, g1 = synth_nail(W, H, 130, 230, 150, 95, 0)
    dcfg = DesignConfig(); dcfg.scale = 0.95; dcfg.warp_tier = "plane"

    class _Eng(DesignEngine):
        def __init__(self, ir, d):
            from src.design_ir import bake_uv_atlas
            from src.surface import ParamSmoother
            self.dcfg = d; self.ir = ir
            self.atlas = bake_uv_atlas(ir, 384); self.smoother = ParamSmoother()
            self._a_des = float(ir.get("aspect_hint", 0.0))

    # 손톱1 렌더
    frame = np.full((H, W, 3), 55, np.uint8)
    for (cx, cy, aw, al) in [(130, 230, 95, 150), (340, 235, 80, 140)]:
        cv2.ellipse(frame, (cx, cy), (aw, al), 0, 0, 360, (70, 70, 70), -1)
    eng = _Eng(ir1, dcfg)
    eng.render(frame, g1, m1, g1.center)

    # 캡처(언워프)
    cap = capture_nail_atlas(frame, g1, m1, dcfg, size=384)
    orig = eng.atlas
    # 라운드트립 충실도(나일1 가시영역): 원 atlas와 캡처 atlas 비교
    both = (orig[:, :, 3] > 0) & (cap[:, :, 3] > 0)
    if both.sum() > 100:
        mse = np.mean((orig[:, :, :3][both].astype(np.float32) -
                       cap[:, :, :3][both].astype(np.float32)) ** 2)
        rt_psnr = 99.0 if mse < 1e-6 else 10 * np.log10(255 * 255 / mse)
    else:
        rt_psnr = 0.0
    cu = content_centroid_u(cap)
    print(f"캡처: 라운드트립 PSNR={rt_psnr:.1f}dB  꽃 무게중심 u={cu:.2f}(<0.5=좌측)")
    assert rt_psnr > 18, f"언워프 충실도 낮음 {rt_psnr:.1f}"
    assert cu < 0.45, "원 디자인은 좌측 비대칭이어야"

    # 손톱2(다른 형상/위치/각도)에 전사
    m2, g2 = synth_nail(W, H, 340, 235, 140, 80, -18)
    transfer_design(frame, cap, g2, m2, dcfg)
    cov2 = int((np.any(frame != 55, axis=2) & (m2 > 0)).sum())
    leak2 = int((np.any(frame != 55, axis=2) & (cv2.dilate(m2, np.ones((9, 9), np.uint8)) == 0)
                 & (m1 == 0)).sum())
    print(f"전사: 손톱2 커버 {cov2}px (>3000)  손톱2 밖 누출 {leak2}px")
    assert cov2 > 3000, "손톱2에 디자인이 충분히 입혀져야"

    # 미러 검증: u→1-u → 무게중심 좌우 반전
    cap_m = cv2.flip(cap, 1)
    cu_m = content_centroid_u(cap_m)
    print(f"미러: 무게중심 u {cu:.2f} → {cu_m:.2f} (1-u 반전, 우측)")
    assert cu_m > 0.55, "미러 후 우측으로 가야"

    # 시각화: [손톱1 원본 | 손톱2 전사 | 캡처 atlas]
    atlas_vis = cv2.cvtColor(cv2.resize(cap, (H, H)), cv2.COLOR_BGRA2BGR)
    cv2.putText(frame, "nail1 -> nail2 transfer", (8, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(atlas_vis, "captured UV atlas", (8, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    combo = np.hstack([frame, atlas_vis])
    out = os.path.join(ROOT, "samples", "a3_transfer_demo.png")
    cv2.imwrite(out, combo)
    print(f"\n시각화: {out}")
    print("ALL A3-4 CHECKS OK")


if __name__ == "__main__":
    main()
