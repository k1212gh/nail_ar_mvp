export * from "./models.js";
export * from "./ws.js";
export * from "./client.js";

/** 백엔드 REST 경로 상수 (프론트 3종 공유). */
export const API = {
  auth: { login: "/api/auth/login", me: "/api/auth/me", password: "/api/auth/password" },
  members: "/api/members",
  reservations: "/api/reservations",
  services: "/api/services",
  designs: "/api/designs",
  deviceProfiles: "/api/device-profiles",
  settings: "/api/settings", // GET 설정 / PATCH 부분수정 / POST /test-edge 폰연결테스트
  stream: "/api/stream", // GET 상태 / POST {on:boolean} 제어
  ws: "/ws",
} as const;
