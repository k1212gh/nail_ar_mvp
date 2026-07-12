// main.js — Electron 메인. 창 생성 + IPC 핸들러로 backend.js 를 렌더러에 노출.
const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const backend = require("./backend");

let win = null;
const log = (name, line) => { if (win && !win.isDestroyed()) win.webContents.send("log", { name, line }); };

function createWindow() {
  win = new BrowserWindow({
    width: 1180, height: 820, title: "네일-AR 보정 스테이션",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false },
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

// --- IPC: 렌더러 버튼 → backend ---
ipcMain.handle("info", () => backend.api.info());
ipcMain.handle("startServer", () => backend.api.startServer(log));
ipcMain.handle("stopServer", () => backend.api.stopServer());
ipcMain.handle("startEyeReg", (_e, opts) => backend.api.startEyeReg(log, opts));
ipcMain.handle("stopEyeReg", () => backend.api.stopEyeReg());
ipcMain.handle("devices", () => backend.api.devices());
ipcMain.handle("connectGlasses", (_e, pkg) => backend.api.connectGlasses(pkg));
ipcMain.handle("reverseList", () => backend.api.reverseList());
ipcMain.handle("frame", (_e, kind) => backend.api.frame(kind));
ipcMain.handle("running", () => backend.api.runningNames());
ipcMain.handle("monitorCalib", (_e, sub, extra) => backend.api.monitorCalib(sub, log, extra));

app.whenReady().then(createWindow);
app.on("window-all-closed", () => {
  backend.api.stopServer(); backend.api.stopEyeReg();
  if (process.platform !== "darwin") app.quit();
});
app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
