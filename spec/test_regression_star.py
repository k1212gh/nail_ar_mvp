"""A3-1 게이트 — 별 PNG가 새 엔진(plane tier, IR 경유)으로 레거시 출력과 동일한가.

레거시 `design_overlay.apply` vs 신규 `DesignEngine.render`(plane) 결과를 PSNR로 비교.
PSNR>45dB면 회귀 없음으로 본다(DESIGN_WARP §8).
"""
import math
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import DesignConfig, GeomConfig            # noqa: E402
from src.geometry import compute_geometry              # noqa: E402
from src import design_overlay                          # noqa: E402
from src.design_render import DesignEngine              # noqa: E402


def psnr(a, b):
    mse = np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2)
    if mse < 1e-9:
        return float("inf")
    return 10.0 * math.log10(255.0 * 255.0 / mse)


def make_nail(w, h, cx, cy, ax_len, ax_wid, ang):
    mask = np.zeros((h, w), np.uint8)
    cv2.ellipse(mask, (cx, cy), (ax_wid, ax_len), ang, 0, 360, 255, -1)
    return mask


def main():
    star = os.path.join(ROOT, "samples", "star.png")
    assert os.path.exists(star), "samples/star.png 없음"

    W, H = 640, 480
    results = []
    # 여러 위치·각도·크기의 손톱에서 비교
    for (cx, cy, al, aw, ang) in [(320, 240, 70, 45, 0),
                                  (200, 180, 60, 40, 25),
                                  (430, 300, 80, 50, -35)]:
        mask = make_nail(W, H, cx, cy, al, aw, ang)
        gcfg = GeomConfig()
        geom = compute_geometry(mask, None, gcfg)
        assert geom is not None
        bg = np.full((H, W, 3), 60, np.uint8)
        cv2.putText(bg, "bg", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (200, 200, 200), 2)

        dcfg = DesignConfig()
        dcfg.image_path = star
        dcfg.scale = 0.85
        dcfg.warp_tier = "plane"
        # 레거시
        legacy = bg.copy()
        design = design_overlay.load_design(star)
        design_overlay.apply(legacy, design, geom, mask, geom.center, dcfg)
        # 신규(plane)
        new = bg.copy()
        eng = DesignEngine(dcfg)
        assert eng.ok(), "엔진 atlas 로드 실패"
        eng.render(new, geom, mask, geom.center, fps=30)

        p = psnr(legacy, new)
        results.append(p)
        print(f"  nail@({cx},{cy},ang={ang}): PSNR(legacy vs new plane) = {p:.1f} dB")

    worst = min(results)
    print(f"\nWORST PSNR = {worst:.1f} dB  (게이트 >45dB)")
    assert worst > 45.0, f"회귀! PSNR {worst:.1f} <= 45dB"
    print("REGRESSION OK — 별 plane 경로가 레거시와 동등")


if __name__ == "__main__":
    main()
