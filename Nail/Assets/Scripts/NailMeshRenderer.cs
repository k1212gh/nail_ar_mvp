// NailMeshRenderer.cs — per-nail CURVED mesh (semi-cylinder strip) with a baked
// per-finger texture. Stage 3 of "enroll once -> bake once -> runtime pose-only":
// nail_bake.json carries each finger's REAL mm size + curvature (measured by the
// edge server's enroll mode, baked by tools/build/bake_nail_design.py), so per frame
// we only need center/axis/distance from the server. The GPU projects the curved
// surface (tilt/perspective come free) and NailBakedGloss sweeps a highlight as the
// surface normal moves. Falls back to Resources/designs + standard sizes when no
// bake has been pushed, so the mode still works out of the box.
//
// Coordinate space mirrors NailOverlayRenderer exactly (same camera-px -> canvas-local
// mapping incl. rotQuadrant/mirror/calibScale), so SPAAM calibration applies as-is.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

public class NailMeshRenderer : MonoBehaviour
{
    [Header("Refs")]
    public RectTransform cameraViewRect;   // canvas rect = coordinate space (px units)
    public bool show = false;

    [Header("AR calibration (mirrors NailOverlayRenderer)")]
    public int rotQuadrant = 1;
    public Vector2 calibOffset = Vector2.zero;
    [Range(0.2f, 3f)] public float calibScale = 1f;
    public bool mirrorX = false, mirrorY = false;
    public float designRotDeg = 0f;
    [Range(0.3f, 3f)] public float designScale = 1.15f;

    // Shift the design ALONG the nail's own axis, as a fraction of nail length.
    // +tip / -base. Needed because the detected centre is DIP+0.6*(TIP-DIP), i.e. slightly
    // PROXIMAL of the visible nail plate -> the design reads as "a bit below the nail".
    // Pose-independent (follows each nail's axis), unlike a global calibOffset.
    [Range(-0.5f, 0.5f)] public float alongTip = 0f;

    // MIRROR mode = pure image-space compositing on the camera feed: no eye parallax, no metric
    // (mm+distance) sizing, no SPAAM spread. One flag neutralises the whole see-through pipeline
    // so mirror can't inherit stale calibration state (the root cause of the small mis-alignments).
    public bool mirrorMode = false;

    // --- Latency compensation (late-stage reprojection) --------------------------------------
    // The offload pipeline (capture -> encode -> detect -> render) lags ~150-250 ms, so a moving
    // nail's design trails the hand. The server sends each nail's velocity (px/s); we draw at
    // pos + v*(age + predictSec) so the design lands where the nail IS, not where it was.
    // Safe by construction for our use case: while drawing, the hand is nearly still -> v≈0 -> no
    // prediction error exactly when precision matters most.
    public float predictSec = 0f;        // pipeline latency to cancel (s). 0 = off
    public float maxPredictSec = 0.25f;  // hard cap so occlusion/stale data can't fling the design

    // --- Distance-adaptive parallax model: offset(d) = A + B/d --------------------------------
    // The camera-eye parallax error scales with 1/distance, so a single fixed calibOffset only
    // aligns at one distance. With per-nail metric distM (from the server) we evaluate the
    // offset PER FRAME, so registration holds across the whole working range. A = constant
    // camera/display axis misalignment (display px); B = parallax coefficient (px·m, ∝ baseline).
    // Solve A,B from pen-pointing at two distances (offset1=A+B/d1, offset2=A+B/d2). When off,
    // falls back to the static calibOffset.
    public bool parallaxEnable = false;
    public Vector2 parallaxA = Vector2.zero;   // display px
    public Vector2 parallaxB = Vector2.zero;   // display px · metre

    // Effective display-px offset for a nail at distance d (m); static fallback if no model/dist.
    private Vector2 OffsetFor(float distM)
    {
        if (mirrorMode) return Vector2.zero;   // mirror: design sits exactly where the nail is in the feed
        if (parallaxEnable && distM > 0.01f) return parallaxA + parallaxB / distM;
        return calibOffset;
    }

    [Header("Mesh / profile")]
    public float focalRatio = 0.86f;   // MUST match config.py HandConfig.focal_ratio
    public float defaultCurve = 0.22f; // sag/width when no bake manifest available
    public float bulgeSign = -1f;      // -1 = bulge toward viewer (canvas local -z)
    public bool tiltEnable = true;     // pitch from length foreshortening vs profile mm
    public float tiltMax = 40f, tiltSign = 1f;

    [Header("Gloss")]
    public float glossStrength = 0.9f, glossPower = 28f;

    [Header("Stability")]
    public float smoothing = 12f;
    public float holdSec = 0.4f;

    // --- baked profile -------------------------------------------------------------
    [Serializable] class BakeNail { public string hand, finger; public float lenMm, widMm, curve; public string tex; }
    [Serializable] class BakeManifest { public int version; public string design; public List<BakeNail> nails = new List<BakeNail>(); }
    class Bake { public float lenMm, widMm, curve; public Texture2D tex; }
    private readonly Dictionary<string, Bake> m_Bake = new Dictionary<string, Bake>();   // "hand:finger"
    private bool m_BakeLoaded;

    // fallback sizes (mm) — same table as bake_nail_design.py DEMO_MM
    private static readonly Dictionary<string, Vector2> k_DefaultMm = new Dictionary<string, Vector2> {
        {"thumb", new Vector2(14.0f, 13.0f)}, {"index", new Vector2(12.0f, 10.0f)},
        {"middle", new Vector2(13.0f, 10.5f)}, {"ring", new Vector2(12.0f, 9.5f)},
        {"pinky", new Vector2(9.5f, 8.0f)},
    };
    private static readonly string[] k_FingerOrder = { "thumb", "index", "middle", "ring", "pinky" };
    private Texture2D[] m_FallbackTex;     // Resources/designs, by finger slot

    // --- per-nail entries ------------------------------------------------------------
    class Entry
    {
        public GameObject go; public MeshFilter mf; public MeshRenderer mr; public Material mat;
        public Vector2 pos, size; public float rot, tilt; public float lastSeen = -999f;
        public Vector2 vel;   // canvas-local px/sec (for latency-compensating prediction)
        public bool placed; public float curve = -1f; public Texture2D tex;
    }
    private readonly Dictionary<string, Entry> m_Entries = new Dictionary<string, Entry>();
    private int m_ImgW = 1, m_ImgH = 1;
    private Shader m_Shader;

    /// <summary>(Re)load nail_bake.json + textures. Called on mode entry / calib bakeReload.</summary>
    public void ReloadBake()
    {
        m_BakeLoaded = true;
        m_Bake.Clear();
        string[] dirs = {
            "/sdcard/Android/data/" + Application.identifier + "/files/nail_bake",   // adb push target
            Path.Combine(Application.persistentDataPath, "nail_bake"),
            Path.Combine(Application.dataPath, "..", "..", "out", "nail_bake"),      // editor/PC test
        };
        foreach (var dir in dirs)
        {
            var mf = Path.Combine(dir, "nail_bake.json");
            try
            {
                if (!File.Exists(mf)) continue;
                var man = JsonUtility.FromJson<BakeManifest>(File.ReadAllText(mf));
                if (man == null || man.nails == null || man.nails.Count == 0) continue;
                int loaded = 0;
                foreach (var n in man.nails)
                {
                    var texPath = Path.Combine(dir, n.tex ?? "");
                    if (!File.Exists(texPath)) continue;
                    var t = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                    if (!t.LoadImage(File.ReadAllBytes(texPath))) continue;
                    t.wrapMode = TextureWrapMode.Clamp;
                    m_Bake[n.hand + ":" + n.finger] = new Bake {
                        lenMm = n.lenMm, widMm = n.widMm,
                        curve = n.curve > 0f ? n.curve : defaultCurve, tex = t };
                    loaded++;
                }
                Debug.Log($"[NailMesh] bake loaded {loaded} nails from {dir} (design={man.design})");
                if (loaded > 0) { InvalidateEntries(); return; }
            }
            catch (Exception e) { Debug.LogWarning("[NailMesh] bake load: " + e.Message); }
        }
        Debug.Log("[NailMesh] no bake found -> fallback designs + standard mm");
        InvalidateEntries();
    }

    // force entries to re-resolve texture/mesh after a reload
    private void InvalidateEntries()
    {
        foreach (var e in m_Entries.Values) { e.curve = -1f; e.tex = null; }
    }

    private Texture2D FallbackTex(string finger)
    {
        if (m_FallbackTex == null)
            m_FallbackTex = Resources.LoadAll<Texture2D>("designs");
        if (m_FallbackTex == null || m_FallbackTex.Length == 0) return Texture2D.whiteTexture;
        int idx = 0;
        for (int i = 0; i < k_FingerOrder.Length; i++) if (finger == k_FingerOrder[i]) { idx = i; break; }
        return m_FallbackTex[idx % m_FallbackTex.Length];
    }

    public void SetResults(List<NailRoi> rois, int imgW, int imgH)
    {
        if (!m_BakeLoaded) ReloadBake();
        m_ImgW = Mathf.Max(1, imgW); m_ImgH = Mathf.Max(1, imgH);
        if (rois == null || rois.Count == 0 || cameraViewRect == null) return;
        var size = cameraViewRect.rect.size;
        int q = ((rotQuadrant % 4) + 4) % 4;
        for (int idx = 0; idx < rois.Count; idx++)
        {
            var r = rois[idx];
            string key = r.Key;
            if (key == null || key == ":") key = "#" + idx;

            m_Bake.TryGetValue(r.Key ?? "", out var bake);
            // runtime pose-only sizing: expected camera px from profile mm + distance.
            // (fallback: the server's per-frame px when we have no profile/distance)
            float fpx = focalRatio * m_ImgW;
            // MIRROR: size straight from the detected px (matches the feed exactly). Metric sizing
            // (mm + distM) is a see-through feature and injects distM estimation error here.
            bool metric = !mirrorMode && bake != null && r.distM > 0.01f;
            float lenCam = metric ? fpx * bake.lenMm * 0.001f / r.distM : r.len;
            float widCam = metric ? fpx * bake.widMm * 0.001f / r.distM : r.wid;

            float nx = Mathf.Clamp01(r.cx / m_ImgW), ny = Mathf.Clamp01(r.cy / m_ImgH);
            Vector2 center = MapNormToLocal(nx, ny, q, size);
            float tnx = Mathf.Clamp01((r.cx + r.ex * r.len * 0.5f) / m_ImgW);
            float tny = Mathf.Clamp01((r.cy + r.ey * r.len * 0.5f) / m_ImgH);
            Vector2 axis = MapNormToLocal(tnx, tny, q, size) - center;
            float deg = (axis.sqrMagnitude > 1e-4f)
                ? Mathf.Atan2(-axis.x, axis.y) * Mathf.Rad2Deg + designRotDeg
                : designRotDeg;

            float w = (widCam / m_ImgW) * size.x * designScale;
            float h = (lenCam / m_ImgH) * size.y * designScale;
            if (q == 1 || q == 3) { var t = w; w = h; h = t; }

            // tilt (pitch about the width axis) from length foreshortening vs profile
            float tilt = 0f;
            if (tiltEnable && metric && lenCam > 1f)
                tilt = Mathf.Clamp(Mathf.Acos(Mathf.Clamp01(r.len / lenCam)) * Mathf.Rad2Deg, 0f, tiltMax);

            var e = GetEntry(key);
            float curve = bake != null ? bake.curve : defaultCurve;
            var tex = bake != null ? bake.tex : FallbackTex(r.finger);
            if (!Mathf.Approximately(e.curve, curve)) { e.mf.sharedMesh = BuildNailMesh(curve, bulgeSign); e.curve = curve; }
            if (!ReferenceEquals(e.tex, tex)) { e.mat.mainTexture = tex; e.tex = tex; }
            // shift along the nail's own axis (fixes the "design sits a bit below the nail" bias)
            Vector2 alongVec = Vector2.zero;
            if (Mathf.Abs(alongTip) > 1e-4f && axis.sqrMagnitude > 1e-4f)
                alongVec = axis.normalized * (alongTip * h);   // h = design length in canvas px
            e.pos = center + alongVec + OffsetFor(r.distM); e.size = new Vector2(w, h);
            e.rot = deg; e.tilt = tilt; e.lastSeen = Time.time;
            // velocity -> canvas space by mapping a point a short step ahead and differencing, so it
            // inherits whatever rotQuadrant/mirror/scale the position mapping uses (no duplicate math).
            const float kVdt = 0.1f;
            e.vel = (Mathf.Abs(r.vx) > 0.01f || Mathf.Abs(r.vy) > 0.01f)
                ? (MapNormToLocal((r.cx + r.vx * kVdt) / m_ImgW, (r.cy + r.vy * kVdt) / m_ImgH, q, size) - center) / kVdt
                : Vector2.zero;
        }
    }

    // Same mapping as NailOverlayRenderer.MapNormToLocal (kept in sync — shared calib).
    private Vector2 MapNormToLocal(float nx, float ny, int q, Vector2 size)
    {
        float rx = nx, ry = ny;
        if (q == 1) { rx = ny; ry = 1f - nx; }
        else if (q == 2) { rx = 1f - nx; ry = 1f - ny; }
        else if (q == 3) { rx = 1f - ny; ry = nx; }
        if (mirrorX) rx = 1f - rx;
        if (mirrorY) ry = 1f - ry;
        return new Vector2((rx - 0.5f) * size.x * calibScale, -(ry - 0.5f) * size.y * calibScale);
    }

    private Entry GetEntry(string key)
    {
        if (m_Entries.TryGetValue(key, out var e)) return e;
        if (m_Shader == null)
        {
            m_Shader = Resources.Load<Shader>("NailBakedGloss");
            if (m_Shader == null) m_Shader = Shader.Find("NailAR/BakedGloss");
        }
        var go = new GameObject("nailmesh_" + key, typeof(MeshFilter), typeof(MeshRenderer));
        go.transform.SetParent(cameraViewRect, false);
        e = new Entry {
            go = go, mf = go.GetComponent<MeshFilter>(), mr = go.GetComponent<MeshRenderer>(),
            mat = new Material(m_Shader),
        };
        e.mr.sharedMaterial = e.mat;
        e.mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        e.mr.receiveShadows = false;
        e.mat.renderQueue = 3100;      // above the (transparent) UI feed
        go.SetActive(false);
        m_Entries.Add(key, e);
        return e;
    }

    // Semi-cylinder strip in UNIT space: x = chord across width [-0.5..0.5],
    // y = base(-0.5) .. tip(+0.5), z = bulge*sign (arc sag, unit-width normalized).
    // UV: u uniform in ARC LENGTH (matches the bake's arc-length resample), v: base=0
    // tip=1 — design PNGs put the TIP at image top (french_tip in gen_nail_design.py),
    // and Unity texture v=1 = image top row.
    private static Mesh BuildNailMesh(float curve, float sign)
    {
        const int ARC = 10, LEN = 6;
        float a = 0.5f, s = Mathf.Max(1e-4f, curve);
        float R = (a * a + s * s) / (2f * s);
        float th0 = Mathf.Asin(Mathf.Clamp01(a / R));
        var verts = new Vector3[(ARC + 1) * (LEN + 1)];
        var uvs = new Vector2[verts.Length];
        for (int iy = 0; iy <= LEN; iy++)
        {
            float vN = (float)iy / LEN;                    // 0=base .. 1=tip
            float y = vN - 0.5f;
            for (int ix = 0; ix <= ARC; ix++)
            {
                float uN = (float)ix / ARC;                // uniform arc
                float th = (2f * uN - 1f) * th0;
                float x = R * Mathf.Sin(th);
                float bulge = R * Mathf.Cos(th) - (R - s); // 0 at edges .. s at center
                verts[iy * (ARC + 1) + ix] = new Vector3(x, y, bulge * sign);
                uvs[iy * (ARC + 1) + ix] = new Vector2(uN, vN);
            }
        }
        var tris = new int[ARC * LEN * 6];
        int t = 0;
        for (int iy = 0; iy < LEN; iy++)
            for (int ix = 0; ix < ARC; ix++)
            {
                int i0 = iy * (ARC + 1) + ix, i1 = i0 + 1, i2 = i0 + (ARC + 1), i3 = i2 + 1;
                tris[t++] = i0; tris[t++] = i2; tris[t++] = i1;
                tris[t++] = i1; tris[t++] = i2; tris[t++] = i3;
            }
        var m = new Mesh { vertices = verts, uv = uvs, triangles = tris };
        m.RecalculateNormals();
        m.RecalculateBounds();
        return m;
    }

    void Update()
    {
        float k = 1f - Mathf.Exp(-smoothing * Time.deltaTime);
        foreach (var e in m_Entries.Values)
        {
            bool expired = !show || (Time.time - e.lastSeen) > holdSec;
            if (expired) { if (e.go.activeSelf) { e.go.SetActive(false); e.placed = false; } continue; }
            if (!e.go.activeSelf) e.go.SetActive(true);
            e.mat.SetFloat("_GlossStrength", glossStrength);
            e.mat.SetFloat("_GlossPower", glossPower);
            var tr = e.go.transform;
            // latency compensation: extrapolate along the nail's velocity for the time already
            // elapsed since this result plus the pipeline lag. Capped so stale/occluded data can't
            // fling the design away; when the hand is still (v≈0) this contributes nothing.
            Vector2 p = e.pos;
            if (predictSec > 0f && e.vel.sqrMagnitude > 1e-6f)
                p += e.vel * Mathf.Min((Time.time - e.lastSeen) + predictSec, maxPredictSec);
            var targetPos = new Vector3(p.x, p.y, 0f);
            var targetRot = Quaternion.Euler(0f, 0f, e.rot) * Quaternion.Euler(e.tilt * tiltSign, 0f, 0f);
            var targetScale = new Vector3(e.size.x, e.size.y, e.size.x);   // bulge scales with width
            if (!e.placed) { tr.localPosition = targetPos; tr.localScale = targetScale; tr.localRotation = targetRot; e.placed = true; }
            tr.localPosition = Vector3.Lerp(tr.localPosition, targetPos, k);
            tr.localScale = Vector3.Lerp(tr.localScale, targetScale, k);
            tr.localRotation = Quaternion.Slerp(tr.localRotation, targetRot, k);
        }
    }
}
