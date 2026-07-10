// 브라우저 온디바이스 "실제 손톱 인식" — YOLOv8-seg ONNX를 onnxruntime-web로 실행.
// PC에서 검증한 디코드(letterbox→추론→앵커필터→NMS→마스크)를 그대로 JS로 옮김.
// 별을 각 손톱의 실제 마스크에 클리핑해 얹는다.
import * as ort from "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/ort.webgpu.bundle.min.mjs";
ort.env.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/";
import { NailDesignRenderer } from "./design_render.js";   // A3 워핑 엔진(옵트인)

const MODEL = "nails_seg.onnx";
const S = 640, NA = 8400, NC = 37, PH = 160, PW = 160, PN = PH * PW;
let CONF = 0.20, IOU = 0.5;   // 검출 잘 안 되면 더 낮춰보기(?conf=0.1)
const _qc = new URLSearchParams(location.search).get("conf");
if (_qc) CONF = parseFloat(_qc) || CONF;

const view = document.getElementById("view");
const ctx = view.getContext("2d");
const hud = document.getElementById("hud");
const msg = document.getElementById("msg");
const controls = document.getElementById("controls");

// 오프스크린들
const pre = document.createElement("canvas"); pre.width = S; pre.height = S;
const pctx = pre.getContext("2d", { willReadFrequently: true });
const m160 = document.createElement("canvas"); m160.width = PW; m160.height = PH;
const mctx = m160.getContext("2d");
let maskCv = document.createElement("canvas");   // 원본 프레임 크기 union 마스크
let designCv = document.createElement("canvas"); // 원본 프레임 크기 디자인 레이어

let session = null, video = null, stream = null, facing = "environment";
let star = null, designScale = 0.85, showDesign = true;
let fpsEma = 0, tPrev = performance.now();

// A3 워핑 엔진 옵트인: ?engine=1 [&curve=0.6]. 기본은 레거시 별 경로(P0-2 실기기 미검증).
const _q = new URLSearchParams(location.search);
const USE_ENGINE = _q.has("engine");
const ENGINE_CURVE = parseFloat(_q.get("curve") || "0") || 0;
let engineRenderer = null;

function setMsg(t) { msg.textContent = t; msg.classList.toggle("hidden", !t); }

async function loadStar() {
  star = new Image();
  await new Promise((res, rej) => { star.onload = res; star.onerror = rej; star.src = "star.png"; });
}

async function initModel() {
  session = await ort.InferenceSession.create(MODEL, {
    executionProviders: ["webgpu", "wasm"],
    graphOptimizationLevel: "all",
  });
}

async function startCamera() {
  if (stream) stream.getTracks().forEach(t => t.stop());
  stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 720 } },
    audio: false,
  });
  if (!video) { video = document.createElement("video"); video.playsInline = true; video.muted = true; }
  video.srcObject = stream;
  await video.play();
}

// letterbox 640 + CHW float 텐서
function preprocess(W, H) {
  const r = Math.min(S / W, S / H), nw = Math.round(W * r), nh = Math.round(H * r);
  const px = (S - nw) >> 1, py = (S - nh) >> 1;
  pctx.fillStyle = "rgb(114,114,114)"; pctx.fillRect(0, 0, S, S);
  pctx.drawImage(video, 0, 0, W, H, px, py, nw, nh);
  const d = pctx.getImageData(0, 0, S, S).data;
  const f = new Float32Array(3 * S * S), n = S * S;
  for (let i = 0; i < n; i++) { f[i] = d[i * 4] / 255; f[i + n] = d[i * 4 + 1] / 255; f[i + 2 * n] = d[i * 4 + 2] / 255; }
  return { tensor: new ort.Tensor("float32", f, [1, 3, S, S]), r, px, py, nw, nh };
}

const sigmoid = x => 1 / (1 + Math.exp(-x));

function iou(a, b) {
  const x1 = Math.max(a.x1, b.x1), y1 = Math.max(a.y1, b.y1);
  const x2 = Math.min(a.x2, b.x2), y2 = Math.min(a.y2, b.y2);
  const w = Math.max(0, x2 - x1), h = Math.max(0, y2 - y1), inter = w * h;
  const ua = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter;
  return ua > 0 ? inter / ua : 0;
}

// PCA(2x2) → 주축 단위벡터 + 길이/폭 (입력: 160공간 픽셀들)
function pca(pts) {
  let mx = 0, my = 0; for (const p of pts) { mx += p[0]; my += p[1]; } mx /= pts.length; my /= pts.length;
  let a = 0, b = 0, c = 0;
  for (const p of pts) { const dx = p[0] - mx, dy = p[1] - my; a += dx * dx; b += dx * dy; c += dy * dy; }
  a /= pts.length; b /= pts.length; c /= pts.length;
  const tr = a + c, det = a * c - b * b, l1 = tr / 2 + Math.sqrt(Math.max(0, tr * tr / 4 - det));
  let ex = b, ey = l1 - a; if (Math.abs(b) < 1e-6) { ex = (a >= c) ? 1 : 0; ey = (a >= c) ? 0 : 1; }
  const L = Math.hypot(ex, ey) || 1; ex /= L; ey /= L;
  if (ey > 0) { ex = -ex; ey = -ey; }              // 영상 위쪽을 tip으로
  const nxv = -ey, nyv = ex;
  let tmin = 1e9, tmax = -1e9, smin = 1e9, smax = -1e9;
  for (const p of pts) {
    const dx = p[0] - mx, dy = p[1] - my;
    const t = dx * ex + dy * ey, su = dx * nxv + dy * nyv;
    if (t < tmin) tmin = t; if (t > tmax) tmax = t; if (su < smin) smin = su; if (su > smax) smax = su;
  }
  // 청구항2: 무게중심 → 방향 박스 중심(주축 투영 min~max 중점). 엄지 등
  // 비대칭/부분 손톱에서 별이 한쪽으로 쏠리던 것을 정중앙으로 보정.
  const tmid = (tmin + tmax) / 2, smid = (smin + smax) / 2;
  const cx = mx + ex * tmid + nxv * smid;
  const cy = my + ey * tmid + nyv * smid;
  return { mx: cx, my: cy, ex, ey, len: tmax - tmin, wid: smax - smin };
}

function detect(W, H) {
  return session.run({ images: preTensor.tensor }).then(out => {
    const o0 = out.output0.data, o1 = out.output1.data;
    const { r, px, py } = preTensor;
    // 후보 + NMS
    const cand = [];
    let maxSc = 0;                                   // 디버그: 임계 미만이라도 최고 점수
    for (let i = 0; i < NA; i++) {
      const sc = o0[4 * NA + i];
      if (sc > maxSc) maxSc = sc;
      if (sc < CONF) continue;
      const cx = o0[i], cy = o0[NA + i], w = o0[2 * NA + i], h = o0[3 * NA + i];
      cand.push({ x1: cx - w / 2, y1: cy - h / 2, x2: cx + w / 2, y2: cy + h / 2, sc, i });
    }
    detect._maxSc = maxSc;
    cand.sort((p, q) => q.sc - p.sc);
    const keep = [];
    for (const cnd of cand) { let ok = true; for (const k of keep) if (iou(cnd, k) > IOU) { ok = false; break; } if (ok) keep.push(cnd); if (keep.length >= 12) break; }

    // 마스크 + 기하 (160공간 → 원본좌표)
    const maskAccum = new Uint8Array(PN);
    const nails = [];
    const to_orig = (mx160, my160) => [((mx160 * 4) - px) / r, ((my160 * 4) - py) / r];
    for (const k of keep) {
      const coef = new Float32Array(32);
      for (let j = 0; j < 32; j++) coef[j] = o0[(5 + j) * NA + k.i];
      const bx1 = Math.max(0, Math.floor(k.x1 / 4)), by1 = Math.max(0, Math.floor(k.y1 / 4));
      const bx2 = Math.min(PW - 1, Math.ceil(k.x2 / 4)), by2 = Math.min(PH - 1, Math.ceil(k.y2 / 4));
      const pts = [];
      for (let my = by1; my <= by2; my++) {
        for (let mx = bx1; mx <= bx2; mx++) {
          const p = my * PW + mx; let s = 0;
          for (let j = 0; j < 32; j++) s += coef[j] * o1[j * PN + p];
          if (sigmoid(s) > 0.5) { maskAccum[p] = 255; pts.push([mx, my]); }
        }
      }
      if (pts.length < 8) continue;
      const g = pca(pts);
      const [cx, cy] = to_orig(g.mx, g.my);
      nails.push({ cx, cy, ex: g.ex, ey: g.ey, len: g.len * 4 / r, wid: g.wid * 4 / r });
    }
    return { nails, maskAccum, r, px, py };
  });
}

let preTensor = null;

function renderClippedStars(res, W, H) {
  if (designCv.width !== W) { designCv.width = W; designCv.height = H; maskCv.width = W; maskCv.height = H; }
  const dctx = designCv.getContext("2d");
  dctx.clearRect(0, 0, W, H);
  for (const n of res.nails) {
    const w = n.wid * designScale, h = n.len * designScale;
    if (w < 3 || h < 3) continue;
    const ang = Math.atan2(n.ex, -n.ey);
    dctx.save(); dctx.translate(n.cx, n.cy); dctx.rotate(ang);
    dctx.drawImage(star, -w / 2, -h / 2, w, h); dctx.restore();
  }
  // union 마스크(160) → 원본크기, content 영역만 매핑
  const id = mctx.createImageData(PW, PH); const a = id.data;
  for (let p = 0; p < PN; p++) { const v = res.maskAccum[p]; a[p * 4] = 255; a[p * 4 + 1] = 255; a[p * 4 + 2] = 255; a[p * 4 + 3] = v; }
  mctx.putImageData(id, 0, 0);
  const mc = maskCv.getContext("2d"); mc.clearRect(0, 0, W, H);
  const sx = res.px / 4, sy = res.py / 4, sw = (S - 2 * res.px) / 4, sh = (S - 2 * res.py) / 4;
  mc.imageSmoothingEnabled = false;
  mc.drawImage(m160, sx, sy, sw, sh, 0, 0, W, H);
  // 디자인 ∩ 마스크
  dctx.globalCompositeOperation = "destination-in";
  dctx.drawImage(maskCv, 0, 0);
  dctx.globalCompositeOperation = "source-over";
  ctx.drawImage(designCv, 0, 0);
}

// A3 엔진 경로(옵트인): union 마스크 빌드 후 WarpSpec 메시 렌더(곡면/기울기). 레거시와 별개.
function renderWithEngine(res, W, H) {
  if (maskCv.width !== W) { maskCv.width = W; maskCv.height = H; }
  const id = mctx.createImageData(PW, PH); const a = id.data;
  for (let p = 0; p < PN; p++) { const v = res.maskAccum[p]; a[p * 4] = 255; a[p * 4 + 1] = 255; a[p * 4 + 2] = 255; a[p * 4 + 3] = v; }
  mctx.putImageData(id, 0, 0);
  const mc = maskCv.getContext("2d"); mc.clearRect(0, 0, W, H);
  const sx = res.px / 4, sy = res.py / 4, sw = (S - 2 * res.px) / 4, sh = (S - 2 * res.py) / 4;
  mc.imageSmoothingEnabled = true; mc.drawImage(m160, sx, sy, sw, sh, 0, 0, W, H);
  engineRenderer.opts.scale = designScale;
  engineRenderer.render(res.nails, W, H, maskCv, ctx, fpsEma);
}

async function loop() {
  if (video && video.readyState >= 2) {
    const W = video.videoWidth, H = video.videoHeight;
    if (view.width !== W) { view.width = W; view.height = H; }
    ctx.drawImage(video, 0, 0, W, H);
    try {
      preTensor = preprocess(W, H);
      const res = await detect(W, H);
      if (showDesign && star) {
        if (USE_ENGINE && engineRenderer) renderWithEngine(res, W, H);
        else renderClippedStars(res, W, H);
      }
      const now = performance.now(); const dt = now - tPrev; tPrev = now;
      if (dt > 0) { const f = 1000 / dt; fpsEma = fpsEma ? 0.9 * fpsEma + 0.1 * f : f; }
      const best = (detect._maxSc || 0).toFixed(2);
      hud.textContent = `fps ${fpsEma.toFixed(1)}   nails ${res.nails.length}   best ${best}  (conf≥${CONF})`;
    } catch (e) { console.error(e); hud.textContent = "추론 오류: " + e.message; }
  }
  requestAnimationFrame(loop);
}

async function main() {
  try {
    await loadStar();
    if (USE_ENGINE) {
      engineRenderer = new NailDesignRenderer({ scale: designScale, curve: ENGINE_CURVE, meshGrid: [10, 8] });
      engineRenderer.setAtlas(star);          // 별을 정규 UV 아틀라스로 사용(임의 디자인 교체 가능)
      console.log("[design] A3 엔진 옵트인 — 백엔드:", engineRenderer.backend, "curve:", ENGINE_CURVE);
    }
    setMsg("모델 로딩 중… (46MB, 처음만)");
    await initModel();
    setMsg("카메라 시작 중…");
    await startCamera();
    setMsg(""); controls.classList.remove("hidden");
    loop();
  } catch (e) {
    setMsg("오류: " + (e && e.message ? e.message : e) +
      "\n(HTTPS·카메라권한 확인. WebGPU 미지원 기기면 wasm으로 느릴 수 있음)");
    console.error(e);
  }
}

document.getElementById("flip").onclick = async () => {
  facing = (facing === "environment") ? "user" : "environment";
  try { await startCamera(); } catch (e) { setMsg("카메라 전환 실패: " + e.message); }
};
document.getElementById("toggle").onclick = () => { showDesign = !showDesign; };
document.getElementById("size").oninput = e => { designScale = parseFloat(e.target.value); };
view.addEventListener("click", () => { showDesign = !showDesign; });

main();
