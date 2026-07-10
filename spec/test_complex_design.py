"""A3-3 복잡 디자인 검증 — 별 PNG가 아닌 멀티레이어(그라데이션+프렌치 벡터+래스터 모티프)가
곡면·기울기에 일반적으로 워핑되는지. + fit_mode(비율보존) + per-nail 클립.
"""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import DesignConfig, GeomConfig                 # noqa: E402
from src.geometry import compute_geometry                   # noqa: E402
from src.design_ir import bake_uv_atlas                     # noqa: E402
from src.design_render import DesignEngine                  # noqa: E402


def make_flower(path, S=200):
    """투명 배경 위 분홍 5엽 꽃 BGRA 모티프 생성."""
    img = np.zeros((S, S, 4), np.uint8)
    cx = cy = S // 2
    for k in range(5):
        ang = k * 72
        M = cv2.getRotationMatrix2D((cx, cy), ang, 1.0)
        petal = np.zeros((S, S, 4), np.uint8)
        cv2.ellipse(petal, (cx, cy - S // 4), (S // 10, S // 5), 0, 0, 360,
                    (180, 120, 240, 255), -1)
        petal = cv2.warpAffine(petal, M, (S, S))
        a = petal[:, :, 3:4].astype(np.float32) / 255
        img[:] = (petal.astype(np.float32) * a + img.astype(np.float32) * (1 - a)).astype(np.uint8)
    cv2.circle(img, (cx, cy), S // 12, (80, 220, 255, 255), -1)
    cv2.imwrite(path, img)
    return path


def synth_nail(W, H, cx, cy, al, aw, ang=0):
    mask = np.zeros((H, W), np.uint8)
    cv2.ellipse(mask, (cx, cy), (aw, al), ang, 0, 360, 255, -1)
    return mask, compute_geometry(mask, None, GeomConfig())


def coverage_aspect(frame, bg, mask):
    changed = np.any(frame != bg, axis=2) & (mask > 0)
    ys, xs = np.where(changed)
    if len(xs) < 5:
        return 0.0
    return (xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1)


def main():
    flower = make_flower(os.path.join(ROOT, "samples", "flower.png"))

    # 복잡 IR: 그라데이션 베이스 + 프렌치 경계(벡터) + 꽃 모티프(래스터)
    ir = {
        "schema": "nail-design/1", "uv_template": "almond",
        "aspect_hint": 0.72, "fit_mode": "stretch",
        "layers": [
            {"id": "grad", "role": "color_region", "type": "gradient",
             "stops": [["#ff5ea2", 0.0], ["#ffd36b", 1.0]], "axis": "v", "opacity": 1.0},
            {"id": "fr", "role": "french_boundary", "type": "vector",
             "path": "M0,0.78 Q0.5,0.62 1,0.78", "stroke": "#ffffff", "width_uv": 0.05},
            {"id": "flower", "role": "color_region", "type": "raster",
             "src": flower, "uv": [0.28, 0.30, 0.72, 0.62], "flip_v": False, "opacity": 1.0},
        ],
        "anchors": [],
    }
    atlas = bake_uv_atlas(ir, size=384)
    nonempty = int((atlas[:, :, 3] > 0).sum())
    print(f"복잡 atlas bake: 비어있지 않은 픽셀 {nonempty}/{384*384} "
          f"({100*nonempty/(384*384):.0f}%)")
    assert nonempty > 384 * 384 * 0.8, "그라데이션 베이스가 대부분 채워야"
    cv2.imwrite(os.path.join(ROOT, "samples", "a3_atlas.png"),
                cv2.cvtColor(atlas, cv2.COLOR_BGRA2BGR))

    W, H = 420, 460
    cx, cy = W // 2, H // 2
    mask, geom = synth_nail(W, H, cx, cy, 150, 95)

    class _Eng(DesignEngine):
        def __init__(self, ir, dcfg):
            self.dcfg = dcfg
            self.ir = ir
            self.atlas = bake_uv_atlas(ir, size=384)
            from src.surface import ParamSmoother
            self.smoother = ParamSmoother()
            self._a_des = float(ir.get("aspect_hint", 0.0))

    # plane vs mesh(curve) 렌더
    def render(tier, curve=0.0):
        d = DesignConfig(); d.scale = 0.95; d.warp_tier = tier; d.curve = curve
        f = np.full((H, W, 3), 55, np.uint8)
        cv2.ellipse(f, (cx, cy), (95, 150), 0, 0, 360, (70, 70, 70), -1)
        _Eng(ir, d).render(f, geom, mask, geom.center)
        return f

    f_plane = render("plane")
    f_mesh = render("mesh", curve=0.85)
    # 곡면에서도 누출 없는지
    changed = np.any(f_mesh != 55, axis=2)
    leak = int((changed & (cv2.dilate(mask, np.ones((9, 9), np.uint8)) == 0)).sum())
    print(f"복잡 디자인 곡면 누출: {leak}px (<200 허용)")
    assert leak < 200

    cv2.putText(f_plane, "complex/plane", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(f_mesh, "complex/mesh(curve)", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    # ---- fit_mode: 정사각 디자인을 길쭉한 손톱에 ----
    sq_ir = {"schema": "nail-design/1", "aspect_hint": 1.0, "fit_mode": "stretch",
             "layers": [{"id": "g", "role": "color_region", "type": "gradient",
                         "stops": [["#40e0ff", 0.0], ["#4060ff", 1.0]], "axis": "u"}]}
    maskt, geomt = synth_nail(W, H, cx, cy, 165, 70)        # 길쭉(폭/길이 작음)
    a_nail = geomt.width / geomt.length
    bg = np.full((H, W, 3), 55, np.uint8)

    d_s = DesignConfig(); d_s.scale = 1.0; d_s.warp_tier = "plane"; d_s.fit_mode = "stretch"
    fs = bg.copy(); _Eng(dict(sq_ir, fit_mode="stretch"), d_s).render(fs, geomt, maskt, geomt.center)
    d_c = DesignConfig(); d_c.scale = 1.0; d_c.warp_tier = "plane"; d_c.fit_mode = "contain"
    fc = bg.copy(); _Eng(dict(sq_ir, fit_mode="contain"), d_c).render(fc, geomt, maskt, geomt.center)

    asp_s = coverage_aspect(fs, bg, maskt)
    asp_c = coverage_aspect(fc, bg, maskt)
    print(f"fit_mode: 손톱비율={a_nail:.2f}  stretch 커버비율={asp_s:.2f}(≈손톱)  "
          f"contain 커버비율={asp_c:.2f}(≈디자인 1.0)")
    assert abs(asp_s - a_nail) < 0.18, "stretch는 손톱 박스를 채워야"
    assert asp_c > asp_s + 0.25, "contain은 정사각 디자인 비율을 보존(더 정사각에 근접)"

    # ---- per-nail 클립: 두 손톱 다른 위치, 디자인이 옆 손톱에 안 샘 ----
    # (PC는 손톱별 mask 인자로 클립하므로 구조적 보장 — 확인)
    f2 = render("plane")                                   # 본 손톱은 cx(폭95)
    other = np.zeros((H, W), np.uint8)
    cv2.ellipse(other, (W - 30, cy), (25, 70), 0, 0, 360, 255, -1)   # 겹치지 않는 우측 끝
    leak_other = int((np.any(f2 != 55, axis=2) & (other > 0)).sum())
    print(f"per-nail 클립: 옆 손톱 영역 침범 {leak_other}px (=0)")
    assert leak_other == 0

    combo = np.hstack([f_plane, f_mesh])
    out = os.path.join(ROOT, "samples", "a3_complex_demo.png")
    cv2.imwrite(out, combo)
    print(f"\n시각화: {out}  /  atlas: samples/a3_atlas.png")
    print("ALL A3-3 CHECKS OK")


if __name__ == "__main__":
    main()
