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

# 대상 패키지: pkg=<name> 인자 또는 NAIL_PKG 환경변수로 바꾼다(앱마다 files 디렉터리가 다름).
#   예) python web/push_calib.py pkg=com.DefaultCompany.NailMirror mode=5
PKG = os.environ.get("NAIL_PKG", "com.DefaultCompany.Nail")
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
    # 전송 계층(USB↔폰 전환): ""=그대로. USB=https://127.0.0.1:8443/infer, LAN=https://<ip>:8443/infer
    "edgeUrl": "",
    # raw TCP 소켓 전송(B', 빠름) + fps 캡. useSocket=1 소켓, sockHost/sockPort, inferInterval(초)
    "useSocket": -1, "sockHost": "", "sockPort": -1, "inferInterval": -1.0,
    # 실물크기 프리뷰 + 렌더 게이팅
    "lifesize": -1, "panelRadPerPx": -1.0, "lifesizeMax": -1.0, "gate": -1,
    # 손톱 축방향 디자인 이동(+팁/-뿌리, 길이 비율) — "디자인이 손톱보다 아래" 교정
    "alongTip": -99.0,
    # 보기: 수동 확대 / 가이드 루페(손톱 중심 크롭+확대) / 단안(0=양안,1=좌,2=우)
    "zoom": -1.0, "guide": -1, "guideZoom": -1.0, "mono": -1,
    # 능동 확대: 손 거리와 무관하게 손톱을 화면에서 일정 크기로 유지
    "guideAuto": -1, "guideTarget": -1.0, "guideZoomMin": -1.0, "guideZoomMax": -1.0,
    # 지연 보상 예측(ms). 0=끔, ~150=오프로드 지연 상쇄
    "predictMs": -1.0,
    # 안경 직접 중계(PC의 screenrecord+컴포지터 없이 안경이 릴레이로 자기 화면 전송).
    # relayOn=1 송출 / relayUrl=http://<릴레이IP>:8090 / relayToken=<PUSH_TOKEN> 이 셋이 있어야 실제로 나간다.
    "relayOn": -1, "relayUrl": "", "relayToken": "", "relayFps": -1.0,
    "relayW": -1, "relayQ": -1, "relayFlipY": -1,
}

# 로그에 그대로 찍으면 안 되는 값 (콘솔·터미널 기록에 토큰이 남는다)
SECRET_KEYS = {"relayToken"}

def main() -> None:
    d = dict(BASE)
    pkg = PKG
    serial = os.environ.get("ANDROID_SERIAL", "")   # 안경+폰이 같이 붙어 있으면 adb가 대상을 못 고른다
    args = sys.argv[1:]
    if not args:                                    # 인자 없음 = 그리드 오프셋만 0으로 리셋
        d["gridOffX"], d["gridOffY"] = 0.0, 0.0
    for a in args:
        if "=" not in a:
            print(f"skip '{a}' (need key=value)"); continue
        k, v = a.split("=", 1)
        if k == "pkg":                              # 대상 앱 패키지 지정(특수 키)
            pkg = v; continue
        if k == "serial":                           # 대상 기기 지정(특수 키). 안경/폰 동시 연결 시 필수
            serial = v; continue
        if k not in d:
            print(f"skip unknown key '{k}'"); continue
        # str vs bool vs int vs float — base 값의 타입으로 결정
        b = BASE[k]
        if isinstance(b, str):      d[k] = v
        elif isinstance(b, bool):   d[k] = v.lower() in ("1", "true", "on", "yes")
        elif isinstance(b, int):    d[k] = int(float(v))
        else:                       d[k] = float(v)
    with open(LOCAL, "w") as f:
        json.dump(d, f)
    dst = f"/sdcard/Android/data/{pkg}/files/nail_calib.json"
    changed = {k: ("***" if k in SECRET_KEYS else d[k]) for k in d if d[k] != BASE[k]}
    cmd = ["adb"] + (["-s", serial] if serial else []) + ["push", LOCAL, dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(f"push -> {pkg}{f'@{serial}' if serial else ''}: {changed} rc={r.returncode} {r.stderr.strip()}")

if __name__ == "__main__":
    main()
