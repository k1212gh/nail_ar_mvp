# nail-platform — 네일샵 통합 관리 플랫폼

기존 AR/YOLO 시스템(`../Nail` `../web` `../android`) 위에 얹는 **백오피스 + 중계제어 + AR연동** 모노레포.
전체 설계: [../docs/BACKOFFICE_PLATFORM_PLAN.md](../docs/BACKOFFICE_PLATFORM_PLAN.md)

## 구조

```
platform/
├── packages/
│   └── shared/     @nail/shared  — 타입·zod스키마·API클라이언트 (3개 프론트가 공유)
├── apps/
│   ├── server/     @nail/server  — Fastify + Prisma + PostgreSQL (REST+WS). 오라클 VM에서 Docker로 구동 = 동기화 허브
│   ├── agent/      @nail/agent   — 안경측 로컬 PC 상주. VM 백엔드 명령으로 중계(edge_serve+컴포지터) start/stop
│   ├── desktop/    @nail/desktop — Electron+React+Vite. 백오피스 + AR 라이브뷰 + 중계제어
│   └── mobile/     @nail/mobile  — Expo/React Native. 외출중 관리 + 중계제어 + 푸시
└── infra/          docker-compose.yml + Caddyfile (VM 배포)
```

## 개발 (P0 착수 시)

```bash
# 사전: Node 20+, pnpm 9+
cd platform
pnpm install

# DB(로컬 개발용) + 백엔드
cd apps/server
cp .env.example .env          # DATABASE_URL, JWT_SECRET 등
pnpm prisma migrate dev       # 스키마 → DB
pnpm dev                      # 백엔드 :3001 (REST+WS)

# 데스크톱/모바일은 각 앱 README 참조 (create-* 스캐폴드 후 붙임)
```

## 역할
`owner`(전권) · `staff`(운영) · `customer`(자기 예약·이력). 데이터·중계상태는 VM 백엔드가 단일 진실원.

## 로드맵
P0 기반 → **P1 중계 On/Off** → P2 회원·예약 → P3 모바일 → P4 AR연동(제원·디자인) → P5 마감. (설계서 §7)
