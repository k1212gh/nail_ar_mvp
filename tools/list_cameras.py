"""사용 가능한 카메라 인덱스 탐지 — 폰 가상 웹캠(Iriun/DroidCam)이 몇 번인지 찾는다.

Windows에서는 노트북 내장캠 + 폰 가상캠이 섞여 인덱스가 0/1/2... 로 제각각이다.
이 스크립트가 0~5번을 열어보고 실제로 프레임이 들어오는 인덱스와 해상도를 알려준다.

사용:  python tools/list_cameras.py
그다음:  python main.py --source <번호> --bench
"""
from __future__ import annotations

import sys

import cv2

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 깨짐 방지
except Exception:  # noqa: BLE001
    pass

print("카메라 인덱스 탐지 중 (0~5)...\n")
found = []
for idx in range(6):
    cap = cv2.VideoCapture(idx)
    if cap is not None and cap.isOpened():
        ok, frame = cap.read()
        if ok and frame is not None:
            h, w = frame.shape[:2]
            print(f"  [{idx}] 사용 가능  ({w}x{h})")
            found.append(idx)
        else:
            print(f"  [{idx}] 열렸지만 프레임 없음")
        cap.release()
    else:
        print(f"  [{idx}] 없음")

print()
if found:
    print(f"-> 사용 가능 인덱스: {found}")
    print(f"   예: python main.py --source {found[-1]} --bench   (보통 마지막이 폰 가상캠)")
else:
    print("-> 열리는 카메라가 없습니다. 폰 가상캠 앱(Iriun/DroidCam)이 실행 중인지,")
    print("   또는 IP Webcam URL 방식(--source http://...)을 쓰는지 확인하세요.")
