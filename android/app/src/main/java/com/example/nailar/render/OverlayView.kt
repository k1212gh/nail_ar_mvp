package com.example.nailar.render

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.util.AttributeSet
import android.view.View
import com.example.nailar.vision.NailRoi
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * 손톱 위 디자인 합성 뷰 — PC `src/design_overlay.py` + A3 곡면 워프 대응.
 * 입력 이미지 px 좌표의 NailRoi 를 받아 PreviewView(fillCenter)와 같은 스케일로
 * 화면에 매핑하고, 디자인을 손톱 크기·방향에 맞춰 그린다.
 *
 * 렌더 모드:
 *  - MESH(기본): 반원기둥 곡면 워프(A3 간소판). Canvas.drawBitmapMesh 로 손톱 곡면에 휨.
 *  - AFFINE: 평면 아핀(구 star 경로, 폴백).
 * 정합 안내선(가이드)도 표시 가능 — 특허의 "실시간 안내".
 *
 * 배경 이미지(setBackgroundImage)를 주면 카메라 대신 정지영상 위에 렌더(글래스 카메라
 * 차단 우회 + 스크린샷 검증용). 배경 없으면 투명(카메라 프리뷰 위 오버레이).
 */
class OverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    private var rois: List<NailRoi> = emptyList()
    private var imgW = 1
    private var imgH = 1

    // 손가락별로 다른 디자인(실제 네일아트처럼). null 자리는 건너뜀.
    private val designs: List<Bitmap> = listOf(
        "designs/design_french.png", "designs/design_floral.png", "designs/design_dots.png",
    ).mapNotNull { loadAsset(it) }
    private val fingerOrder = listOf("thumb", "index", "middle", "ring", "pinky")
    private fun designFor(finger: String): Bitmap? {
        if (designs.isEmpty()) return null
        val i = fingerOrder.indexOf(finger).let { if (it < 0) 0 else it }
        return designs[i % designs.size]
    }
    private var bg: Bitmap? = null
    private var designScale = 1.7f     // 손톱을 덮도록 크게(랜드마크 추정 손톱판이 작아 보정)

    // 곡면 워프 파라미터
    private val meshCols = 10
    private val meshRows = 12
    private val halfAngleRad = 1.05f   // 반원기둥 반각(~60도) — 가장자리 압축량

    var showDesign = true
    var showGuide = false              // 디자인이 주인공. 안내선은 옵션(특허 "안내" 시 켜기)
    var useMesh = true

    private val bmpPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val guidePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.GREEN; strokeWidth = 3f; style = Paint.Style.STROKE
    }
    private val centerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.GREEN }

    fun setResults(rois: List<NailRoi>, imageW: Int, imageH: Int) {
        this.rois = rois
        this.imgW = imageW.coerceAtLeast(1)
        this.imgH = imageH.coerceAtLeast(1)
        postInvalidate()
    }

    fun setBackgroundImage(b: Bitmap?) { bg = b; postInvalidate() }
    fun toggleDesign() { showDesign = !showDesign; invalidate() }
    fun setDesignScale(s: Float) { designScale = s; invalidate() }
    fun nailCount(): Int = rois.size

    // 화면 정렬: 0=왼쪽, 0.5=가운데, 1=오른쪽 (글래스 시야 보정용, config 로 조절)
    var alignX = 0.0f
    // fill=true: 화면 꽉 채움(크게·선명, 가장자리 크롭) / false: fit(전체 보임, 레터박스)
    var fillMode = false
    private fun mapping(): FloatArray {
        val sf = if (fillMode) max(width.toFloat() / imgW, height.toFloat() / imgH)
                 else min(width.toFloat() / imgW, height.toFloat() / imgH)
        val offX = (width - imgW * sf) * alignX.coerceIn(0f, 1f)
        return floatArrayOf(sf, offX, (height - imgH * sf) / 2f)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val (sf, offX, offY) = mapping().let { Triple(it[0], it[1], it[2]) }

        bg?.let {
            val m = Matrix().apply { postScale(sf, sf); postTranslate(offX, offY) }
            canvas.drawBitmap(it, m, bmpPaint)
        }
        if (rois.isEmpty()) return

        for (r in rois) {
            val cx = r.cx * sf + offX
            val cy = r.cy * sf + offY
            val lenPx = r.lengthPx * sf
            val widPx = r.widthPx * sf
            val d = designFor(r.finger)
            if (showDesign && d != null) {
                if (useMesh) drawDesignMesh(canvas, d, cx, cy, lenPx, widPx, r.axisX, r.axisY)
                else drawDesignAffine(canvas, d, cx, cy, lenPx, widPx, r.axisX, r.axisY)
            }
            if (showGuide) drawGuide(canvas, cx, cy, lenPx, widPx, r.axisX, r.axisY)
        }
    }

    /** 반원기둥 곡면 워프: 폭 방향으로 sin 압축(가장자리가 말려 들어감). */
    private fun drawDesignMesh(
        canvas: Canvas, bmp: Bitmap,
        cx: Float, cy: Float, lenPx: Float, widPx: Float, ax: Float, ay: Float,
    ) {
        val bx = -ay; val by = ax                       // 폭(가로) 단위축
        val halfLen = lenPx * designScale / 2f
        val halfWid = widPx * designScale / 2f
        val sinHalf = sin(halfAngleRad)
        val nv = (meshCols + 1) * (meshRows + 1)
        val verts = FloatArray(nv * 2)
        val colors = IntArray(nv)                       // 정점 음영(반원기둥 노멀)
        var k = 0; var ci = 0
        for (row in 0..meshRows) {
            val v = row.toFloat() / meshRows            // 0=위(팁쪽), 1=아래(뿌리쪽)
            val along = (v - 0.5f) * (2f * halfLen)     // 세로축 위치
            for (col in 0..meshCols) {
                val u = col.toFloat() / meshCols        // 0..1 가로
                val phi = (u - 0.5f) * (2f * halfAngleRad)
                val across = halfWid * (sin(phi) / sinHalf)   // 곡면 압축
                // 화면좌표 = 중심 + along*세로축(ax,ay) + across*가로축(bx,by)
                verts[k++] = cx + along * ax + across * bx
                verts[k++] = cy + along * ay + across * by
                val b = 0.55f + 0.45f * cos(phi)        // 중앙 밝고 가장자리 어둡게
                val g = (255f * b).toInt().coerceIn(0, 255)
                colors[ci++] = (0xFF shl 24) or (g shl 16) or (g shl 8) or g
            }
        }
        canvas.drawBitmapMesh(bmp, meshCols, meshRows, verts, 0, colors, 0, bmpPaint)
    }

    private fun drawDesignAffine(
        canvas: Canvas, bmp: Bitmap,
        cx: Float, cy: Float, lenPx: Float, widPx: Float, ax: Float, ay: Float,
    ) {
        val deg = Math.toDegrees(atan2(ax.toDouble(), -ay.toDouble())).toFloat()
        val sx = (widPx * designScale) / bmp.width
        val sy = (lenPx * designScale) / bmp.height
        val m = Matrix().apply {
            postTranslate(-bmp.width / 2f, -bmp.height / 2f)
            postScale(sx, sy); postRotate(deg); postTranslate(cx, cy)
        }
        canvas.drawBitmap(bmp, m, bmpPaint)
    }

    private fun drawGuide(
        canvas: Canvas, cx: Float, cy: Float, lenPx: Float, widPx: Float, ax: Float, ay: Float,
    ) {
        val hl = lenPx / 2f
        canvas.drawLine(cx - ax * hl, cy - ay * hl, cx + ax * hl, cy + ay * hl, guidePaint)
        val bx = -ay; val by = ax; val hw = widPx / 2f
        canvas.drawLine(cx - bx * hw, cy - by * hw, cx + bx * hw, cy + by * hw, guidePaint)
        canvas.drawCircle(cx, cy, 4f, centerPaint)
    }

    private fun loadAsset(path: String): Bitmap? = try {
        context.assets.open(path).use { BitmapFactory.decodeStream(it) }
    } catch (e: Exception) { null }
}
