"""폰 카메라(idx0, Windows Phone Link 가상카메라) 연속 캡처 → web/_live.jpg.

캘리브 정합용 공유 뷰: 형은 브라우저(https://<PC>:8443/live.html)로, 나(에이전트)는
web/_live.jpg 파일로 같은 폰 화면을 실시간으로 본다. 폰을 눈 위치에 맞추는 동안
초점/구도를 같이 보며 잡는다.

원자적 저장: _live.tmp.jpg 로 쓴 뒤 os.replace → 서버가 반쪽 프레임을 읽지 않음.
검정 프레임(폰 스트림 꺼짐)도 그대로 내보내고 평균밝기를 stdout에 찍어 상태 확인.
"""
from __future__ import annotations

import os
import time

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_live.jpg")
TMP = os.path.join(HERE, "_live.tmp.jpg")

def main() -> None:
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cap.isOpened():
        print("[live] idx0 열기 실패", flush=True)
        return
    print("[live] idx0 open; writing web/_live.jpg ~10fps", flush=True)
    n, last = 0, 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.1)
                continue
            # Windows: os.replace can raise WinError 5 if the server is mid-read of _live.jpg.
            # Retry a few times, then skip this frame — never let one collision kill the loop.
            cv2.imwrite(TMP, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            for _try in range(5):
                try:
                    os.replace(TMP, OUT)
                    break
                except PermissionError:
                    time.sleep(0.02)
            n += 1
            now = time.time()
            if now - last > 2.0:            # 2초마다 상태 1줄
                print(f"[live] frame#{n} {frame.shape[1]}x{frame.shape[0]} mean={frame.mean():.1f}", flush=True)
                last = now
            time.sleep(0.1)
    finally:
        cap.release()

if __name__ == "__main__":
    main()
