// 에지 오프로드 클라이언트 (Phase 0b) — 폰 카메라 → PC /infer(인식) → A3 곡면 렌더.
// 무거운 추론은 PC가 하므로 브라우저 ONNX(best 0.00) 우회. 추론/렌더 분리로 렌더는 매끄럽다.
import { NailDesignRenderer } from "./design_render.js";

const SEND_W = 512;                 // 서버로 보낼 프레임 가로(작을수록 빠름)
const view = document.getElementById("view");
const ctx = view.getContext("2d");
const hud = document.getElementById("hud");
const msg = document.getElementById("msg");
const controls = document.getElementById("controls");

let video = null, stream = null, facing = "environment";
let star = null, engine = null;
const _q = new URLSearchParams(location.search);
const USE_GL = _q.has("gl");            // 기본=Canvas2D 곡면 메시(확실). ?gl=1 → WebGL 시도
const DBG = _q.has("dbg");              // ?dbg=1 → 검출 외곽(초록)+중심(빨강) 표시
let designScale = 0.85, curveVal = 0.6, showDesign = true;
let busy = false, lastNails = [], lastMs = 0, lastN = 0, srvErr = "";
let fpsEma = 0, tPrev = performance.now();

const send = document.createElement("canvas");
const sctx = send.getContext("2d");

// 검출된 손톱 외곽들로 마스크 캔버스 생성 → 디자인을 실제 손톱 모양에 클리핑
const maskCv = document.createElement("canvas");
const mctx = maskCv.getContext("2d");
function buildMask(W, H) {
  if (maskCv.width !== W) { maskCv.width = W; maskCv.height = H; }
  mctx.clearRect(0, 0, W, H);
  mctx.fillStyle = "#fff";
  for (const n of lastNails) {
    const c = n.contour;
    if (!c || c.length < 3) continue;
    mctx.beginPath(); mctx.moveTo(c[0][0], c[0][1]);
    for (let i = 1; i < c.length; i++) mctx.lineTo(c[i][0], c[i][1]);
    mctx.closePath(); mctx.fill();
  }
  return maskCv;
}

function setMsg(t) { msg.textContent = t; msg.classList.toggle("hidden", !t); }

async function loadStar() {
  star = new Image();
  await new Promise((res, rej) => { star.onload = res; star.onerror = rej; star.src = "star.png"; });
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

async function infer() {
  if (busy || !video || video.readyState < 2) return;
  busy = true;
  try {
    const W = video.videoWidth, H = video.videoHeight;
    const sw = SEND_W, sh = Math.max(1, Math.round(SEND_W * H / W));
    send.width = sw; send.height = sh;
    sctx.drawImage(video, 0, 0, sw, sh);
    const blob = await new Promise(r => send.toBlob(r, "image/jpeg", 0.6));
    const resp = await fetch("/infer", { method: "POST", body: blob });
    const j = await resp.json();
    srvErr = "";
    lastMs = j.ms || 0; lastN = (j.nails || []).length;
    const sx = W / j.w, sy = H / j.h;
    lastNails = (j.nails || []).map(n => ({
      cx: n.cx * sx, cy: n.cy * sy, ex: n.ex, ey: n.ey,
      len: n.len * sx, wid: n.wid * sx, tiltDeg: 0,
      contour: (n.contour || []).map(p => [p[0] * sx, p[1] * sy]),
    }));
  } catch (e) {
    srvErr = (e && e.message) ? e.message : String(e);
  } finally {
    busy = false;
  }
}

function loop() {
  if (video && video.readyState >= 2) {
    const W = video.videoWidth, H = video.videoHeight;
    if (view.width !== W) { view.width = W; view.height = H; }
    ctx.drawImage(video, 0, 0, W, H);
    if (DBG && star && star.naturalWidth) ctx.drawImage(star, 8, 8, 64, 64);  // 좌상단 원본 별(디버그)
    if (showDesign && engine && lastNails.length) {
      engine.opts.scale = designScale;
      if ("curve" in engine.opts) engine.opts.curve = curveVal;
      // 실제 손톱 외곽 마스크에 디자인 클리핑 → 비스듬/부분이어도 손톱에 '발린' 느낌
      engine.render(lastNails, W, H, buildMask(W, H), ctx, fpsEma);
    }
    if (DBG) {   // 검출 외곽(초록)+중심(빨강) 확인용
      for (const n of lastNails) {
        if (n.contour && n.contour.length > 2) {
          ctx.strokeStyle = "rgba(0,255,0,.9)"; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(n.contour[0][0], n.contour[0][1]);
          for (let i = 1; i < n.contour.length; i++) ctx.lineTo(n.contour[i][0], n.contour[i][1]);
          ctx.closePath(); ctx.stroke();
        }
        ctx.fillStyle = "red"; ctx.beginPath(); ctx.arc(n.cx, n.cy, 5, 0, 7); ctx.fill();
      }
    }
    if (!busy) infer();                       // 왕복 끝나는 대로 다음 추론

    const now = performance.now(), dt = now - tPrev; tPrev = now;
    if (dt > 0) { const f = 1000 / dt; fpsEma = fpsEma ? 0.9 * fpsEma + 0.1 * f : f; }
    hud.textContent = `render ${fpsEma.toFixed(0)}fps  infer ${lastMs}ms  nails ${lastN}`
      + (engine ? ` [${engine.backend}]` : "") + ` star${star ? star.naturalWidth : 0}`
      + (srvErr ? `  서버오류:${srvErr}` : "");
  }
  requestAnimationFrame(loop);
}

async function main() {
  try {
    setMsg("별 로딩…"); await loadStar();
    engine = new NailDesignRenderer({ scale: designScale, curve: curveVal, meshGrid: [10, 8], force2d: !USE_GL });
    engine.setAtlas(star);
    setMsg("카메라 시작…"); await startCamera();
    setMsg(""); controls.classList.remove("hidden");
    loop();
  } catch (e) {
    setMsg("오류: " + (e && e.message ? e.message : e) + "\n(HTTPS·카메라권한 확인)");
    console.error(e);
  }
}

document.getElementById("flip").onclick = async () => {
  facing = (facing === "environment") ? "user" : "environment";
  try { await startCamera(); } catch (e) { setMsg("카메라 전환 실패: " + e.message); }
};
document.getElementById("toggle").onclick = () => { showDesign = !showDesign; };
document.getElementById("size").oninput = e => { designScale = parseFloat(e.target.value); };
document.getElementById("curve").oninput = e => { curveVal = parseFloat(e.target.value); };
view.addEventListener("click", () => { showDesign = !showDesign; });

main();
