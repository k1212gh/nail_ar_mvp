"""중앙 로깅 설정 — 콘솔 + 파일 로그, 네이티브(TF/MediaPipe) 잡음 억제.

- 흩어진 print 대신 모듈별 로거(`nailar.<module>`)를 쓴다.
- 콘솔은 --log-level(기본 INFO), 파일은 항상 DEBUG로 logs/ 에 타임스탬프 파일 저장.
- MediaPipe/TFLite의 C++ 로그(W0000…, "Created TensorFlow Lite…")는
  setup_logging() 을 mediapipe import 전에 호출하면 환경변수로 억제된다.
"""
from __future__ import annotations

import logging
import os
import sys
import time

_CONFIGURED = False
_ROOT_NAME = "nailar"


def quiet_native_logs() -> None:
    """TF/absl/glog 네이티브 로그 억제 — mediapipe 로드 전에 호출돼야 효과."""
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")   # TF: ERROR 이상만
    os.environ.setdefault("GLOG_minloglevel", "2")        # glog/absl: ERROR 이상만


def setup_logging(level: str = "INFO", log_dir: str = "logs",
                  to_file: bool = True, quiet_native: bool = True) -> logging.Logger:
    global _CONFIGURED
    if quiet_native:
        quiet_native_logs()

    root = logging.getLogger(_ROOT_NAME)
    if _CONFIGURED:
        return root
    root.setLevel(logging.DEBUG)
    root.propagate = False

    console_level = getattr(logging, str(level).upper(), logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(console_level)
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                                      datefmt="%H:%M:%S"))
    root.addHandler(ch)

    if to_file:
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, time.strftime("nailar_%Y%m%d_%H%M%S.log"))
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s [%(filename)s:%(lineno)d]: %(message)s"))
        root.addHandler(fh)
        root.info("로그 파일: %s", path)

    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    """모듈용 로거. 예: get_logger('pipeline') -> 'nailar.pipeline'."""
    return logging.getLogger(_ROOT_NAME).getChild(name)
