"""외부캠 자동정합 런타임 — 웹캠으로 눈을 추적해 안경 앱에 시차보정(A,B)을 밀어넣는다.

파이프라인:
  노트북 웹캠 → MediaPipe FaceLandmarker(홍채+머리포즈) → 눈 3D·안경안착점 3D 측정
  → src.eye_geometry 로 baseline b → 시차모델 (A,B) → NailMesh 앱 nail_calib.json 로 push
  → 앱이 손 깊이 d 마다 offset(d)=A+B/d 로 자동 정합 (재빌드 불필요).

전제: 사용자가 안경을 쓴 채 이 웹캠을 바라보고, 손을 안경 카메라 앞(25~40cm)에 둔다.
      edge_serve.py(손톱 검출)는 별도 터미널에서 동시 구동.

사용:
  .venv\\Scripts\\python web\\eye_reg.py --dry        # push 없이 측정만(캘리브 확인)
  .venv\\Scripts\\python web\\eye_reg.py               # NailMesh 앱에 실제 push
  옵션: --dominant right|left  --package com.DefaultCompany.NailMesh  --hfov 60
        --gcam-dy -0.010 --gcam-dz 0.012  --sign-x 1 --sign-y 1  (캘리브 값 주입)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mpp
from mediapipe.tasks.python import vision

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from src import eye_geometry as EG   # noqa: E402

MODEL = os.path.join(ROOT, "models", "face_landmarker.task")
LOCAL_JSON = os.path.join(HERE, "_eye_calib_push.json")


def find_adb() -> str:
    """PATH 우선, 없으면 winget scrcpy 번들 adb."""
    from shutil import which
    p = which("adb")
    if p:
        return p
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    for dirpath, _, files in os.walk(base):
        if "adb.exe" in files and "scrcpy" in dirpath.lower():
            return os.path.join(dirpath, "adb.exe")
    return "adb"


def calib_json(ab, mode_armesh: bool, calib_scale: float = -1.0) -> dict:
    """mesh 시차모델만 갱신하고 나머지는 센티널(건드리지 않음). calib_scale>0이면 배율도 고정."""
    Ax, Ay, Bx, By = ab
    d = {
        "offsetX": 0.0, "offsetY": 0.0, "scale": float(calib_scale), "designScale": 0.0,
        "rot": -999, "flipX": -1, "flipY": -1, "canvasRot": -999.0, "designRot": -999.0,
        "stretchX": -1.0, "stretchY": -1.0, "gridOn": -1, "dynDepth": -1, "depthM": -1.0,
        "smoothing": -1.0, "holdSec": -1.0, "camW": -1, "camH": -1, "crossOn": -1,
        # --- mesh 깊이적응 시차모델(외부캠이 채우는 값) ---
        "meshParallaxOn": 1,
        "pAx": float(Ax), "pAy": float(Ay), "pBx": float(Bx), "pBy": float(By),
    }
    if mode_armesh:
        d["mode"] = 3   # NailMode.ARMesh (곡면 디자인 + 시차모델)
    else:
        d["mode"] = -1
    return d


def push(adb: str, pkg: str, data: dict) -> str:
    with open(LOCAL_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f)
    dst = f"/sdcard/Android/data/{pkg}/files/nail_calib.json"
    r = subprocess.run([adb, "push", LOCAL_JSON, dst], capture_output=True, text=True)
    return "OK" if r.returncode == 0 else f"ERR {r.stderr.strip()}"


def head_R_from_matrix(mat) -> np.ndarray:
    """FaceLandmarker 변환행렬(4x4) → 회전 3x3."""
    try:
        M = np.array(mat.data, dtype=float).reshape(4, 4) if hasattr(mat, "data") else np.array(mat, float).reshape(4, 4)
        return M[:3, :3]
    except Exception:
        return np.eye(3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="push 안 하고 측정만 출력")
    ap.add_argument("--cam", type=int, default=0)
    ap.add_argument("--package", default="com.DefaultCompany.NailMesh")
    ap.add_argument("--dominant", choices=["right", "left"], default="right")
    ap.add_argument("--hfov", type=float, default=60.0)
    ap.add_argument("--disp-hfov", type=float, default=27.0)
    ap.add_argument("--disp-w", type=float, default=1280.0)
    ap.add_argument("--gcam-dx", type=float, default=0.0)
    ap.add_argument("--gcam-dy", type=float, default=-0.010)
    ap.add_argument("--gcam-dz", type=float, default=0.012)
    ap.add_argument("--sign-x", type=float, default=1.0)
    ap.add_argument("--sign-y", type=float, default=1.0)
    ap.add_argument("--ax", type=float, default=0.0)
    ap.add_argument("--ay", type=float, default=0.0)
    ap.add_argument("--push-sec", type=float, default=0.8, help="push 최소 간격(0.7s 폴링 존중)")
    ap.add_argument("--fps", type=float, default=4.0, help="처리 프레임/초 상한(CPU 보호; edge_serve와 공존)")
    ap.add_argument("--calib-scale", type=float, default=-1.0, help=">0이면 앱 calibScale 고정(손톱 벌어짐 조정)")
    ap.add_argument("--ema", type=float, default=0.3, help="A/B 지수평활(0=고정,1=즉각)")
    ap.add_argument("--no-armesh", action="store_true", help="mode=ARMesh 강제 전환 끔")
    args = ap.parse_args()

    cfg = EG.EyeRegConfig(webcam_hfov_deg=args.hfov, display_hfov_deg=args.disp_hfov,
                          display_px_w=args.disp_w, gcam_dx=args.gcam_dx, gcam_dy=args.gcam_dy,
                          gcam_dz=args.gcam_dz, sign_x=args.sign_x, sign_y=args.sign_y,
                          Ax_px=args.ax, Ay_px=args.ay)
    iris_idx = EG.IRIS_R if args.dominant == "right" else EG.IRIS_L

    if not os.path.isfile(MODEL):
        print(f"[eye_reg] 모델 없음: {MODEL}\n  다운로드: curl -sL -o {MODEL} "
              "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task")
        sys.exit(1)
    adb = find_adb()
    opts = vision.FaceLandmarkerOptions(
        base_options=mpp.BaseOptions(model_asset_path=MODEL),
        running_mode=vision.RunningMode.VIDEO, num_faces=1,
        output_facial_transformation_matrixes=True, min_face_detection_confidence=0.4)
    fl = vision.FaceLandmarker.create_from_options(opts)

    cap = cv2.VideoCapture(args.cam, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"[eye_reg] 웹캠[{args.cam}] 열기 실패 — 다른 앱이 점유중이거나 권한 문제")
        sys.exit(1)
    print("=" * 64)
    print(f"  외부캠 자동정합  cam={args.cam}  pkg={args.package}  dominant={args.dominant}")
    print(f"  {'DRY(측정만)' if args.dry else 'PUSH'}  adb={os.path.basename(adb)}")
    print("  안경 쓰고 이 웹캠을 바라보세요. 종료: Ctrl+C")
    print("=" * 64)

    ema_ab = None
    last_push = 0.0
    n = 0
    frame_int = 1.0 / max(0.5, args.fps)   # CPU 보호: 처리 간격
    next_t = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            now0 = time.time()
            if now0 < next_t:               # fps 상한 — 남는 프레임은 버림(mediapipe 부하 억제)
                time.sleep(min(0.02, next_t - now0))
                continue
            next_t = now0 + frame_int
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mpimg = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts = int(time.perf_counter() * 1000)
            res = fl.detect_for_video(mpimg, ts)
            if not res.face_landmarks:
                if n % 30 == 0:
                    print("  … 얼굴 미검출 (웹캠 정면으로)")
                n += 1
                continue
            lm = res.face_landmarks[0]
            pts = np.array([[p.x * w, p.y * h] for p in lm], dtype=float)   # 정규화→px
            ic, idiam = EG.iris_center_and_diameter(pts, iris_idx)
            mount_px = pts[cfg.mount_landmark]
            R = head_R_from_matrix(res.facial_transformation_matrixes[0]) \
                if res.facial_transformation_matrixes else np.eye(3)
            # 눈 깊이(홍채)로 안착점 깊이 근사(둘 다 얼굴, 깊이 유사)
            eye_tmp = EG.eye_position_webcam(ic, idiam, w, h, cfg)
            out = EG.full_pipeline(ic, idiam, mount_px, float(eye_tmp[2]), w, h, R, cfg)
            ab = np.array(out["AB"], dtype=float)
            ema_ab = ab if ema_ab is None else (1 - args.ema) * ema_ab + args.ema * ab
            now = time.time()
            if n % 15 == 0:
                e = out["eye_W"]; b = out["baseline_xy"]
                o30 = EG.offset_at_depth(tuple(ema_ab), 0.30)
                print(f"  눈={e.round(3)}m b={b.round(4)}m AB=({ema_ab[0]:.0f},{ema_ab[1]:.0f},"
                      f"{ema_ab[2]:.0f},{ema_ab[3]:.0f}) off@30cm=({o30[0]:.0f},{o30[1]:.0f})px")
            if not args.dry and (now - last_push) >= args.push_sec:
                st = push(adb, args.package, calib_json(tuple(ema_ab), not args.no_armesh, args.calib_scale))
                last_push = now
                if st != "OK":
                    print("  push:", st)
            n += 1
    except KeyboardInterrupt:
        print("\n[eye_reg] 종료")
    finally:
        cap.release(); fl.close()


if __name__ == "__main__":
    main()
