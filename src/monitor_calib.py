"""모니터 기반 OST 안경 정합 캘리브레이션 — 순수 수학 코어 (하드웨어 비의존, 단위테스트 가능).

목표: 사용자가 '안경 디스플레이의 크로스헤어'를 '실제 모니터의 네 모서리'에 겹쳐 보도록 정렬하면,
그 대응들로부터 **눈(동공)이 안경 월드카메라 프레임에서 어디 있는지** E(eye_cam)를 역산한다.
E 로부터 앱의 깊이적응 시차모델 offset(d)=A+B/d 의 (A,B)를 만든다 (src/eye_geometry.parallax_AB 와 동일 모델).

파이프라인:
  1) 안경 월드카메라가 모니터를 본다 → 4모서리 픽셀 → cv2.solvePnP 로 모니터 4모서리의
     3D 위치(카메라 프레임, m) 를 얻는다.  (camera_pose_from_corners)
  2) 사용자가 여러 거리에서 디스플레이 크로스헤어를 그 모서리들에 겹친다 →
     (display_norm[0..1], 모서리_3D[카메라프레임]) 대응 수집.
  3) SPAAM DLT(docs/AR_REGISTRATION_RESEARCH.md §2.1)로 3×4 투영 P(3D카메라→2D디스플레이px)를 풀고,
     P의 카메라중심 = 눈위치 E(eye_cam) 를 추출.  (solve_eye_in_camera)
  4) baseline b=(E_x,E_y) → (Ax,Ay,Bx,By).  (eye_to_AB)

[좌표계]
  Gc = 안경 월드카메라 프레임 (원점=카메라 광심, +x 오른쪽, +y 아래, +z 전방). 3D 점/눈이 여기.
  D  = 안경 디스플레이 정규화 좌표 [0..1] (0,0=좌상, 1,1=우하). px = norm·[display_px_w, display_px_h].

단위: 미터(m). 각도: 내부 라디안, 입력은 도(deg).
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import cv2

# 3D 점군이 (거의) 한 평면에 있는지 판정하는 상대임계 — 최소/최대 특이값 비.
# 단일 모니터 거리(모든 대응이 한 평면)면 z-분산이 0 → 비≈0 → planar_warn.
_PLANAR_RATIO_THRESH = 1e-3


@dataclass
class MonitorCalibConfig:
    monitor_w_m: float                    # 모니터 활성영역 물리 가로(m)
    monitor_h_m: float                    # 물리 세로(m)
    glasses_cam_hfov_deg: float = 66.0    # 안경 월드카메라 수평 화각(대략)
    display_px_w: float = 1280.0          # AR 캔버스 가로 px
    display_hfov_deg: float = 27.0        # 디스플레이 표시 화각(deg)

    def f_glasses_cam_px(self, img_w: int) -> float:
        """안경 월드카메라 초점거리[px] = (img_w/2)/tan(HFOV/2)."""
        return (img_w * 0.5) / math.tan(math.radians(self.glasses_cam_hfov_deg) * 0.5)

    def f_display_px(self) -> float:
        """디스플레이 초점[px] = (display_px_w/2)/tan(dispHFOV/2). offset(d)=A+B/d 스케일."""
        return (self.display_px_w * 0.5) / math.tan(math.radians(self.display_hfov_deg) * 0.5)

    def display_px_h(self) -> float:
        """디스플레이 세로 px.

        디스플레이는 수평 화각(display_hfov_deg)과 정사각 픽셀만 주어진다. 세로 화각/종횡비가
        따로 주어지지 않으므로 세로 px 를 유일하게 유도할 수 없다 → 4:3 종횡비 가정
        (display_px_h = display_px_w·0.75). 정사각 픽셀이므로 f는 x/y 동일(f_display_px).
        캘리브로 실제 세로화각을 알면 이 함수만 교체하면 된다.
        """
        return self.display_px_w * 0.75


# ---------------------------------------------------------------------------
# 1) PnP: 모니터 4모서리 픽셀 → 카메라 프레임 3D
# ---------------------------------------------------------------------------
def camera_pose_from_corners(corners_px, img_w: int, img_h: int,
                             cfg: MonitorCalibConfig) -> dict:
    """모니터 4모서리 픽셀(TL,TR,BR,BL) → 카메라 프레임에서의 3D 위치.

    corners_px : (4,2) float 픽셀좌표, 순서 TL,TR,BR,BL.
    img_w,img_h: 안경 카메라 영상 크기(px) — 초점거리/주점 계산용.
    반환       : {"R":(3,3), "t":(3,), "corners_cam":(4,3)}
                 corners_cam[i] = R@obj[i] + t = i번째 모서리의 3D(카메라프레임, m).
    """
    corners_px = np.asarray(corners_px, dtype=np.float64).reshape(-1, 2)
    if corners_px.shape[0] != 4:
        raise ValueError("corners_px 는 (4,2) 여야 함 (TL,TR,BR,BL)")

    W, H = cfg.monitor_w_m, cfg.monitor_h_m
    # 모니터 자체 프레임(원점=중심, x오른쪽, y아래, z=0 평면). 이미지 y-down 규약과 일치.
    obj = np.array([[-W / 2, -H / 2, 0.0],   # TL
                    [ W / 2, -H / 2, 0.0],   # TR
                    [ W / 2,  H / 2, 0.0],   # BR
                    [-W / 2,  H / 2, 0.0]],  # BL
                   dtype=np.float64)

    f = cfg.f_glasses_cam_px(img_w)
    K = np.array([[f, 0.0, img_w * 0.5],
                  [0.0, f, img_h * 0.5],
                  [0.0, 0.0, 1.0]], dtype=np.float64)
    dist = np.zeros((5, 1), dtype=np.float64)

    ok, rvec, tvec = cv2.solvePnP(obj, corners_px, K, dist,
                                  flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise RuntimeError("cv2.solvePnP 실패")

    R, _ = cv2.Rodrigues(rvec)
    t = tvec.reshape(3)
    corners_cam = (R @ obj.T).T + t
    return {"R": R, "t": t, "corners_cam": corners_cam}


# ---------------------------------------------------------------------------
# DLT 유틸 (Hartley 정규화) — docs/AR_REGISTRATION_RESEARCH.md §2.1
# ---------------------------------------------------------------------------
def _normalize_2d(pts: np.ndarray):
    """2D 점 → 중심0·평균거리√2. 반환 (정규화점(N,2), 3×3 T) with x̃ = T·x(동차)."""
    c = pts.mean(axis=0)
    d = np.sqrt(((pts - c) ** 2).sum(axis=1)).mean()
    s = np.sqrt(2.0) / (d + 1e-12)
    T = np.array([[s, 0, -s * c[0]],
                  [0, s, -s * c[1]],
                  [0, 0, 1.0]], float)
    ph = np.c_[pts, np.ones(len(pts))]
    return (ph @ T.T)[:, :2], T


def _normalize_3d(pts: np.ndarray):
    """3D 점 → 중심0·평균거리√3. 반환 (정규화점(N,3), 4×4 U)."""
    c = pts.mean(axis=0)
    d = np.sqrt(((pts - c) ** 2).sum(axis=1)).mean()
    s = np.sqrt(3.0) / (d + 1e-12)
    U = np.array([[s, 0, 0, -s * c[0]],
                  [0, s, 0, -s * c[1]],
                  [0, 0, s, -s * c[2]],
                  [0, 0, 0, 1.0]], float)
    ph = np.c_[pts, np.ones(len(pts))]
    return (ph @ U.T)[:, :3], U


def _solve_dlt(world_xyz: np.ndarray, screen_uv: np.ndarray) -> np.ndarray:
    """Hartley 정규화 → SVD 최소특이벡터 → 역정규화. 3×4 P 반환. (§2.1 그대로)"""
    Xn, U = _normalize_3d(world_xyz)
    un, T = _normalize_2d(screen_uv)
    rows = []
    for (x, y, z), (uu, vv) in zip(Xn, un):
        Xh = [x, y, z, 1.0]
        rows.append([0, 0, 0, 0, *[-e for e in Xh], *[vv * e for e in Xh]])
        rows.append([*Xh, 0, 0, 0, 0, *[-uu * e for e in Xh]])
    A = np.asarray(rows, float)                      # (2N, 12)
    _, _, Vt = np.linalg.svd(A)
    P_tilde = Vt[-1].reshape(3, 4)                   # 최소특이값 우특이벡터
    P = np.linalg.inv(T) @ P_tilde @ U               # 역정규화
    return P


def _project(P: np.ndarray, world_xyz: np.ndarray) -> np.ndarray:
    """P 로 3D→2D px 투영. 반환 (N,2)."""
    Xh = np.c_[np.asarray(world_xyz, float), np.ones(len(world_xyz))]
    ph = Xh @ P.T
    return ph[:, :2] / ph[:, 2:3]


def _camera_center(P: np.ndarray) -> np.ndarray:
    """P=[M|p4] 의 카메라중심 C: M·C=-p4 (lstsq, 특이 M 에도 안전). 반환 (3,)."""
    M = P[:, :3]
    p4 = P[:, 3]
    C, *_ = np.linalg.lstsq(M, -p4, rcond=None)
    return C


# ---------------------------------------------------------------------------
# 2) SPAAM DLT: (display_norm, 3D) 대응 → 눈 위치 E(eye_cam)
# ---------------------------------------------------------------------------
def solve_eye_in_camera(correspondences, cfg: MonitorCalibConfig) -> dict:
    """(display_norm[0..1], 모서리_3D[카메라프레임]) 대응들 → 눈위치 E + 투영 P.

    correspondences: [(display_norm_xy(2,), point_cam_3d(3,)), ...]  (>=6, 여러 거리 권장)
    물리의미: 눈에서 볼 때 디스플레이의 그 점이 3D 모니터점과 겹친다.
    SPAAM DLT 로 3×4 P(3D카메라 → 디스플레이 px = norm·[display_px_w, display_px_h]) 를 풀고,
    P의 카메라중심(=눈)을 반환.

    반환: {"eye_cam":(3,), "residual_px":float, "P":(3,4), "n":int, "planar_warn":bool}
      residual_px = P 의 대응 재투영 RMS[px]. (평면 퇴화 시 낙관적으로 작거나, 완전퇴화면 inf)
      planar_warn = 3D 점군이 (거의) 한 평면(단일 거리)일 때 True — P는 반환하나 눈/잔차 신뢰불가.
    """
    if correspondences is None or len(correspondences) < 6:
        raise ValueError("SPAAM DLT 는 대응쌍 6개 이상 필요 (여러 거리 권장)")

    px_scale = np.array([cfg.display_px_w, cfg.display_px_h()], float)
    world = np.array([np.asarray(c[1], float).reshape(3) for c in correspondences], float)
    disp_norm = np.array([np.asarray(c[0], float).reshape(2) for c in correspondences], float)
    screen = disp_norm * px_scale                    # (N,2) 디스플레이 픽셀

    n = int(world.shape[0])

    # 평면 퇴화 판정: 중심화 3D 점군의 특이값 비 (최소/최대).
    centered = world - world.mean(axis=0)
    sv = np.linalg.svd(centered, compute_uv=False)
    planar_warn = bool(sv[0] <= 1e-12 or (sv[-1] / sv[0]) < _PLANAR_RATIO_THRESH)

    P = _solve_dlt(world, screen)

    # 재투영 RMS. 평면 퇴화 시 P가 특이해 w≈0(0/0)일 수 있으니 경고 억제 후 유한성 검사.
    with np.errstate(divide="ignore", invalid="ignore"):
        proj = _project(P, world)
        residual_px = float(np.sqrt(((proj - screen) ** 2).sum(axis=1).mean()))
    if not np.isfinite(residual_px):
        # 퇴화(단일평면)로 재투영이 정의불가 → 신뢰불가 신호로 inf (임계비교에서 통과 안 됨).
        residual_px = float("inf")
    eye_cam = _camera_center(P)

    return {"eye_cam": eye_cam, "residual_px": residual_px, "P": P,
            "n": n, "planar_warn": planar_warn}


# ---------------------------------------------------------------------------
# 3) 눈위치 → 시차모델 (A,B)
# ---------------------------------------------------------------------------
def eye_to_AB(eye_cam, cfg: MonitorCalibConfig):
    """눈위치 E(카메라프레임) → 앱 시차모델 (Ax,Ay,Bx,By). offset(d)=A+B/d [디스플레이 px].

    baseline b=(E_x,E_y)[m]. Ax=Ay=0.0, Bx=f_display_px·b_x, By=f_display_px·b_y.
    (src/eye_geometry.parallax_AB 와 일관: sign=+1, A=0 인 경우와 동일.)
    """
    eye_cam = np.asarray(eye_cam, float).reshape(3)
    fdisp = cfg.f_display_px()
    Ax, Ay = 0.0, 0.0
    Bx = fdisp * float(eye_cam[0])
    By = fdisp * float(eye_cam[1])
    return Ax, Ay, Bx, By
