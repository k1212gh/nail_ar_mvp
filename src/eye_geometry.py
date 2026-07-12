"""외부캠 복합 자동정합 — 기하 코어 (순수 수학, 하드웨어 비의존 / 단위테스트 가능).

목표: 외부 카메라(노트북 웹캠/폰)가 사용자 얼굴을 봐서 **눈(동공) 3D 위치**를 측정하고,
그 눈과 **안경 월드카메라** 사이의 baseline b 로부터, 안경 앱의 깊이적응 시차모델
    offset(d) = A + B/d           (NailMeshRenderer, 런타임 pAx/pAy/pBx/pBy)
에 넣을 (A, B)를 계산한다. 이렇게 하면 손 깊이 d 가 변해도 앱이 프레임마다 자동 정합한다.

[왜 이게 X3의 아이트래킹 부재를 대체하나]
- 근거리 OST 시차오차 ‖E‖ ≈ O′·|p_z/d_focal − 1| 의 미지수는 '눈 위치 O′'.
- 외부캠 FaceLandmarker 홍채로 O′(눈 3D)를 밖에서 측정 → 미지수 제거 → x/y 정합 자동.
- (흐림/복시(VAC)는 4m 고정초점 광학이라 이 방법으로도 안 잡힘 — docs/AR_REGISTRATION_RESEARCH.md §1.2)

[좌표계]
  W  = 외부 웹캠 프레임 (원점=웹캠 광심, +x 오른쪽, +y 아래, +z 전방=피사체쪽)  ← 픽셀/깊이가 여기
  H  = 머리(안경) 프레임 (FaceLandmarker 머리포즈로 W와 연결)
  Gc = 안경 월드카메라 프레임 (H 기준 고정 오프셋 = 기기상수, 1회 캘리브)
  D  = 안경 디스플레이 정규화 좌표 (앱이 그리는 곳; f_disp[px] 로 각→px)

단위: 미터(m). 각도: 라디안 내부 계산, 입력은 도(deg).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Sequence, Tuple

import numpy as np

# MediaPipe FaceLandmarker(478 랜드마크) 홍채 인덱스
IRIS_R = (468, 469, 470, 471, 472)   # 오른눈(사용자 기준) 홍채: 중심 + 상하좌우
IRIS_L = (473, 474, 475, 476, 477)   # 왼눈 홍채
IRIS_DIAMETER_M = 0.01170            # 사람 홍채(각막윤부) 지름 ≈ 11.7mm — 개인차 작아 메트릭 앵커로 표준 사용


@dataclass
class EyeRegConfig:
    # --- 외부 웹캠 내부파라미터 ---
    webcam_hfov_deg: float = 60.0     # 노트북 웹캠 수평 화각(대략). 정밀시 체스보드 캘리브로 대체.
    # --- 기기 기하: 안경 '월드카메라'가 '안경 안착점(코받침)'에 대해 어디 있나 (머리축, m) ---
    #   눈이 아니라 '안경 위 고정점'에 대한 오프셋이라 사람이 바뀌어도 상수(기기 상수).
    #   눈 위치는 홍채로 매 사람 측정 → baseline = 측정된눈 − (측정된 코받침 + 이 오프셋).
    #   X3 월드카메라 ≈ 코받침보다 위(+, y아래축이라 음수)·전방(+z). 1회 캘리브로 정밀화.
    gcam_dx: float = 0.000            # 좌우(오른쪽+)
    gcam_dy: float = -0.010           # 상하(아래+). 카메라가 코받침보다 ~10mm 위
    gcam_dz: float = 0.012            # 전후(전방+). 카메라가 코받침보다 ~12mm 앞
    # 안경 안착점으로 쓸 얼굴 랜드마크(코받침 상단, 미간). MediaPipe 168≈미간/코시작.
    mount_landmark: int = 168
    # --- 안경 디스플레이 초점(정규화→각) : offset 단위를 앱 캔버스 px로 맞춤 ---
    #   f_disp[px] = 디스플레이 가로 px / (2·tan(dispHFOV/2)).  X3 캔버스 가로≈1280px.
    display_px_w: float = 1280.0
    display_hfov_deg: float = 27.0    # X3 표시 화각(대략, 대각 ~25-30°). 캘리브로 정밀화.
    # --- 앱 축 매핑(측정 baseline → pBx/pBy 부호). 안경/앱 좌표계에 맞춰 캘리브로 확정. ---
    sign_x: float = 1.0
    sign_y: float = 1.0
    # 상수항 A (카메라-디스플레이 광축 정렬 오프셋, 기기상수). 보통 작음; 캘리브로 잡음.
    Ax_px: float = 0.0
    Ay_px: float = 0.0

    def f_webcam_px(self, img_w: int) -> float:
        """웹캠 초점거리[px] = (W/2)/tan(HFOV/2)."""
        return (img_w * 0.5) / math.tan(math.radians(self.webcam_hfov_deg) * 0.5)

    def f_display_px(self) -> float:
        """디스플레이 초점[px] = (Wd/2)/tan(dispHFOV/2). offset(d)=A+B/d 의 스케일 k."""
        return (self.display_px_w * 0.5) / math.tan(math.radians(self.display_hfov_deg) * 0.5)


def iris_center_and_diameter(landmarks_px: np.ndarray, idx: Sequence[int]) -> Tuple[np.ndarray, float]:
    """홍채 5점(중심,상,하,좌,우 근사)에서 (중심[px2], 지름[px]).

    landmarks_px: (N,2) 픽셀 좌표. idx[0]=중심, idx[1:]=주변 4점.
    지름 = 주변점들의 중심까지 평균거리 ×2 (원 근사, 노이즈에 강인).
    """
    c = landmarks_px[idx[0]]
    ring = landmarks_px[list(idx[1:])]
    r = float(np.mean(np.linalg.norm(ring - c, axis=1)))
    return c.astype(float), 2.0 * r


def eye_position_webcam(center_px: np.ndarray, diam_px: float, img_w: int, img_h: int,
                        cfg: EyeRegConfig) -> np.ndarray:
    """홍채(중심px, 지름px) + 이미지크기 → 눈 3D[m] (웹캠 W 프레임).

    깊이 Z = f · D_iris / d_iris_px (핀홀; 실지름 11.7mm 앵커).
    X,Y = (u-cx)·Z/f, (v-cy)·Z/f.  principal point = (W/2, H/2) 가정(정밀시 캘리브).
    """
    if diam_px <= 1e-6:
        raise ValueError("홍채 지름 px 가 0")
    f = cfg.f_webcam_px(img_w)
    Z = f * IRIS_DIAMETER_M / float(diam_px)
    cx, cy = img_w * 0.5, img_h * 0.5
    X = (float(center_px[0]) - cx) * Z / f
    Y = (float(center_px[1]) - cy) * Z / f
    return np.array([X, Y, Z], dtype=float)


def glasses_cam_position(mount_W: np.ndarray, head_R: np.ndarray, cfg: EyeRegConfig) -> np.ndarray:
    """측정된 안경 안착점(코받침, 웹캠 프레임) + 머리축 고정오프셋 → 안경 월드카메라 3D[m] (W)."""
    off = np.array([cfg.gcam_dx, cfg.gcam_dy, cfg.gcam_dz], dtype=float)
    return mount_W + head_R @ off


def baseline_eye_minus_gcam(eye_W: np.ndarray, gcam_W: np.ndarray, head_R: np.ndarray) -> np.ndarray:
    """baseline b = (측정된 눈 − 측정된 안경카메라) 를 '카메라(머리) 축' 좌우/상하 성분[m]으로.

    eye_W, gcam_W : 각각 웹캠 프레임의 3D[m] (눈=홍채측정, gcam=코받침측정+오프셋).
    head_R        : 머리 회전 3x3 (W←H). 카메라축≈머리축.
    반환          : (b_x, b_y)[m] = head_Rᵀ·(eye−gcam) 의 앞 2성분.

    ★ 사람마다 눈 위치가 다르면 b 가 달라짐 → '사람별 자동정합'이 여기서 성립.
    """
    b_cam = head_R.T @ (np.asarray(eye_W, float) - np.asarray(gcam_W, float))
    return b_cam[:2].copy()


def parallax_AB(b_xy: np.ndarray, cfg: EyeRegConfig) -> Tuple[float, float, float, float]:
    """baseline b[m] → 앱 mesh 시차모델 (Ax,Ay,Bx,By).  offset(d)=A+B/d [디스플레이 px].

    B = f_disp · b  (px·m).  손 깊이 d[m] 로 나눠 px 오프셋. 부호는 sign_x/y 로 앱축에 정렬.
    A = 광축 정렬 상수(px).
    """
    fdisp = cfg.f_display_px()
    Bx = cfg.sign_x * fdisp * float(b_xy[0])
    By = cfg.sign_y * fdisp * float(b_xy[1])
    return cfg.Ax_px, cfg.Ay_px, Bx, By


def offset_at_depth(ab: Tuple[float, float, float, float], depth_m: float) -> Tuple[float, float]:
    """(Ax,Ay,Bx,By)와 손 깊이 d[m] → 그 순간 디스플레이 오프셋[px]. 검증/시뮬용."""
    Ax, Ay, Bx, By = ab
    if depth_m <= 1e-3:
        return Ax, Ay
    return Ax + Bx / depth_m, Ay + By / depth_m


def full_pipeline(iris_center_px: np.ndarray, iris_diam_px: float,
                  mount_center_px: np.ndarray, mount_depth_m: float,
                  img_w: int, img_h: int, head_R: np.ndarray, cfg: EyeRegConfig) -> dict:
    """측정 픽셀 → (눈3D, 안경카메라3D, baseline, A/B). 런타임/테스트 공용 한방 함수.

    iris_*        : 홍채 중심px·지름px (눈 3D·깊이 산출)
    mount_*       : 안경 안착점(코받침) 중심px + 그 깊이[m] (홍채깊이와 같은 프레임)
    head_R        : 머리 회전 3x3 (없으면 np.eye(3))
    """
    eye = eye_position_webcam(iris_center_px, iris_diam_px, img_w, img_h, cfg)
    # 코받침(안착점) 3D: 같은 핀홀로 역투영(깊이는 홍채깊이 근사 사용 가능)
    f = cfg.f_webcam_px(img_w)
    mx = (float(mount_center_px[0]) - img_w * 0.5) * mount_depth_m / f
    my = (float(mount_center_px[1]) - img_h * 0.5) * mount_depth_m / f
    mount = np.array([mx, my, mount_depth_m], dtype=float)
    gcam = glasses_cam_position(mount, head_R, cfg)
    b = baseline_eye_minus_gcam(eye, gcam, head_R)
    ab = parallax_AB(b, cfg)
    return {"eye_W": eye, "gcam_W": gcam, "baseline_xy": b, "AB": ab,
            "f_webcam_px": f, "f_display_px": cfg.f_display_px()}
