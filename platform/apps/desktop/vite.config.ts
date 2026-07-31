import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" → Electron file:// 로드. dev proxy → 백엔드(3001)로 /api·/ws 전달(같은 오리진처럼).
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:3001",
      "/ws": { target: "ws://localhost:3001", ws: true },
    },
  },
  build: { outDir: "dist" },
});
