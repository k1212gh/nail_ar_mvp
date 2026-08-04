# 네일샵 통합 관리 플랫폼 — 설계서 (백오피스 + 중계제어 + AR연동)

> 작성 2026-07-31. 기존 AR/YOLO 시스템(안경·edge_serve·폰 온디바이스·릴레이)은 **그대로 두고 그 위에 얹는** 관리 계층.
> 결정사항: **백엔드=오라클 VM 자체호스팅**, **모바일=React Native/Expo**, **데스크톱=Electron**, 데스크톱↔모바일 **동기화**.

---

## 1. 목표 & 범위

사장님이 **한 곳에서** 네일샵을 운영하는 환경:
- **중계 On/Off** — 안경 라이브 스트림을 버튼 하나로 켜고/끄고, 라이브뷰 시청 (오늘 만든 릴레이 활용)
- **백오피스** — 회원 관리 / 예약 관리 / 제원(AR 장비·세팅) 관리 / 네일 디자인 카탈로그
- **동기화** — 데스크톱(Electron)과 모바일(RN)이 같은 데이터를 실시간 공유
- **AR 연동** — 기존 검출/오버레이 시스템과 회원·디자인·캘리브레이션이 연결

**비범위(당분간 X)**: 결제/POS, 회계, 멀티지점. (데이터 모델엔 확장 여지만 남김)

---

## 2. 아키텍처

```
                    ┌──────────────── 오라클 VM (nail-relay2, Docker) ────────────────┐
                    │  ┌───────────┐  ┌─────────────┐  ┌──────────────┐  ┌─────────┐  │
   인터넷 ─────────►│  │  Caddy    │─►│ 백엔드 API   │─►│ PostgreSQL   │  │ 릴레이   │  │
   (HTTPS)          │  │ (리버스   │  │ Node+TS      │  │ (회원·예약·  │  │ (중계,  │  │
                    │  │  프록시)  │  │ REST+WS      │  │  제원·디자인)│  │ 기존)   │  │
                    │  └───────────┘  └──────┬──────┘  └──────────────┘  └────▲────┘  │
                    └─────────────────────────┼──────────────────────────────┼───────┘
                        REST/CRUD + WebSocket(실시간 동기화·중계상태)          │ /push
              ┌──────────────────────┬────────┴───────────┐                   │
        Electron 데스크톱       React Native(Expo) 모바일    로컬 에이전트 ────┘
        (백오피스+AR라이브뷰+     (외출중 관리+중계제어+       (안경측 PC:
         중계제어)                푸시알림)                    edge_serve/컴포지터
              └──── 공유 TS 패키지(타입·API클라·로직·일부UI) ────┘   start/stop 수행)
                              ▲
                    기존 AR/YOLO (안경·폰·edge_serve) — 검출/캘리브 데이터 공급, 그대로 유지
```

**핵심 원칙**
- **오라클 VM = 단일 진실원(single source of truth) + 동기화 허브.** 모든 클라이언트는 VM 백엔드와만 통신 → 자동 동기화.
- **모노레포 + TypeScript 공유.** Electron(React)과 RN이 타입·API클라이언트·비즈니스로직을 공유 → 중복 최소.
- **기존 시스템 무수정.** edge_serve/릴레이/안경앱은 API로 "연동만". 백오피스가 그 위 레이어.

---

## 3. 기술 스택 (선택 근거)

| 영역 | 선택 | 근거 |
|---|---|---|
| 모노레포 | **pnpm workspaces + Turborepo** | 패키지 공유·증분빌드. nx보다 가벼움 |
| 공유 | `packages/shared` (TS): 타입, zod 스키마, API 클라이언트, 로직 | 프론트 3종이 동일 타입 사용 |
| 백엔드 | **Node.js + Fastify + Prisma + PostgreSQL** | 프론트(TS)와 **타입 공유**가 최대 이점. Prisma로 스키마=타입 |
| 실시간 | **WebSocket**(예약변경·중계상태 푸시) + REST(CRUD) | 동기화 허브 요건 |
| 데스크톱 | **Electron + React + Vite** | 요청 스택. AR 라이브뷰(`/stream`) 임베드 용이 |
| 모바일 | **Expo (React Native)** | 요청 스택. EAS 빌드, 푸시알림, 카메라 |
| 인증 | **JWT (owner/staff 역할)** | 단순·자체호스팅 적합 |
| 배포(VM) | **docker-compose** (postgres·backend·relay·caddy) | 오늘 만든 Docker 환경 연장 |
| HTTPS | **Caddy** (자동 인증서) | 토큰·개인정보 암호화 필수 |

> 대안 검토: 백엔드를 Python(FastAPI)로 하면 기존 edge와 언어 통일되나, **프론트 3종과 타입 공유가 안 됨** → 동기화 앱엔 Node+TS가 유리. 기존 edge_serve는 Python 그대로 두고 백엔드만 Node.

---

## 4. 데이터 모델 (초안)

```
User(스태프)   : id, name, role(owner|staff), phone, passwordHash
Member(회원)   : id, name, phone, memo, createdAt, tags[], preferredDesignIds[]
Visit(방문이력): id, memberId, date, service, staffId, photoUrls[], designId?
Reservation(예약): id, memberId?, name, phone, startAt, endAt, service, status(요청|확정|완료|취소), staffId?, memo
Design(디자인) : id, name, thumbnailUrl, meshRef?(AR 오버레이 연결), tags[]
DeviceProfile(제원): id, label, type(glasses|phone|edge), 
                    settings(json: camW/camH, inferInterval, calibOffset, guideTarget, mode ...),
                    activeFlag   ← 안경/edge 캘리브레이션·세팅을 여기서 관리→푸시
StreamSession(중계): id, state(on|off), startedBy, startedAt, agentId, viewerLink
AuditLog       : id, actorId, action, target, at
```

- **DeviceProfile**이 "제원 관리"의 핵심 — 기존 `push_calib.py`가 하던 안경 세팅(camW, inferInterval, calibOffset, mode 등)을 **DB에서 관리하고 버튼으로 안경/edge에 적용**.
- 사진·썸네일은 VM 로컬 볼륨 또는 오브젝트 스토리지(추후).

---

## 5. 컴포넌트 상세

### 5.1 백엔드 (VM, Docker)
- REST: `/auth`, `/members`, `/reservations`, `/designs`, `/device-profiles`, `/stream`(제어), `/agents`
- WebSocket: 예약/중계상태 변경을 전 클라이언트에 브로드캐스트
- Prisma 마이그레이션으로 DB 스키마 관리
- 파일 업로드(회원 사진 등) → VM 볼륨 `/opt/nail/uploads`

### 5.2 로컬 에이전트 (안경측 PC) — **중계 On/Off의 실체**
- 문제: 안경→검출→송출 파이프라인(edge_serve+컴포지터)은 **안경 꽂힌 로컬 PC**에서 돎. 릴레이(VM)는 받기만 함. 그래서 "원격 On/Off"엔 로컬 대리자가 필요.
- 해결: 로컬 PC에 **경량 에이전트**(Python/Node) 상주 → VM 백엔드에 WebSocket 연결(아웃바운드만, 방화벽 무관) → 백엔드가 "중계 켜/꺼" 명령 보내면 에이전트가 `edge_serve.py`+`relay_compose_push.py` **start/stop** + 안경 wake/adb 처리.
- 상태(fps, 안경연결, 검출수)를 백엔드로 보고 → 앱에서 표시.

### 5.3 데스크톱 (Electron)
- 백오피스 전 기능 + **AR 라이브뷰**(릴레이 `/stream`을 `<img>`로 임베드) + 중계 On/Off 버튼
- 로컬 PC에 있으니 로컬 에이전트를 내장(Electron 메인프로세스가 에이전트 겸함)해도 됨

### 5.4 모바일 (Expo/RN)
- 백오피스(외출 중 예약확인·회원조회) + 중계 On/Off + 라이브뷰 + **푸시알림**(새 예약 등)

### 5.5 공유 패키지
- `@nail/shared`: 타입, zod 스키마, API 클라이언트(fetch 래퍼), 인증 훅, 날짜/포맷 유틸, 재사용 UI 로직

---

## 6. 중계 On/Off 흐름 (요청 핵심 기능)

```
[앱: 중계 켜기] → 백엔드 POST /stream {on} → WS로 로컬에이전트에 명령
  → 에이전트: 안경 wake + adb reverse + edge_serve 실행 + relay_compose_push 실행
  → 프레임이 VM 릴레이로 흐름 → 앱 라이브뷰(/stream)에 영상
[앱: 중계 끄기] → 에이전트가 두 프로세스 종료 → 릴레이 대기화면
```
- 앱에선 **버튼 하나 + 상태표시(ON/OFF, fps, 안경연결)**. 오늘 만든 릴레이/컴포지터를 그대로 재사용.

---

## 7. 단계별 로드맵

| 단계 | 내용 | 산출물 |
|---|---|---|
| **P0 기반** | 모노레포 스캐폴드, VM에 docker-compose(postgres+backend+caddy), 인증, 공유타입 | 로그인 되는 빈 껍데기 |
| **P1 중계제어** | 로컬 에이전트 + `/stream` 제어 + 데스크톱 "중계 On/Off + 라이브뷰" | 버튼으로 켜고/끄는 데모 |
| **P2 백오피스 코어** | 회원·예약 CRUD (백엔드+데스크톱 UI) + WS 동기화 | 예약/회원 관리 |
| **P3 모바일** | Expo 앱: 회원·예약·중계제어 + 푸시알림 | 폰에서 관리 |
| **P4 AR 연동** | DeviceProfile(제원)로 안경/edge 세팅 관리→적용, 디자인 카탈로그↔AR | 캘리브·디자인 통합 |
| **P5 마감** | 오프라인 캐시, 역할/권한, 백업, HTTPS 도메인 | 운영 준비 |

각 단계 끝에 동작하는 산출물 → 점진적. P1이 오늘 작업과 바로 이어져 체감 빠름.

---

## 8. 배포

- **VM**: `docker-compose up -d` (postgres, backend, relay, caddy). Caddy가 HTTPS 종단 + `/api`·`/stream` 라우팅. 도메인 있으면 자동 인증서(없으면 self-signed).
- **데스크톱**: electron-builder → Windows 설치파일(.exe)
- **모바일**: Expo EAS build → Android APK (+iOS는 추후)
- 무료티어(2 OCPU/12GB) 안에서 postgres+backend+relay 동시 구동 가능(경량).

---

## 9. 확정 결정 (2026-07-31)

1. **도메인 없음** → Caddy 내부TLS(self-signed) 또는 IP+HTTP로 시작, 추후 도메인 붙이면 자동 HTTPS.
2. **다중 사용자** → 역할 3종: `owner`(사장님, 전권) · `staff`(스태프, 운영) · `customer`(고객, 자기 예약·이력만). 스태프도 백오피스 열람, 고객은 예약/자기정보.
3. **예약 = 일반 예약시스템 + 백오피스, 네일 특화** → 캘린더/타임슬롯 예약, 서비스·소요시간·담당자, 고객 셀프예약(승인/확정 플로우), 노쇼/취소, **네일 특화**(디자인 선택·사진첨부·시술이력·재방문주기). 기존 예약데이터 마이그레이션은 없음(신규).
4. **제원 관리 = 안경/edge 세팅값 관리** 확정 → `push_calib.py`가 하던 camW·inferInterval·calibOffset·guideTarget·mode 등을 DB에서 프로필로 관리하고 버튼으로 적용.
5. **코드 위치 = 기존 레포 안 `platform/` 모노레포** (기존 AR코드와 공존, 내 추천대로 디렉토리 정리).

### 반영: 역할·예약 모델 보강
```
User: role(owner|staff|customer) 추가. customer는 Member와 1:1 연결 가능.
Reservation: 셀프예약 지원 위해 status(요청|확정|완료|취소|노쇼), source(staff|self), 
             designId?, photoUrls[](시술 후), depositPaid?(추후)
Service(시술종류): id, name, durationMin, price?, category  ← 예약 슬롯 계산용
BusinessHours/Slot: 영업시간·휴무·슬롯 규칙 (예약 가능시간 산출)
```

---

## 10. 디렉토리 구조 (기존 레포 안 `platform/` 모노레포)

```
nail_ar_mvp/
├── Nail/ web/ android/ tools/ docs/ ...   ← 기존 AR/YOLO (무수정)
└── platform/                               ← 신규 모노레포
    ├── package.json  pnpm-workspace.yaml  turbo.json  tsconfig.base.json
    ├── packages/
    │   └── shared/        @nail/shared  (타입·zod스키마·API클라·로직)
    ├── apps/
    │   ├── server/        @nail/server  (Fastify+Prisma+Postgres, REST+WS)
    │   ├── agent/         @nail/agent   (안경측 로컬 PC: 중계 start/stop)
    │   ├── desktop/       @nail/desktop (Electron+React+Vite)
    │   └── mobile/        @nail/mobile  (Expo/React Native)
    └── infra/             docker-compose.yml  Caddyfile
```

## 11. 다음 액션
**P0 착수**: 위 `platform/` 뼈대 생성 → VM에 postgres+backend(docker-compose) → 인증 → 로그인 되는 껍데기. 이어서 P1(중계제어)로.
