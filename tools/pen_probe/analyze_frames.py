#!/usr/bin/env python3
"""펜 가림(occlusion) A단계 오프라인 분석 — 수집한 프레임에 도구-무관 가림검출 + 소프트 penDim 시뮬.

브러시가 오면 이 스크립트만 새 프레임 폴더로 다시 돌리면 된다(코드 수정 불필요).

수집:  web/edge_serve.py 를 DUMP_DIR=<폴더> 로 켜고 실행 → 손+도구를 카메라 앞에 대면 원본 프레임이 쌓인다.
분석:  python tools/pen_probe/analyze_frames.py --frames <폴더> --out <출력폴더>

접근: "도구를 검출"하지 않는다. 손톱 컨투어 안에서 '손톱면 색(중앙값)'과 Lab 거리가 큰 픽셀 = 뭔가 덮은 곳.
      편차에 비례해 디자인 알파를 낮추면(soft penDim) 하이라이트 노이즈는 무시되고 도구만 흐려진다.
결론(2026-07): 살구색 연필은 편차가 중간이라 효과 미묘. 금속 페룰/검정 털의 실제 브러시는 편차가 커서 잘 먹힐 것.
"""
import argparse
import glob
import os
import sys

import cv2
import numpy as np

# edge_serve 의 YOLO 손톱 세그(_infer_yolo)를 그대로 재사용
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "web"))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import edge_serve as E  # noqa: E402

LO, HI = 26.0, 60.0          # Lab 편차 → 가림가중치 정규화(LO 아래=손톱/하이라이트 무시, HI 위=확실히 가림)
PEN_DIM = 0.18               # 완전가림 시 남는 디자인 불투명도(작을수록 더 사라짐)
BASE_A = 0.85                # 평소 디자인 불투명도
COLS = [(210, 90, 230), (240, 190, 90), (110, 210, 130), (90, 150, 240)]  # BGR 데모 디자인색


def occluder_weight(im, nl):
    """손톱별로 '손톱면 색과의 Lab 편차'를 0..1 가림가중치로. (occ_weight, nail_mask) 반환."""
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
    h, w = im.shape[:2]
    wocc = np.zeros((h, w), np.float32)
    naily = np.zeros((h, w), bool)
    for nd in nl:
        cont = nd.get("contour")
        if not cont:
            continue
        poly = np.array(cont, np.int32).reshape(-1, 1, 2)
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [poly], 255)
        mb = m > 0
        core = cv2.erode(m, np.ones((3, 3), np.uint8)) > 0
        if core.sum() < 20:
            core = mb
        med = np.median(lab[core], axis=0)
        dev = np.linalg.norm(lab - med, axis=2)
        wp = np.clip((dev - LO) / (HI - LO), 0, 1)
        wocc[mb] = wp[mb]
        naily |= mb
    return wocc, naily


def render_sim(im, nl, wocc):
    """가짜 디자인을 손톱에 얹어 (가림처리 없음, 소프트 penDim) 두 합성을 만든다."""
    h, w = im.shape[:2]
    dcol = np.zeros((h, w, 3), np.float32)
    a_no = np.zeros((h, w), np.float32)
    for i, nd in enumerate(nl):
        cont = nd.get("contour")
        if not cont:
            continue
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [np.array(cont, np.int32).reshape(-1, 1, 2)], 255)
        mb = m > 0
        dcol[mb] = COLS[i % len(COLS)]
        a_no[mb] = BASE_A
    a_sd = cv2.GaussianBlur(a_no * (1 - wocc * (1 - PEN_DIM)), (0, 0), 1.0)

    def comp(a):
        a3 = a[..., None]
        return np.clip(im.astype(np.float32) * (1 - a3) + dcol * a3, 0, 255).astype(np.uint8)
    return comp(a_no), comp(a_sd)


def crop_hand(img, nl, pad=70):
    xs = [p[0] for nd in nl for p in nd.get("contour", [])]
    ys = [p[1] for nd in nl for p in nd.get("contour", [])]
    if not xs:
        return img
    h, w = img.shape[:2]
    return img[max(0, min(ys) - pad):min(h, max(ys) + pad),
              max(0, min(xs) - pad):min(w, max(xs) + pad)]


def label(img, txt):
    img = img.copy()
    cv2.rectangle(img, (0, 0), (img.shape[1], 24), (0, 0, 0), -1)
    cv2.putText(img, txt, (7, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True, help="원본 프레임(jpg) 폴더")
    ap.add_argument("--out", default="pen_out", help="출력 폴더")
    ap.add_argument("--min-nails", type=int, default=2, help="이 개수 이상 검출된 프레임만 처리")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    files = sorted(glob.glob(os.path.join(a.frames, "*.jpg")))
    stats = []
    for f in files:
        im = cv2.imread(f)
        if im is None:
            continue
        nl = E._infer_yolo(im)
        if len(nl) < a.min_nails:
            continue
        wocc, naily = occluder_weight(im, nl)
        b_no, b_sd = render_sim(im, nl, wocc)
        c_no, c_sd = crop_hand(b_no, nl), crop_hand(b_sd, nl)
        sc = max(1, int(360 / max(1, c_no.shape[0])))
        c_no = cv2.resize(c_no, None, fx=sc, fy=sc, interpolation=cv2.INTER_NEAREST)
        c_sd = cv2.resize(c_sd, None, fx=sc, fy=sc, interpolation=cv2.INTER_NEAREST)
        sep = np.full((c_no.shape[0], 6, 3), 255, np.uint8)
        pair = np.hstack([label(c_no, "1) NO occlusion"), sep, label(c_sd, "2) soft penDim")])
        cv2.imwrite(os.path.join(a.out, "sim_" + os.path.basename(f)), pair)
        occ_frac = (wocc[naily] > 0.5).sum() / max(1, naily.sum())
        stats.append((os.path.basename(f), len(nl), occ_frac))

    stats.sort(key=lambda x: -x[2])
    print(f"처리 {len(stats)}프레임 (가림비율 상위):")
    for name, n, fr in stats[:12]:
        print(f"  {name}  nails={n}  occ={fr*100:.0f}%")
    print(f"출력: {os.path.abspath(a.out)}")


if __name__ == "__main__":
    main()
