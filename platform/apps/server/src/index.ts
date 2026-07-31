/** @nail/server — Fastify 백엔드 (REST + WebSocket). 동기화 허브. */
import Fastify from "fastify";
import cors from "@fastify/cors";
import websocket from "@fastify/websocket";
import fstatic from "@fastify/static";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { registerAuth } from "./auth.js";
import { routes } from "./routes.js";
import { hub } from "./hub.js";

const app = Fastify({ logger: { transport: undefined } });

await app.register(cors, { origin: true });
await registerAuth(app);
await app.register(websocket);
await app.register(routes);

app.get("/api/health", async () => ({ ok: true }));

// 프론트(빌드된 웹) 서빙 — WEB_DIR(있으면). 같은 오리진이라 CORS·IP 불필요.
const webDir = process.env.WEB_DIR ?? join(process.cwd(), "web");
if (existsSync(join(webDir, "index.html"))) {
  await app.register(fstatic, { root: webDir });
  app.setNotFoundHandler((req, reply) => {
    if (req.url.startsWith("/api") || req.url.startsWith("/ws")) return reply.code(404).send({ error: "not found" });
    return reply.sendFile("index.html"); // SPA fallback
  });
  console.log(`[nail-server] serving web from ${webDir}`);
}

// WebSocket: 앱 구독자 + 안경측 에이전트(?role=agent)
app.get("/ws", { websocket: true }, (socket, req) => {
  const isAgent = (req.query as { role?: string })?.role === "agent";
  if (isAgent) { hub.setAgent(socket); app.log.info("agent connected"); }
  else hub.addClient(socket);

  socket.on("message", (raw: Buffer) => {
    try {
      const m = JSON.parse(raw.toString());
      if (isAgent && m.type === "agent.status") hub.setStream({ state: m.state, fps: m.fps, glassesConnected: m.glassesConnected });
    } catch { /* noop */ }
  });
  socket.on("close", () => { isAgent ? hub.clearAgent() : hub.removeClient(socket); });
});

const port = Number(process.env.PORT ?? 3001);
await app.listen({ host: "0.0.0.0", port });
console.log(`[nail-server] http://localhost:${port}  (REST /api/*, WS /ws)`);
