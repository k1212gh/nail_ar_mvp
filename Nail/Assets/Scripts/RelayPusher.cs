// RelayPusher.cs — 안경이 자기 화면(AR 오버레이 포함)을 오라클 릴레이로 직접 POST한다.
//
// 지금까지의 경로:  안경 --USB--> PC(adb screenrecord + web/relay_compose_push.py) --인터넷--> 릴레이
// 이 컴포넌트의 경로: 안경 --WiFi--> 릴레이            (PC가 사슬에서 빠진다)
//
// 프레임당 처리 (3단 파이프라인 — 각 단이 서로를 기다리지 않는다):
//   [메인]   전용 캡처 카메라가 AR 캔버스를 RenderTexture에 단안으로 직접 렌더
//            → AsyncGPUReadback → raw 복사(≈0.5ms)
//   [인코더] RGB24 raw → JPEG                              ← X3에서 480x360 기준 수십 ms
//   [업로더] JPEG → keep-alive HTTP POST /push (스레드 N개) ← 인터넷 왕복 40~100ms
//
// 단을 나눈 이유는 실측이다. 인코딩과 업로드를 한 스레드에서 직렬로 하면
// (인코딩 100ms + 왕복 100ms) = 5fps 에 묶였다. web/relay_compose_push.py 가 WORKERS=4 로
// 푼 것과 똑같은 문제 — 지연을 겹쳐야 fps가 산다.
//
// 캡처를 '전용 카메라 렌더'로 하는 이유(실측으로 배운 것):
//   처음엔 ScreenCapture.CaptureScreenshotIntoRenderTexture 로 백버퍼를 잡았다. 송출은 되는데
//   화면이 완전 검정으로만 나갔다. 같은 순간 adb screencap 은 카메라 피드가 멀쩡히 찍혔으니
//   안경 화면이 검은 게 아니라, XR 스테레오 합성 결과를 그 API가 못 가져오는 것이었다.
//   AR 캔버스는 World Space(카메라 앞 m_Depth 에 떠 있는 판)라서, 카메라 하나를 더 두고
//   그 캔버스를 단안으로 다시 그리면 XR 합성을 거치지 않고도 같은 그림을 얻는다.
//
// EdgeClient가 검출 서버로 보내는 건 카메라 원본이라 오버레이가 없다. 사장님이 봐야 하는 건
// 손톱 위에 디자인이 얹힌 '안경이 보여주는 화면'이므로 캔버스(피드 + 오버레이)를 그려야 한다.
//
// 설정은 nail_calib.json (NailARController.PollCalib이 0.7초마다 반영) — 재빌드 없이 켜고 끈다:
//   {"relayOn":1,"relayUrl":"http://161.33.176.78:8090","relayToken":"<PUSH_TOKEN>","relayFps":12}
//
// ⚠ 토큰이 안경의 nail_calib.json에 평문으로 남고 릴레이도 HTTP(평문)다. web/cloud_relay.py 상단
//   주석과 동일한 전제 — 실운영은 릴레이 앞단 HTTPS + 토큰 회전이 필요하다.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;

public class RelayPusher : MonoBehaviour
{
    // --- 설정 (nail_calib.json 으로 런타임 주입; NailARController가 대입) ---
    public bool on;                       // 중계 송출 on/off
    public float fps = 12f;               // 송출 fps 목표. 안경 발열/배터리 때문에 PC 컴포지터(20)보다 낮게
    public int width = 480;               // 전송 가로 px. 인코딩 비용이 픽셀 수에 비례해서 fps를 지배한다
    public int quality = 70;              // JPEG 품질
    public bool flipY;                    // 화면이 뒤집혀 보일 때 1 (플랫폼별 RT 원점 차이 보정)
    public int workers = 3;               // 업로드 스레드 수. 왕복 지연을 겹쳐 fps를 올린다

    // --- 엔드포인트 (워커 스레드가 읽으므로 m_EpLock 으로 보호) ---
    private readonly object m_EpLock = new object();
    private string m_Url = "", m_Token = "";
    private string m_Host = "", m_Path = "";
    private int m_Port = 80;
    private int m_Epoch;                  // 주소/토큰이 바뀔 때 증가 → 커넥션들이 스스로 재접속

    // --- 캡처 ---
    private Camera m_Cap;                 // AR 캔버스를 단안으로 다시 그리는 전용 카메라
    private RenderTexture m_Small, m_Flip;
    private Texture2D m_Sync;             // AsyncGPUReadback 미지원 기기 폴백용
    private int m_InFlight;               // 진행 중인 readback 수 (백로그 방지)
    private float m_LastCap;
    private bool m_Warned, m_WarnedCam;

    // --- 파이프라인 큐 ---
    private readonly object m_RawLock = new object();
    private byte[] m_Raw; private int m_RawW, m_RawH;      // 인코더 입력: 최신 1장(신선도 우선)
    private readonly object m_JpgLock = new object();
    private readonly Queue<byte[]> m_JpgQ = new Queue<byte[]>();   // 업로더 입력
    private const int k_JpgMax = 3;                        // 꽉 차면 가장 오래된 것부터 버린다

    private Thread m_Enc;
    private Thread[] m_Up;
    private volatile bool m_Run;

    // --- 통계 (스레드 간 공유; Interlocked) ---
    private int m_Sent, m_Err, m_Dropped, m_LastSent;
    private volatile int m_EncMs, m_NetMs;
    private float m_StatAt;

    /// <summary>엔드포인트 변경(주소/토큰). 실제로 바뀔 때만 epoch를 올려 커넥션을 갈아끼운다.</summary>
    public void SetEndpoint(string url, string token)
    {
        url = url ?? ""; token = token ?? "";
        if (url == m_Url && token == m_Token) return;
        string host = "", path = "/push?token=" + Uri.EscapeDataString(token);
        int port = 80;
        if (!string.IsNullOrEmpty(url))
        {
            try
            {
                var u = new Uri(url);
                host = u.Host;
                port = u.IsDefaultPort ? 80 : u.Port;
            }
            catch (Exception e) { Debug.LogWarning("[Relay] bad relayUrl: " + e.Message); }
        }
        lock (m_EpLock)
        {
            m_Url = url; m_Token = token;
            m_Host = host; m_Port = port; m_Path = path;
            m_Epoch++;
        }
        Debug.Log($"[Relay] endpoint -> {host}:{port}{(string.IsNullOrEmpty(token) ? "  (token 비어있음!)" : "")}");
    }

    public bool Ready { get { lock (m_EpLock) { return on && m_Host.Length > 0 && m_Token.Length > 0; } } }
    // calib의 ""=leave 규약을 호출측이 지킬 수 있게 현재 값을 노출한다.
    public string Url => m_Url;
    public string Token => m_Token;

    // 설정 영속화. nail_calib.json 은 push_calib.py 가 '모든 필드'를 leave 센티널로 채워 덮어쓰기
    // 때문에, 다른 용도로 calib를 한 번만 밀어도 relayToken 이 "" 로 지워진다. 앱이 살아있는 동안은
    // ""=leave 규약으로 버티지만 재시작하면 중계가 죽는다(실제로 겪음). 마지막 설정을 기기에 남긴다.
    // ⚠ 토큰이 PlayerPrefs 에도 평문으로 남는다 — calib 파일과 같은 수준의 노출이다.
    private const string k_PrefUrl = "nailar.relayUrl", k_PrefTok = "nailar.relayToken",
                         k_PrefOn = "nailar.relayOn", k_PrefFps = "nailar.relayFps",
                         k_PrefW = "nailar.relayW", k_PrefQ = "nailar.relayQ", k_PrefFlip = "nailar.relayFlipY";

    private void LoadPrefs()
    {
        string u = PlayerPrefs.GetString(k_PrefUrl, "");
        if (u.Length > 0) SetEndpoint(u, PlayerPrefs.GetString(k_PrefTok, ""));
        on = PlayerPrefs.GetInt(k_PrefOn, 0) == 1;
        fps = PlayerPrefs.GetFloat(k_PrefFps, fps);
        width = PlayerPrefs.GetInt(k_PrefW, width);
        quality = PlayerPrefs.GetInt(k_PrefQ, quality);
        flipY = PlayerPrefs.GetInt(k_PrefFlip, 0) == 1;
        if (u.Length > 0) Debug.Log($"[Relay] 저장된 설정 복원 (on={on} {width}px @{fps}fps)");
    }

    /// <summary>calib로 설정이 바뀔 때마다 NailARController가 호출한다.</summary>
    public void SavePrefs()
    {
        PlayerPrefs.SetString(k_PrefUrl, m_Url);
        PlayerPrefs.SetString(k_PrefTok, m_Token);
        PlayerPrefs.SetInt(k_PrefOn, on ? 1 : 0);
        PlayerPrefs.SetFloat(k_PrefFps, fps);
        PlayerPrefs.SetInt(k_PrefW, width);
        PlayerPrefs.SetInt(k_PrefQ, quality);
        PlayerPrefs.SetInt(k_PrefFlip, flipY ? 1 : 0);
        PlayerPrefs.Save();
    }

    void Start()
    {
        LoadPrefs();
        m_Run = true;
        m_Enc = new Thread(EncodeLoop) { IsBackground = true, Name = "RelayEncode" };
        m_Enc.Start();
        int n = Mathf.Clamp(workers, 1, 6);
        m_Up = new Thread[n];
        for (int i = 0; i < n; i++)
        {
            m_Up[i] = new Thread(UploadLoop) { IsBackground = true, Name = "RelayUp" + i };
            m_Up[i].Start();
        }
        StartCoroutine(CaptureLoop());
    }

    void OnDestroy()
    {
        m_Run = false;
        if (m_Cap != null) { Destroy(m_Cap.gameObject); m_Cap = null; }
        if (m_Small != null) { m_Small.Release(); m_Small = null; }
        if (m_Flip != null) { m_Flip.Release(); m_Flip = null; }
    }

    // ---------------- 1단: 캡처 (메인 스레드) ----------------

    private IEnumerator CaptureLoop()
    {
        var eof = new WaitForEndOfFrame();
        while (true)
        {
            if (!Ready) { m_LastCap = 0f; yield return null; continue; }
            float interval = fps > 0f ? 1f / fps : 0f;
            if (Time.unscaledTime - m_LastCap < interval) { yield return null; continue; }
            // 백버퍼는 이 프레임의 렌더가 끝난 뒤에야 최종 화면을 담는다.
            yield return eof;
            m_LastCap = Time.unscaledTime;
            try { Capture(); }
            catch (Exception e) { Debug.LogWarning("[Relay] capture: " + e.Message); }
            Stats();
        }
    }

    /// <summary>AR 캔버스를 단안으로 다시 그릴 전용 카메라. 메인 카메라의 자식이라 위치·자세·화각이
    /// 같고, stereoTargetEye=None 이라 XR 출력에는 끼어들지 않는다(안경 화면은 그대로).</summary>
    private bool EnsureCapCam()
    {
        if (m_Cap != null) return true;
        var main = Camera.main;
        if (main == null)
        {
            if (!m_WarnedCam) { m_WarnedCam = true; Debug.LogWarning("[Relay] Camera.main 없음 — 캡처 불가"); }
            return false;
        }
        var go = new GameObject("RelayCapCam");
        go.transform.SetParent(main.transform, false);
        m_Cap = go.AddComponent<Camera>();
        m_Cap.CopyFrom(main);
        m_Cap.stereoTargetEye = StereoTargetEyeMask.None;
        m_Cap.clearFlags = CameraClearFlags.SolidColor;
        m_Cap.backgroundColor = Color.black;
        m_Cap.cullingMask = ~0;      // mono 모드면 캔버스가 전용 레이어(31)로 옮겨가므로 전부 그린다
        m_Cap.depth = -100;          // 화면 출력 순서에 영향 없게
        m_Cap.enabled = false;       // 매 프레임 자동 렌더 금지 — 우리가 필요할 때만 Render()
        m_Cap.targetTexture = null;
        Debug.Log($"[Relay] 캡처 카메라 생성 (fov={m_Cap.fieldOfView:F1})");
        return true;
    }

    private void Capture()
    {
        // readback이 밀리면 캡처를 건너뛴다 — 쌓아봐야 오래된 프레임이라 버릴 것들이다.
        if (m_InFlight >= 2) { Interlocked.Increment(ref m_Dropped); return; }
        if (!EnsureCapCam()) return;

        int sw = Screen.width, sh = Screen.height;
        if (sw <= 0 || sh <= 0) return;
        // RGB24는 행이 4바이트 정렬을 타므로 가로/세로를 4의 배수로 맞춘다(패딩으로 색이 밀리는 것 방지).
        int outW = Mathf.Max(16, width & ~3);
        // 안경 화면은 좌/우 두 눈이 나란한 형태라, 한쪽 눈(가로 절반) 기준으로 종횡비를 잡는다.
        int outH = Mathf.Max(16, Mathf.RoundToInt(outW * sh / Mathf.Max(1f, sw * 0.5f)) & ~3);
        if (m_Small == null || m_Small.width != outW || m_Small.height != outH)
        {
            if (m_Small != null) m_Small.Release();
            m_Small = new RenderTexture(outW, outH, 16, RenderTextureFormat.ARGB32);
            if (m_Flip != null) { m_Flip.Release(); m_Flip = null; }
        }

        m_Cap.aspect = (float)outW / outH;
        m_Cap.targetTexture = m_Small;
        m_Cap.Render();
        m_Cap.targetTexture = null;

        var src = m_Small;
        if (flipY)
        {
            if (m_Flip == null) m_Flip = new RenderTexture(outW, outH, 0, RenderTextureFormat.ARGB32);
            Graphics.Blit(m_Small, m_Flip, new Vector2(1f, -1f), new Vector2(0f, 1f));
            src = m_Flip;
        }

        if (SystemInfo.supportsAsyncGPUReadback)
        {
            m_InFlight++;
            // RGB24: 알파를 뺀 만큼(25%) 복사·인코딩할 바이트가 준다. JPEG에 알파는 쓰이지 않는다.
            AsyncGPUReadback.Request(src, 0, TextureFormat.RGB24, OnReadback);
        }
        else
        {
            if (!m_Warned) { m_Warned = true; Debug.LogWarning("[Relay] AsyncGPUReadback 미지원 → 동기 ReadPixels 폴백(프레임 스톨 발생)"); }
            SyncGrab(src, outW, outH);
        }
    }

    private void OnReadback(AsyncGPUReadbackRequest r)
    {
        m_InFlight--;
        if (r.hasError || !Ready) return;
        try
        {
            // GetData가 돌려주는 NativeArray는 이 콜백이 끝나면 무효가 된다 → 워커에 넘기려면 복사가 필수.
            // 이 memcpy(≈0.5ms)로 수십 ms짜리 인코딩을 메인 스레드 밖으로 빼는 거래다.
            PutRaw(r.GetData<byte>().ToArray(), m_Small.width, m_Small.height);
        }
        catch (Exception e) { Debug.LogWarning("[Relay] readback: " + e.Message); }
    }

    /// <summary>AsyncGPUReadback 미지원 기기용 폴백. 파이프라인을 세우므로 fps가 떨어진다.</summary>
    private void SyncGrab(RenderTexture src, int w, int h)
    {
        if (m_Sync == null || m_Sync.width != w || m_Sync.height != h)
            m_Sync = new Texture2D(w, h, TextureFormat.RGB24, false);
        var prev = RenderTexture.active;
        RenderTexture.active = src;
        m_Sync.ReadPixels(new Rect(0, 0, w, h), 0, 0);
        m_Sync.Apply(false);
        RenderTexture.active = prev;
        PutRaw(m_Sync.GetRawTextureData(), w, h);   // 인코딩은 폴백 경로에서도 인코더 스레드가 한다
    }

    private void PutRaw(byte[] raw, int w, int h)
    {
        if (raw == null || raw.Length == 0) return;
        lock (m_RawLock)
        {
            if (m_Raw != null) Interlocked.Increment(ref m_Dropped);   // 인코더가 아직 이전 장 처리 중
            m_Raw = raw; m_RawW = w; m_RawH = h;
        }
    }

    private void Stats()
    {
        float dt = Time.unscaledTime - m_StatAt;
        if (dt < 5f) return;
        int sent = m_Sent;
        float f = (sent - m_LastSent) / dt;      // 실제 송출 fps — 튜닝의 유일한 지표
        m_LastSent = sent; m_StatAt = Time.unscaledTime;
        Debug.Log($"[Relay] {f:F1}fps sent={sent} err={m_Err} drop={m_Dropped} enc={m_EncMs}ms net={m_NetMs}ms " +
                  $"{m_Small?.width}x{m_Small?.height}@q{quality} up={m_Up?.Length}");
    }

    // ---------------- 2단: 인코딩 (전용 스레드) ----------------

    private void EncodeLoop()
    {
        var clock = new System.Diagnostics.Stopwatch();
        while (m_Run)
        {
            byte[] raw = null; int w = 0, h = 0;
            lock (m_RawLock) { raw = m_Raw; w = m_RawW; h = m_RawH; m_Raw = null; }
            if (raw == null) { Thread.Sleep(2); continue; }
            try
            {
                clock.Restart();
                // 관리 배열 오버로드라 NativeArray 수명 문제 없이 워커 스레드에서 인코딩할 수 있다.
                byte[] jpg = ImageConversion.EncodeArrayToJPG(raw, GraphicsFormat.R8G8B8_UNorm, (uint)w, (uint)h, 0, quality);
                m_EncMs = (int)clock.ElapsedMilliseconds;
                if (jpg == null || jpg.Length == 0) { Interlocked.Increment(ref m_Err); continue; }
                lock (m_JpgLock)
                {
                    while (m_JpgQ.Count >= k_JpgMax) { m_JpgQ.Dequeue(); Interlocked.Increment(ref m_Dropped); }
                    m_JpgQ.Enqueue(jpg);
                }
            }
            catch (Exception e)
            {
                Interlocked.Increment(ref m_Err);
                Debug.LogWarning("[Relay] encode: " + e.Message);
                Thread.Sleep(50);
            }
        }
    }

    // ---------------- 3단: 업로드 (스레드 N개) ----------------
    // UnityWebRequest는 메인 스레드 코루틴이라 업로드 지연이 렌더 루프와 얽힌다. 소켓을 직접 들고
    // 백그라운드에서 보내되, keep-alive를 유지해 프레임마다 TCP 핸드셰이크를 다시 하지 않는다.

    private void UploadLoop()
    {
        var conn = new Conn();
        var clock = new System.Diagnostics.Stopwatch();
        while (m_Run)
        {
            byte[] jpg = null;
            lock (m_JpgLock) { if (m_JpgQ.Count > 0) jpg = m_JpgQ.Dequeue(); }
            if (jpg == null) { Thread.Sleep(2); continue; }
            string host, path; int port, epoch;
            lock (m_EpLock) { host = m_Host; port = m_Port; path = m_Path; epoch = m_Epoch; }
            if (host.Length == 0) continue;
            try
            {
                clock.Restart();
                conn.Send(host, port, path, epoch, jpg);
                m_NetMs = (int)clock.ElapsedMilliseconds;
                Interlocked.Increment(ref m_Sent);
            }
            catch (Exception)
            {
                Interlocked.Increment(ref m_Err);
                conn.Close();
                Thread.Sleep(300);   // 릴레이가 죽었거나 WiFi가 끊긴 상태에서 매 프레임 재시도 방지
            }
        }
        conn.Close();
    }

    /// <summary>업로드 스레드 하나가 전용으로 쓰는 keep-alive HTTP 커넥션.</summary>
    private class Conn
    {
        private TcpClient m_Cli;
        private NetworkStream m_S;
        private int m_Epoch = -1;

        public void Send(string host, int port, string path, int epoch, byte[] jpg)
        {
            if (epoch != m_Epoch) { Close(); m_Epoch = epoch; }   // 주소/토큰이 바뀌었다
            if (m_Cli == null || !m_Cli.Connected || m_S == null)
            {
                Close();
                m_Cli = new TcpClient { NoDelay = true, SendTimeout = 5000, ReceiveTimeout = 5000 };
                m_Cli.Connect(host, port);
                m_S = m_Cli.GetStream();
            }
            var head = Encoding.ASCII.GetBytes(
                "POST " + path + " HTTP/1.1\r\n" +
                "Host: " + host + ":" + port + "\r\n" +
                "Content-Type: image/jpeg\r\n" +
                "Content-Length: " + jpg.Length + "\r\n" +
                "Connection: keep-alive\r\n\r\n");
            m_S.Write(head, 0, head.Length);
            m_S.Write(jpg, 0, jpg.Length);
            m_S.Flush();
            ReadResponse();
        }

        public void Close()
        {
            try { m_S?.Close(); } catch { }
            try { m_Cli?.Close(); } catch { }
            m_S = null; m_Cli = null;
        }

        /// <summary>응답(보통 "ok" 2바이트)을 끝까지 비워 다음 POST가 같은 커넥션을 쓰게 한다.
        /// 토큰이 틀리면 릴레이가 403 + Connection: close 로 끊으므로 다음 전송에서 재연결된다.</summary>
        private void ReadResponse()
        {
            int len = -1; bool close = false;
            string line;
            while ((line = ReadLine()).Length > 0)
            {
                int c = line.IndexOf(':');
                if (c <= 0) continue;
                string k = line.Substring(0, c).Trim().ToLowerInvariant();
                string v = line.Substring(c + 1).Trim();
                if (k == "content-length") int.TryParse(v, out len);
                else if (k == "connection" && v.ToLowerInvariant().Contains("close")) close = true;
            }
            if (len > 0)
            {
                var buf = new byte[len]; int o = 0;
                while (o < len)
                {
                    int n = m_S.Read(buf, o, len - o);
                    if (n <= 0) throw new Exception("closed");
                    o += n;
                }
            }
            if (close) Close();
        }

        private string ReadLine()
        {
            var sb = new StringBuilder(64);
            while (true)
            {
                int b = m_S.ReadByte();
                if (b < 0) throw new Exception("closed");
                if (b == '\n') break;
                if (b != '\r') sb.Append((char)b);
            }
            return sb.ToString();
        }
    }
}
