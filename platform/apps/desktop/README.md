# @nail/desktop — Electron 백오피스 (데스크톱)

기능: 백오피스(회원·예약·제원·디자인) + **AR 라이브뷰**(릴레이 `/stream` 임베드) + **중계 On/Off**.
안경측 PC에 설치되니 `@nail/agent`를 메인프로세스에 내장해도 됨.

## 스캐폴드 (P1 착수 시)
Electron+React+Vite는 CLI로 초기화 후 `@nail/shared` 의존 추가:
```bash
cd apps/desktop
pnpm create @quick-start/electron . --template react-ts   # 또는 electron-vite
# package.json name → "@nail/desktop", dependencies에 "@nail/shared": "workspace:*" 추가
```
- 라이브뷰: `<img src="{RELAY_BASE}/stream?token={VIEW}">`
- 중계제어: `POST {SERVER}/api/stream {on}` + WS로 상태구독 (`@nail/shared`의 `API`, `ServerEvent`)

> 뼈대만 잡아둠. 실제 Electron 스캐폴드는 위 CLI로 생성(수기로 만들면 버전 꼬임).
