package com.example.nailar.vision

/**
 * 손톱 후보 영역 — PC `src/hand_landmarks.py` 의 NailROI 를 옮긴 것.
 * 좌표는 모두 "분석 입력 이미지(업라이트 비트맵)"의 픽셀 단위.
 * OverlayView 가 뷰 좌표로 변환해 그린다.
 */
data class NailRoi(
    val finger: String,
    val handedness: String,
    val cx: Float,        // 손톱 중심 x (입력 이미지 px)
    val cy: Float,        // 손톱 중심 y
    val axisX: Float,     // 손톱 세로(팁) 방향 단위벡터 x
    val axisY: Float,     // 〃 y
    val lengthPx: Float,  // 손톱 세로 길이 ~ (TIP-DIP 거리)
    val widthPx: Float,   // 손톱 가로 폭(추정)
)
