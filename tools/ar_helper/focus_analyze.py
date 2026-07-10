#!/usr/bin/env python3
"""focus_analyze.py — quantify how sharp the glasses camera sees a near object.

Risk ⓐ (IMPLEMENTATION_PLAN Phase 2): can the RayNeo camera resolve a fingernail
at 20-40 cm sharply enough for detection? This script grades photos captured by
the glasses (pulled via adb) using standard no-reference focus measures.

Metrics:
  * lapvar  = variance of Laplacian  (primary focus measure; higher = sharper)
  * teneng  = Tenengrad / Sobel gradient energy (secondary)
  * center  = same metrics on the central ROI (where the held nail sits)

Usage:
  python focus_analyze.py IMG [IMG ...]
  python focus_analyze.py --label 30cm shot30.jpg --label 40cm shot40.jpg
  python focus_analyze.py --selftest      # verify metric discriminates sharp vs blur
"""
import sys
import argparse
import cv2
import numpy as np


def focus_scores(gray: np.ndarray) -> dict:
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    return {
        "lapvar": float(lap.var()),
        "teneng": float((gx * gx + gy * gy).mean()),
    }


def center_roi(gray: np.ndarray, frac: float = 0.4) -> np.ndarray:
    h, w = gray.shape
    ch, cw = int(h * frac), int(w * frac)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    return gray[y0:y0 + ch, x0:x0 + cw]


# Heuristic thresholds for "sharp enough to detect a nail". lapvar is scale/expo
# dependent, so treat as relative when comparing shots; absolute band is a guide.
SHARP = 120.0
SOFT = 40.0


def verdict(lapvar_center: float) -> str:
    if lapvar_center >= SHARP:
        return "SHARP  [OK] (nail detection viable)"
    if lapvar_center >= SOFT:
        return "SOFT   [~]  (marginal; try lighting/distance)"
    return "BLURRY [X]  (below detection floor - likely fixed-focus limit)"


def analyze(path: str, label: str | None = None):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        print(f"  ! cannot read {path}")
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    whole = focus_scores(gray)
    cen = focus_scores(center_roi(gray))
    name = label or path
    print(f"[{name}]  {w}x{h}")
    print(f"    whole : lapvar={whole['lapvar']:8.1f}  teneng={whole['teneng']:8.1f}")
    print(f"    center: lapvar={cen['lapvar']:8.1f}  teneng={cen['teneng']:8.1f}  -> {verdict(cen['lapvar'])}")
    return cen["lapvar"]


def analyze_video(path: str, every: int = 10):
    """Grade sharpness across a camera recording (scrcpy --video-source=camera).
    Samples every `every`-th frame; reports the sharpest/blurriest and a verdict."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"  ! cannot open video {path}")
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    i, scored = 0, []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % every == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            scored.append((i / fps, focus_scores(center_roi(gray))["lapvar"]))
        i += 1
    cap.release()
    if not scored:
        print("  ! no frames")
        return None
    best = max(scored, key=lambda s: s[1])
    worst = min(scored, key=lambda s: s[1])
    med = sorted(s[1] for s in scored)[len(scored) // 2]
    print(f"[video {path}]  {len(scored)} sampled frames @ ~{fps:.0f}fps")
    print(f"    best  t={best[0]:5.1f}s  center lapvar={best[1]:8.1f}  -> {verdict(best[1])}")
    print(f"    median center lapvar={med:8.1f}  -> {verdict(med)}")
    print(f"    worst t={worst[0]:5.1f}s  center lapvar={worst[1]:8.1f}")
    print("    tip: the best frame = the distance/lighting where the nail is sharpest.")
    return best[1]


def selftest():
    """Synthetic check: sharp edge chart must outscore its blurred copy."""
    rng = np.zeros((480, 640), np.uint8)
    # high-frequency checker + text-like bars = plenty of edges
    rng[::8, :] = 255
    rng[:, ::8] = 255
    cv2.putText(rng, "NAIL 30cm", (60, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, 200, 3)
    sharp = focus_scores(rng)["lapvar"]
    blur = focus_scores(cv2.GaussianBlur(rng, (0, 0), 3))["lapvar"]
    print(f"selftest: sharp lapvar={sharp:.1f}  blurred lapvar={blur:.1f}")
    ok = sharp > blur * 3
    print("selftest:", "PASS" if ok else "FAIL", "(sharp must be >>  blurred)")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="*")
    ap.add_argument("--label", action="append", default=[])
    ap.add_argument("--video", help="grade a camera recording (mp4)")
    ap.add_argument("--every", type=int, default=10, help="sample every Nth video frame")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.video:
        analyze_video(a.video, a.every)
        return
    if not a.images:
        ap.print_help()
        sys.exit(2)
    labels = a.label + [None] * (len(a.images) - len(a.label))
    results = []
    for p, lb in zip(a.images, labels):
        v = analyze(p, lb)
        if v is not None:
            results.append((lb or p, v))
    if len(results) > 1:
        best = max(results, key=lambda r: r[1])
        print(f"\nBest focus: {best[0]} (center lapvar={best[1]:.1f})")


if __name__ == "__main__":
    main()
