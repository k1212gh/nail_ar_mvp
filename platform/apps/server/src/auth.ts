import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import fjwt from "@fastify/jwt";
import bcrypt from "bcryptjs";
import type { Role } from "@nail/shared";

export const hash = (pw: string) => bcrypt.hash(pw, 10);
export const verify = (pw: string, h: string) => bcrypt.compare(pw, h);

declare module "@fastify/jwt" {
  interface FastifyJWT { payload: { sub: string; role: Role; name: string }; user: { sub: string; role: Role; name: string }; }
}

export async function registerAuth(app: FastifyInstance) {
  await app.register(fjwt, { secret: process.env.JWT_SECRET ?? "dev-secret" });

  app.decorate("authenticate", async (req: FastifyRequest, reply: FastifyReply) => {
    try { await req.jwtVerify(); } catch { return reply.code(401).send({ error: "unauthorized" }); }
  });

  // 역할 가드: requireRole("owner","staff")
  app.decorate("requireRole", (...roles: Role[]) => async (req: FastifyRequest, reply: FastifyReply) => {
    try { await req.jwtVerify(); } catch { return reply.code(401).send({ error: "unauthorized" }); }
    if (!roles.includes(req.user.role)) return reply.code(403).send({ error: "forbidden" });
  });
}

declare module "fastify" {
  interface FastifyInstance {
    authenticate: (req: FastifyRequest, reply: FastifyReply) => Promise<void>;
    requireRole: (...roles: Role[]) => (req: FastifyRequest, reply: FastifyReply) => Promise<void>;
  }
}
