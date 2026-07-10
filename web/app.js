// 브라우저 온디바이스 네일 AR — PC `--seg none` 로직을 MediaPipe JS로 이식.
// 손 랜드마크로 손톱판 크기·위치를 추정해 별 이미지를 손톱에 얹는다(세그 없음).
import { HandLandmarker, FilesetResolver }
  from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
import { NailDesignRenderer } from "./design_render.js";   // A3 곡면·기울기 워핑 엔진

// --- PC geometry_from_roi 와 동일 비율 ---
const TIP_DIP = {
  thumb: [4, 3], index: [8, 7], middle: [12, 11], ring: [16, 15], pinky: [20, 19],
};
const CENTER_RATIO = 0.72;   // 손톱 중심 = DIP→TIP 72%
const LEN_RATIO = 0.55;      // 손톱 세로 = 끝마디 × 0.55
const WID_RATIO = 0.75;      // 손톱 가로 = 세로 × 0.75

// A3 엔진 옵션: ?flat=1(옛 평면별) | ?curve=0.55(곡률 반각) | ?notilt(z기울기 끄기)
const _Q = new URLSearchParams(location.search);
const FLAT = _Q.has("flat");
const ENGINE_CURVE = _Q.has("curve") ? (parseFloat(_Q.get("curve")) || 0) : 0.55;
const USE_TILT = !_Q.has("notilt");
const TILT_GAIN = 1.4, TILT_MAX = 55;
let engine = null;

const view = document.getElementById("view");
const ctx = view.getContext("2d");
const hud = document.getElementById("hud");
const msg = document.getElementById("msg");
const controls = document.getElementById("controls");

let landmarker = null;
let video = null;
let stream = null;
let facing = "environment";   // 후면 카메라 우선
let showDesign = true;
let designScale = 0.85;
let star = null;
let lastVideoTime = -1;
let fpsEma = 0, tPrev = performance.now();

function setMsg(t) { msg.textContent = t; msg.classList.toggle("hidden", !t); }

async function loadStar() {
  star = new Image();
  await new Promise((res, rej) => {
    star.onload = res; star.onerror = rej; star.src = "star.png";
  });
}

async function initLandmarker() {
  const fileset = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm");
  landmarker = await HandLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: "hand_landmarker.task", delegate: "GPU" },
    runningMode: "VIDEO",
    numHands: 2,
    minHandDetectionConfidence: 0.5,
    minHandPresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
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

// 손 랜드마크 → 손톱 배치(입력 영상 px)
function nailsFrom(result, W, H) {
  const out = [];
  const hands = result.landmarks || [];
  for (const lms of hands) {
    for (const k in TIP_DIP) {
      const [ti, di] = TIP_DIP[k];
      const tip = lms[ti], dip = lms[di];
      const tx = tip.x * W, ty = tip.y * H, dx = dip.x * W, dy = dip.y * H;
      const vx = tx - dx, vy = ty - dy;
      const len = Math.hypot(vx, vy);
      if (len < 1) continue;
      const nailLen = len * LEN_RATIO;
      // z(상대깊이) 차 → out-of-plane 기울기. tip이 카메라 쪽(z 작음)이면 +(확대).
      const lenN = Math.hypot(tip.x - dip.x, tip.y - dip.y) || 1e-3;
      let tiltDeg = Math.atan2(-((tip.z ?? 0) - (dip.z ?? 0)), lenN) * 180 / Math.PI * TILT_GAIN;
      tiltDeg = Math.max(-TILT_MAX, Math.min(TILT_MAX, tiltDeg));
      out.push({
        cx: dx + vx * CENTER_RATIO, cy: dy + vy * CENTER_RATIO,
        ax: vx / len, ay: vy / len,
        len: nailLen, wid: nailLen * WID_RATIO, tiltDeg,
      });
    }
  }
  return out;
}

function drawStar(n) {
  const w = n.wid * designScale, h = n.len * designScale;
  if (w < 2 || h < 2) return;
  // 이미지 '위(-y)'를 손톱 팁 방향(ax,ay)에 맞춤 (캔버스 회전, y-down)
  const ang = Math.atan2(n.ax, -n.ay);
  ctx.save();
  ctx.translate(n.cx, n.cy);
  ctx.rotate(ang);
  ctx.drawImage(star, -w / 2, -h / 2, w, h);
  ctx.restore();
}

function loop() {
  if (video && video.readyState >= 2) {
    const W = video.videoWidth, H = video.videoHeight;
    if (view.width !== W) { view.width = W; view.height = H; }
    ctx.drawImage(video, 0, 0, W, H);

    let nails = [];
    if (landmarker && video.currentTime !== lastVideoTime) {
      lastVideoTime = video.currentTime;
      const res = landmarker.detectForVideo(video, performance.now());
      nails = nailsFrom(res, W, H);
      window._lastNails = nails;
    } else {
      nails = window._lastNails || [];
    }
    if (showDesign && star) {
      if (engine) {
        engine.opts.scale = designScale;
        const arr = nails.map(n => ({ cx: n.cx, cy: n.cy, ex: n.ax, ey: n.ay,
          len: n.len, wid: n.wid, tiltDeg: USE_TILT ? n.tiltDeg : 0 }));
        engine.render(arr, W, H, null, ctx, fpsEma);     // 마스크 없음(랜드마크) → 별 알파만
      } else {
        for (const n of nails) drawStar(n);
      }
    }

    const now = performance.now();
    const dt = now - tPrev; tPrev = now;
    if (dt > 0) { const f = 1000 / dt; fpsEma = fpsEma ? 0.9 * fpsEma + 0.1 * f : f; }
    const tag = engine ? ` [${engine.backend}${ENGINE_CURVE ? " curve" : ""}${USE_TILT ? " tilt" : ""}]` : "";
    hud.textContent = `fps ${fpsEma.toFixed(1)}   nails ${nails.length}${tag}`;
  }
  requestAnimationFrame(loop);
}

async function main() {
  try {
    setMsg("별·모델 불러오는 중…");
    await loadStar();
    if (!FLAT) {
      engine = new NailDesignRenderer({ scale: designScale, curve: ENGINE_CURVE, meshGrid: [10, 8] });
      engine.setAtlas(star);
      console.log("[app] A3 엔진:", engine.backend, "curve", ENGINE_CURVE, "tilt", USE_TILT);
    }
    await initLandmarker();
    setMsg("카메라 시작 중…");
    await startCamera();
    setMsg("");
    controls.classList.remove("hidden");
    loop();
  } catch (e) {
    setMsg("오류: " + (e && e.message ? e.message : e) +
      "\n(카메라 권한/HTTPS 확인. 다른 앱이 카메라 사용 중이면 종료)");
    console.error(e);
  }
}

document.getElementById("flip").onclick = async () => {
  facing = (facing === "environment") ? "user" : "environment";
  try { await startCamera(); } catch (e) { setMsg("카메라 전환 실패: " + e.message); }
};
document.getElementById("toggle").onclick = () => { showDesign = !showDesign; };
document.getElementById("size").oninput = (e) => { designScale = parseFloat(e.target.value); };
// 화면 탭으로도 별 on/off
view.addEventListener("click", () => { showDesign = !showDesign; });

main();
