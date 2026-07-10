# 🥽 안경 데모 실행서 (외부/노트북용)

> **검증됨(2026-07-11, 데스크톱):** 안경(RayNeo X3 Pro) → USB → PC 에지서버 루프가
> **~15-20fps, 검출 9ms/프레임**으로 실동작. `infer bytes=20700 nails=5` = 성공.
> 이 문서는 **가져갈 노트북(외장 GPU 없어도 OK)** 에서 같은 걸 재현하는 절차.

## 데모 구조 (한 줄)
안경 카메라 → **USB(`adb reverse tcp:8443`)** → 노트북 `edge_serve.py`가 손톱 검출 →
안경이 곡면 네일 디자인 렌더 (매직미러). **WiFi/인터넷 불필요, 전부 USB+localhost.**

---

## A. 노트북 1회 세팅 (오늘 밤 미리!)

```powershell
# 1) 파이썬 (없으면)
winget install Python.Python.3.11
# 2) adb + 화면미러 (scrcpy가 adb 포함)
winget install Genymobile.scrcpy
# 3) 코드 가져오기 (셋 중 하나)
git clone https://github.com/k1212gh/nail_ar_mvp    # gh 로그인 필요
#  또는 github.com/k1212gh/nail_ar_mvp → Code → Download ZIP
#  또는 데스크톱 폴더를 USB로 복사 (단 Nail/Library·_archive 제외하면 가벼움)
# 4) 의존성 설치 (torch 포함 ~수분 소요)
cd nail_ar_mvp
python -m pip install -r requirements.txt
```

**adb 연결 확인** (안경 USB 연결 후):
```powershell
adb devices          # →  006A5E5038F3297   device   가 떠야 정상
```
- `unauthorized` → 안경에서 **"USB 디버깅 허용"** 수락.
- 목록이 비었으면(Windows 복합USB 드라이버 문제) → 관리자로
  `tools\ar_helper\Fix-ADB-Driver-ADMIN.cmd` 실행 후 재시도.

> 앱은 **안경에 이미 설치돼 있음**(`com.DefaultCompany.NailMesh` 등). 노트북 바뀌어도
> 안경은 그대로라 재설치 불필요. 카메라 권한도 이미 부여됨.

---

## B. 데모 당일 (매번 이 순서)

**터미널 1 — 에지 서버 (켜두고 그대로):**
```powershell
cd nail_ar_mvp
python web/edge_serve.py
```
→ `워밍업 완료` + `에지 추론 서버` 배너가 뜨면 준비 완료. (첫 실행 시 인증서 자동생성.)

**터미널 2 — 안경 연결 + 앱 실행:**
```powershell
adb reverse tcp:8443 tcp:8443
adb shell input keyevent KEYCODE_WAKEUP
adb shell svc power stayon true
adb shell monkey -p com.DefaultCompany.NailMesh -c android.intent.category.LAUNCHER 1
```

**확인:** 안경을 쓰고 **손을 카메라 앞 25~40cm**에 대면 손톱에 디자인이 얹힘.
→ 터미널 1에 `infer ... nails=5` 가 뜨면 검출 성공. (`nails=0`이면 손이 안 잡히는 것.)

> 다른 버전을 쓰려면 패키지명만 교체: `com.DefaultCompany.Nail`(그리드/디자인) /
> `com.DefaultCompany.NailCalib`(캘리브) / `com.DefaultCompany.NailMesh`(곡면 메쉬, 최신).

---

## C. 문제 해결 (현장 대응)

| 증상 | 조치 |
|---|---|
| 안경 화면 검정 / 앱 멈춤 | Doze 절전. **안경을 쓰거나** `adb shell input keyevent KEYCODE_WAKEUP` 후 앱 재실행 |
| `nails=0`만 계속 | 손 거리(25~40cm)·조명 확인. 카메라 권한: `adb shell pm grant com.DefaultCompany.NailMesh android.permission.CAMERA` |
| 터미널1에 infer 로그 안 옴 | `adb reverse --list`로 `tcp:8443` 확인. 없으면 `adb reverse tcp:8443 tcp:8443` 재실행 |
| `adb devices` 비어있음 | USB 재연결 → 디버깅 허용 → 안 되면 Fix-ADB-Driver-ADMIN.cmd(관리자) |
| 서버가 import 에러로 안 켜짐 | `pip install -r requirements.txt` 재실행 (ultralytics/cryptography 필요) |

## D. 백업 (항상 준비)
- **오늘 밤 정상 동작을 녹화**해 폰에 저장. 현장에서 뭐가 터져도 이걸로 방어.
- 화면 미러가 필요하면 `scrcpy`로 안경 화면을 노트북에 띄울 수 있음(단 XR 보안 서피스는 검게 나올 수 있음 → 폰으로 안경 낀 사람 손 시연을 직접 촬영이 더 확실).

## E. 물리 체크리스트
- [ ] 노트북·안경 충전 100% / USB 케이블(안경용)
- [ ] 위 A 세팅을 **노트북에서 실제로 1회 완주**(오늘 밤 리허설)
- [ ] 밝은 조명 자리
- [ ] 백업 영상 폰에 저장
