package com.example.nailar.vision

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.os.SystemClock
import androidx.camera.core.ImageProxy
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.framework.image.MPImage
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarker
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarkerResult
import kotlin.math.hypot

/**
 * MediaPipe HandLandmarker(LIVE_STREAM) 래퍼 — PC `src/hand_landmarks.py` 대응.
 * CameraX 프레임을 받아 손당 21개 랜드마크를 구하고, 손가락별 TIP/DIP 로
 * 손톱 ROI(중심·세로축·길이·폭)를 산출해 콜백으로 넘긴다.
 *
 * 결과 콜백: (손톱들, 입력이미지 W, 입력이미지 H, 추론ms)
 */
class HandNailDetector(
    context: Context,
    private val onResult: (List<NailRoi>, Int, Int, Long) -> Unit,
    private val onError: (String) -> Unit = {},
) {
    // 손가락별 (TIP, DIP) 랜드마크 인덱스 — PC 와 동일
    private val tipDip = linkedMapOf(
        "thumb" to (4 to 3),
        "index" to (8 to 7),
        "middle" to (12 to 11),
        "ring" to (16 to 15),
        "pinky" to (20 to 19),
    )
    // PC `geometry_from_roi`(--seg none)와 동일한 손톱판 추정 비율
    private val nailCenterRatio = 0.72f   // 손톱 중심 = DIP→TIP 의 72% 지점(끝쪽)
    private val nailLengthRatio = 0.55f   // 손톱 세로 = 끝마디(TIP-DIP) × 0.55
    private val widthRatio = 0.75f         // 손톱 가로 = 세로 × 0.75

    private val landmarker: HandLandmarker
    private var lastW = 1
    private var lastH = 1
    private var frameStartMs = 0L

    init {
        val base = BaseOptions.builder()
            .setModelAssetPath("hand_landmarker.task")  // assets/ 에 위치
            .build()
        val options = HandLandmarker.HandLandmarkerOptions.builder()
            .setBaseOptions(base)
            .setRunningMode(RunningMode.LIVE_STREAM)
            .setNumHands(2)
            .setMinHandDetectionConfidence(0.5f)
            .setMinHandPresenceConfidence(0.5f)
            .setMinTrackingConfidence(0.5f)
            .setResultListener { result, _ -> handleResult(result) }
            .setErrorListener { e -> onError(e.message ?: "HandLandmarker error") }
            .build()
        landmarker = HandLandmarker.createFromOptions(context, options)
    }

    /** CameraX 프레임 1장 분석(비동기). 호출 측은 ImageProxy 소유권을 넘긴다. */
    fun detect(imageProxy: ImageProxy) {
        val bmp = try {
            imageProxy.toUprightBitmap()
        } finally {
            imageProxy.close()
        }
        lastW = bmp.width
        lastH = bmp.height
        frameStartMs = SystemClock.uptimeMillis()
        val mp: MPImage = BitmapImageBuilder(bmp).build()
        landmarker.detectAsync(mp, frameStartMs)
    }

    fun close() = landmarker.close()

    private fun ImageProxy.toUprightBitmap(): Bitmap {
        val bitmap = this.toBitmap()                 // RGBA_8888 출력 포맷 가정
        val rot = imageInfo.rotationDegrees
        if (rot == 0) return bitmap
        val m = Matrix().apply { postRotate(rot.toFloat()) }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, m, true)
    }

    private fun handleResult(result: HandLandmarkerResult) {
        val rois = ArrayList<NailRoi>()
        val hands = result.landmarks()
        val handed = result.handednesses()
        for (i in hands.indices) {
            val lms = hands[i]
            val label = handed.getOrNull(i)?.getOrNull(0)?.categoryName() ?: "?"
            for ((finger, pair) in tipDip) {
                val tip = lms[pair.first]
                val dip = lms[pair.second]
                val tx = tip.x() * lastW; val ty = tip.y() * lastH
                val dx = dip.x() * lastW; val dy = dip.y() * lastH
                val vx = tx - dx; val vy = ty - dy
                val len = hypot(vx, vy)
                if (len < 1f) continue
                val nailLen = len * nailLengthRatio
                rois.add(
                    NailRoi(
                        finger = finger,
                        handedness = label,
                        cx = dx + vx * nailCenterRatio,
                        cy = dy + vy * nailCenterRatio,
                        axisX = vx / len,
                        axisY = vy / len,
                        lengthPx = nailLen,
                        widthPx = nailLen * widthRatio,
                    )
                )
            }
        }
        val infMs = SystemClock.uptimeMillis() - frameStartMs
        onResult(rois, lastW, lastH, infMs)
    }

    companion object {
        private val TIP_DIP = linkedMapOf(
            "thumb" to (4 to 3), "index" to (8 to 7), "middle" to (12 to 11),
            "ring" to (16 to 15), "pinky" to (20 to 19),
        )
        private const val CENTER = 0.72f
        private const val LEN = 0.55f
        private const val WID = 0.75f

        /** 정지 이미지에서 손톱 ROI 검출 (글래스 카메라 차단 우회 / 스크린샷 검증용). */
        fun detectImage(context: Context, bitmap: Bitmap): List<NailRoi> {
            val base = BaseOptions.builder().setModelAssetPath("hand_landmarker.task").build()
            val opts = HandLandmarker.HandLandmarkerOptions.builder()
                .setBaseOptions(base)
                .setRunningMode(RunningMode.IMAGE)
                .setNumHands(2)
                .setMinHandDetectionConfidence(0.4f)
                .build()
            val lm = HandLandmarker.createFromOptions(context, opts)
            val result = lm.detect(BitmapImageBuilder(bitmap).build())
            lm.close()
            return buildRois(result, bitmap.width, bitmap.height)
        }

        private fun buildRois(result: HandLandmarkerResult, w: Int, h: Int): List<NailRoi> {
            val rois = ArrayList<NailRoi>()
            val hands = result.landmarks()
            val handed = result.handednesses()
            for (i in hands.indices) {
                val lms = hands[i]
                val label = handed.getOrNull(i)?.getOrNull(0)?.categoryName() ?: "?"
                for ((finger, pair) in TIP_DIP) {
                    val tip = lms[pair.first]; val dip = lms[pair.second]
                    val tx = tip.x() * w; val ty = tip.y() * h
                    val dx = dip.x() * w; val dy = dip.y() * h
                    val vx = tx - dx; val vy = ty - dy
                    val len = hypot(vx, vy)
                    if (len < 1f) continue
                    val nailLen = len * LEN
                    rois.add(
                        NailRoi(
                            finger = finger, handedness = label,
                            cx = dx + vx * CENTER, cy = dy + vy * CENTER,
                            axisX = vx / len, axisY = vy / len,
                            lengthPx = nailLen, widthPx = nailLen * WID,
                        )
                    )
                }
            }
            return rois
        }
    }
}
