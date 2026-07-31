# @nail/mobile — Expo / React Native (모바일)

기능: 외출중 백오피스(예약확인·회원조회) + **중계 On/Off** + 라이브뷰 + **푸시알림**(새 예약 등).

## 스캐폴드 (P3 착수 시)
```bash
cd apps
pnpm create expo-app mobile --template
# app.json name, package.json name → "@nail/mobile", "@nail/shared": "workspace:*" 추가
# 모노레포 metro 설정(watchFolders) 필요 — Expo 모노레포 가이드 참조
```
- Electron과 **비즈니스 로직·타입·API클라(@nail/shared) 공유**, 화면만 RN 컴포넌트로.
- 라이브뷰: RN `<Image>` 또는 WebView로 `/stream`.
- 푸시: Expo Notifications + 백엔드가 예약이벤트 시 발송.

> 뼈대만 잡아둠. 실제 Expo 스캐폴드는 위 CLI로 생성.
