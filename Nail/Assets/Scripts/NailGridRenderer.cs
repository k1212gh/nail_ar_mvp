// NailGridRenderer.cs — graph-paper grid centered on each detected nail (사장님 PoC).
// Same camera-px -> display-rect mapping as NailOverlayRenderer, but draws a metric grid:
//   cell_px(camera) = f_px * cellMm/1000 / distM   (pinhole; f_px = focalRatio * imgW)
// Centers are smoothed with a One-Euro filter (Casiez CHI 2012 — beats Kalman on the
// jitter/lag tradeoff for interactive tracking); distM gets a much heavier low-pass +
// 5% hysteresis so the cells never "breathe" (grid-stability research, 2026-07).
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

public class NailGridRenderer : MonoBehaviour
{
    [Header("Refs")]
    public RectTransform cameraViewRect;    // display rect = coordinate space (same as overlay)

    [Header("Grid")]
    public bool show = false;               // toggled by mode preset / calib gridOn
    public int gridCells = 7;               // NxN cells (odd -> a true center cross)
    public float cellMm = 1f;               // metric cell size ("≈1mm" — distM has ~5% error)
    [Range(0.1f, 1f)] public float gridAlpha = 0.65f;  // mid-contrast per Bayle 2021
    public float gridRotDeg = 0f;           // grid rotation (deg). when followNail=false this IS the angle.
    public bool followNail = false;         // false = axis-aligned graph paper (stable, no spin) — default;
                                            // true = crosshair tracks each nail's direction (spins with it)
    public Vector2 gridOffset = Vector2.zero;   // display-px shift to sit the grid on the nail (calib)
    public float gridScale = 1f;            // fudge factor on top of the metric size
    public float focalRatio = 0.86f;        // f_px = focalRatio * imgW (matches server config.py)

    [Header("Mapping (camera px -> eye), set by mode preset")]
    public int rotQuadrant = 0;
    public bool mirrorX = false, mirrorY = false;
    // Camera FOV is WIDER than the display FOV, so a direct camera-norm -> display-norm map
    // compresses the finger spread toward the center (grids cluster). posScale spreads the
    // mapped positions outward from the canvas center to match the real (wide) finger angles
    // as seen through the see-through display. 1 = no spread; >1 = spread out. Tuned by eye.
    public float posScale = 1f;

    [Header("Stability")]
    public float minCutoff = 1.0f;          // One-Euro: lower = less slow-motion jitter
    public float beta = 0.007f;             // One-Euro: higher = less fast-motion lag
    public float holdSec = 0.3f;            // keep grid on brief detection loss, then reset

    // --- One-Euro filter (Casiez, Roussel, Vogel — CHI 2012) ---
    class OneEuro
    {
        float m_XPrev, m_DxPrev; bool m_Init;
        static float Alpha(float cutoff, float dt)
        {
            float tau = 1f / (2f * Mathf.PI * cutoff);
            return 1f / (1f + tau / Mathf.Max(dt, 1e-4f));
        }
        public float Filter(float x, float dt, float minCutoff, float beta, float dCutoff = 1f)
        {
            if (!m_Init) { m_Init = true; m_XPrev = x; m_DxPrev = 0f; return x; }
            float dx = (x - m_XPrev) / Mathf.Max(dt, 1e-4f);
            m_DxPrev = Mathf.Lerp(m_DxPrev, dx, Alpha(dCutoff, dt));
            float cutoff = minCutoff + beta * Mathf.Abs(m_DxPrev);
            m_XPrev = Mathf.Lerp(m_XPrev, x, Alpha(cutoff, dt));
            return m_XPrev;
        }
        public void Reset() { m_Init = false; }
    }

    class Slot
    {
        public OneEuro fx = new OneEuro(), fy = new OneEuro();
        public RawImage img;
        public float rot;
        public float lastSeen = -999f;      // per-finger hold/reset (was a single global timer)
    }

    // Keyed by nail identity (hand+finger) so each finger keeps its OWN One-Euro filter across
    // frames. Index-keyed slots crossed filters when a finger bent/occluded and indices shifted.
    private readonly Dictionary<string, Slot> m_Slots = new Dictionary<string, Slot>();
    private int m_ImgW = 1, m_ImgH = 1;
    private float m_LastFeedT = -1f;
    private float m_DistM = -1f;            // heavily-smoothed shared distance
    private Texture2D m_GridTex;

    /// <summary>Feed detections (same cadence/coords as NailOverlayRenderer.SetResults).</summary>
    public void SetResults(List<NailRoi> rois, int imgW, int imgH)
    {
        if (!show) return;
        m_ImgW = Mathf.Max(1, imgW); m_ImgH = Mathf.Max(1, imgH);
        if (rois == null || rois.Count == 0) return;   // hold handled per-slot in Update via lastSeen

        // shared metric distance: heavy low-pass + 5% hysteresis so cells never breathe
        float distSum = 0f; int distN = 0;
        foreach (var r in rois) if (r.distM > 0.01f) { distSum += r.distM; distN++; }
        if (distN > 0)
        {
            float d = distSum / distN;
            if (m_DistM <= 0f) m_DistM = d;
            else if (Mathf.Abs(d - m_DistM) / m_DistM > 0.05f)
                m_DistM = Mathf.Lerp(m_DistM, d, 0.15f);   // update only past 5%, gently
        }

        float dt = m_LastFeedT > 0f ? Time.time - m_LastFeedT : 0.15f;
        m_LastFeedT = Time.time;

        var size = cameraViewRect.rect.size;
        int q = ((rotQuadrant % 4) + 4) % 4;
        for (int i = 0; i < rois.Count; i++)
        {
            var r = rois[i];
            var s = GetSlot(KeyFor(r, i));
            // center + tip mapped through the SAME pipeline -> grid follows each nail's axis
            // through any rot/mirror/parent-flip (same robust scheme as NailOverlayRenderer).
            float nx = Mathf.Clamp01(r.cx / m_ImgW), ny = Mathf.Clamp01(r.cy / m_ImgH);
            Vector2 center = MapNormToLocal(nx, ny, q, size);
            float tnx = Mathf.Clamp01((r.cx + r.ex * r.len * 0.5f) / m_ImgW);
            float tny = Mathf.Clamp01((r.cy + r.ey * r.len * 0.5f) / m_ImgH);
            Vector2 axis = MapNormToLocal(tnx, tny, q, size) - center;
            // One-Euro on the display-space center + calib offset to sit it on the nail
            float lx = s.fx.Filter(center.x, dt, minCutoff, beta) + gridOffset.x;
            float ly = s.fy.Filter(center.y, dt, minCutoff, beta) + gridOffset.y;

            // metric grid size: camera px -> display px via the x-axis factor for BOTH axes
            // (keeps cells square on screen; canvas aspect 2.67 vs camera 1.6 would distort)
            float fPx = focalRatio * m_ImgW;
            float cellPxCam = m_DistM > 0.01f ? fPx * (cellMm * 0.001f) / m_DistM
                                              : Mathf.Max(6f, r.len / gridCells); // fallback: ~nail-size grid
            float gridPx = cellPxCam * gridCells * gridScale;
            float w = gridPx / m_ImgW * size.x;

            // graph paper is axis-aligned by default (stable). only spin with the nail if followNail.
            s.rot = (followNail && axis.sqrMagnitude > 1e-4f)
                ? Mathf.Atan2(-axis.x, axis.y) * Mathf.Rad2Deg + gridRotDeg
                : gridRotDeg;

            var rt = s.img.rectTransform;
            rt.anchoredPosition = new Vector2(lx, ly);
            rt.sizeDelta = new Vector2(w, w);
            s.img.enabled = true;
            s.lastSeen = Time.time;
        }
        // slots NOT seen this frame are hidden/reset by Update() once past holdSec (per finger)
    }

    // Stable identity key for a nail's slot: hand+finger. Falls back to a positional key only
    // when the server omits identity (old behaviour) so nothing breaks.
    private static string KeyFor(NailRoi r, int i)
    {
        string k = r.Key;
        return (k == null || k == ":") ? ("#" + i) : k;
    }

    // Map normalized camera point -> display-rect local, applying rotQuadrant + mirror (matches
    // NailOverlayRenderer). No calibScale/offset here — grid uses full-rect metric mapping.
    private Vector2 MapNormToLocal(float nx, float ny, int q, Vector2 size)
    {
        float rx = nx, ry = ny;
        if (q == 1) { rx = ny; ry = 1f - nx; }
        else if (q == 2) { rx = 1f - nx; ry = 1f - ny; }
        else if (q == 3) { rx = 1f - ny; ry = nx; }
        if (mirrorX) rx = 1f - rx;
        if (mirrorY) ry = 1f - ry;
        // posScale spreads positions out from the canvas center (camera FOV > display FOV fix)
        return new Vector2((rx - 0.5f) * size.x * posScale, -(ry - 0.5f) * size.y * posScale);
    }

    private Slot GetSlot(string key)
    {
        if (!m_Slots.TryGetValue(key, out var s))
        {
            var go = new GameObject("grid_" + key, typeof(RectTransform), typeof(RawImage));
            go.transform.SetParent(cameraViewRect, false);
            var img = go.GetComponent<RawImage>();
            img.texture = GridTexture();
            img.raycastTarget = false;
            img.color = new Color(0.3f, 1f, 1f, gridAlpha);
            s = new Slot { img = img };
            m_Slots.Add(key, s);
        }
        return s;
    }

    void Update()
    {
        foreach (var s in m_Slots.Values)
        {
            // per-finger hold: hide + reset this finger's filter once it hasn't been seen recently
            bool off = !show || (Time.time - s.lastSeen) > holdSec;
            if (off) { if (s.img.enabled) { s.img.enabled = false; s.fx.Reset(); s.fy.Reset(); } continue; }
            if (!s.img.enabled) continue;
            s.img.color = new Color(0.3f, 1f, 1f, gridAlpha);
            // angle: slerp (wraparound-safe), extra hysteresis happens naturally via slerp speed
            s.img.rectTransform.localRotation = Quaternion.Slerp(
                s.img.rectTransform.localRotation, Quaternion.Euler(0, 0, s.rot),
                1f - Mathf.Exp(-10f * Time.deltaTime));
        }
    }

    /// <summary>Runtime-generated graph-paper texture: thin cell lines + bold center cross.</summary>
    private Texture2D GridTexture()
    {
        if (m_GridTex != null) return m_GridTex;
        int cells = Mathf.Max(3, gridCells | 1);           // force odd for a true center
        int cellPx = 24, sz = cells * cellPx + 1;
        var tex = new Texture2D(sz, sz, TextureFormat.RGBA32, false);
        var px = new Color32[sz * sz];
        var clear = new Color32(255, 255, 255, 0);
        var thin  = new Color32(255, 255, 255, 140);
        var bold  = new Color32(255, 255, 255, 255);
        for (int i = 0; i < px.Length; i++) px[i] = clear;
        int c = sz / 2;
        for (int y = 0; y < sz; y++)
            for (int x = 0; x < sz; x++)
            {
                bool line = (x % cellPx == 0) || (y % cellPx == 0);
                bool cross = Mathf.Abs(x - c) <= 1 || Mathf.Abs(y - c) <= 1;
                if (cross) px[y * sz + x] = bold;
                else if (line) px[y * sz + x] = thin;
            }
        tex.SetPixels32(px); tex.Apply(false);
        tex.wrapMode = TextureWrapMode.Clamp;
        m_GridTex = tex;
        return tex;
    }
}
