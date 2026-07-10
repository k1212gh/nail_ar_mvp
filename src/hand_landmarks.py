"""손 랜드마크 + 손톱 ROI 추정 (MediaPipe HandLandmarker).

역할
----
- 프레임에서 손당 21개 랜드마크를 얻는다.
- 각 손가락의 TIP/DIP 랜드마크로 손톱이 있을 ROI(회전 사각형)를 추정한다.
- 주의: 랜드마크는 '관절 키포인트'이지 손톱 외곽이 아니다. 손톱 경계는
  세그멘테이션 모듈(nail_segmentation.py)이 ROI 안에서 따로 구한다.

설계
----
MediaPipe가 없거나 모델 파일이 없어도 import 자체는 실패하지 않는다.
HandLandmarker.create() 호출 시 안내 메시지와 함께 예외를 던진다.
"""
from __future__ import annotations

import math
import os
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .log_setup import get_logger

log = get_logger("hand")

# 손가락별 (TIP, DIP) 랜드마크 인덱스 — 엄지는 (TIP=4, IP=3)
FINGER_TIP_DIP = {
    "thumb":  (4, 3),
    "index":  (8, 7),
    "middle": (12, 11),
    "ring":   (16, 15),
    "pinky":  (20, 19),
}

# (MCP, PIP) per finger — used to tell an EXTENDED finger (nail visible) from a curled
# one (fist). A finger is "up" when its TIP is farther from the wrist than its PIP.
FINGER_MCP_PIP = {
    "thumb":  (2, 3),
    "index":  (5, 6),
    "middle": (9, 10),
    "ring":   (13, 14),
    "pinky":  (17, 18),
}

_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
              "hand_landmarker/float16/1/hand_landmarker.task")


@dataclass
class NailROI:
    """손톱 후보 영역(회전 사각형)."""
    finger: str
    handedness: str          # "Left"/"Right"
    center: tuple            # (x, y) px
    axis: tuple              # 손톱 세로 방향 단위벡터 (TIP 방향)
    size: float              # ROI 한 변(px)
    tip_xy: tuple
    dip_xy: tuple
    facing: float = 0.0      # >0 이면 손등(손톱)이 카메라를 향함 / <0 이면 손바닥
    dist_m: float = 0.0      # 카메라~손 절대거리(m). World Landmarks + 핀홀로 추정(0=미상)
    extended: float = 1.0    # 1이면 손가락 폄(손톱 보임) / 0이면 굽힘(주먹)

    def to_box_points(self) -> np.ndarray:
        """회전 사각형의 네 꼭짓점(px). 크롭/마스킹에 사용."""
        cx, cy = self.center
        ax, ay = self.axis
        px, py = -ay, ax  # 직교축
        h = self.size / 2.0
        pts = [
            (cx + ax * h + px * h, cy + ay * h + py * h),
            (cx + ax * h - px * h, cy + ay * h - py * h),
            (cx - ax * h - px * h, cy - ay * h - py * h),
            (cx - ax * h + px * h, cy - ay * h + py * h),
        ]
        return np.array(pts, dtype=np.float32)


def ensure_model(model_path: str) -> str:
    """모델 파일이 없으면 다운로드 시도. 실패 시 경로만 반환(이후 호출에서 처리)."""
    if os.path.isfile(model_path):
        return model_path
    os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
    try:
        log.info("손 모델 다운로드 중... %s", model_path)
        urllib.request.urlretrieve(_MODEL_URL, model_path)
        log.info("손 모델 다운로드 완료")
    except Exception as e:  # noqa: BLE001
        log.error("손 모델 자동 다운로드 실패(%s). 수동으로 받아 두세요: %s", e, _MODEL_URL)
    return model_path


class HandLandmarkDetector:
    def __init__(self, cfg):
        self.cfg = cfg
        self._landmarker = None
        self._mp = None
        self._frame_idx = 0

    def _lazy_init(self):
        if self._landmarker is not None:
            return
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
        except ImportError as e:  # noqa: BLE001
            raise RuntimeError(
                "mediapipe가 필요합니다. `pip install mediapipe` 후 다시 실행하세요."
            ) from e

        model_path = ensure_model(self.cfg.model_path)
        if not os.path.isfile(model_path):
            raise RuntimeError(
                f"손 랜드마크 모델이 없습니다: {model_path}\n  다운로드: {_MODEL_URL}")

        base = mp_python.BaseOptions(model_asset_path=model_path)
        options = mp_vision.HandLandmarkerOptions(
            base_options=base,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=self.cfg.max_hands,
            min_hand_detection_confidence=self.cfg.min_detection_confidence,
            min_hand_presence_confidence=self.cfg.min_presence_confidence,
            min_tracking_confidence=self.cfg.min_tracking_confidence,
        )
        self._mp = mp
        self._vision = mp_vision
        self._landmarker = mp_vision.HandLandmarker.create_from_options(options)

    def detect(self, frame_bgr, timestamp_ms: Optional[int] = None) -> List[NailROI]:
        """프레임 → 손톱 ROI 리스트."""
        self._lazy_init()
        import cv2
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        if timestamp_ms is None:
            timestamp_ms = int(self._frame_idx * (1000.0 / max(1, self.cfg_fps())))
        self._frame_idx += 1

        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)
        rois: List[NailROI] = []
        if not result.hand_landmarks:
            return rois

        # focal length (px) for the pinhole distance model; ~horizontal-FOV based.
        focal_px = self.cfg.focal_ratio * w

        for i, lms in enumerate(result.hand_landmarks):
            handed = "Unknown"
            if result.handedness and i < len(result.handedness):
                handed = result.handedness[i][0].category_name

            # palm/back facing: 2D winding of (wrist -> index_MCP, wrist -> pinky_MCP).
            # Sign flips with handedness; >0 => back of hand (nails) toward camera.
            wl, im5, pm17 = lms[0], lms[5], lms[17]
            cross_z = ((im5.x - wl.x) * (pm17.y - wl.y)
                       - (im5.y - wl.y) * (pm17.x - wl.x))
            facing = cross_z if handed == "Right" else -cross_z

            # absolute camera->hand distance via MediaPipe metric World Landmarks + pinhole:
            # dist = focal_px * metric_span(m) / pixel_span(px). Use index_MCP<->pinky_MCP
            # (cross-hand span barely foreshortens when nails face the camera).
            dist_m = 0.0
            if result.hand_world_landmarks and i < len(result.hand_world_landmarks):
                W = result.hand_world_landmarks[i]
                mdx, mdy, mdz = W[5].x - W[17].x, W[5].y - W[17].y, W[5].z - W[17].z
                metric = math.sqrt(mdx * mdx + mdy * mdy + mdz * mdz)
                pdx = (im5.x - pm17.x) * w
                pdy = (im5.y - pm17.y) * h
                pixel = math.hypot(pdx, pdy)
                if pixel > 1e-3 and metric > 1e-4:
                    dist_m = focal_px * metric / pixel

            for finger, (tip_i, dip_i) in FINGER_TIP_DIP.items():
                tip = lms[tip_i]
                dip = lms[dip_i]
                tx, ty = tip.x * w, tip.y * h
                dx, dy = dip.x * w, dip.y * h
                vx, vy = tx - dx, ty - dy
                length = math.hypot(vx, vy)
                if length < 1e-3:
                    continue
                ax, ay = vx / length, vy / length  # DIP→TIP = 손톱 세로 방향
                # 손톱 중심은 DIP와 TIP 사이 끝쪽(약 65%)
                cx = dx + vx * 0.65
                cy = dy + vy * 0.65
                size = max(self.cfg.roi_min_px, length * self.cfg.roi_scale)
                # extended? PIP 관절 각도(3D): MCP-PIP-TIP가 펴지면 ~180°, 굽히면 작아짐.
                # (시점 무관 — ModiFace/연구 권장. 엄지는 MCP=2,IP=3,TIP=4로 자동 처리)
                mcp_i, pip_i = FINGER_MCP_PIP[finger]
                mj, pjj = lms[mcp_i], lms[pip_i]
                ux, uy, uz = mj.x - pjj.x, mj.y - pjj.y, mj.z - pjj.z   # PIP->MCP
                wx, wy, wz = tip.x - pjj.x, tip.y - pjj.y, tip.z - pjj.z  # PIP->TIP
                nu = math.sqrt(ux*ux + uy*uy + uz*uz)
                nw = math.sqrt(wx*wx + wy*wy + wz*wz)
                cosang = (ux*wx + uy*wy + uz*wz) / (nu * nw + 1e-9)
                ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
                extended = 1.0 if ang > 150.0 else 0.0
                rois.append(NailROI(
                    finger=finger, handedness=handed,
                    center=(cx, cy), axis=(ax, ay), size=float(size),
                    tip_xy=(tx, ty), dip_xy=(dx, dy),
                    facing=float(facing), dist_m=float(dist_m), extended=extended))
        return rois

    def cfg_fps(self) -> float:
        return 30.0

    def close(self):
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
