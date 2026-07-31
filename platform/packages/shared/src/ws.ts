/** WebSocket 메시지 규격 — 실시간 동기화 + 중계 에이전트 제어. */
import { z } from "zod";
import { StreamSession, Reservation } from "./models.js";

/** 서버 → 클라이언트(앱)·에이전트 브로드캐스트 */
export const ServerEvent = z.discriminatedUnion("type", [
  z.object({ type: z.literal("stream.state"), session: StreamSession }),
  z.object({ type: z.literal("reservation.upsert"), reservation: Reservation }),
  z.object({ type: z.literal("reservation.delete"), id: z.string() }),
  // 에이전트 대상 명령 (stream.start 시 검출 엔진/폰주소 동봉)
  z.object({
    type: z.literal("agent.command"),
    command: z.enum(["stream.start", "stream.stop"]),
    edgeEngine: z.enum(["pc", "phone"]).optional(),
    phoneHost: z.string().optional(),
    phonePort: z.number().optional(),
    penOcclusion: z.boolean().optional(),
  }),
]);
export type ServerEvent = z.infer<typeof ServerEvent>;

/** 에이전트 → 서버 (상태 보고) */
export const AgentReport = z.discriminatedUnion("type", [
  z.object({ type: z.literal("agent.hello"), agentId: z.string() }),
  z.object({
    type: z.literal("agent.status"),
    state: z.enum(["off", "starting", "on", "error"]),
    fps: z.number().optional(),
    glassesConnected: z.boolean().optional(),
    detail: z.string().optional(),
  }),
]);
export type AgentReport = z.infer<typeof AgentReport>;
