import type { ServerEvent, StreamSession } from "@nail/shared";

/** 실시간 허브: 앱 구독자 + 안경측 에이전트 + 중계 상태. */
class Hub {
  clients = new Set<any>();
  agent: any = null;
  stream: StreamSession = { id: "s1", state: "off" };

  addClient(ws: any) { this.clients.add(ws); this.sendTo(ws, { type: "stream.state", session: this.stream }); }
  removeClient(ws: any) { this.clients.delete(ws); }
  setAgent(ws: any) { this.agent = ws; }
  clearAgent() { this.agent = null; this.setStream({ state: "off" }); }

  broadcast(ev: ServerEvent) { const m = JSON.stringify(ev); for (const c of this.clients) this.safe(c, m); }
  sendTo(ws: any, ev: ServerEvent) { this.safe(ws, JSON.stringify(ev)); }
  commandAgent(command: "stream.start" | "stream.stop", payload?: Record<string, unknown>) { if (this.agent) this.safe(this.agent, JSON.stringify({ type: "agent.command", command, ...(payload ?? {}) })); return !!this.agent; }

  setStream(patch: Partial<StreamSession>) { this.stream = { ...this.stream, ...patch }; this.broadcast({ type: "stream.state", session: this.stream }); }
  private safe(ws: any, msg: string) { try { ws.send(msg); } catch { /* noop */ } }
}
export const hub = new Hub();
