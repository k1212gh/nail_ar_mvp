/** 프레임워크 무관 API 클라이언트 (데스크톱·모바일 공유). fetch 기반. */
import { API } from "./index.js";

export type LoginResult = { token: string; user: { id: string; name: string; role: string } };

export function createClient(baseUrl: string, getToken: () => string | null) {
  const req = async (path: string, init: RequestInit = {}) => {
    const token = getToken();
    const res = await fetch(baseUrl + path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers ?? {}),
      },
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.error ?? `HTTP ${res.status}`);
    return res.status === 204 ? null : res.json();
  };
  return {
    login: (name: string, password: string): Promise<LoginResult> =>
      req(API.auth.login, { method: "POST", body: JSON.stringify({ name, password }) }),
    me: () => req(API.auth.me),
    changePassword: (current: string, next: string) => req(API.auth.password, { method: "POST", body: JSON.stringify({ current, next }) }),
    members: {
      list: () => req(API.members),
      create: (m: any) => req(API.members, { method: "POST", body: JSON.stringify(m) }),
      update: (id: string, m: any) => req(`${API.members}/${id}`, { method: "PATCH", body: JSON.stringify(m) }),
      remove: (id: string) => req(`${API.members}/${id}`, { method: "DELETE" }),
    },
    reservations: {
      list: (q?: { from?: string; to?: string }) => req(API.reservations + (q ? `?${new URLSearchParams(q as any)}` : "")),
      create: (r: any) => req(API.reservations, { method: "POST", body: JSON.stringify(r) }),
      update: (id: string, r: any) => req(`${API.reservations}/${id}`, { method: "PATCH", body: JSON.stringify(r) }),
      remove: (id: string) => req(`${API.reservations}/${id}`, { method: "DELETE" }),
    },
    services: { list: () => req(API.services), create: (s: any) => req(API.services, { method: "POST", body: JSON.stringify(s) }) },
    designs: {
      list: () => req(API.designs),
      create: (d: any) => req(API.designs, { method: "POST", body: JSON.stringify(d) }),
      remove: (id: string) => req(`${API.designs}/${id}`, { method: "DELETE" }),
    },
    deviceProfiles: {
      list: () => req(API.deviceProfiles),
      create: (p: any) => req(API.deviceProfiles, { method: "POST", body: JSON.stringify(p) }),
      update: (id: string, p: any) => req(`${API.deviceProfiles}/${id}`, { method: "PATCH", body: JSON.stringify(p) }),
    },
    stream: { get: () => req(API.stream), set: (on: boolean) => req(API.stream, { method: "POST", body: JSON.stringify({ on }) }) },
    settings: {
      get: () => req(API.settings),
      update: (patch: any) => req(API.settings, { method: "PATCH", body: JSON.stringify(patch) }),
      testEdge: (body?: { host?: string; port?: number }) => req(`${API.settings}/test-edge`, { method: "POST", body: JSON.stringify(body ?? {}) }),
    },
  };
}
export type NailApi = ReturnType<typeof createClient>;
