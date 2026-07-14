"""추적·정합 — 칼만 필터로 손톱 중심점을 안정화 (계획서 D).

MVP 단계 구현
-------------
- 손가락별 칼만 필터(상수속도 모델)로 center를 평활화해 떨림을 줄인다.
- 검출이 비는 프레임(가림 등)에는 예측값으로 위치를 유지한다.
- 무거운 매 프레임 재검출 대신, 메인 루프가 redetect_every 주기로만 전체
  검출을 돌리고 사이 프레임은 예측으로 메운다(광류 자리에 칼만 예측 사용).

확장 지점
---------
KLT 광류를 쓰려면 update_with_flow(prev_gray, cur_gray, pts)를 추가해
측정값(center)을 광류 추적 결과로 대체하면 된다. 인터페이스는 동일하다.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import cv2
import numpy as np


class _CenterKalman:
    """[x, y, vx, vy] 상태의 상수속도 칼만 필터."""

    def __init__(self, x, y, q=1e-2, r=1e-1):
        kf = cv2.KalmanFilter(4, 2)
        kf.transitionMatrix = np.array([[1, 0, 1, 0],
                                        [0, 1, 0, 1],
                                        [0, 0, 1, 0],
                                        [0, 0, 0, 1]], np.float32)
        kf.measurementMatrix = np.array([[1, 0, 0, 0],
                                         [0, 1, 0, 0]], np.float32)
        kf.processNoiseCov = np.eye(4, dtype=np.float32) * q
        kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * r
        kf.errorCovPost = np.eye(4, dtype=np.float32)
        kf.statePost = np.array([[x], [y], [0], [0]], np.float32)
        self.kf = kf
        self.misses = 0

    def predict(self) -> Tuple[float, float]:
        p = self.kf.predict()
        return float(p[0, 0]), float(p[1, 0])   # (4,1) 배열 → 0-d 스칼라 인덱싱 (numpy>=2 호환)

    def correct(self, x, y) -> Tuple[float, float]:
        m = np.array([[np.float32(x)], [np.float32(y)]])
        c = self.kf.correct(m)
        self.misses = 0
        return float(c[0, 0]), float(c[1, 0])   # numpy>=2: float(1-원소 배열) 금지 → [i,0]

    def speed(self) -> float:
        """현재 추정 속도 크기(px/frame). 렌더 게이팅(손 정지 판정)에 사용."""
        s = self.kf.statePost
        return float(np.hypot(s[2, 0], s[3, 0]))


class NailTracker:
    """손가락 키(handedness+finger)별로 중심점을 추적·평활화."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._filters: Dict[str, _CenterKalman] = {}
        self.max_misses = max(2, cfg.redetect_every * 2)

    @staticmethod
    def _key(geom) -> str:
        return f"{geom.handedness}:{geom.finger}"

    def smooth(self, geom) -> tuple:
        """측정된 geom.center를 칼만으로 평활화한 (x, y) 반환."""
        key = self._key(geom)
        cx, cy = geom.center
        if key not in self._filters:
            self._filters[key] = _CenterKalman(
                cx, cy, self.cfg.kalman_process_noise, self.cfg.kalman_measure_noise)
            return cx, cy
        kf = self._filters[key]
        kf.predict()
        return kf.correct(cx, cy)

    def speed(self, geom) -> float:
        """가장 최근 평활화 후 이 손가락의 칼만 속도 크기(px/frame). 필터 없으면 0."""
        kf = self._filters.get(self._key(geom))
        return kf.speed() if kf is not None else 0.0

    def predict_missing(self, seen_keys) -> Dict[str, tuple]:
        """이번 프레임에 검출 안 된 손가락은 예측으로 위치 유지.
        반환: {key: (x, y)} — 오버레이가 흐리게 표시할 수 있음."""
        ghosts = {}
        for key, kf in list(self._filters.items()):
            if key in seen_keys:
                continue
            kf.misses += 1
            if kf.misses > self.max_misses:
                del self._filters[key]
                continue
            ghosts[key] = kf.predict()
        return ghosts
