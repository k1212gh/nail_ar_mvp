// EdgeClient.cs — send a camera frame to the PC edge server (web/edge_serve.py)
// and receive nail geometry. Reuses the EXISTING /infer endpoint so detection
// (YOLOv8-seg / MediaPipe) stays on PC; Unity only captures + renders.
//
// /infer response: {"ok":true,"w":W,"h":H,"ms":X,"nails":[{"cx":..,"cy":..,"axisX":..,"axisY":..,"lengthPx":..,"widthPx":..}]}
// Reach the PC over USB via: adb reverse tcp:8081 tcp:8081  -> url = http://127.0.0.1:8081/infer
using System;
using System.Collections;
using System.Collections.Generic;
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

[Serializable]
public class InferResult
{
    public bool ok;
    public int w, h;
    public float ms;
    public List<NailRoi> nails = new List<NailRoi>();
    public EnrollStatus enroll;
}

// Accept the edge server's self-signed cert (local dev only). edge_serve.py = HTTPS:8443.
class AcceptAllCerts : CertificateHandler { protected override bool ValidateCertificate(byte[] c) => true; }

public class EdgeClient
{
    // edge_serve.py serves POST /infer over HTTPS:8443 (self-signed). Over USB:
    //   adb reverse tcp:8443 tcp:8443   -> url = https://127.0.0.1:8443/infer
    public string url = "https://127.0.0.1:8443/infer";
    public bool enroll;              // append ?enroll=1 (server accumulates mm samples)
    public bool enrollResetPending;  // one-shot &reset=1 on entering the Enroll mode

    /// <summary>POST a JPEG frame, parse nail ROIs. Runs as a coroutine.</summary>
    public IEnumerator Infer(byte[] jpeg, Action<InferResult> onResult)
    {
        string u = url;
        if (enroll)
        {
            u += (u.Contains("?") ? "&" : "?") + "enroll=1";
            if (enrollResetPending) { u += "&reset=1"; enrollResetPending = false; }
        }
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
