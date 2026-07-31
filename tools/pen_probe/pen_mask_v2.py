#!/usr/bin/env python3
"""펜 가림 v2 — 오탐 감소형 펜 마스크. (A단계 analyze_frames.py 개선)

기존(v1): 손톱면 색 대비 Lab 편차 → 소프트 penDim. 문제 = 하이라이트/가장자리 오탐 ~25%.
v2 개선: 편차맵을 이진화 → **연결성분** 분석으로 "펜다운" 영역만 남김:
  - 펜/브러시는 손톱 '경계를 가로질러 밖에서' 들어오는 크고 길쭉한 연결영역.
  - 하이라이트/무늬는 손톱 '안에 흩어진 작은' 성분.
  → (면적 큼) AND (경계 margin까지 뻗음 OR 길쭉함) 인 성분만 채택 → 오탐 급감.
그 위에 소프트 penDim(편차 비례 흐리기)로 자연스럽게.

사용: python tools/pen_probe/pen_mask_v2.py --frames samples/pen --out pen_out2
파라미터는 아래 상수 + CLI. 프레임에서 손톱이 YOLO로 검출돼야 함(min-nails).
"""
import argparse, glob, os, sys
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "web")); sys.path.insert(0, ROOT); os.chdir(ROOT)
import edge_serve as E  # noqa: E402
import pen_occlusion as PO  # noqa: E402  단일 소스: 라이브(web/pen_occlusion.py)와 동일 알고리즘

# --- 튜닝 파라미터 ---
DEV_LO, DEV_HI = 22.0, 60.0   # Lab 편차 정규화(약편차 무시~강편차 확실)
BIN_THR = 0.35                # 이진화 임계(정규화 편차)
MARGIN = 14                   # 손톱 밖 margin(px) — 펜이 경계 넘어오는지 보는 띠
MIN_AREA_FRAC = 0.04          # 손톱면적 대비 최소 성분 면적(이하=노이즈 버림)
ELONG_MIN = 2.2              # 길쭉함(장축/단축) 이상이면 펜으로 인정
MARGIN_FRAC = 0.12           # 성분이 margin(밖)에 이만큼 걸치면 '경계횡단=펜'
HL_TOL = 7.0                 # 손톱보다 이만큼 밝으면 하이라이트로 간주 시작
HL_RANGE = 20.0              # 이 밝기차 위는 완전 하이라이트(occluder 제외)
PEN_DIM = 0.15               # 완전가림시 남는 디자인 불투명도(작을수록 더 사라짐)
BASE_A = 0.85
COLS = [(210,90,230),(240,190,90),(110,210,130),(90,150,240)]


def nail_masks(im, nl):
    h, w = im.shape[:2]
    out = []
    for nd in nl:
        c = nd.get("contour")
        if not c: continue
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [np.array(c, np.int32).reshape(-1,1,2)], 255)
        out.append(m)
    return out


def pen_mask(im, nl):
    """오탐 감소 펜 마스크(0..1 소프트) + 진단 이진맵. 알고리즘은 web/pen_occlusion.py(단일 소스)."""
    contours = [nd.get("contour") for nd in nl if nd.get("contour")]
    soft = PO.pen_soft_mask(im, contours)
    hard = (soft > 0.05).astype(np.uint8)   # 시각화용(가림 적용되는 픽셀)
    return soft, hard


def sim(im, nl, soft):
    h, w = im.shape[:2]
    dcol = np.zeros((h, w, 3), np.float32); a_no = np.zeros((h, w), np.float32)
    for i, m in enumerate(nail_masks(im, nl)):
        mb = m > 0; dcol[mb] = COLS[i % len(COLS)]; a_no[mb] = BASE_A
    a_sd = a_no * (1 - soft * (1 - PEN_DIM))
    def comp(a):
        a3 = a[..., None]
        return np.clip(im.astype(np.float32)*(1-a3) + dcol*a3, 0, 255).astype(np.uint8)
    return comp(a_no), comp(a_sd)


def crop(img, nl, pad=60):
    xs = [p[0] for nd in nl for p in nd.get("contour", [])]; ys = [p[1] for nd in nl for p in nd.get("contour", [])]
    if not xs: return img
    h, w = img.shape[:2]
    return img[max(0,min(ys)-pad):min(h,max(ys)+pad), max(0,min(xs)-pad):min(w,max(xs)+pad)]


def lab_img(img, t):
    img = img.copy(); cv2.rectangle(img,(0,0),(img.shape[1],22),(0,0,0),-1)
    cv2.putText(img,t,(6,16),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,255,255),1); return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True); ap.add_argument("--out", default="pen_out2")
    ap.add_argument("--min-nails", type=int, default=1)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.frames, "*.jpg")) + glob.glob(os.path.join(a.frames, "*.png")))
    done = 0
    for f in files:
        im = cv2.imread(f)
        if im is None: continue
        nl = E._infer_yolo(im)
        if len(nl) < a.min_nails:
            print(f"skip {os.path.basename(f)}: nails={len(nl)}"); continue
        soft, hard = pen_mask(im, nl)
        heat = cv2.applyColorMap((soft*255).astype(np.uint8), cv2.COLORMAP_JET)
        penvis = im.copy(); penvis[hard>0] = (0,0,255)
        no, sd = sim(im, nl, soft)
        tiles = [lab_img(crop(im,nl),"raw"), lab_img(crop(penvis,nl),"pen-mask"),
                 lab_img(crop(heat,nl),"weight"), lab_img(crop(no,nl),"design(no-occ)"),
                 lab_img(crop(sd,nl),"design(penDim v2)")]
        H = 300
        tiles = [cv2.resize(t,(int(t.shape[1]*H/t.shape[0]),H)) for t in tiles]
        cv2.imwrite(os.path.join(a.out, os.path.basename(f)), cv2.hconcat(tiles))
        done += 1; print(f"ok {os.path.basename(f)} nails={len(nl)}")
    print(f"=== {done}장 처리 → {a.out} ===")


if __name__ == "__main__":
    main()
