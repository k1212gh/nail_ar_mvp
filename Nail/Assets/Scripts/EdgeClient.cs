// EdgeClient.cs — send a camera frame to the PC edge server (web/edge_serve.py)
// and receive nail geometry. Reuses the EXISTING /infer endpoint so detection
// (YOLOv8-seg / MediaPipe) stays on PC; Unity only captures + renders.
//
// /infer response: {"ok":true,"w":W,"h":H,"ms":X,"nails":[{"cx":..,"cy":..,"axisX":..,"axisY":..,"lengthPx":..,"widthPx":..}]}
// Reach the PC over USB via: adb reverse tcp:8081 tcp:8081  -> url = http://127.0.0.1:8081/infer
using System;
using System.Collections;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;
using UnityEngine.Networking;

// Matches web/edge_serve.py /infer response exactly:
//   {"cx":734.8,"cy":939.8,"ex":0.64,"ey":-0.77,"len":58.1,"wid":50.5,"contour":[[x,y],...]}
[Serializable]
public struct NailRoi
{
    public float cx, cy;      // nail center (input image px)
    public float ex, ey;      // tip-direction unit vector
    public float len, wid;    // nail length / width (px)
    public float distM;       // camera->hand absolute distance (m) via World Landmarks (0=unknown)
    public float lenMm, widMm; // REAL nail size (mm) — only when a reference card is in frame (?card=1)
    public float speed;       // kalman speed (px/frame) of this nail
    public bool stable;       // speed <= threshold → safe to render (render gating; hides latency ghosting)
    public float vx, vy;      // kalman velocity in IMAGE px/SECOND — drives latency-compensating
                              // prediction on the client (pos + v*(age+predict)), like VR reprojection
    public string finger;     // "thumb"/"index"/"middle"/"ring"/"pinky" — STABLE identity
    public string hand;       // "Left"/"Right" — with finger, keys the per-nail smoothing slot
    // Identity key so each real nail keeps its OWN smoothing filter across frames. Without this,
    // slots matched by array index cross filters when a finger bends/occludes and indices shift
    // (grid/design slides between fingers, stale motion bleeds in). Falls back to "" (empty) which
    // the renderers replace with a positional key so behaviour degrades to the old index scheme.
    public string Key => (hand ?? "") + ":" + (finger ?? "");
    // NOTE: 'contour' (polygon) is also returned by /infer for precise nail-shape
    // clipping — omitted here (JsonUtility can't parse nested arrays). Add a custom
    // parser when porting the exact nail-outline mask.
}

// Enrollment progress (server accumulates per-finger mm samples -> nail_profile.json).
// Present in the response only while ?enroll=1; `active` guards missing-field defaults.
[Serializable]
public class EnrollStatus
{
    public bool active;
    public int count, need;   // min sample count across the best hand's 5 fingers / target
    public bool done;
    public string msg;        // ready-to-display HUD line, e.g. "[Right] T12 I40 ... /40"
}

// Reference-card scale (ISO/IEC 7810 ID-1 credit card = 85.60 x 53.98 mm), returned with ?card=1.
// mmPerPx converts image pixels -> real millimetres, which drives the LIFE-SIZE preview zoom.
[Serializable]
public class CardInfo
{
    public bool found;
    public float mmPerPx;     // real mm per image px (card plane); 0 when not found
    public float longPx;      // detected card long-edge length (px) — diagnostics
}

[Serializable]
public class InferResult
{
    public bool ok;
    public int w, h;
    public float ms;
    public List<NailRoi> nails = new List<NailRoi>();
    public EnrollStatus enroll;
    public CardInfo card;     // present only with ?card=1
}

// Accept the edge server's self-signed cert (local dev only). edge_serve.py = HTTPS:8443.
class AcceptAllCerts : CertificateHandler { protected override bool ValidateCertificate(byte[] c) => true; }

public class EdgeClient
{
    // edge_serve.py serves POST /infer over HTTPS:8443 (self-signed). Over USB:
    //   adb reverse tcp:8443 tcp:8443   -> url = https://127.0.0.1:8443/infer
    // TRANSPORT: the endpoint is intentionally NOT hard-coded to USB. It is overridable at runtime
    // via nail_calib.json {"edgeUrl": "..."} so the same build works for:
    //   USB (now):  adb reverse tcp:8443 tcp:8443 -> https://127.0.0.1:8443/infer
    //   Phone/LAN:  https://<host-ip>:8443/infer   (no rebuild needed)
    public string url = "https://127.0.0.1:8443/infer";
    public bool enroll;              // append ?enroll=1 (server accumulates mm samples)
    public bool enrollResetPending;  // one-shot &reset=1 on entering the Enroll mode
    public bool wantCard;            // append ?card=1 (server returns card mmPerPx + per-nail mm)

    /// <summary>POST a JPEG frame, parse nail ROIs. Runs as a coroutine.</summary>
    public IEnumerator Infer(byte[] jpeg, Action<InferResult> onResult)
    {
        string u = url;
        if (enroll)
        {
            u += (u.Contains("?") ? "&" : "?") + "enroll=1";
            if (enrollResetPending) { u += "&reset=1"; enrollResetPending = false; }
        }
        if (wantCard) u += (u.Contains("?") ? "&" : "?") + "card=1";
        using (var req = new UnityWebRequest(u, UnityWebRequest.kHttpVerbPOST))
        {
            req.uploadHandler = new UploadHandlerRaw(jpeg) { contentType = "image/jpeg" };
            req.downloadHandler = new DownloadHandlerBuffer();
            req.certificateHandler = new AcceptAllCerts();
            req.timeout = 3;
            yield return req.SendWebRequest();

            if (req.result != UnityWebRequest.Result.Success)
            {
                onResult?.Invoke(null);
                yield break;
            }
            InferResult res = null;
            try { res = JsonUtility.FromJson<InferResult>(req.downloadHandler.text); }
            catch (Exception e) { Debug.LogWarning("EdgeClient parse: " + e.Message); }
            onResult?.Invoke(res);
        }
    }
}

// Raw TCP socket transport (B') — persistent connection kills the per-frame TLS handshake that
// caps HTTP at ~2-3 fps. Protocol:  request [4B total-len BE][1B flags(bit0=card)][JPEG] ,
// response [4B len BE][JSON]. Plaintext (LAN/USB). Socket I/O runs on a background thread; the
// coroutine submits a frame then polls Done (frames-in-flight = 1).
public class EdgeSocketClient
{
    public string host = "127.0.0.1";
    public int port = 8444;
    public bool wantCard;

    TcpClient _cli;
    NetworkStream _s;
    Thread _worker;
    volatile bool _run;

    readonly object _lock = new object();
    byte[] _reqJpeg;
    string _resp;
    bool _reqPending, _resDone, _resErr;

    public void Start()
    {
        if (_worker != null && _worker.IsAlive) return;
        _run = true;
        _worker = new Thread(Worker) { IsBackground = true };
        _worker.Start();
    }
    public void Stop() { _run = false; try { _cli?.Close(); } catch { } }

    // main thread: hand off a frame, then poll Done/Err/Resp
    public void Submit(byte[] jpeg)
    {
        lock (_lock) { _reqJpeg = jpeg; _reqPending = true; _resDone = false; _resErr = false; }
    }
    public bool Done { get { lock (_lock) { return _resDone; } } }
    public bool Err  { get { lock (_lock) { return _resErr; } } }
    public string Resp { get { lock (_lock) { return _resp; } } }

    void Worker()
    {
        while (_run)
        {
            byte[] job = null;
            lock (_lock) { if (_reqPending) { job = _reqJpeg; _reqPending = false; } }
            if (job == null) { Thread.Sleep(2); continue; }
            try
            {
                EnsureConn();
                WriteFrame(job);
                string r = ReadFrame();
                lock (_lock) { _resp = r; _resDone = true; }
            }
            catch (Exception)
            {
                try { _cli?.Close(); } catch { }
                _cli = null; _s = null;
                lock (_lock) { _resErr = true; _resDone = true; }
            }
        }
    }

    void EnsureConn()
    {
        if (_cli != null && _cli.Connected) return;
        _cli = new TcpClient { NoDelay = true };
        _cli.Connect(host, port);
        _s = _cli.GetStream();
    }
    void WriteFrame(byte[] jpg)
    {
        int total = jpg.Length + 1;   // 1 flags byte + payload
        _s.Write(BitConverter.GetBytes(IPAddress.HostToNetworkOrder(total)), 0, 4);
        _s.WriteByte((byte)(wantCard ? 1 : 0));
        _s.Write(jpg, 0, jpg.Length);
        _s.Flush();
    }
    string ReadFrame()
    {
        int n = IPAddress.NetworkToHostOrder(BitConverter.ToInt32(ReadN(4), 0));
        return Encoding.UTF8.GetString(ReadN(n));
    }
    byte[] ReadN(int n)
    {
        var b = new byte[n]; int o = 0;
        while (o < n) { int r = _s.Read(b, o, n - o); if (r <= 0) throw new Exception("closed"); o += r; }
        return b;
    }
}
