package com.example.nailar.camera

import android.content.Context
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import java.util.concurrent.Executors

/**
 * CameraX 설정 — PC `src/video_source.py` 대응(입력 소스).
 * 후면 카메라로 Preview + ImageAnalysis 를 바인딩하고, 매 프레임을 analyzer 로 넘긴다.
 * 출력 포맷을 RGBA_8888 로 두어 ImageProxy.toBitmap() 변환을 단순화한다.
 */
class CameraController(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val previewView: PreviewView,
    private val analyzer: (ImageProxy) -> Unit,
) {
    private val executor = Executors.newSingleThreadExecutor()

    fun start() {
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            val provider = future.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }

            val analysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                .build()
                .also { it.setAnalyzer(executor) { proxy -> analyzer(proxy) } }

            provider.unbindAll()
            provider.bindToLifecycle(
                lifecycleOwner,
                CameraSelector.DEFAULT_BACK_CAMERA,   // 손톱은 후면 카메라(초점 양호)
                preview,
                analysis,
            )
        }, ContextCompat.getMainExecutor(context))
    }

    fun shutdown() = executor.shutdown()
}
