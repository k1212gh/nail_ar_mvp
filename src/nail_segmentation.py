"""손톱 세그멘테이션 — ROI 안에서 손톱 외곽 마스크를 구한다.

모듈형 전략(계획서 A-2, A-4 반영)
--------------------------------
- 'grabcut'  : 학습 데이터 없이 즉시 동작. ROI 중앙을 전경 시드로 GrabCut.  (기본)
- 'color'    : HSV 임계 기반(매니큐어 등 색이 뚜렷할 때 빠름).
- 'external' : SAM2/MobileSAM/YOLO11-seg 등 외부 모델을 끼우는 자리.
               set_external(fn) 으로 콜러블을 주입하면 그 함수가 마스크를 만든다.

세 방식 모두 동일한 인터페이스 segment(frame, roi) -> mask(uint8 0/255, 전체 프레임 크기)
를 반환하므로, 데이터가 쌓여 커스텀 모델로 교체할 때 호출부는 바뀌지 않는다.
"""
from __future__ import annotations

from typing import Callable, Optional

import cv2
import numpy as np


class NailSegmenter:
    def __init__(self, cfg):
        self.cfg = cfg
        self._external: Optional[Callable] = None

    def set_external(self, fn: Callable[[np.ndarray, object], np.ndarray]) -> None:
        """SAM/YOLO 등 외부 분할기 주입. fn(roi_crop_bgr, roi) -> mask_crop(uint8)."""
        self._external = fn

    # --- public ---------------------------------------------------------
    def segment(self, frame_bgr: np.ndarray, roi) -> Optional[np.ndarray]:
        crop, (x0, y0, cw, ch), M = self._extract_roi(frame_bgr, roi)
        if crop is None:
            return None

        if self.cfg.method == "external" and self._external is not None:
            mask_crop = self._external(crop, roi)
        elif self.cfg.method == "color":
            mask_crop = self._segment_color(crop)
        else:
            mask_crop = self._segment_grabcut(crop)

        if mask_crop is None or int(mask_crop.sum() // 255) < self.cfg.min_mask_area:
            return None

        # ROI 크롭 마스크를 전체 프레임 좌표로 되돌린다.
        full = np.zeros(frame_bgr.shape[:2], dtype=np.uint8)
        full[y0:y0 + ch, x0:x0 + cw] = mask_crop
        return full

    # --- ROI 추출 -------------------------------------------------------
    def _extract_roi(self, frame, roi):
        h, w = frame.shape[:2]
        box = roi.to_box_points()
        xs, ys = box[:, 0], box[:, 1]
        x0, y0 = int(max(0, xs.min())), int(max(0, ys.min()))
        x1, y1 = int(min(w, xs.max())), int(min(h, ys.max()))
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None, (0, 0, 0, 0), None
        crop = frame[y0:y1, x0:x1].copy()
        return crop, (x0, y0, x1 - x0, y1 - y0), None

    # --- 방식별 구현 ----------------------------------------------------
    def _segment_grabcut(self, crop):
        # 속도: 큰 크롭은 축소해서 grabcut 후 마스크를 원배율로 복원(품질 손실 미미)
        full_h, full_w = crop.shape[:2]
        max_side = getattr(self.cfg, "grabcut_max_side", 0)
        scaled = False
        if max_side and max(full_h, full_w) > max_side:
            s = max_side / float(max(full_h, full_w))
            crop = cv2.resize(crop, (max(2, int(full_w * s)), max(2, int(full_h * s))),
                              interpolation=cv2.INTER_AREA)
            scaled = True

        ch, cw = crop.shape[:2]
        mask = np.full((ch, cw), cv2.GC_PR_BGD, np.uint8)
        # 중앙 타원을 '확실한 전경' 시드로
        cx, cy = cw // 2, ch // 2
        ax, ay = max(2, cw // 3), max(2, ch // 3)
        cv2.ellipse(mask, (cx, cy), (ax, ay), 0, 0, 360, cv2.GC_FGD, -1)
        cv2.ellipse(mask, (cx, cy), (int(ax * 1.4), int(ay * 1.4)), 0, 0, 360,
                    cv2.GC_PR_FGD, -1)
        # 가장자리는 확실한 배경
        mask[:2, :] = cv2.GC_BGD
        mask[-2:, :] = cv2.GC_BGD
        mask[:, :2] = cv2.GC_BGD
        mask[:, -2:] = cv2.GC_BGD
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        try:
            cv2.grabCut(crop, mask, None, bgd, fgd,
                        self.cfg.grabcut_iters, cv2.GC_INIT_WITH_MASK)
        except cv2.error:
            return None
        out = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
        if scaled:
            out = cv2.resize(out, (full_w, full_h), interpolation=cv2.INTER_NEAREST)
        return self._cleanup(out)

    def _segment_color(self, crop):
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        lo = np.array(self.cfg.color_lower, np.uint8)
        hi = np.array(self.cfg.color_upper, np.uint8)
        mask = cv2.inRange(hsv, lo, hi)
        return self._cleanup(mask)

    def _cleanup(self, mask):
        """노이즈 제거 + 가장 큰 연결요소만 남김."""
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return mask
        biggest = max(cnts, key=cv2.contourArea)
        clean = np.zeros_like(mask)
        cv2.drawContours(clean, [biggest], -1, 255, -1)
        return clean
