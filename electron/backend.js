// backend.js — 기존 Python 서버/스크립트 + adb 를 child_process 로 감싸는 오케스트레이션.
// 서버 코드는 전혀 수정하지 않는다. 이 파일이 "껍데기"의 손발.
const { spawn, execFile } = require("child_process");
const path = require("path");
const fs = require("fs");

// repo 루트 탐색: 개발(=electron/..) → 패키징 시엔 그 위치에 web/이 없으므로
// NAIL_REPO 환경변수 → 고정 경로 순으로 폴백(패키징 배포 대비).
function findRoot() {
  const cands = [
    process.env.NAIL_REPO,
    path.resolve(__dirname, ".."),
    "C:\\Users\\k1212\\Desktop\\TOY\\nail_ar_mvp",
  ].filter(Boolean);
  for (const c of cands) {
    try { if (fs.existsSync(path.join(c, "web", "edge_serve.py"))) return c; } catch {}
  }
  return path.resolve(__dirname, "..");
}
const ROOT = findRoot();                                    // 저장소 루트
const PY = path.join(ROOT, ".venv", "Scripts", "python.exe"); // 클린 venv 파이썬
const ENV = { ...process.env, PYTHONUTF8: "1", PYTHONUNBUFFERED: "1" };

// --- adb 경로 해결: PATH → winget scrcpy 번들 ---
function resolveAdb() {
  const local = process.env.LOCALAPPDATA || "";
  const base = path.join(local, "Microsoft", "WinGet", "Packages");
  try {
    const stack = [base];
    while (stack.length) {
      const d = stack.pop();
      let ents;
      try { ents = fs.readdirSync(d, { withFileTypes: true }); } catch { continue; }
      for (const e of ents) {
        const p = path.join(d, e.name);
        if (e.isDirectory()) stack.push(p);
        else if (e.name === "adb.exe" && p.toLowerCase().includes("scrcpy")) return p;
      }
    }
  } catch {}
  return "adb"; // PATH 폴백
}
const ADB = resolveAdb();

const procs = {};   // name -> ChildProcess (edge_serve, eye_reg)

function spawnPy(name, args, onLine) {
  if (procs[name]) return { ok: false, msg: `${name} 이미 실행중` };
  const cp = spawn(PY, args, { cwd: ROOT, env: ENV });
  procs[name] = cp;
  const feed = (buf) => String(buf).split(/\r?\n/).forEach((l) => l && onLine && onLine(name, l));
  cp.stdout.on("data", feed);
  cp.stderr.on("data", feed);
  cp.on("exit", (code) => { onLine && onLine(name, `[exit ${code}]`); delete procs[name]; });
  return { ok: true };
}

function kill(name) {
  const cp = procs[name];
  if (!cp) return { ok: false, msg: `${name} 미실행` };
  // 윈도우: 트리 종료
  try { execFile("taskkill", ["/PID", String(cp.pid), "/T", "/F"]); } catch {}
  delete procs[name];
  return { ok: true };
}

function adb(args) {
  return new Promise((res) => {
    execFile(ADB, args, { env: { ...ENV, ADB_LIBUSB: "0" } }, (err, so, se) =>
      res({ ok: !err, out: (so || "") + (se || ""), code: err ? err.code : 0 }));
  });
}

// --- 고수준 액션 ---
const api = {
  info: () => ({ ROOT, PY, ADB, pyExists: fs.existsSync(PY) }),

  startServer: (onLine) => spawnPy("edge_serve", ["web/edge_serve.py"], onLine),
  stopServer: () => kill("edge_serve"),

  startEyeReg: (onLine, opts = {}) => {
    const a = ["-u", "web/eye_reg.py", "--fps", String(opts.fps || 2),
      "--package", opts.package || "com.DefaultCompany.NailMesh", "--dominant", opts.dominant || "right"];
    if (opts.calibScale) a.push("--calib-scale", String(opts.calibScale));
    return spawnPy("eye_reg", a, onLine);
  },
  stopEyeReg: () => kill("eye_reg"),

  async devices() { return (await adb(["devices", "-l"])).out; },
  async connectGlasses(pkg = "com.DefaultCompany.NailMesh") {
    const steps = [];
    steps.push("reverse: " + (await adb(["reverse", "tcp:8443", "tcp:8443"])).out.trim());
    await adb(["shell", "input", "keyevent", "KEYCODE_WAKEUP"]);
    await adb(["shell", "svc", "power", "stayon", "true"]);
    steps.push("launch: " + (await adb(["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])).out.split("\n").find((l) => /injected|Error/.test(l)));
    return steps.join("\n");
  },
  async reverseList() { return (await adb(["reverse", "--list"])).out; },

  // 라이브 프리뷰: 안경 카메라 최근 프레임을 data URL 로
  frame(kind = "frame") {
    const f = path.join(ROOT, kind === "detect" ? "_last_detect.jpg" : "_last_frame.jpg");
    try {
      const b = fs.readFileSync(f);
      return { ok: true, dataUrl: "data:image/jpeg;base64," + b.toString("base64"),
        mtime: fs.statSync(f).mtimeMs };
    } catch { return { ok: false }; }
  },

  // 모니터 보정 서브커맨드 래핑
  monitorCalib: (sub, onLine, extra = []) =>
    spawnPy("moncalib_" + sub + "_" + Date.now(), ["web/monitor_calib_run.py", sub, ...extra], onLine),

  // 서버 최근 infer 로그에서 nails 수 파싱(상태판용)
  runningNames: () => Object.keys(procs),
};

module.exports = { api, ADB, ROOT, PY };
