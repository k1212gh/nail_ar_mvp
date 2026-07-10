package com.example.nailar

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Bundle
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import com.example.nailar.camera.CameraController
import com.example.nailar.render.OverlayView
import com.example.nailar.vision.HandNailDetector
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * 오케스트레이션 — PC `main.py` + `src/pipeline.py` 대응.
 *
 * 두 모드:
 *  - IMAGE MODE: 앱 외부폴더에 nail_input.jpg 가 있으면, 카메라 대신 그 정지영상으로
 *    손톱 검출 → 곡면 디자인 오버레이 렌더. (RayNeo 는 서드파티 카메라를 차단하므로
 *    글래스에서 시연/검증하는 경로. adb push .../files/nail_input.jpg 로 주입.)
 *  - CAMERA MODE: 후면 카메라 라이브(폰에서 동작; 글래스는 카메라 차단으로 미동작).
 */
class MainActivity : AppCompatActivity() {

    private lateinit var previewView: PreviewView
    private lateinit var overlayView: OverlayView
    private lateinit var hudText: TextView

    private var detector: HandNailDetector? = null
    private var camera: CameraController? = null
    private val io = Executors.newSingleThreadExecutor()
    @Volatile private var netRunning = false

    private val requestCamera =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) startCamera()
            else { Toast.makeText(this, "카메라 권한이 필요합니다", Toast.LENGTH_LONG).show(); finish() }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        previewView = findViewById(R.id.previewView)
        overlayView = findViewById(R.id.overlayView)
        hudText = findViewById(R.id.hudText)
        overlayView.setOnClickListener { overlayView.toggleDesign() }

        val cfg = readConfig()
        cfg?.let { applyOverlayConfig(it) }
        val frameUrl = cfg?.optString("frameUrl", "") ?: ""
        val input = File(getExternalFilesDir(null), "nail_input.jpg")
        when {
            frameUrl.isNotEmpty() -> startNetworkMode(frameUrl)   // 폰/PC 캡처 → 안경 표시
            input.exists() -> startImageMode(input)               // 정지영상 시연
            hasCameraPermission() -> startCamera()                // 폰 로컬 카메라
            else -> requestCamera.launch(Manifest.permission.CAMERA)
        }
    }

    private fun readConfig(): JSONObject? = try {
        val f = File(getExternalFilesDir(null), "nailar_config.json")
        if (f.exists()) JSONObject(f.readText()) else null
    } catch (e: Exception) { null }

    private fun applyOverlayConfig(c: JSONObject) {
        overlayView.showGuide = c.optBoolean("showGuide", overlayView.showGuide)
        overlayView.useMesh = c.optBoolean("useMesh", overlayView.useMesh)
        if (c.has("designScale")) overlayView.setDesignScale(c.optDouble("designScale", 1.7).toFloat())
        if (c.has("alignX")) overlayView.alignX = c.optDouble("alignX", 0.0).toFloat()
        overlayView.fillMode = c.optBoolean("fill", overlayView.fillMode)
    }

    /** NETWORK MODE: 외부(폰/PC)에서 프레임 JPEG 을 받아 안경이 검출+렌더 = 표시 전용 클라이언트.
     *  안경 카메라 차단을 우회하는 최종 제품 경로(캡처=폰/PC, 표시=안경). */
    private fun startNetworkMode(url: String) {
        previewView.visibility = View.GONE
        hudText.text = "NET: connecting $url ..."
        netRunning = true
        io.execute {
            var frames = 0
            while (netRunning) {
                val t0 = System.currentTimeMillis()
                val bmp = fetchBitmap(url)
                if (bmp == null) { Thread.sleep(400); continue }
                val rois = try { HandNailDetector.detectImage(this, bmp) } catch (e: Exception) { emptyList() }
                val ms = System.currentTimeMillis() - t0
                frames++
                val n = frames
                runOnUiThread {
                    overlayView.setBackgroundImage(bmp)
                    overlayView.setResults(rois, bmp.width, bmp.height)
                    hudText.text = "NET: nails ${rois.size}  ${ms}ms/frame  #$n"
                }
                Thread.sleep(120)
            }
        }
    }

    private fun fetchBitmap(url: String): android.graphics.Bitmap? = try {
        val c = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 2000; readTimeout = 3000; requestMethod = "GET"
        }
        c.inputStream.use { BitmapFactory.decodeStream(it) }
    } catch (e: Exception) { android.util.Log.w("NailAR", "fetch failed: ${e.message}"); null }

    /** 정지영상 파이프라인: 카메라 없이 손톱 검출 → 곡면 디자인 오버레이. */
    private fun startImageMode(input: File) {
        previewView.visibility = View.GONE
        hudText.text = "IMAGE MODE: 검출 중..."
        io.execute {
            val bmp = BitmapFactory.decodeFile(input.absolutePath)
            if (bmp == null) {
                runOnUiThread { hudText.text = "이미지 로드 실패: ${input.name}" }
                return@execute
            }
            val t0 = System.currentTimeMillis()
            val rois = try { HandNailDetector.detectImage(this, bmp) }
                catch (e: Exception) { runOnUiThread { hudText.text = "검출 오류: ${e.message}" }; emptyList() }
            val ms = System.currentTimeMillis() - t0
            runOnUiThread {
                overlayView.setBackgroundImage(bmp)
                overlayView.setResults(rois, bmp.width, bmp.height)
                hudText.text = "IMAGE: nails ${rois.size}  det ${ms}ms  ${bmp.width}x${bmp.height} (탭=디자인)"
            }
        }
    }

    private fun startCamera() {
        detector = HandNailDetector(
            context = this,
            onResult = { rois, w, h, infMs ->
                runOnUiThread {
                    overlayView.setResults(rois, w, h)
                    hudText.text = "nails: ${rois.size}   inf: ${infMs}ms   (탭=디자인 on/off)"
                }
            },
            onError = { msg -> runOnUiThread { Toast.makeText(this, msg, Toast.LENGTH_SHORT).show() } },
        )
        camera = CameraController(
            context = this, lifecycleOwner = this, previewView = previewView,
            analyzer = { proxy -> detector?.detect(proxy) },
        ).also { it.start() }
    }

    private fun hasCameraPermission() =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED

    override fun onDestroy() {
        super.onDestroy()
        netRunning = false
        camera?.shutdown()
        detector?.close()
        io.shutdown()
    }
}
