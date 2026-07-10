"""SPAAM / DLT — OST-HMD 눈↔디스플레이 투영행렬(3×4 P) 추정.

연구(docs/AR_REGISTRATION_RESEARCH.md) 기반 구현. 대응쌍 (3D 월드점 X ↔ 2D 디스플레이 픽셀 u)
N개(≥6)로 P를 푼다. 눈+디스플레이를 핀홀 카메라로 보는 표준 DLT:

    s·[u,v,1]ᵀ = P·[X,Y,Z,1]ᵀ ,   P ∈ ℝ³ˣ⁴  (11 DOF)

핵심: (1) Hartley 정규화(2D 평균거리√2, 3D √3) — SVD 조건수 안정, (2) SVD 최소특이벡터,
(3) 역정규화. 참고 구현 fatihksubasi/spaam, YutaItoh/HMD-Calibration와 수식 일치.

주의(X3): 이 솔버는 x/y 정합만 개선. 4m 고정초점 + 무 아이트래킹이라 근거리 깊이/흐림/VAC는
못 잡는다(docs/AR_REGISTRATION_RESEARCH.md §1). Stereo-SPAAM은 좌/우 각각 P를 풀고 IPD로 검증.
"""
from __future__ import annotations

import numpy as np


def _normalize_2d(pts: np.ndarray):
    """2D 점을 중심0·평균거리√2로. 반환 (정규화점, 3×3 유사변환 T) with T·x = x̃."""
    c = pts.mean(axis=0)
    d = np.sqrt(((pts - c) ** 2).sum(axis=1)).mean()
    s = np.sqrt(2.0) / (d + 1e-12)
    T = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]], float)
    ph = np.c_[pts, np.ones(len(pts))]
    return (ph @ T.T)[:, :2], T


def _normalize_3d(pts: np.ndarray):
    """3D 점을 중심0·평균거리√3로. 반환 (정규화점, 4×4 U)."""
    c = pts.mean(axis=0)
    d = np.sqrt(((pts - c) ** 2).sum(axis=1)).mean()
    s = np.sqrt(3.0) / (d + 1e-12)
    U = np.array([[s, 0, 0, -s * c[0]],
                  [0, s, 0, -s * c[1]],
                  [0, 0, s, -s * c[2]],
                  [0, 0, 0, 1]], float)
    ph = np.c_[pts, np.ones(len(pts))]
    return (ph @ U.T)[:, :3], U


def solve_projection(world_xyz: np.ndarray, screen_uv: np.ndarray) -> np.ndarray:
    """대응쌍으로 3×4 투영행렬 P를 DLT+SVD로 추정.

    world_xyz : (N,3) 트래킹/카메라 좌표계의 3D 점
    screen_uv : (N,2) 그에 대응하는 디스플레이 픽셀
    반환      : (3,4) P.  u ~ P·[X,Y,Z,1]ᵀ (동차, 마지막으로 나눔)
    """
    X = np.asarray(world_xyz, float)
    u = np.asarray(screen_uv, float)
    if len(X) < 6:
        raise ValueError("SPAAM은 대응쌍 6개 이상 필요")
    Xn, U = _normalize_3d(X)
    un, T = _normalize_2d(u)

    rows = []
    for (x, y, z), (uu, vv) in zip(Xn, un):
        Xh = [x, y, z, 1.0]
        rows.append([0, 0, 0, 0, *[-e for e in Xh], *[vv * e for e in Xh]])
        rows.append([*Xh, 0, 0, 0, 0, *[-uu * e for e in Xh]])
    A = np.asarray(rows, float)                 # (2N, 12)

    _, _, Vt = np.linalg.svd(A)
    P_tilde = Vt[-1].reshape(3, 4)              # 최소특이값의 우특이벡터
    P = np.linalg.inv(T) @ P_tilde @ U          # 역정규화
    return P / (np.linalg.norm(P[2, :3]) + 1e-12)


def project(P: np.ndarray, world_xyz: np.ndarray) -> np.ndarray:
    """P로 3D점들을 2D 픽셀로 투영. 반환 (N,2)."""
    Xh = np.c_[np.asarray(world_xyz, float), np.ones(len(world_xyz))]
    ph = Xh @ P.T
    return ph[:, :2] / ph[:, 2:3]


def reprojection_error(P, world_xyz, screen_uv) -> float:
    """평균 재투영 픽셀오차(RMS)."""
    pr = project(P, world_xyz)
    return float(np.sqrt(((pr - np.asarray(screen_uv, float)) ** 2).sum(axis=1).mean()))


def _self_test():
    """합성 P로 점 투영→노이즈→DLT 복원, 재투영오차 확인."""
    rng = np.random.default_rng(0)
    # 임의의 그럴듯한 눈-디스플레이 투영(내부 K + 외부 [R|t])
    K = np.array([[900, 0, 640], [0, 900, 240], [0, 0, 1]], float)
    rvec = rng.normal(0, 0.2, 3)
    th = np.linalg.norm(rvec); ax = rvec / (th + 1e-9)
    Kx = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    R = np.eye(3) + np.sin(th) * Kx + (1 - np.cos(th)) * Kx @ Kx
    t = np.array([0.02, -0.01, 0.6])
    P_true = K @ np.c_[R, t]

    # 여러 깊이에 퍼진 3D 손끝 대응점(잘 조건화되게)
    X = rng.uniform([-0.15, -0.1, 0.15], [0.15, 0.1, 0.6], size=(30, 3))
    u = project(P_true, X)
    u_noisy = u + rng.normal(0, 0.5, u.shape)       # 0.5px 정렬노이즈

    P_est = solve_projection(X, u_noisy)
    err = reprojection_error(P_est, X, u)
    print(f"[spaam self-test] N=30, alignment noise=0.5px -> reprojection RMS = {err:.3f}px")
    assert err < 3.0, f"reconstruction failed ({err:.2f}px)"
    print("[spaam self-test] PASS - DLT/SVD recovered P accurately under noise")


if __name__ == "__main__":
    _self_test()
