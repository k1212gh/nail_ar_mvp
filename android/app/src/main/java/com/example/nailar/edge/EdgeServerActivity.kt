package com.example.nailar.edge

import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.nailar.R
import java.net.Inet4Address
import java.net.NetworkInterface

/**
 * 온디바이스 에지 서버 화면 — 시작하면 이 폰이 안경의 YOLO 손톱검출 서버가 된다.
 * 안경측: push_calib  useSocket=1  sockHost=<여기 표시된 IP>  sockPort=8444
 */
class EdgeServerActivity : AppCompatActivity() {

    private var onnx: NailOnnx? = null
    private var server: EdgeServer? = null
    private lateinit var status: TextView
    private lateinit var addr: TextView
    private lateinit var toggle: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_edge)
        status = findViewById(R.id.status)
        addr = findViewById(R.id.addr)
        toggle = findViewById(R.id.toggle)

        val ip = wifiIp() ?: "?.?.?.?"
        addr.text = "sockHost=$ip  sockPort=8444"
        status.text = "모델 로딩 중…"
        toggle.isEnabled = false

        // 모델 로드 + NNAPI 세션 준비는 무거우니 백그라운드
        Thread {
            val t0 = System.currentTimeMillis()
            // 기본 CPU — S22 Ultra 실측상 CPU(479ms) > XNNPACK(573) > NNAPI(1425). --es ep 로 변경 가능.
            val ep = intent.getStringExtra("ep") ?: "cpu"   // cpu|xnnpack|nnapi
            val m = try {
                NailOnnx(this, ep = ep)
            } catch (e: Throwable) {
                runOnUiThread { status.text = "모델 로드 실패: ${e.message}" }
                return@Thread
            }
            onnx = m
            runOnUiThread {
                status.text = "준비됨 (backend=${m.backend}, ${System.currentTimeMillis() - t0}ms)\n시작을 누르세요"
                toggle.isEnabled = true
                // --ez autostart true 이면 탭 없이 자동 시작(스크립트/헤드리스 테스트용)
                if (intent.getBooleanExtra("autostart", false)) startServer()
            }
        }.start()

        toggle.setOnClickListener {
            if (server == null) startServer() else stopServer()
        }
    }

    private fun startServer() {
        val m = onnx ?: return
        if (server != null) return
        val srv = EdgeServer(m, 8444) { s -> runOnUiThread { status.text = s } }
        server = srv
        srv.start()
        toggle.text = "중지"
    }

    private fun stopServer() {
        server?.stop()
        server = null
        toggle.text = "시작"
        status.text = "중지됨"
    }

    override fun onDestroy() {
        server?.stop()
        super.onDestroy()
    }

    /** 같은 WiFi에서 안경/폰이 접속할 이 기기의 사설 IPv4. */
    private fun wifiIp(): String? {
        try {
            for (nif in NetworkInterface.getNetworkInterfaces()) {
                if (!nif.isUp || nif.isLoopback) continue
                for (a in nif.inetAddresses) {
                    if (a is Inet4Address && a.isSiteLocalAddress) return a.hostAddress
                }
            }
        } catch (_: Exception) {}
        return null
    }
}
