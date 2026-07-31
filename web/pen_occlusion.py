"""펜/도구 가림방지 (occlusion) — 손톱 위에 놓인 펜을 검출해 디자인이 펜을 덮지 않게 한다.

문제: 파이프라인이 손톱→디자인 순으로 합성 → 손톱 위에 펜을 얹어도 디자인이 펜을 가려버림
     (사실은 손톱→펜→디자인이라 펜이 디자인을 가려야 자연스럽다).
목표: design_alpha = nail AND NOT pen  (펜이 지나는 손톱 픽셀은 디자인을 흐리게/투명하게).

방법(색-편차 기반, 도구 종류에 독립적):
  1) 손톱 코어(erode) 색의 중앙값(Lab)을 기준으로 각 픽셀의 편차 dev를 구한다.
  2) 스펙큘러 하이라이트(손톱보다 밝음, L↑)는 occluder 아님 → 가중치에서 제외.
  3) dev를 이진화 → 연결성분 분석: "크고(면적) + (길쭉 OR 손톱경계 밖으로 뻗음)" 성분만 펜으로 채택
     (하이라이트·무늬는 손톱 안 작은 성분이라 탈락).
  4) 채택 성분의 편차를 0..1 소프트 가중치로 만들어, 손톱 안쪽(경계 링 제외 erode)에만 적용.

색-편차 접근의 한계(docs/PEN_OCCLUSION_PROGRESS.md): 살색 연필 등 손톱과 색이 비슷한 도구는 약함.
실측(안경 사진/영상 187장)에서 검은 펜/금속 페룰 브러시는 확실히 검출·가림됨.

라이브 사용:
    from pen_occlusion import pen_soft_mask, apply_occlusion
    soft = pen_soft_mask(bgr, contours)          # contours: List[List[[x,y]]]
    out  = apply_occlusion(bgr, design_bgr, design_alpha, soft)
"""
from __future__ import annotations
import cv2
import numpy as np

# --- 튜닝 파라미터 (안경 실측 187장에서 확정) ---
DEV_LO, DEV_HI = 22.0, 60.0   # Lab 편차 정규화(약편차 무시~강편차 확실)
BIN_THR = 0.35                # 이진화 임계(정규화 편차)
MARGIN = 14                   # 손톱 밖 margin(px) — 펜이 경계 넘어오는지 보는 띠
MIN_AREA_FRAC = 0.04          # 손톱면적 대비 최소 성분 면적(이하=노이즈 버림)
ELONG_MIN = 2.2              # 길쭉함(장축/단축) 이상이면 펜으로 인정
MARGIN_FRAC = 0.12           # 성분이 margin(밖)에 이만큼 걸치면 '경계횡단=펜'
HL_TOL = 7.0                 # 손톱보다 이만큼 밝으면 하이라이트로 간주 시작
HL_RANGE = 20.0              # 이 밝기차 위는 완전 하이라이트(occluder 제외)
APP_ERODE = 5                # 디자인 가림 적용 전 손톱 erode(경계 링 오탐 제거)


def _fill(contour, h, w):
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [np.array(contour, np.int32).reshape(-1, 1, 2)], 255)
    return m


def contours_to_masks(contours, h, w):
    """검출 결과의 외곽선 리스트 → 손톱 이진 마스크 리스트."""
    return [_fill(c, h, w) for c in contours if c]


def pen_soft_mask(im_bgr, contours):
    """손톱 위 펜/도구를 검출한 0..1 소프트 가림 가중치(H,W float32) 반환.

    contours: 손톱 외곽선 리스트(List[List[[x,y]]]). 편차/연결성분으로 펜만 남긴다.
    """
    h, w = im_bgr.shape[:2]
    lab = cv2.cvtColor(im_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    soft = np.zeros((h, w), np.float32)
    k_app = np.ones((APP_ERODE, APP_ERODE), np.uint8)
    for m in contours_to_masks(contours, h, w):
        mb = m > 0
        if mb.sum() < 30:
            continue
        core = cv2.erode(m, np.ones((3, 3), np.uint8), iterations=1) > 0
        if core.sum() < 20:
            core = mb
        med = np.median(lab[core], axis=0)
        dev = np.linalg.norm(lab - med, axis=2)
        wn = np.clip((dev - DEV_LO) / (DEV_HI - DEV_LO), 0, 1)
        # 하이라이트 제외: 손톱보다 밝은(L↑) 스펙큘러는 occluder 아님. 펜은 어둡거나 색이 다름.
        dL = lab[:, :, 0] - med[0]
        hl = np.clip(1 - np.maximum(0, dL - HL_TOL) / HL_RANGE, 0.0, 1.0)
        wn = wn * hl
        # 손톱 + 밖 margin 띠
        dil = cv2.dilate(m, np.ones((2 * MARGIN + 1, 2 * MARGIN + 1), np.uint8)) > 0
        cand = ((wn > BIN_THR) & dil).astype(np.uint8)
        cand = cv2.morphologyEx(cand, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, lbl, stats, _ = cv2.connectedComponentsWithStats(cand, 8)
        nail_area = mb.sum()
        margin_only = dil & ~mb
        keep = np.zeros((h, w), np.uint8)
        for i in range(1, n):
            comp = lbl == i
            area = int(comp.sum())
            if area < MIN_AREA_FRAC * nail_area:
                continue
            ys, xs = np.where(comp)
            cov = np.cov(np.stack([xs, ys]).astype(np.float32))
            ev = np.linalg.eigvalsh(cov) if cov.shape == (2, 2) else np.array([1.0, 1.0])
            elong = (ev[-1] / max(ev[0], 1e-3)) ** 0.5
            crosses = (comp & margin_only).sum() / max(area, 1)
            if elong >= ELONG_MIN or crosses >= MARGIN_FRAC:
                keep |= comp.astype(np.uint8)
        app = cv2.erode(m, k_app, iterations=1) > 0     # 경계 링 제외 → 안쪽에만 가림
        soft[app] = np.maximum(soft[app], (wn * (keep > 0))[app])
    return cv2.GaussianBlur(soft, (0, 0), 1.2)


def apply_occlusion(im_bgr, design_bgr, design_alpha, soft, pen_dim=0.15):
    """디자인 합성 시 펜 가림 적용. design_alpha를 (1 - soft*(1-pen_dim))로 낮춰 펜이 비쳐 보이게.

    im_bgr: 배경(카메라). design_bgr: 디자인 색(H,W,3). design_alpha: 디자인 불투명도(H,W 0..1). soft: pen_soft_mask 결과.
    """
    a = design_alpha * (1.0 - soft * (1.0 - pen_dim))
    a3 = a[..., None]
    return np.clip(im_bgr.astype(np.float32) * (1 - a3) + design_bgr.astype(np.float32) * a3, 0, 255).astype(np.uint8)
