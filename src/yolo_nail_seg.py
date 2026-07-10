"""YOLO 손톱 인스턴스 세그 — 실제 손톱을 인식해 마스크를 만든다(--seg yolo).

기존 `NailSegmenter.set_external(fn)` 후킹에 그대로 끼운다: fn(crop_bgr, roi) -> mask_crop.
MediaPipe ROI(손톱 위치)로 잘라낸 크롭 안에서 YOLO가 손톱을 분할하므로,
입력이 작아 빠르고, 파이프라인(ROI·캐시·추적·기하·디자인 클리핑)은 한 줄도 안 바뀐다.

모델: HuggingFace mnemic/nails_seg_yolov8 (YOLOv8-s, nails, CC-BY-4.0) 또는 직접 학습한 yolo11-seg.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from .log_setup import get_logger

log = get_logger("yolo")


class YoloNailSegmenter:
    def __init__(self, model_path: str, conf: float = 0.35, imgsz: int = 256,
                 device: Optional[str] = None):
        from ultralytics import YOLO  # 무거우므로 지연 import
        self.model = YOLO(model_path)
        self.conf = conf
        self.imgsz = imgsz
        if device is None:
            try:
                import torch
                device = "cuda:0" if torch.cuda.is_available() else "cpu"
            except Exception:  # noqa: BLE001
                device = "cpu"
        self.device = device
        log.info("YOLO 손톱 모델 로드: %s (device=%s, imgsz=%d)", model_path, device, imgsz)

    def detect_full(self, frame_bgr: np.ndarray) -> list:
        """전체 프레임에서 손톱 마스크 목록 반환(각 전체프레임 크기 uint8 0/255).

        모델이 전체 손 이미지로 학습돼 있어 전체프레임 1회 추론이 가장 정확·빠르다.
        """
        h, w = frame_bgr.shape[:2]
        res = self.model.predict(frame_bgr, conf=self.conf, imgsz=self.imgsz,
                                 device=self.device, verbose=False)
        r = res[0]
        out = []
        if r.masks is None:
            return out
        for m in r.masks.data.cpu().numpy():        # [N, mh, mw], 0~1
            mm = cv2.resize((m * 255).astype(np.uint8), (w, h),
                            interpolation=cv2.INTER_NEAREST)
            if int((mm > 0).sum()) >= 20:
                out.append(mm)
        return out

    def segment_crop(self, crop_bgr: np.ndarray, roi) -> Optional[np.ndarray]:
        """ROI 크롭에서 손톱 마스크(크롭 크기 uint8 0/255) 반환. 없으면 None."""
        h, w = crop_bgr.shape[:2]
        if h < 8 or w < 8:
            return None
        res = self.model.predict(crop_bgr, conf=self.conf, imgsz=self.imgsz,
                                 device=self.device, verbose=False)
        r = res[0]
        if r.masks is None or len(r.masks.data) == 0:
            return None
        # 크롭 중앙(=손톱) 기준으로 가장 큰 마스크 선택
        best, best_area = None, -1
        for m in r.masks.data.cpu().numpy():        # [N, mh, mw], 0~1
            mm = cv2.resize((m * 255).astype(np.uint8), (w, h),
                            interpolation=cv2.INTER_NEAREST)
            area = int((mm > 0).sum())
            if area > best_area:
                best_area, best = area, mm
        return best
