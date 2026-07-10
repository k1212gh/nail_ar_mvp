// 웹 디자인 렌더 오케스트레이터 — GPU 정책(P0-2) + 폴백 사다리 (DESIGN_WARP §6/§8).
// 핵심 수학은 warp_spec.mjs(파리티 검증) 공유. tier=plane은 canvas2D, tilt/mesh는 WebGL.
//
// P0-2 GPU 컨텍스트 정책: ORT는 추론에 WebGPU(ort.webgpu.bundle)를 점유한다. 렌더는
// **별도 WebGL2 컨텍스트**(오버레이 캔버스)를 쓴다. WebGL2 미지원/컨텍스트 lost 시
// canvas2D plane으로 우아하게 강등(곡면 포기, 동작 유지). 실기기 검증 필요(아래 NOTE).

import { buildWarpSpec } from "./warp_spec.mjs";
import { WarpGL, gridIndices } from "./warp_gl.js";

// Canvas2D 삼각형 텍스처 매핑 — 소스 uv삼각형 → 화면 삼각형 아핀 후 클립 drawImage.
// WebGL 없이도 곡면 메시 워핑(진짜 별 색 보장). a*=소스 픽셀, s*=화면 픽셀.
function drawTexTri(ctx, img, iw, ih, uvA, uvB, uvC, sA, sB, sC) {
  const a0 = [uvA[0] * iw, uvA[1] * ih], a1 = [uvB[0] * iw, uvB[1] * ih], a2 = [uvC[0] * iw, uvC[1] * ih];
  const det = (a1[0] - a0[0]) * (a2[1] - a0[1]) - (a2[0] - a0[0]) * (a1[1] - a0[1]);
  if (Math.abs(det) < 1e-6) return;
  const m11 = ((sB[0] - sA[0]) * (a2[1] - a0[1]) - (sC[0] - sA[0]) * (a1[1] - a0[1])) / det;
  const m12 = ((sC[0] - sA[0]) * (a1[0] - a0[0]) - (sB[0] - sA[0]) * (a2[0] - a0[0])) / det;
  const m21 = ((sB[1] - sA[1]) * (a2[1] - a0[1]) - (sC[1] - sA[1]) * (a1[1] - a0[1])) / det;
  const m22 = ((sC[1] - sA[1]) * (a1[0] - a0[0]) - (sB[1] - sA[1]) * (a2[0] - a0[0])) / det;
  const dx = sA[0] - m11 * a0[0] - m12 * a0[1];
  const dy = sA[1] - m21 * a0[0] - m22 * a0[1];
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(sA[0], sA[1]); ctx.lineTo(sB[0], sB[1]); ctx.lineTo(sC[0], sC[1]); ctx.closePath();
  ctx.clip();
  ctx.setTransform(m11, m21, m12, m22, dx, dy);
  ctx.drawImage(img, 0, 0);
  ctx.restore();   // 클립+트랜스폼 복원(identity)
}

// nail {cx,cy,ex,ey,len,wid, tiltDeg?} → SurfaceParams.
// 마스크 경로(yolo)는 n.tiltDeg 없음 → tilt=0 (P0-1). 랜드마크 경로는 z로 tiltDeg 주입.
export function paramsFromNail(n, opts = {}) {
  return {
    center_px: [n.cx, n.cy],
    axis_major: [n.ex, n.ey],
    axis_minor: [-n.ey, n.ex],
    length: n.len, width: n.wid,
    scale: opts.scale ?? 0.9, along: opts.along ?? 0.0,
    tilt_deg: n.tiltDeg ?? 0.0, tilt_axis: [1.0, 0.0],
    curv_half_angle: opts.curve ?? 0.0, persp_f: 0.0,
    feather_uv: opts.featherUV ?? 0.0, alpha: opts.alpha ?? 1.0,
  };
}

export function chooseTier(params, want = "auto", fps = null) {
  const hasCurv = (params.curv_half_angle || 0) > 1e-3;
  const hasTilt = Math.abs(params.tilt_deg || 0) > 0.5;
  if (want !== "auto") return want;
  if (fps !== null && fps < 8) return "plane";
  if (hasCurv) return "mesh";
  if (hasTilt) return "tilt";
  return "plane";
}

export class NailDesignRenderer {
  constructor(opts = {}) {
    this.opts = opts;
    this.backend = "none";
    this.gl = null;
    this.atlasImg = null;
    this.glCanvas = (typeof document !== "undefined") ? document.createElement("canvas") : null;
    this._initGL();
  }

  _initGL() {
    if (this.opts && this.opts.force2d) { this.backend = "canvas2d"; return; }  // 진단/폴백
    if (!this.glCanvas) { this.backend = "canvas2d"; return; }
    try {
      this.gl = new WarpGL(this.glCanvas);
      this.backend = "webgl";
      // 컨텍스트 lost → canvas2D plane 폴백 (P0-2)
      this.glCanvas.addEventListener("webglcontextlost", (e) => {
        e.preventDefault();
        console.warn("[design] WebGL 컨텍스트 lost → canvas2D plane 폴백");
        this.backend = "canvas2d"; this.gl = null;
      });
      this.glCanvas.addEventListener("webglcontextrestored", () => {
        try { this._initGL(); if (this.atlasImg) this.gl.setAtlas(this.atlasImg); } catch (_) {}
      });
    } catch (err) {
      console.warn("[design] WebGL2 미지원 → canvas2D plane:", err.message);
      this.backend = "canvas2d";
    }
  }

  setAtlas(img) {
    this.atlasImg = img;
    if (this.backend === "webgl" && this.gl) this.gl.setAtlas(img);
  }

  _whiteMask() {            // 마스크 없는 경로(랜드마크=세그 없음)용 1×1 흰색 → m=1
    if (!this._wm) {
      this._wm = document.createElement("canvas"); this._wm.width = this._wm.height = 1;
      const c = this._wm.getContext("2d"); c.fillStyle = "#fff"; c.fillRect(0, 0, 1, 1);
    }
    return this._wm;
  }

  // nails: 검출 손톱. maskCanvas: 전체프레임 마스크(알파) 또는 null(클립 없음). outCtx: 합성 대상.
  render(nails, W, H, maskCanvas, outCtx, fps = null) {
    if (!this.atlasImg || !nails.length) return;
    const o = this.opts;
    const params = nails.map((n) => paramsFromNail(n, o));
    if (this.backend === "webgl" && this.gl) {
      const tier = (p) => chooseTier(p, o.tier ?? "auto", fps);
      const grid = o.meshGrid ?? [10, 8];
      const specs = params.map((p) => {
        const t = tier(p);
        return { spec: buildWarpSpec(p, t, (t === "mesh" || t === "mesh_shaded") ? grid : [1, 1]) };
      });
      this.gl.render(specs, W, H, maskCanvas || this._whiteMask(), o.alpha ?? 1.0);
      outCtx.drawImage(this.glCanvas, 0, 0);
    } else {
      this._renderCanvas2D(params, W, H, maskCanvas, outCtx);
    }
  }

  // Canvas2D 텍스처 메시 워핑 — 곡면(mesh)·기울기(tilt)·평면 모두 삼각형 매핑으로 렌더.
  // WebGL 텍스처가 흰색 나오는 기기 대비 확실한 경로(drawImage=진짜 색).
  _renderCanvas2D(params, W, H, maskCanvas, outCtx) {
    const tmp = document.createElement("canvas"); tmp.width = W; tmp.height = H;
    const c = tmp.getContext("2d");
    const img = this.atlasImg, iw = img.width, ih = img.height;
    const o = this.opts;
    const grid = o.mesh2d ?? [6, 4];           // 2D는 약간 성긴 격자(성능)
    for (const p of params) {
      const t = chooseTier(p, o.tier ?? "auto", null);
      const useGrid = (t === "mesh" || t === "mesh_shaded") ? grid : [1, 1];
      const spec = buildWarpSpec(p, t, useGrid);
      const [ny, nx] = spec.grid;
      const idx = gridIndices(ny, nx);
      for (let k = 0; k < idx.length; k += 3) {
        const i0 = idx[k], i1 = idx[k + 1], i2 = idx[k + 2];
        drawTexTri(c, img, iw, ih, spec.uv[i0], spec.uv[i1], spec.uv[i2],
                   spec.screen[i0], spec.screen[i1], spec.screen[i2]);
      }
    }
    if (maskCanvas) {                          // 마스크 있으면 클립(yolo), 없으면 별 알파만
      c.globalCompositeOperation = "destination-in";
      c.drawImage(maskCanvas, 0, 0);
      c.globalCompositeOperation = "source-over";
    }
    outCtx.drawImage(tmp, 0, 0);
  }
}

// NOTE(P0-2): 실기기 검증 대기 항목 — (1) ORT WebGPU와 본 WebGL2 동시 점유 시 모바일
// 컨텍스트 lost 빈도, (2) highp 미지원 기기 plane 강등, (3) 마스크 텍스처 GPU↔CPU 비용.
// 검증 전까지 yolo.html은 기존 경로 유지, 본 엔진은 ?engine=1 옵트인으로 노출.
