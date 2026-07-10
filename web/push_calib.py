"""nail_calib.json 을 글래스로 adb push → 앱이 0.7초 폴링으로 자동 반영.

사용:
  python web/push_calib.py gridOffX=300 gridOffY=0 gridPosScale=1.8 gridMinCutoff=0.4 gridBeta=0.5
  python web/push_calib.py offsetX=300 offsetY=0            # 디자인(overlay)에 같은 보정
  (인자 없으면 전부 그대로 두고 gridOff=0,0 만 리셋)

모든 필드 기본 = "leave" 센티널 → canvasRot/flipY 등 기존 설정을 건드리지 않는다.
key=value 로 준 것만 실제 값으로 덮어씀.
"""
import json
import os
import subprocess
import sys

PKG = "com.DefaultCompany.Nail"
DST = f"/sdcard/Android/data/{PKG}/files/nail_calib.json"
HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(HERE, "_calib_push.json")

# 모든 필드 = "leave" 센티널
BASE = {
    "offsetX": 0.0, "offsetY": 0.0, "scale": 1.0, "designScale": 0.0,
    "rot": -999, "mirrorX": False, "mirrorY": False, "showFeed": False,
    "depthM": -1.0, "smoothing": -1.0, "holdSec": -1.0,
    "dynDepth": -1, "depthK": -1.0, "distScale": -1.0,
    "canvasRot": -999.0, "mode": -1, "designRot": -999.0,
    "flipX": -1, "flipY": -1,
    "gridOn": -1, "cellMm": -1.0, "gridAlpha": -1.0, "gridRot": -999.0,
    "gridScale": -1.0, "gridFollow": -1,
    "gridOffX": -99999.0, "gridOffY": -99999.0,
    "gridPosScale": -1.0, "gridMinCutoff": -1.0, "gridBeta": -1.0,
    "crossOn": -1, "crossX": -99999.0, "crossY": -99999.0,
    "camW": -1, "camH": -1, "stretchX": -1.0, "stretchY": -1.0,
}

def main() -> None:
    d = dict(BASE)
    args = sys.argv[1:]
    if not args:                                    # 인자 없음 = 그리드 오프셋만 0으로 리셋
        d["gridOffX"], d["gridOffY"] = 0.0, 0.0
    for a in args:
        if "=" not in a:
            print(f"skip '{a}' (need key=value)"); continue
        k, v = a.split("=", 1)
        if k not in d:
            print(f"skip unknown key '{k}'"); continue
        # int vs float vs bool by the base type
        b = BASE[k]
        if isinstance(b, bool):     d[k] = v.lower() in ("1", "true", "on", "yes")
        elif isinstance(b, int):    d[k] = int(float(v))
        else:                       d[k] = float(v)
    with open(LOCAL, "w") as f:
        json.dump(d, f)
    changed = {k: d[k] for k in d if d[k] != BASE[k]}
    r = subprocess.run(["adb", "push", LOCAL, DST], capture_output=True, text=True)
    print(f"push {changed} rc={r.returncode} {r.stderr.strip()}")

if __name__ == "__main__":
    main()
