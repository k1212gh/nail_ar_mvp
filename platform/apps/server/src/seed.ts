/** 초기 데이터: owner 계정 + 샘플 서비스·회원·디자인·예약·제원. */
import { prisma, J } from "./db.js";
import { hash } from "./auth.js";

async function main() {
  let owner = await prisma.user.findFirst({ where: { name: "사장님" } });
  if (!owner) owner = await prisma.user.create({ data: { name: "사장님", role: "owner", passwordHash: await hash("nail1234") } });

  if ((await prisma.service.count()) === 0) {
    await prisma.service.createMany({ data: [
      { name: "젤 네일", durationMin: 90, price: 50000, category: "gel" },
      { name: "손톱 케어", durationMin: 40, price: 25000, category: "care" },
      { name: "네일 아트(AR)", durationMin: 120, price: 80000, category: "art" },
    ] });
  }
  if ((await prisma.member.count()) === 0) {
    const m = await prisma.member.create({ data: { name: "김민지", phone: "010-1234-5678", memo: "핑크 선호", tags: J.str(["단골", "AR"]) } });
    const svc = await prisma.service.findFirst();
    const start = new Date(); start.setHours(14, 0, 0, 0);
    const end = new Date(start.getTime() + 90 * 60000);
    await prisma.reservation.create({ data: { memberId: m.id, name: m.name, phone: m.phone, serviceId: svc?.id, startAt: start, endAt: end, status: "confirmed", source: "staff" } });
  }
  if ((await prisma.design.count()) === 0) {
    await prisma.design.createMany({ data: [
      { name: "체리블라썸", tags: J.str(["봄", "핑크"]) },
      { name: "글리터 그라데이션", tags: J.str(["파티"]) },
    ] });
  }
  if ((await prisma.deviceProfile.count()) === 0) {
    await prisma.deviceProfile.create({ data: { label: "안경 기본(320)", type: "glasses", active: true, settings: J.str({ camW: 640, camH: 400, inferInterval: 0.03, guideTarget: 0.45, mode: 5 }) } });
  }
  console.log("seed done. 로그인: 사장님 / nail1234  (owner)");
}
main().then(() => process.exit(0)).catch((e) => { console.error(e); process.exit(1); });
