package com.example.nailar.edge

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import ai.onnxruntime.providers.NNAPIFlags
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import java.nio.FloatBuffer
import java.util.EnumSet
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sqrt

/** 손톱 하나 — 원본 이미지 좌표계. web/edge_serve.py 스키마와 동일. */
data class Nail(
    val cx: Float, val cy: Float,
    val ex: Float, val ey: Float,
    val len: Float, val wid: Float,
    val contour: List<IntArray>,
)

/**
 * torch-free YOLOv8-seg 손톱검출 (onnxruntime-android, NNAPI 가속).
 * web/yolo.js / tools/onnx_edge/onnx_infer.py 의 letterbox→추론→NMS→마스크→PCA 를 그대로 이식.
 */
class NailOnnx(context: Context, modelAsset: String = "nails_seg.onnx") {

    companion object {
        const val S = 640
        const val NA = 8400
        const val PW = 160
        const val PH = 160
        const val PN = PW * PH
        const val CONF = 0.20f
        const val IOU = 0.5f
        const val MASK_THR = 0.5f
        const val MAXDET = 12
    }

    private val env = OrtEnvironment.getEnvironment()
    private val session: OrtSession
    private val inputName: String
    var backend: String = "cpu"; private set

    init {
        val bytes = context.assets.open(modelAsset).use { it.readBytes() }
        val opts = OrtSession.SessionOptions()
        opts.setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        try {
            // Snapdragon Hexagon NPU / Adreno GPU 로 라우팅 (fp16 허용)
            opts.addNnapi(EnumSet.of(NNAPIFlags.USE_FP16))
            backend = "nnapi"
        } catch (t: Throwable) {
            backend = "cpu"
        }
        session = env.createSession(bytes, opts)
        inputName = session.inputNames.iterator().next()
    }

    private fun sigmoid(x: Float) = 1f / (1f + Math.exp(-x.toDouble()).toFloat())

    private class Cand(val x1: Float, val y1: Float, val x2: Float, val y2: Float, val sc: Float, val i: Int)

    private fun iou(a: Cand, b: Cand): Float {
        val x1 = max(a.x1, b.x1); val y1 = max(a.y1, b.y1)
        val x2 = min(a.x2, b.x2); val y2 = min(a.y2, b.y2)
        val w = max(0f, x2 - x1); val h = max(0f, y2 - y1); val inter = w * h
        val ua = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter
        return if (ua > 0) inter / ua else 0f
    }

    private class Geo(val mx: Float, val my: Float, val ex: Float, val ey: Float, val len: Float, val wid: Float)

    /** 160-space 마스크 픽셀들 → 중심(방향박스 중점)·주축·길이·폭. (yolo.js pca 이식) */
    private fun pca(pts: List<IntArray>): Geo {
        var mx = 0.0; var my = 0.0
        for (p in pts) { mx += p[0]; my += p[1] }
        mx /= pts.size; my /= pts.size
        var a = 0.0; var b = 0.0; var c = 0.0
        for (p in pts) { val dx = p[0] - mx; val dy = p[1] - my; a += dx * dx; b += dx * dy; c += dy * dy }
        a /= pts.size; b /= pts.size; c /= pts.size
        val tr = a + c; val det = a * c - b * b
        val l1 = tr / 2 + sqrt(max(0.0, tr * tr / 4 - det))
        var ex = b; var ey = l1 - a
        if (abs(b) < 1e-6) { if (a >= c) { ex = 1.0; ey = 0.0 } else { ex = 0.0; ey = 1.0 } }
        val L = hypot(ex, ey).let { if (it == 0.0) 1.0 else it }
        ex /= L; ey /= L
        if (ey > 0) { ex = -ex; ey = -ey }
        val nx = -ey; val ny = ex
        var tmin = 1e9; var tmax = -1e9; var smin = 1e9; var smax = -1e9
        for (p in pts) {
            val dx = p[0] - mx; val dy = p[1] - my
            val t = dx * ex + dy * ey; val su = dx * nx + dy * ny
            if (t < tmin) tmin = t; if (t > tmax) tmax = t
            if (su < smin) smin = su; if (su > smax) smax = su
        }
        val tmid = (tmin + tmax) / 2; val smid = (smin + smax) / 2
        val ccx = mx + ex * tmid + nx * smid
        val ccy = my + ey * tmid + ny * smid
        return Geo(ccx.toFloat(), ccy.toFloat(), ex.toFloat(), ey.toFloat(),
            (tmax - tmin).toFloat(), (smax - smin).toFloat())
    }

    /** 볼록껍질(monotone chain) — cv2.findContours 대용(볼록 근사). 입력/출력 정수점. */
    private fun convexHull(pts: List<IntArray>): List<IntArray> {
        if (pts.size < 3) return pts
        val p = pts.distinctBy { it[0] * 100000 + it[1] }.sortedWith(compareBy({ it[0] }, { it[1] }))
        if (p.size < 3) return p
        fun cross(o: IntArray, a: IntArray, b: IntArray) =
            (a[0] - o[0]).toLong() * (b[1] - o[1]) - (a[1] - o[1]).toLong() * (b[0] - o[0])
        val lower = ArrayList<IntArray>()
        for (pt in p) {
            while (lower.size >= 2 && cross(lower[lower.size - 2], lower[lower.size - 1], pt) <= 0) lower.removeAt(lower.size - 1)
            lower.add(pt)
        }
        val upper = ArrayList<IntArray>()
        for (pt in p.asReversed()) {
            while (upper.size >= 2 && cross(upper[upper.size - 2], upper[upper.size - 1], pt) <= 0) upper.removeAt(upper.size - 1)
            upper.add(pt)
        }
        lower.removeAt(lower.size - 1); upper.removeAt(upper.size - 1)
        return lower + upper
    }

    /** JPEG → (W, H, nails). 안경/폰이 보낸 프레임을 검출. */
    fun infer(jpeg: ByteArray): Triple<Int, Int, List<Nail>> {
        val bmp = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size) ?: return Triple(0, 0, emptyList())
        val W = bmp.width; val H = bmp.height
        val r = min(S.toFloat() / W, S.toFloat() / H)
        val nw = (W * r).roundToInt(); val nh = (H * r).roundToInt()
        val px = (S - nw) / 2; val py = (S - nh) / 2

        // letterbox (gray 114 배경)
        val lb = Bitmap.createBitmap(S, S, Bitmap.Config.ARGB_8888)
        Canvas(lb).apply {
            drawColor(Color.rgb(114, 114, 114))
            drawBitmap(Bitmap.createScaledBitmap(bmp, nw, nh, true), px.toFloat(), py.toFloat(), null)
        }
        val pixels = IntArray(S * S); lb.getPixels(pixels, 0, S, 0, 0, S, S)
        val n = S * S
        val chw = FloatArray(3 * n)
        for (i in 0 until n) {
            val q = pixels[i]
            chw[i] = ((q shr 16) and 0xff) / 255f          // R
            chw[i + n] = ((q shr 8) and 0xff) / 255f        // G
            chw[i + 2 * n] = (q and 0xff) / 255f            // B
        }

        val input = OnnxTensor.createTensor(env, FloatBuffer.wrap(chw), longArrayOf(1, 3, S.toLong(), S.toLong()))
        val res = session.run(mapOf(inputName to input))
        val a0 = FloatArray(37 * NA); (res.get("output0").get() as OnnxTensor).floatBuffer.get(a0)
        val a1 = FloatArray(32 * PN); (res.get("output1").get() as OnnxTensor).floatBuffer.get(a1)
        res.close(); input.close()

        // 후보 + NMS
        val cands = ArrayList<Cand>()
        for (i in 0 until NA) {
            val sc = a0[4 * NA + i]
            if (sc < CONF) continue
            val cx = a0[i]; val cy = a0[NA + i]; val w = a0[2 * NA + i]; val h = a0[3 * NA + i]
            cands.add(Cand(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, sc, i))
        }
        cands.sortByDescending { it.sc }
        val keep = ArrayList<Cand>()
        for (cd in cands) {
            if (keep.any { iou(cd, it) > IOU }) continue
            keep.add(cd); if (keep.size >= MAXDET) break
        }

        val nails = ArrayList<Nail>()
        for (k in keep) {
            val coef = FloatArray(32) { a0[(5 + it) * NA + k.i] }
            val bx1 = max(0, (k.x1 / 4).toInt()); val by1 = max(0, (k.y1 / 4).toInt())
            val bx2 = min(PW - 1, ceil(k.x2 / 4.0).toInt()); val by2 = min(PH - 1, ceil(k.y2 / 4.0).toInt())
            val pts = ArrayList<IntArray>()
            for (my in by1..by2) for (mx in bx1..bx2) {
                val p = my * PW + mx
                var s = 0f
                for (j in 0 until 32) s += coef[j] * a1[j * PN + p]
                if (sigmoid(s) > MASK_THR) pts.add(intArrayOf(mx, my))
            }
            if (pts.size < 8) continue
            val g = pca(pts)
            val ocx = (g.mx * 4 - px) / r
            val ocy = (g.my * 4 - py) / r
            val contour = convexHull(pts).map {
                intArrayOf(((it[0].toFloat() * 4 - px) / r).roundToInt(),
                           ((it[1].toFloat() * 4 - py) / r).roundToInt())
            }
            nails.add(Nail(ocx, ocy, g.ex, g.ey, g.len * 4 / r, g.wid * 4 / r, contour))
        }
        return Triple(W, H, nails)
    }
}
