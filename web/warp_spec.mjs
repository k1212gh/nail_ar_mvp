// WarpSpec — PC·웹 공유 순수 수학 (DESIGN_WARP §3). `spec/warp_spec.py`와 줄 단위 미러.
// 의존 0(Math만). spec/test_parity.py가 atol=1e-4 일치를 강제.
// 좌표 규약: u 가로(0좌·0.5능선·1우, axis_minor) / v 세로(0뿌리·1팁, axis_major). 로컬 z=카메라쪽(+).

const EPS = 1e-9;

function rotInPlaneAxis(x, y, z, ax, ay, deg) {
  const n = Math.hypot(ax, ay);
  if (n < EPS || Math.abs(deg) < EPS) return [x, y, z];
  ax /= n; ay /= n;
  const th = deg * Math.PI / 180, c = Math.cos(th), s = Math.sin(th);
  const adotp = ax * x + ay * y;
  const cx = ay * z, cy = -ax * z, cz = ax * y - ay * x;
  const xr = x * c + cx * s + ax * adotp * (1 - c);
  const yr = y * c + cy * s + ay * adotp * (1 - c);
  const zr = z * c + cz * s;
  return [xr, yr, zr];
}

function perspF(p) {
  const f = p.persp_f || 0.0;
  if (f > 0) return f;
  const L = p.length ?? 1.0, W = p.width ?? 1.0;
  return 2.0 * Math.max(L, W) * (p.scale ?? 1.0);
}

export function vertexScreen(u, v, p, tier) {
  const [cx, cy] = p.center_px, [ux, uy] = p.axis_major, [vx, vy] = p.axis_minor;
  const L = p.length, W = p.width, scale = p.scale ?? 1.0, along = p.along ?? 0.0;

  const useTilt = (tier === "tilt" || tier === "mesh" || tier === "mesh_shaded");
  const useCurv = (tier === "mesh" || tier === "mesh_shaded");
  const cha = useCurv ? (p.curv_half_angle || 0.0) : 0.0;
  const tilt = useTilt ? (p.tilt_deg || 0.0) : 0.0;

  let t_loc = (v - 0.5) * L * scale + (L * scale * 0.5) * along;
  let s_loc, z;
  if (cha > 1e-6) {
    const phi = (u - 0.5) * 2.0 * cha;
    s_loc = Math.sin(phi) / Math.sin(cha) * (W * scale * 0.5);
    z = (Math.cos(phi) - Math.cos(cha)) * (W * scale * 0.5);
  } else {
    s_loc = (u - 0.5) * W * scale; z = 0.0;
  }

  if (Math.abs(tilt) > 1e-6) {
    const tax = p.tilt_axis || [1.0, 0.0];
    [s_loc, t_loc, z] = rotInPlaneAxis(s_loc, t_loc, z, tax[0], tax[1], tilt);
  }

  let k;
  if (Math.abs(tilt) > 1e-6 || cha > 1e-6) {
    const f = perspF(p);
    // z>0 = 카메라 쪽(가까움) → 확대. 약투영 k = f/(f-z).
    k = (f - z) > EPS ? f / (f - z) : 1.0;
  } else { k = 1.0; }

  const sx = s_loc * k, tx = t_loc * k;
  return [cx + vx * sx + ux * tx, cy + vy * sx + uy * tx];
}

const CORNERS = [[0, 0], [1, 0], [0, 1], [1, 1]];   // 격자 행우선(TL,TR,BL,BR)

export function buildWarpSpec(params, tier = "plane", grid = [1, 1]) {
  let uv, screen, g;
  if (tier === "plane" || tier === "tilt") {
    uv = CORNERS.map(c => [c[0], c[1]]);
    screen = CORNERS.map(([u, v]) => vertexScreen(u, v, params, tier));
    g = [1, 1];
  } else {
    let ny = Math.max(1, grid[0] | 0), nx = Math.max(1, grid[1] | 0);
    uv = []; screen = [];
    for (let iy = 0; iy <= ny; iy++) {
      const v = iy / ny;
      for (let ix = 0; ix <= nx; ix++) {
        const u = ix / nx;
        uv.push([u, v]);
        screen.push(vertexScreen(u, v, params, tier));
      }
    }
    g = [ny, nx];
  }
  return { tier, grid: g, uv, screen,
           feather_uv: params.feather_uv ?? 0.0, alpha: params.alpha ?? 1.0 };
}
