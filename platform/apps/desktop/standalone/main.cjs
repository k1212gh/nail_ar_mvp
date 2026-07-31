// 네일샵 백오피스 데스크톱(윈도우) 앱 — 배포 백엔드 URL을 감싸는 네이티브 창.
// 서버 = API+웹 같은 오리진(@fastify/static). NAIL_APP_URL 로 대상 서버 변경 가능.
const { app, BrowserWindow, Menu } = require("electron");

const APP_URL = process.env.NAIL_APP_URL || "http://161.33.176.78:3001";

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    title: "네일샵 백오피스",
    webPreferences: { contextIsolation: true },
  });
  win.loadURL(APP_URL);
  win.webContents.on("did-fail-load", (_e, code, desc) => {
    win.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(
      `<body style="font-family:system-ui;background:#f6f5f8;color:#1e1b24;text-align:center;padding-top:15%">
       <h2>💅 서버에 연결 중…</h2><p style="color:#8a8593">${APP_URL}<br>(${desc || code}) 5초 후 재시도</p></body>`));
    setTimeout(() => win.loadURL(APP_URL), 5000);
  });
}

app.whenReady().then(() => { Menu.setApplicationMenu(null); createWindow(); });
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
