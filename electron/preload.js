// preload.js — 렌더러에 안전한 API 만 노출(contextBridge). nodeIntegration 없이 IPC 브리지.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("api", {
  info: () => ipcRenderer.invoke("info"),
  startServer: () => ipcRenderer.invoke("startServer"),
  stopServer: () => ipcRenderer.invoke("stopServer"),
  startEyeReg: (opts) => ipcRenderer.invoke("startEyeReg", opts),
  stopEyeReg: () => ipcRenderer.invoke("stopEyeReg"),
  devices: () => ipcRenderer.invoke("devices"),
  connectGlasses: (pkg) => ipcRenderer.invoke("connectGlasses", pkg),
  reverseList: () => ipcRenderer.invoke("reverseList"),
  frame: (kind) => ipcRenderer.invoke("frame", kind),
  running: () => ipcRenderer.invoke("running"),
  monitorCalib: (sub, extra) => ipcRenderer.invoke("monitorCalib", sub, extra),
  onLog: (cb) => ipcRenderer.on("log", (_e, d) => cb(d)),
});
