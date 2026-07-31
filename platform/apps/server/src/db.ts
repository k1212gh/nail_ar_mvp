import { PrismaClient } from "@prisma/client";

export const prisma = new PrismaClient();

// SQLite Json-string 필드 ↔ JS 값 매핑 헬퍼
export const J = {
  arr: (s: string | null | undefined): string[] => { try { return s ? JSON.parse(s) : []; } catch { return []; } },
  obj: (s: string | null | undefined): Record<string, unknown> => { try { return s ? JSON.parse(s) : {}; } catch { return {}; } },
  str: (v: unknown): string => JSON.stringify(v ?? []),
};

export const memberOut = (m: any) => ({ ...m, tags: J.arr(m.tags), preferredDesignIds: J.arr(m.preferredDesignIds), createdAt: m.createdAt.toISOString() });
export const reservationOut = (r: any) => ({ ...r, photoUrls: J.arr(r.photoUrls), startAt: r.startAt.toISOString(), endAt: r.endAt.toISOString(), createdAt: r.createdAt.toISOString() });
export const designOut = (d: any) => ({ ...d, tags: J.arr(d.tags) });
export const profileOut = (p: any) => ({ ...p, settings: J.obj(p.settings), updatedAt: p.updatedAt.toISOString() });

// ---------- 샵 전역 설정 (검출 엔진 등) ----------
export type ShopSettings = {
  edgeEngine: "pc" | "phone"; // 손톱검출을 어디서: PC(GPU) vs 폰(온디바이스)
  phoneHost: string;          // 폰 에지 IP (같은 WiFi). 안경이 소켓으로 붙는 대상
  phonePort: number;          // 폰 EdgeServer 소켓 포트(기본 8444)
  penOcclusion: boolean;      // 펜 가림방지 사용
};
export const DEFAULT_SETTINGS: ShopSettings = { edgeEngine: "pc", phoneHost: "", phonePort: 8444, penOcclusion: true };

export async function getSettings(): Promise<ShopSettings> {
  const row = await prisma.setting.findUnique({ where: { key: "shop" } });
  return { ...DEFAULT_SETTINGS, ...(row ? (J.obj(row.value) as Partial<ShopSettings>) : {}) };
}
export async function setSettings(patch: Partial<ShopSettings>): Promise<ShopSettings> {
  const next = { ...(await getSettings()), ...patch };
  await prisma.setting.upsert({ where: { key: "shop" }, create: { key: "shop", value: J.str(next) }, update: { value: J.str(next) } });
  return next;
}
