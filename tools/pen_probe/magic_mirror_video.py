#!/usr/bin/env python3
"""매직미러 before/after 영상 — 디자인이 펜을 '덮는' 것 vs 펜에서 '투명해지는(가림)' 것 비교.

샘플 프레임(hand+nail+pen)마다 [가림 없음 | 가림 적용] 나란히 렌더 → mp4. 펜 가림이 실제로 무엇을
하는지 한눈에 보이는 증명 영상. web/magic_mirror.py + pen_occlusion.py 사용.

  python tools/pen_probe/magic_mirror_video.py --frames samples/pen --out mirror.mp4 --fps 12
"""
import argparse, glob, os, sys, subprocess
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "web")); sys.path.insert(0, ROOT); os.chdir(ROOT)
import edge_serve as E  # noqa: E402
import magic_mirror as MM  # noqa: E402

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
H = 480  # 출력 패널 높이


def label(img, txt, color):
    cv2.rectangle(img, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
    cv2.putText(img, txt, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", default="mirror.mp4")
    ap.add_argument("--fps", type=float, default=12)
    ap.add_argument("--every", type=int, default=1)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.frames, "vf_*.jpg")) or glob.glob(os.path.join(a.frames, "*.jpg")))[::a.every]
    tmp = os.path.join(os.path.dirname(a.out) or ".", "_mm_frames")
    os.makedirs(tmp, exist_ok=True)
    n = 0
    for f in files:
        im = cv2.imread(f)
        if im is None:
            continue
        nails = E._infer_yolo(im)
        left = MM.render(im, nails, occlude=False)    # 디자인이 펜을 덮음
        right = MM.render(im, nails, occlude=True)     # 펜에서 디자인 투명(가림)
        def fit(x):
            return cv2.resize(x, (int(x.shape[1] * H / x.shape[0]), H))
        left, right = fit(left), fit(right)
        label(left, "occlusion OFF (design covers pen)", (60, 60, 255))
        label(right, "occlusion ON (pen shows through)", (120, 235, 120))
        sep = np.full((H, 4, 3), (255, 255, 255), np.uint8)
        frame = cv2.hconcat([left, sep, right])
        cv2.imwrite(os.path.join(tmp, f"{n:04d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        n += 1
        if n % 20 == 0:
            print(f"  {n} frames... (nails={len(nails)})", flush=True)
    print(f"렌더 {n}장 → mp4 인코딩")
    # ffmpeg로 mp4(H.264)
    cmd = [FFMPEG, "-y", "-framerate", str(a.fps), "-i", os.path.join(tmp, "%04d.jpg"),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", a.out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(f"ffmpeg rc={r.returncode}", (r.stderr[-200:] if r.returncode else f"→ {a.out}"))


if __name__ == "__main__":
    main()
