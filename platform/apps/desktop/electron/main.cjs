// Electron 메인 — dev면 Vite 서버, prod면 빌드된 dist 로드.
const { app, BrowserWindow } = require("electron");
const path = require("node:path");

const DEV = !!process.env.VITE_DEV_SERVER_URL || !app.isPackaged;

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    title: "네일샵 백오피스",
    webPreferences: { contextIsolation: true },
  });
  if (process.env.VITE_DEV_SERVER_URL) win.loadURL(process.env.VITE_DEV_SERVER_URL);
  else win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
