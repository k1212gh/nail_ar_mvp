"""모니터 기반 다거리 4점 SPAAM 보정 — 런타임 오케스트레이션(서브커맨드).

아이디어: 노트북 모니터(알려진 실제 크기)를 정밀 평면 기준물로 삼아,
  1) 안경 카메라가 모니터 4모서리를 봐서 PnP → 모서리 3D(카메라 프레임)  [객관]
  2) 안경 디스플레이 크로스헤어를 각 모서리에 정렬            [주관, 눈 기준]
  3) 여러 거리에서 대응점 수집 → SPAAM DLT → 눈 위치 → (A,B) → 앱 push
앱 재빌드 불필요(런타임 crossX/crossY + mesh 시차 pAx..pBy 사용).

이 스크립트는 '한 방 대화형 루프'가 아니라, 오퍼레이터(사람/에이전트)가
단계별로 호출하는 서브커맨드로 설계됨(정렬 확인은 사람이 하므로).

서브커맨드:
  show-pattern            모니터에 전체화면 흰 사각(+4모서리 마크) 표시(안경이 볼 대상). ESC 종료.
  detect                  최근 안경 프레임(_last_frame.jpg)에서 모니터 사각 검출 + PnP 출력
  crosshair --x .15 --y .15   디스플레이 크로스헤어를 그 정규화위치로 push
  record --slot TL --x .15 --y .15   지금 프레임의 해당 모서리 3D + display(x,y) 대응점 저장
  status                  수집된 대응점 개수/거리 요약
  solve [--push]          대응점으로 눈위치·A/B 계산, --push면 앱에 반영
  reset                   대응점 초기화

경로: 안경 프레임은 edge_serve.py 가 매 프레임 저장하는 <root>/_last_frame.jpg 를 읽음.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

LAST_FRAME = os.path.join(ROOT, "_last_frame.jpg")
STATE = os.path.join(HERE, "_monitor_calib_state.json")
PUSH_JSON = os.path.join(HERE, "_monitor_calib_push.json")
DEFAULT_PKG = "com.DefaultCompany.NailMesh"

# 슬롯(모니터/디스플레이 모서리) — TL,TR,BR,BL 순서 고정
SLOTS = ["TL", "TR", "BR", "BL"]


def find_adb() -> str:
    from shutil import which
    p = which("adb")
    if p:
        return p
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    for dp, _, files in os.walk(base):
        if "adb.exe" in files and "scrcpy" in dp.lower():
            return os.path.join(dp, "adb.exe")
    return "adb"


# ---------------- 모니터 패턴(안경이 볼 대상) ----------------
def cmd_show_pattern(args):
    """전체화면 흰 사각 + 4모서리 십자마크. 안경 카메라가 이 사각을 검출한다."""
    win = "MONITOR_CALIB"
    cv2.namedWindow(win, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    W, H = args.w, args.h
    img = np.zeros((H, W, 3), np.uint8)
    cv2.rectangle(img, (2, 2), (W - 3, H - 3), (255, 255, 255), 4)   # 밝은 테두리(검출용)
    img[:] = np.where(img.sum(2, keepdims=True) > 0, img, 235)        # 화면 대부분 밝게(모니터=밝은 사각)
    m = 40
    for (x, y) in [(m, m), (W - m, m), (W - m, H - m), (m, H - m)]:   # 4모서리 십자
        cv2.drawMarker(img, (x, y), (0, 0, 0), cv2.MARKER_CROSS, 60, 4)
    cv2.putText(img, "MONITOR CALIB - 안경으로 이 화면을 보세요 (ESC 종료)", (60, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    while True:
        cv2.imshow(win, img)
        if (cv2.waitKey(50) & 0xFF) == 27:
            break
    cv2.destroyAllWindows()


# ---------------- 안경 프레임에서 모니터 사각 검출 ----------------
def detect_monitor_quad(frame: np.ndarray):
    """가장 큰 밝은 사각형 4모서리(px, TL,TR,BR,BL 순) 반환 or None."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # 모니터는 방보다 밝음 → Otsu 위쪽
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0.0
    H, W = frame.shape[:2]
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 0.05 * W * H:            # 너무 작은 건 무시
            continue
        peri = cv2.arcLength(c, True)
        ap = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(ap) == 4 and cv2.isContourConvex(ap) and area > best_area:
            best_area = area
            best = ap.reshape(4, 2).astype(np.float32)
    if best is None:
        return None
    return order_corners(best)


def order_corners(pts: np.ndarray) -> np.ndarray:
    """4점 → TL,TR,BR,BL 순 정렬."""
    s = pts.sum(1)
    d = np.diff(pts, axis=1).ravel()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], np.float32)


def load_frame():
    if not os.path.isfile(LAST_FRAME):
        print(f"[calib] 안경 프레임 없음: {LAST_FRAME} (edge_serve 실행중? 손/화면이 카메라에?)")
        return None
    fr = cv2.imread(LAST_FRAME)
    return fr


def make_cfg(args):
    from src.monitor_calib import MonitorCalibConfig
    return MonitorCalibConfig(monitor_w_m=args.mon_w, monitor_h_m=args.mon_h,
                              glasses_cam_hfov_deg=args.cam_hfov,
                              display_px_w=args.disp_w, display_hfov_deg=args.disp_hfov)


def cmd_detect(args):
    fr = load_frame()
    if fr is None:
        return
    quad = detect_monitor_quad(fr)
    if quad is None:
        print("[calib] 모니터 사각 검출 실패 — 안경이 모니터 전체를 보게, 방을 어둡게/화면 밝게")
        return
    print("[calib] 모니터 모서리(px, TL,TR,BR,BL):")
    for s, p in zip(SLOTS, quad):
        print(f"    {s}: ({p[0]:.0f}, {p[1]:.0f})")
    try:
        from src.monitor_calib import camera_pose_from_corners
        cfg = make_cfg(args)
        H, W = fr.shape[:2]
        pose = camera_pose_from_corners(quad, W, H, cfg)
        cc = pose["corners_cam"]
        print(f"[calib] PnP OK — 모니터 중심거리 ≈ {np.mean(cc, 0)[2]*100:.1f}cm")
        for s, p in zip(SLOTS, cc):
            print(f"    {s} 3D(cam,m): ({p[0]:+.3f},{p[1]:+.3f},{p[2]:+.3f})")
    except Exception as e:
        print(f"[calib] PnP 단계 건너뜀(monitor_calib 준비중?): {e}")


# ---------------- 크로스헤어 push ----------------
def push_calib(pkg: str, d: dict) -> str:
    with open(PUSH_JSON, "w", encoding="utf-8") as f:
        json.dump(d, f)
    dst = f"/sdcard/Android/data/{pkg}/files/nail_calib.json"
    r = subprocess.run([find_adb(), "push", PUSH_JSON, dst], capture_output=True, text=True)
    return "OK" if r.returncode == 0 else f"ERR {r.stderr.strip()}"


def crosshair_json(nx: float, ny: float, canvas_w: float, canvas_h: float, mode_calib: bool) -> dict:
    """display 정규화(nx,ny)∈[0,1] → 앱 crossX/crossY(캔버스 로컬 px, 중심0).
    부호/스케일은 세션에서 확정(--sign 계열은 향후 추가). 우선 중심기준 선형 매핑."""
    cx = (nx - 0.5) * canvas_w
    cy = (ny - 0.5) * canvas_h
    d = {k: v for k, v in _SENTINEL.items()}
    d.update({"crossOn": 1, "crossX": float(cx), "crossY": float(cy)})
    if mode_calib:
        d["mode"] = 2   # NailMode.Calib
    return d


def cmd_crosshair(args):
    d = crosshair_json(args.x, args.y, args.canvas_w, args.canvas_h, not args.no_mode)
    st = push_calib(args.package, d)
    print(f"[calib] 크로스헤어 → 디스플레이({args.x:.2f},{args.y:.2f}) canvasPx({d['crossX']:.0f},{d['crossY']:.0f})  push={st}")


# ---------------- 대응점 기록 ----------------
def _load_state():
    if os.path.isfile(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return {"corr": []}


def _save_state(s):
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def cmd_record(args):
    fr = load_frame()
    if fr is None:
        return
    quad = detect_monitor_quad(fr)
    if quad is None:
        print("[calib] 모서리 검출 실패 — record 취소")
        return
    try:
        from src.monitor_calib import camera_pose_from_corners
        cfg = make_cfg(args)
        H, W = fr.shape[:2]
        pose = camera_pose_from_corners(quad, W, H, cfg)
        idx = SLOTS.index(args.slot)
        corner_cam = pose["corners_cam"][idx].tolist()
    except Exception as e:
        print(f"[calib] PnP 실패: {e}")
        return
    s = _load_state()
    s["corr"].append({"slot": args.slot, "display_norm": [args.x, args.y],
                      "corner_cam": corner_cam, "dist_m": pose["corners_cam"][idx][2]})
    _save_state(s)
    print(f"[calib] 기록 #{len(s['corr'])}: slot={args.slot} disp=({args.x:.2f},{args.y:.2f}) "
          f"3D=({corner_cam[0]:+.3f},{corner_cam[1]:+.3f},{corner_cam[2]:+.3f})m")


def cmd_status(args):
    s = _load_state()
    n = len(s["corr"])
    dists = sorted(set(round(c["dist_m"], 2) for c in s["corr"]))
    print(f"[calib] 대응점 {n}개, 거리대(대략): {dists} m")
    print(f"    (권장: ≥2거리 × 4모서리 = ≥8점. 현재 {'충분' if n>=8 and len(dists)>=2 else '부족'})")


def cmd_reset(args):
    _save_state({"corr": []})
    print("[calib] 대응점 초기화")


def cmd_solve(args):
    from src.monitor_calib import solve_eye_in_camera, eye_to_AB
    cfg = make_cfg(args)
    s = _load_state()
    corr = [(np.array(c["display_norm"], float), np.array(c["corner_cam"], float)) for c in s["corr"]]
    if len(corr) < 6:
        print(f"[calib] 대응점 부족({len(corr)}<6). 더 수집하세요(여러 거리).")
        return
    res = solve_eye_in_camera(corr, cfg)
    eye = res["eye_cam"]
    Ax, Ay, Bx, By = eye_to_AB(eye, cfg)
    print(f"[calib] 눈위치(cam,m)=({eye[0]:+.3f},{eye[1]:+.3f},{eye[2]:+.3f})  "
          f"잔차={res.get('residual_px','?')}px  n={res.get('n',len(corr))}")
    print(f"[calib] → A=({Ax:.1f},{Ay:.1f}) B=({Bx:.1f},{By:.1f})  (offset(d)=A+B/d)")
    if res.get("planar_warn"):
        print("[calib] ⚠ 단일평면 경고 — 거리를 2~3개로 늘리면 정확도↑")
    if args.push:
        d = {k: v for k, v in _SENTINEL.items()}
        d.update({"meshParallaxOn": 1, "pAx": Ax, "pAy": Ay, "pBx": Bx, "pBy": By,
                  "crossOn": 0, "mode": 3})
        print("  push:", push_calib(args.package, d))


# 모든 필드 센티널(건드리지 않음) — 앱이 값>센티널일 때만 반영
_SENTINEL = {
    "offsetX": 0.0, "offsetY": 0.0, "scale": -1.0, "designScale": 0.0, "rot": -999,
    "flipX": -1, "flipY": -1, "canvasRot": -999.0, "designRot": -999.0, "stretchX": -1.0,
    "stretchY": -1.0, "gridOn": -1, "dynDepth": -1, "depthM": -1.0, "smoothing": -1.0,
    "holdSec": -1.0, "camW": -1, "camH": -1, "crossOn": -1, "crossX": -99999.0, "crossY": -99999.0,
    "meshParallaxOn": -1, "pAx": -99999.0, "pAy": -99999.0, "pBx": -99999.0, "pBy": -99999.0,
    "mode": -1,
}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--package", default=DEFAULT_PKG)
        p.add_argument("--mon-w", type=float, default=0.344, help="모니터 표시영역 실제 폭(m)")
        p.add_argument("--mon-h", type=float, default=0.193, help="실제 높이(m)")
        p.add_argument("--cam-hfov", type=float, default=66.0, help="안경 카메라 화각(deg)")
        p.add_argument("--disp-w", type=float, default=1280.0)
        p.add_argument("--disp-hfov", type=float, default=27.0)
        p.add_argument("--canvas-w", type=float, default=1280.0)
        p.add_argument("--canvas-h", type=float, default=480.0)

    p = sub.add_parser("show-pattern"); p.add_argument("--w", type=int, default=1920); p.add_argument("--h", type=int, default=1080)
    p = sub.add_parser("detect"); common(p)
    p = sub.add_parser("crosshair"); common(p); p.add_argument("--x", type=float, required=True); p.add_argument("--y", type=float, required=True); p.add_argument("--no-mode", action="store_true")
    p = sub.add_parser("record"); common(p); p.add_argument("--slot", choices=SLOTS, required=True); p.add_argument("--x", type=float, required=True); p.add_argument("--y", type=float, required=True)
    p = sub.add_parser("status"); common(p)
    p = sub.add_parser("reset"); common(p)
    p = sub.add_parser("solve"); common(p); p.add_argument("--push", action="store_true")

    args = ap.parse_args()
    {"show-pattern": cmd_show_pattern, "detect": cmd_detect, "crosshair": cmd_crosshair,
     "record": cmd_record, "status": cmd_status, "reset": cmd_reset, "solve": cmd_solve}[args.cmd](args)


if __name__ == "__main__":
    main()
