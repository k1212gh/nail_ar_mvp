"""파이프라인 오케스트레이션 — 입력 소스와 무관하게 프레임을 처리한다.

흐름: frame → 손 랜드마크/ROI → 손톱 세그 → 기하 산출 → 칼만 평활 → 오버레이
입력이 폰이든 글래스든 process(frame) 시그니처는 동일하다.
"""
from __future__ import annotations

import time
from typing import List

from . import design_overlay, overlay
from .geometry import compute_geometry, geometry_from_roi
from .hand_landmarks import HandLandmarkDetector
from .log_setup import get_logger
from .nail_segmentation import NailSegmenter
from .tracking import NailTracker

log = get_logger("pipeline")


class NailARPipeline:
    def __init__(self, cfg):
        self.cfg = cfg
        self.detector = HandLandmarkDetector(cfg.hand)
        self.segmenter = NailSegmenter(cfg.seg)
        self.tracker = NailTracker(cfg.track)
        # YOLO 손톱 인식(--seg yolo): 전체프레임에서 실제 손톱을 직접 검출
        self._yolo = None
        if cfg.seg.method == "yolo":
            from .yolo_nail_seg import YoloNailSegmenter
            self._yolo = YoloNailSegmenter(cfg.seg.nail_model, conf=cfg.seg.yolo_conf,
                                           imgsz=cfg.seg.yolo_imgsz)
        # 디자인 엔진(A3: IR + atlas + WarpSpec 워핑) 1회 로드. design_overlay 대체.
        self._design_engine = None
        if getattr(cfg, "design", None) and cfg.design.image_path:
            from .design_render import DesignEngine
            eng = DesignEngine(cfg.design)
            if not eng.ok():
                log.warning("디자인을 열 수 없음: %s", cfg.design.image_path)
            else:
                self._design_engine = eng
                log.info("디자인 엔진 로드(IR/atlas): %s", cfg.design.image_path)
        self._frame_no = 0
        self._last_rois: List = []
        # 검출 주기 사이 재사용하는 캐시: [(roi, mask, geom)]
        self._cache: List = []
        # 이번 프레임에 검출·평활된 손톱 결과(계측용). [{key, center, angle, length, area}]
        self.last_results: List[dict] = []
        # 직전 프레임 단계별 소요(ms) — main이 주기적으로 로깅해 병목 진단
        self.last_timing: dict = {}

    def process(self, frame, timestamp_ms=None, source_label="", fps=0.0):
        """프레임 1장 처리 후, 오버레이가 그려진 프레임을 반환."""
        self._frame_no += 1
        cfg = self.cfg
        self.last_results = []
        t = {"detect": 0.0, "seg": 0.0, "geom": 0.0, "overlay": 0.0}

        # === YOLO 손톱 인식: 전체프레임에서 직접 검출(매 프레임, MediaPipe 불필요) ===
        if self._yolo is not None:
            t0 = time.perf_counter()
            masks = self._yolo.detect_full(frame)
            t["seg"] = (time.perf_counter() - t0) * 1000.0
            t0 = time.perf_counter()
            cache = []
            for mask in masks:
                geom = compute_geometry(mask, None, cfg.geom)
                if geom is not None:
                    cache.append((None, mask, geom))
            t["geom"] = (time.perf_counter() - t0) * 1000.0
            self._cache = cache
            self._last_rois = []
            return self._draw(frame, t, fps, source_label)

        # --- 무거운 단계(검출+세그+기하)는 재검출 주기에만 수행하고 사이엔 캐시 재사용 ---
        # ROI가 주기 내내 동일하므로 매 프레임 grabcut을 돌리는 건 낭비였다(병목).
        refresh = (self._frame_no % max(1, cfg.track.redetect_every) == 1) or not self._cache
        if refresh:
            t0 = time.perf_counter()
            self._last_rois = self.detector.detect(frame, timestamp_ms)
            t["detect"] = (time.perf_counter() - t0) * 1000.0

            cache = []
            for roi in self._last_rois:
                if cfg.seg.method == "none":
                    # 세그 없이 랜드마크로만 배치(맨손톱에 안정적·빠름)
                    t0 = time.perf_counter()
                    geom = geometry_from_roi(roi)
                    t["geom"] += (time.perf_counter() - t0) * 1000.0
                    cache.append((roi, None, geom))
                    continue
                t0 = time.perf_counter()
                mask = self.segmenter.segment(frame, roi)
                t["seg"] += (time.perf_counter() - t0) * 1000.0
                if mask is None:
                    continue
                t0 = time.perf_counter()
                geom = compute_geometry(mask, roi, cfg.geom)
                t["geom"] += (time.perf_counter() - t0) * 1000.0
                if geom is None:
                    continue
                cache.append((roi, mask, geom))
            self._cache = cache

        return self._draw(frame, t, fps, source_label)

    def _draw(self, frame, t, fps, source_label):
        """캐시(roi, mask, geom)를 프레임에 그린다. roi=None 은 YOLO 인스턴스."""
        cfg = self.cfg
        seen_keys = set()
        t0 = time.perf_counter()
        for roi, mask, geom in self._cache:
            if cfg.show_roi and roi is not None:
                overlay.draw_roi(frame, roi)
            if cfg.show_mask and mask is not None:
                overlay.draw_mask(frame, mask)
            if roi is not None:
                sc = self.tracker.smooth(geom)
                key = self.tracker._key(geom)
                seen_keys.add(key)
            else:
                sc = geom.center            # YOLO: 매 프레임 직접 검출이라 추적 불필요
                key = None
            self.last_results.append({
                "key": key, "center": sc, "angle": geom.angle_deg,
                "length": geom.length,
                "area": int((mask > 0).sum()) if mask is not None else 0,
            })
            overlay.draw_geometry(frame, geom, sc, cfg)
            # 디자인 합성 — A3 엔진(IR/atlas/WarpSpec). YOLO면 실제 손톱 마스크로 클리핑.
            if self._design_engine is not None and cfg.show_design:
                self._design_engine.render(frame, geom, mask, sc, key=key, fps=fps)
        t["overlay"] += (time.perf_counter() - t0) * 1000.0

        # 가림 등으로 안 보인 손톱은 예측 위치를 흐리게 표시(추적 모드만)
        for _, xy in self.tracker.predict_missing(seen_keys).items():
            overlay.draw_ghost(frame, xy)

        overlay.draw_landmarks(frame, self._last_rois, cfg)
        n = len(self.last_results)
        overlay.draw_hud(frame, fps, n, source_label, cfg.seg.method)
        t["nails"] = n
        self.last_timing = t
        return frame

    def close(self):
        self.detector.close()
