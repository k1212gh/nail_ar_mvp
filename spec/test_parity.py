"""WarpSpec py↔js 패리티 테스트 (DESIGN_WARP §3).

동일 입력에서 spec/warp_spec.py 와 web/warp_spec.mjs 의 출력이 atol=1e-4로 일치해야 통과.
실행: python spec/test_parity.py   (node 필요)
"""
import json
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from spec.warp_spec import build_warp_spec  # noqa: E402

ATOL = 1e-4


def _axes(angle_deg):
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)        # major(팁)
    return [ux, uy], [-uy, ux]               # minor = major 90° 회전


def fixtures():
    cases = []
    base_majors = [0.0, 23.0, -57.0, 90.0]
    for ang in base_majors:
        major, minor = _axes(ang)
        p = {
            "center_px": [320.0 + ang, 240.0 - ang],
            "axis_major": major, "axis_minor": minor,
            "length": 80.0, "width": 55.0, "scale": 0.85, "along": 0.0,
            "tilt_deg": 0.0, "tilt_axis": [1.0, 0.0],
            "curv_half_angle": 0.0, "persp_f": 0.0,
            "feather_uv": 0.04, "alpha": 1.0,
        }
        cases.append({"params": dict(p), "tier": "plane", "grid": [1, 1]})
        # tilt
        pt = dict(p); pt["tilt_deg"] = 22.0; pt["tilt_axis"] = [0.3, 0.95]
        cases.append({"params": pt, "tier": "tilt", "grid": [1, 1]})
        # mesh + curvature + tilt
        pm = dict(p); pm["curv_half_angle"] = 0.6; pm["tilt_deg"] = 14.0
        pm["tilt_axis"] = [1.0, 0.2]; pm["along"] = 0.2
        cases.append({"params": pm, "tier": "mesh", "grid": [6, 5]})
        # mesh shaded, 곡률만
        pc = dict(p); pc["curv_half_angle"] = 0.9
        cases.append({"params": pc, "tier": "mesh_shaded", "grid": [10, 8]})
    return cases


def run_node(cases):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(cases, f)
        path = f.name
    try:
        r = subprocess.run(["node", os.path.join(HERE, "_parity_node.mjs"), path],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("node 실패:\n" + r.stderr)
        return json.loads(r.stdout)
    finally:
        os.unlink(path)


def main():
    cases = fixtures()
    py = [build_warp_spec(c["params"], c["tier"], c["grid"]) for c in cases]
    js = run_node(cases)
    assert len(py) == len(js), f"케이스 수 불일치 {len(py)} vs {len(js)}"

    max_err = 0.0
    n_pts = 0
    for i, (a, b) in enumerate(zip(py, js)):
        assert a["tier"] == b["tier"] and a["grid"] == b["grid"], f"#{i} tier/grid 불일치"
        assert len(a["screen"]) == len(b["screen"]), f"#{i} 정점수 불일치"
        for (xa, ya), (xb, yb) in zip(a["screen"], b["screen"]):
            ex = max(abs(xa - xb), abs(ya - yb))
            max_err = max(max_err, ex)
            n_pts += 1
            if ex > ATOL:
                raise AssertionError(
                    f"#{i} {a['tier']} 정점 오차 {ex:.2e} > {ATOL} : py({xa:.4f},{ya:.4f}) js({xb:.4f},{yb:.4f})")
    print(f"PARITY OK — {len(cases)} 케이스, {n_pts} 정점, 최대오차 {max_err:.2e} (atol {ATOL})")


if __name__ == "__main__":
    main()
