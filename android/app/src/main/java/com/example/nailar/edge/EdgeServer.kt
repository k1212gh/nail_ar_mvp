package com.example.nailar.edge

import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.DataInputStream
import java.net.ServerSocket
import java.net.Socket

/**
 * 안경/폰이 붙는 온디바이스 에지 서버 — web/edge_serve.py 소켓 경로(8444)와 100% 동일 프로토콜.
 *   요청:  [4B big-endian total][1B flags][JPEG]   (total = 1 + JPEG길이)
 *   응답:  [4B big-endian len][JSON]                {"ok","w","h","ms","nails":[{cx,cy,ex,ey,len,wid,contour}]}
 * 안경측은 push_calib 로 sockHost=<이 폰 IP>, sockPort=8444 만 지정하면 그대로 붙는다.
 */
class EdgeServer(
    private val onnx: NailOnnx,
    private val port: Int = 8444,
    private val onStatus: (String) -> Unit,
) {
    @Volatile private var running = false
    private var server: ServerSocket? = null

    fun start() {
        if (running) return
        running = true
        Thread({ acceptLoop() }, "edge-accept").start()
    }

    fun stop() {
        running = false
        try { server?.close() } catch (_: Exception) {}
    }

    private fun acceptLoop() {
        try {
            val s = ServerSocket(port)
            s.reuseAddress = true
            server = s
            onStatus("대기 중 :$port (backend=${onnx.backend})")
            while (running) {
                val cli = try { s.accept() } catch (e: Exception) { if (running) onStatus("accept 오류"); break }
                Thread({ handle(cli) }, "edge-client").start()
            }
        } catch (e: Exception) {
            if (running) onStatus("서버 오류: ${e.message}")
        }
    }

    private fun readU32(ins: DataInputStream): Int {
        val b = ByteArray(4)
        ins.readFully(b)
        return ((b[0].toInt() and 0xff) shl 24) or ((b[1].toInt() and 0xff) shl 16) or
               ((b[2].toInt() and 0xff) shl 8) or (b[3].toInt() and 0xff)
    }

    private fun writeU32(out: BufferedOutputStream, v: Int) {
        out.write((v ushr 24) and 0xff); out.write((v ushr 16) and 0xff)
        out.write((v ushr 8) and 0xff); out.write(v and 0xff)
    }

    private fun handle(cli: Socket) {
        val peer = cli.inetAddress?.hostAddress ?: "?"
        try {
            cli.tcpNoDelay = true
            val ins = DataInputStream(BufferedInputStream(cli.getInputStream()))
            val out = BufferedOutputStream(cli.getOutputStream())
            onStatus("접속: $peer")
            while (running) {
                val total = try { readU32(ins) } catch (e: Exception) { break }
                if (total < 1 || total > 20_000_000) break
                val payload = ByteArray(total)
                ins.readFully(payload)
                // payload[0] = flags(bit0=wantCard, 미사용), 나머지 = JPEG
                val jpeg = payload.copyOfRange(1, total)
                val t0 = System.nanoTime()
                val (w, h, nails) = onnx.infer(jpeg)
                val ms = (System.nanoTime() - t0) / 1e6
                val json = buildJson(w, h, ms, nails).toByteArray(Charsets.UTF_8)
                writeU32(out, json.size); out.write(json); out.flush()
                onStatus("$peer  nails=${nails.size}  ${ms.toInt()}ms  (${(1000.0 / ms).toInt()}fps)")
            }
        } catch (_: Exception) {
        } finally {
            try { cli.close() } catch (_: Exception) {}
        }
    }

    private fun f1(v: Float) = String.format("%.1f", v)
    private fun f4(v: Float) = String.format("%.4f", v)

    private fun buildJson(w: Int, h: Int, ms: Double, nails: List<Nail>): String {
        val sb = StringBuilder(256)
        sb.append("{\"ok\":true,\"w\":").append(w).append(",\"h\":").append(h)
            .append(",\"ms\":").append(f1(ms.toFloat())).append(",\"nails\":[")
        for ((i, n) in nails.withIndex()) {
            if (i > 0) sb.append(',')
            sb.append("{\"cx\":").append(f1(n.cx)).append(",\"cy\":").append(f1(n.cy))
                .append(",\"ex\":").append(f4(n.ex)).append(",\"ey\":").append(f4(n.ey))
                .append(",\"len\":").append(f1(n.len)).append(",\"wid\":").append(f1(n.wid))
                .append(",\"contour\":[")
            for ((j, pt) in n.contour.withIndex()) {
                if (j > 0) sb.append(',')
                sb.append('[').append(pt[0]).append(',').append(pt[1]).append(']')
            }
            sb.append("]}")
        }
        sb.append("]}")
        return sb.toString()
    }
}
