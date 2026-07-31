/**
 * @nail/agent — 안경측 로컬 PC 상주. VM 백엔드 WS에 붙어 "중계 켜/꺼" 명령을 받아
 * 오늘 만든 파이프라인(edge_serve.py + relay_compose_push.py)을 start/stop 한다.
 * 아웃바운드 WS만 쓰므로 집 ISP의 22 차단 등과 무관.
 *
 * P1 뼈대: 프로세스 spawn/kill + 상태보고. 안경 wake(adb)·자동재시작은 이후 보강.
 */
import { spawn, type ChildProcess } from "node:child_process";
import WebSocket from "ws";
import type { ServerEvent, AgentReport } from "@nail/shared";

const {
  SERVER_WS = "ws://localhost:3001/ws?role=agent",
  AGENT_ID = "shop-pc-1",
  REPO_DIR = process.cwd(),
  ADB = "adb",
  RELAY_URL = "http://localhost:8090",
  PUSH_TOKEN = "",
  GLASSES_PKG = "com.DefaultCompany.NailGuide",
} = process.env;

type StartCfg = { edgeEngine?: "pc" | "phone"; phoneHost?: string; phonePort?: number; penOcclusion?: boolean };

let edge: ChildProcess | null = null;
let compositor: ChildProcess | null = null;
let ws: WebSocket | null = null;

function report(r: AgentReport) { ws?.readyState === WebSocket.OPEN && ws.send(JSON.stringify(r)); }

function startStream(cfg: StartCfg = {}) {
  if (edge || compositor) return;
  const engine = cfg.edgeEngine ?? "pc";
  report({ type: "agent.status", state: "starting", detail: `engine=${engine}` });
  // 안경 wake (best-effort)
  try { spawn(ADB, ["shell", "input", "keyevent", "KEYCODE_WAKEUP"], { stdio: "ignore" }); } catch { /* noop */ }

  if (engine === "phone") {
    // 폰 온디바이스 검출: 안경을 폰 EdgeServer 소켓으로 지정(같은 WiFi). PC는 edge_serve 미실행.
    const host = cfg.phoneHost || "";
    const port = String(cfg.phonePort || 8444);
    if (!host) { report({ type: "agent.status", state: "error", detail: "phoneHost 미설정" }); return; }
    try {
      spawn("python", ["web/push_calib.py", `pkg=${GLASSES_PKG}`, "useSocket=1", `sockHost=${host}`, `sockPort=${port}`],
        { cwd: REPO_DIR, stdio: "ignore" });
    } catch { /* noop */ }
    // 폰엔 웹 모니터(/last.jpg)가 없어 컴포지터 DET 패널은 대기표시 — 안경 AR 화면은 정상 방송.
  } else {
    // PC 에지: adb reverse + edge_serve.py(GPU YOLO). 펜 가림 데모 on/off 전달.
    for (const args of [["reverse", "tcp:8443", "tcp:8443"], ["reverse", "tcp:8444", "tcp:8444"], ["reverse", "tcp:8080", "tcp:8080"]]) {
      try { spawn(ADB, args, { stdio: "ignore" }); } catch { /* noop */ }
    }
    // 폰→PC 전환 대비: 안경 전송을 USB로 되돌림(이전에 폰 소켓으로 잡혀있으면 PC edge에 안 붙음).
    try {
      spawn("python", ["web/push_calib.py", `pkg=${GLASSES_PKG}`, "useSocket=0", "edgeUrl=https://127.0.0.1:8443/infer"],
        { cwd: REPO_DIR, stdio: "ignore" });
    } catch { /* noop */ }
    edge = spawn("python", ["web/edge_serve.py"], {
      cwd: REPO_DIR, stdio: "ignore",
      env: { ...process.env, NAIL_OCC_DEMO: cfg.penOcclusion === false ? "0" : "1" },
    });
  }
  // 앱 실행 (NailGuide) — 잠시 뒤
  setTimeout(() => spawn(ADB, ["shell", "monkey", "-p", GLASSES_PKG, "-c", "android.intent.category.LAUNCHER", "1"], { stdio: "ignore" }), 3000);
  // 컴포지터(안경AR + (있으면)검출뷰 → 릴레이). AR 화면은 엔진과 무관하게 동일 방송.
  compositor = spawn("python", ["web/relay_compose_push.py"], {
    cwd: REPO_DIR, stdio: "ignore",
    env: { ...process.env, ADB, RELAY_URL, PUSH_TOKEN, COMPOSE_FPS: "20", WORKERS: "4" },
  });
  report({ type: "agent.status", state: "on", detail: `engine=${engine}` });
}

function stopStream() {
  edge?.kill(); compositor?.kill();
  edge = compositor = null;
  try { spawn(ADB, ["shell", "svc", "power", "stayon", "false"], { stdio: "ignore" }); } catch { /* noop */ }
  report({ type: "agent.status", state: "off" });
}

function connect() {
  ws = new WebSocket(SERVER_WS);
  ws.on("open", () => report({ type: "agent.hello", agentId: AGENT_ID }));
  ws.on("message", (raw) => {
    try {
      const ev = JSON.parse(raw.toString()) as ServerEvent;
      if (ev.type === "agent.command") {
        if (ev.command === "stream.start") startStream({ edgeEngine: ev.edgeEngine, phoneHost: ev.phoneHost, phonePort: ev.phonePort, penOcclusion: ev.penOcclusion });
        else stopStream();
      }
    } catch { /* noop */ }
  });
  ws.on("close", () => { setTimeout(connect, 3000); }); // 자동 재접속
  ws.on("error", () => ws?.close());
}

connect();
console.log(`[agent] ${AGENT_ID} → ${SERVER_WS}`);
