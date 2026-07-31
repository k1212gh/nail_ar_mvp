import { createClient, API } from "@nail/shared";
import type { ServerEvent, StreamSession } from "@nail/shared";

// 기본 = 같은 오리진("") — 백엔드가 이 웹을 서빙하므로 /api·/ws 상대경로.
// dev는 vite proxy가 /api·/ws를 localhost:3001로 넘김.
export const BASE = (import.meta.env.VITE_API_BASE as string) ?? "";
const TKEY = "nail.token";

export const token = {
  get: () => localStorage.getItem(TKEY),
  set: (t: string) => localStorage.setItem(TKEY, t),
  clear: () => localStorage.removeItem(TKEY),
};

export const api = createClient(BASE, token.get);

/** WS 구독 — 중계상태·예약변경 실시간 수신. onEvent 콜백 등록. */
export function connectWs(onEvent: (ev: ServerEvent) => void): () => void {
  const url = BASE.replace(/^http/, "ws") + API.ws;
  let ws: WebSocket | null = null;
  let closed = false;
  const open = () => {
    ws = new WebSocket(url);
    ws.onmessage = (m) => { try { onEvent(JSON.parse(m.data)); } catch { /* noop */ } };
    ws.onclose = () => { if (!closed) setTimeout(open, 2000); };
    ws.onerror = () => ws?.close();
  };
  open();
  return () => { closed = true; ws?.close(); };
}

export type { ServerEvent, StreamSession };
