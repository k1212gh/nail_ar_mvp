/**
 * 공유 도메인 모델 — zod 스키마 = 런타임 검증 + TS 타입(단일 정의).
 * 서버(Prisma)·데스크톱·모바일이 모두 이 타입을 사용.
 * 설계서: ../../../docs/BACKOFFICE_PLATFORM_PLAN.md §4, §9
 */
import { z } from "zod";

export const Role = z.enum(["owner", "staff", "customer"]);
export type Role = z.infer<typeof Role>;

export const ReservationStatus = z.enum(["requested", "confirmed", "done", "canceled", "noshow"]);
export type ReservationStatus = z.infer<typeof ReservationStatus>;

export const User = z.object({
  id: z.string(),
  name: z.string(),
  role: Role,
  phone: z.string().optional(),
  memberId: z.string().optional(), // customer일 때 Member와 연결
  createdAt: z.string(), // ISO
});
export type User = z.infer<typeof User>;

export const Member = z.object({
  id: z.string(),
  name: z.string(),
  phone: z.string(),
  memo: z.string().optional(),
  tags: z.array(z.string()).default([]),
  preferredDesignIds: z.array(z.string()).default([]),
  createdAt: z.string(),
});
export type Member = z.infer<typeof Member>;

export const Service = z.object({
  id: z.string(),
  name: z.string(),
  durationMin: z.number().int().positive(),
  price: z.number().nonnegative().optional(),
  category: z.string().optional(),
});
export type Service = z.infer<typeof Service>;

export const Reservation = z.object({
  id: z.string(),
  memberId: z.string().optional(),
  name: z.string(), // 비회원 예약도 허용
  phone: z.string(),
  serviceId: z.string().optional(),
  startAt: z.string(), // ISO
  endAt: z.string(),
  status: ReservationStatus,
  source: z.enum(["staff", "self"]),
  staffId: z.string().optional(),
  designId: z.string().optional(),
  photoUrls: z.array(z.string()).default([]),
  memo: z.string().optional(),
});
export type Reservation = z.infer<typeof Reservation>;

export const Design = z.object({
  id: z.string(),
  name: z.string(),
  thumbnailUrl: z.string().optional(),
  meshRef: z.string().optional(), // 기존 AR 오버레이(NailMesh) 연결
  tags: z.array(z.string()).default([]),
});
export type Design = z.infer<typeof Design>;

/** 제원 = 안경/edge 세팅 프로필 (기존 push_calib.py 대체). */
export const DeviceProfile = z.object({
  id: z.string(),
  label: z.string(),
  type: z.enum(["glasses", "phone", "edge"]),
  settings: z.record(z.union([z.number(), z.string(), z.boolean()])), // camW, inferInterval, calibOffset, guideTarget, mode ...
  active: z.boolean().default(false),
  updatedAt: z.string(),
});
export type DeviceProfile = z.infer<typeof DeviceProfile>;

/** 샵 전역 설정 — 검출 엔진(PC/폰) 선택 등. 앱 '설정' 탭에서 관리. */
export const EdgeEngine = z.enum(["pc", "phone"]);
export type EdgeEngine = z.infer<typeof EdgeEngine>;

export const ShopSettings = z.object({
  edgeEngine: EdgeEngine, // pc = 이 매장PC(GPU) / phone = 폰 온디바이스(같은 WiFi)
  phoneHost: z.string(),  // 폰 에지 IP (edgeEngine=phone일 때 안경이 붙는 대상)
  phonePort: z.number().int().positive(), // 폰 EdgeServer 소켓 포트(기본 8444)
  penOcclusion: z.boolean(), // 펜 가림방지
});
export type ShopSettings = z.infer<typeof ShopSettings>;

/** 중계(스트림) 상태 — 앱의 On/Off 버튼이 이걸 토글. */
export const StreamState = z.enum(["off", "starting", "on", "error"]);
export type StreamState = z.infer<typeof StreamState>;

export const StreamSession = z.object({
  id: z.string(),
  state: StreamState,
  agentId: z.string().optional(),
  fps: z.number().optional(),
  glassesConnected: z.boolean().optional(),
  viewerLink: z.string().optional(),
  startedBy: z.string().optional(),
  startedAt: z.string().optional(),
});
export type StreamSession = z.infer<typeof StreamSession>;
