# 피드백 알림 브리지 — 셋업

작업 진행/결과 요약을 **텔레그램으로 받고**, 당신의 컨펌을 **다시 읽는** 양방향 채널.
의존성 없음(파이썬 stdlib). 파일: [telegram_notify.py](telegram_notify.py).

## 1) 봇 만들기 (1분)
1. 텔레그램에서 **@BotFather** 검색 → `/newbot` → 이름 지정 → **BOT TOKEN** 받기 (예: `123456:ABC-...`)
2. 방금 만든 **당신 봇에게 아무 메시지나** 보내기 ("hi")

## 2) 연결
```
python tools/notify/telegram_notify.py setup --token <BOT_TOKEN>
```
→ chat_id를 찾아 `telegram_config.json`에 저장. (실패 시: 봇에게 먼저 메시지 보냈는지 확인)

## 3) 사용
```
python tools/notify/telegram_notify.py send "M2 완료: APK 빌드됨. 다음: 안경 설치. 컨펌?"
python tools/notify/telegram_notify.py poll     # 당신 답장 읽기 (컨펌 루프용)
```

## 자율 세션에서의 사용 흐름
- 각 마일스톤 완료 → `send`로 **요약 + 다음 계획** 전송
- 다음 단계 진행 전 → `poll`로 당신 컨펌/수정 지시 확인 → 반영
- 토큰 주기 전에는 `PushNotification`(폰 푸시)로 대체 알림.

> 보안: 토큰은 로컬 `telegram_config.json`에만 저장(커밋 금지). 텔레그램 봇 API는
> HTTPS. 대화는 당신과 봇 사이 1:1.

## 대안 채널
- **Slack:** incoming webhook URL 하나면 `send`를 웹훅 POST로 바꾸면 됨(요청 시 추가).
- **KakaoTalk:** "나에게 보내기"는 Kakao OAuth 필요 — 텔레그램보다 번거로움. 요청 시 안내.
