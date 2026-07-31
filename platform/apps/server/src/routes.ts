import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { prisma, J, memberOut, reservationOut, designOut, profileOut, getSettings, setSettings } from "./db.js";
import net from "node:net";
import { hash, verify } from "./auth.js";
import { hub } from "./hub.js";

const relayBase = process.env.RELAY_BASE ?? "";
const relayView = process.env.RELAY_VIEW_TOKEN ?? "";

export async function routes(app: FastifyInstance) {
  const staff = { preHandler: app.requireRole("owner", "staff") };
  const owner = { preHandler: app.requireRole("owner") };

  // ---------- auth ----------
  app.post("/api/auth/login", async (req, reply) => {
    const { name, password } = z.object({ name: z.string(), password: z.string() }).parse(req.body);
    const u = await prisma.user.findFirst({ where: { name } });
    if (!u?.passwordHash || !(await verify(password, u.passwordHash))) return reply.code(401).send({ error: "invalid credentials" });
    const token = app.jwt.sign({ sub: u.id, role: u.role as any, name: u.name });
    return { token, user: { id: u.id, name: u.name, role: u.role } };
  });
  app.get("/api/auth/me", { preHandler: app.authenticate }, async (req) => req.user);

  // ---------- members ----------
  app.get("/api/members", staff, async () => (await prisma.member.findMany({ orderBy: { createdAt: "desc" } })).map(memberOut));
  app.post("/api/members", staff, async (req) => {
    const b = z.object({ name: z.string(), phone: z.string(), memo: z.string().optional(), tags: z.array(z.string()).default([]) }).parse(req.body);
    return memberOut(await prisma.member.create({ data: { name: b.name, phone: b.phone, memo: b.memo, tags: J.str(b.tags) } }));
  });
  app.patch("/api/members/:id", staff, async (req) => {
    const { id } = req.params as { id: string };
    const b = z.object({ name: z.string().optional(), phone: z.string().optional(), memo: z.string().optional(), tags: z.array(z.string()).optional() }).parse(req.body);
    return memberOut(await prisma.member.update({ where: { id }, data: { ...b, tags: b.tags ? J.str(b.tags) : undefined } }));
  });
  app.delete("/api/members/:id", owner, async (req) => { await prisma.member.delete({ where: { id: (req.params as any).id } }); return { ok: true }; });

  // ---------- services ----------
  app.get("/api/services", { preHandler: app.authenticate }, async () => prisma.service.findMany());
  app.post("/api/services", owner, async (req) => {
    const b = z.object({ name: z.string(), durationMin: z.number().int().positive(), price: z.number().optional(), category: z.string().optional() }).parse(req.body);
    return prisma.service.create({ data: b });
  });

  // ---------- reservations ----------
  app.get("/api/reservations", { preHandler: app.authenticate }, async (req) => {
    const q = z.object({ from: z.string().optional(), to: z.string().optional() }).parse(req.query);
    const where = q.from || q.to ? { startAt: { gte: q.from ? new Date(q.from) : undefined, lte: q.to ? new Date(q.to) : undefined } } : {};
    return (await prisma.reservation.findMany({ where, orderBy: { startAt: "asc" } })).map(reservationOut);
  });
  app.post("/api/reservations", { preHandler: app.authenticate }, async (req) => {
    const b = z.object({
      memberId: z.string().optional(), name: z.string(), phone: z.string(), serviceId: z.string().optional(),
      startAt: z.string(), endAt: z.string(), designId: z.string().optional(), memo: z.string().optional(),
      source: z.enum(["staff", "self"]).default("staff"),
    }).parse(req.body);
    const r = reservationOut(await prisma.reservation.create({ data: { ...b, startAt: new Date(b.startAt), endAt: new Date(b.endAt), status: b.source === "self" ? "requested" : "confirmed" } }));
    hub.broadcast({ type: "reservation.upsert", reservation: r as any });
    return r;
  });
  app.patch("/api/reservations/:id", staff, async (req) => {
    const { id } = req.params as { id: string };
    const b = z.object({ status: z.enum(["requested", "confirmed", "done", "canceled", "noshow"]).optional(), startAt: z.string().optional(), endAt: z.string().optional(), staffId: z.string().optional(), memo: z.string().optional(), designId: z.string().optional() }).parse(req.body);
    const r = reservationOut(await prisma.reservation.update({ where: { id }, data: { ...b, startAt: b.startAt ? new Date(b.startAt) : undefined, endAt: b.endAt ? new Date(b.endAt) : undefined } }));
    hub.broadcast({ type: "reservation.upsert", reservation: r as any });
    return r;
  });
  app.delete("/api/reservations/:id", staff, async (req) => { const { id } = req.params as any; await prisma.reservation.delete({ where: { id } }); hub.broadcast({ type: "reservation.delete", id }); return { ok: true }; });

  // ---------- designs ----------
  app.get("/api/designs", { preHandler: app.authenticate }, async () => (await prisma.design.findMany()).map(designOut));
  app.post("/api/designs", staff, async (req) => {
    const b = z.object({ name: z.string(), thumbnailUrl: z.string().optional(), meshRef: z.string().optional(), tags: z.array(z.string()).default([]) }).parse(req.body);
    return designOut(await prisma.design.create({ data: { ...b, tags: J.str(b.tags) } }));
  });
  app.delete("/api/designs/:id", staff, async (req) => { await prisma.design.delete({ where: { id: (req.params as any).id } }); return { ok: true }; });

  // ---------- device profiles (제원 = 안경/edge 세팅) ----------
  app.get("/api/device-profiles", staff, async () => (await prisma.deviceProfile.findMany()).map(profileOut));
  app.post("/api/device-profiles", staff, async (req) => {
    const b = z.object({ label: z.string(), type: z.enum(["glasses", "phone", "edge"]), settings: z.record(z.any()).default({}) }).parse(req.body);
    return profileOut(await prisma.deviceProfile.create({ data: { label: b.label, type: b.type, settings: J.str(b.settings) } }));
  });
  app.patch("/api/device-profiles/:id", staff, async (req) => {
    const { id } = req.params as { id: string };
    const b = z.object({ label: z.string().optional(), settings: z.record(z.any()).optional(), active: z.boolean().optional() }).parse(req.body);
    return profileOut(await prisma.deviceProfile.update({ where: { id }, data: { ...b, settings: b.settings ? J.str(b.settings) : undefined } }));
  });

  // ---------- 샵 설정 (검출 엔진 선택 등) ----------
  app.get("/api/settings", { preHandler: app.authenticate }, async () => getSettings());
  app.patch("/api/settings", owner, async (req) => {
    const b = z.object({
      edgeEngine: z.enum(["pc", "phone"]).optional(),
      phoneHost: z.string().optional(),
      phonePort: z.number().int().positive().optional(),
      penOcclusion: z.boolean().optional(),
    }).parse(req.body);
    return setSettings(b);
  });
  // 폰 에지 연결 테스트 — 같은 WiFi에서 폰 소켓포트가 열려있는지(TCP connect) 확인.
  app.post("/api/settings/test-edge", staff, async (req, reply) => {
    const s = await getSettings();
    const host = (req.body as any)?.host || s.phoneHost;
    const port = (req.body as any)?.port || s.phonePort;
    if (!host) return reply.code(400).send({ error: "폰 IP가 설정되지 않았습니다" });
    const ok = await new Promise<boolean>((resolve) => {
      const sock = net.connect({ host, port, timeout: 2500 }, () => { sock.destroy(); resolve(true); });
      sock.on("error", () => resolve(false));
      sock.on("timeout", () => { sock.destroy(); resolve(false); });
    });
    return { ok, host, port, message: ok ? `폰 에지(${host}:${port}) 연결 성공` : `연결 실패 — 폰에서 Nail Edge Server 실행/같은 WiFi/IP 확인` };
  });

  // ---------- stream control (중계 On/Off) ----------
  app.get("/api/stream", { preHandler: app.authenticate }, async () => {
    const s = await getSettings();
    // 대시보드가 활성 검출엔진을 표시할 수 있게 엔진 정보 동봉.
    return { ...hub.stream, viewerLink: relayBase ? `${relayBase}/monitor?token=${relayView}` : undefined, edgeEngine: s.edgeEngine, phoneHost: s.phoneHost };
  });
  app.post("/api/stream", staff, async (req, reply) => {
    const { on } = z.object({ on: z.boolean() }).parse(req.body);
    const s = await getSettings();
    // 폰 엔진인데 IP 미설정이면 켜기 전에 명확히 차단(에이전트가 조용히 실패하는 것 방지).
    if (on && s.edgeEngine === "phone" && !s.phoneHost)
      return reply.code(400).send({ error: "폰 에지가 선택됨 — 설정 탭에서 폰 IP를 먼저 입력·저장하세요" });
    // stream.start 시 현재 검출 엔진/폰주소를 에이전트에 동봉 → 에이전트가 알맞은 파이프라인 구동
    const payload = on ? { edgeEngine: s.edgeEngine, phoneHost: s.phoneHost, phonePort: s.phonePort, penOcclusion: s.penOcclusion } : undefined;
    if (!hub.commandAgent(on ? "stream.start" : "stream.stop", payload)) return reply.code(409).send({ error: "안경측 PC 에이전트 미접속" });
    hub.setStream({ state: on ? "starting" : "off" });
    return { ok: true, state: hub.stream.state, edgeEngine: s.edgeEngine };
  });
}
