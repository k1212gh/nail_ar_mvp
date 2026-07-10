"""WarpSpec — PC·웹 공유 순수 수학 (DESIGN_WARP §3).

이 모듈은 **라이브러리 의존 0**(math만). `web/warp_spec.mjs`와 줄 단위로 미러되며,
`spec/test_parity.py`가 동일 입력에서 두 구현의 출력이 atol=1e-4로 일치함을 강제한다.

입력: SurfaceParams(dict, plain number) + tier + grid
출력: WarpSpec(dict) — 정점 uv(src) / screen(dst) 그리드. 렌더러(cv2.remap/canvas/WebGL)는
      이 정점만 소비하므로, 곡률·tilt 수식이 바뀌어도 렌더러는 불변.

좌표 규약(동결):
  u ∈ [0,1] 가로: u=0 좌측, u=0.5 능선, u=1 우측  → axis_minor
  v ∈ [0,1] 세로: v=0 뿌리, v=1 팁                → axis_major(+ 가 팁)
  로컬 3D: x=s(minor), y=t(major), z=카메라 쪽(+).
"""
import math

EPS = 1e-9


def _rot_in_plane_axis(x, y, z, ax, ay, deg):
    """평면내 축 a=(ax,ay,0) 둘레로 (x,y,z)를 deg 회전 (Rodrigues). 평면을 화면 밖으로 기울임."""
    n = math.hypot(ax, ay)
    if n < EPS or abs(deg) < EPS:
        return x, y, z
    ax /= n
    ay /= n
    th = math.radians(deg)
    c = math.cos(th)
    s = math.sin(th)
    adotp = ax * x + ay * y                 # a·P (a_z=0)
    # a×P = (ay*z, -ax*z, ax*y - ay*x)
    cx = ay * z
    cy = -ax * z
    cz = ax * y - ay * x
    xr = x * c + cx * s + ax * adotp * (1 - c)
    yr = y * c + cy * s + ay * adotp * (1 - c)
    zr = z * c + cz * s                       # a_z=0 → 마지막 항 0
    return xr, yr, zr


def _persp_f(p):
    f = p.get("persp_f", 0.0) or 0.0
    if f > 0:
        return f
    # 기본 초점거리: 손톱 크기에 비례(약투영 강도 적당). f가 클수록 원근 약함.
    L = p.get("length", 1.0)
    W = p.get("width", 1.0)
    return 2.0 * max(L, W) * p.get("scale", 1.0)


def vertex_screen(u, v, p, tier):
    """정규 UV (u,v) → 프레임 픽셀 (x,y). tier에 따라 곡률/tilt 적용."""
    cx, cy = p["center_px"]
    ux, uy = p["axis_major"]
    vx, vy = p["axis_minor"]
    L = p["length"]
    W = p["width"]
    scale = p.get("scale", 1.0)
    along = p.get("along", 0.0)

    use_tilt = tier in ("tilt", "mesh", "mesh_shaded")
    use_curv = tier in ("mesh", "mesh_shaded")
    cha = (p.get("curv_half_angle", 0.0) or 0.0) if use_curv else 0.0
    tilt = (p.get("tilt_deg", 0.0) or 0.0) if use_tilt else 0.0

    t_loc = (v - 0.5) * L * scale + (L * scale * 0.5) * along
    if cha > 1e-6:
        phi = (u - 0.5) * 2.0 * cha
        s_loc = math.sin(phi) / math.sin(cha) * (W * scale * 0.5)
        z = (math.cos(phi) - math.cos(cha)) * (W * scale * 0.5)
    else:
        s_loc = (u - 0.5) * W * scale
        z = 0.0

    if abs(tilt) > 1e-6:
        tax = p.get("tilt_axis", [1.0, 0.0])
        s_loc, t_loc, z = _rot_in_plane_axis(s_loc, t_loc, z, tax[0], tax[1], tilt)

    if abs(tilt) > 1e-6 or cha > 1e-6:
        f = _persp_f(p)
        # z>0 = 카메라 쪽(가까움) → 확대. 약투영 k = f/(f-z).
        k = f / (f - z) if (f - z) > EPS else 1.0
    else:
        k = 1.0

    sx = s_loc * k
    tx = t_loc * k
    x = cx + vx * sx + ux * tx
    y = cy + vy * sx + uy * tx
    return x, y


# 4점 코너 UV — 격자 행우선 순서(TL,TR,BL,BR)로 reshape(2,2)가 정상 격자가 되게.
_CORNERS = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]


def build_warp_spec(params, tier="plane", grid=(1, 1)):
    """SurfaceParams → WarpSpec dict. plane/tilt=4코너, mesh=격자."""
    if tier in ("plane", "tilt"):
        uv = [list(c) for c in _CORNERS]
        screen = [list(vertex_screen(u, v, params, tier)) for (u, v) in _CORNERS]
        g = [1, 1]
    else:  # mesh / mesh_shaded
        ny, nx = int(grid[0]), int(grid[1])
        ny = max(1, ny)
        nx = max(1, nx)
        uv = []
        screen = []
        for iy in range(ny + 1):
            v = iy / ny
            for ix in range(nx + 1):
                u = ix / nx
                uv.append([u, v])
                screen.append(list(vertex_screen(u, v, params, tier)))
        g = [ny, nx]
    return {
        "tier": tier,
        "grid": g,
        "uv": uv,
        "screen": screen,
        "feather_uv": params.get("feather_uv", 0.0),
        "alpha": params.get("alpha", 1.0),
    }
