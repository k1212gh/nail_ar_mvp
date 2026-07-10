// NailOverlayRenderer.cs — draw the nail design on each detected nail as a true AR
// overlay. Camera px -> normalized -> rotate(camera->eye) -> display-rect local, with
// live-tunable calibration. Temporal smoothing (lerp) + hold-on-gap so the design does
// not flicker/jump when detection is momentarily lost.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

public class NailOverlayRenderer : MonoBehaviour
{
    [Header("Refs")]
    public RectTransform cameraViewRect;   // display rect (overlay parent / coordinate space)
    public Sprite[] designs;               // per-finger designs (french/floral/dots ...)
    public bool show = true;               // mode presets hide designs (e.g. ARGrid shows grid only)
    [Range(0.3f, 3f)] public float designScale = 1.3f;

    [Header("AR calibration (camera px -> what the eye sees)")]
    public int rotQuadrant = 1;                  // 0/1/2/3 = 0/90/180/270 deg (camera->eye)
    public Vector2 calibOffset = Vector2.zero;   // display-px shift (parallax / mounting)
    [Range(0.2f, 3f)] public float calibScale = 1f;
    public bool mirrorX = false, mirrorY = false;
    public float designRotDeg = 0f;              // extra spin on each design (deg); fixes tip-direction
                                                 // mismatch when the canvas is rotated (mirror mode)

    [Header("Stability")]
    public float smoothing = 12f;   // lerp speed toward target (higher = snappier)
    public float holdSec = 0.4f;    // keep last designs this long when detection drops to 0

    // One entry per nail IDENTITY (hand+finger), not per array index — so each finger's design
    // keeps its own smoothed transform + assigned sprite even when a finger bends/occludes and
    // the detection order shifts. Index-keyed pooling slid designs between fingers.
    class Entry { public Image img; public Vector2 pos, size; public float rot; public Sprite sprite; public float lastSeen = -999f; public bool placed; }
    private readonly Dictionary<string, Entry> m_Entries = new Dictionary<string, Entry>();
    private int m_ImgW = 1, m_ImgH = 1;

    private static readonly string[] k_FingerOrder = { "thumb", "index", "middle", "ring", "pinky" };
    private static int FingerIndex(string finger)   // stable design slot per finger
    {
        if (finger != null)
            for (int i = 0; i < k_FingerOrder.Length; i++) if (finger == k_FingerOrder[i]) return i;
        return 0;
    }

    /// <summary>Build sprites from Assets/Resources/designs/*.png at runtime (no scene wiring).</summary>
    public void LoadDesignsFromResources()
    {
        var texs = Resources.LoadAll<Texture2D>("designs");
        if (texs == null || texs.Length == 0) { Debug.LogWarning("[NailAR] no designs in Resources/designs"); return; }
        var list = new List<Sprite>();
        foreach (var t in texs)
            list.Add(Sprite.Create(t, new Rect(0, 0, t.width, t.height), new Vector2(0.5f, 0.5f), 100f));
        designs = list.ToArray();
        Debug.Log("[NailAR] loaded " + designs.Length + " designs from Resources");
    }

    public void SetResults(List<NailRoi> rois, int imgW, int imgH)
    {
        m_ImgW = Mathf.Max(1, imgW); m_ImgH = Mathf.Max(1, imgH);
        if (rois != null && rois.Count > 0)
            ComputeTargets(rois);
        // if empty: keep previous entries; Update() hides each after its own holdSec
    }

    // Map a normalized camera point [0..1] to display-rect local coords, applying the same
    // rotQuadrant + mirror the feed uses. Used for BOTH the nail center and its tip so the
    // design orientation is derived from the mapped base->tip vector — this makes it follow
    // each nail's real direction through ANY transform (rot/mirror/parent flip), instead of
    // ad-hoc angle math. (ModiFace CVPRW 2019 orients each nail by a base->tip direction field.)
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

    private void ComputeTargets(List<NailRoi> rois)
    {
        var size = cameraViewRect.rect.size;
        int q = ((rotQuadrant % 4) + 4) % 4;
        for (int idx = 0; idx < rois.Count; idx++)
        {
            var r = rois[idx];
            float nx = Mathf.Clamp01(r.cx / m_ImgW), ny = Mathf.Clamp01(r.cy / m_ImgH);
            Vector2 center = MapNormToLocal(nx, ny, q, size);
            // nail tip = center + axis*half-length (camera px) -> map through the SAME pipeline
            float tnx = Mathf.Clamp01((r.cx + r.ex * r.len * 0.5f) / m_ImgW);
            float tny = Mathf.Clamp01((r.cy + r.ey * r.len * 0.5f) / m_ImgH);
            Vector2 axis = MapNormToLocal(tnx, tny, q, size) - center;   // base->tip AS DISPLAYED
            // rotate a tip-up (+Y) sprite to align its tip with `axis`; designRotDeg = sprite-default fudge
            float deg = (axis.sqrMagnitude > 1e-4f)
                ? Mathf.Atan2(-axis.x, axis.y) * Mathf.Rad2Deg + designRotDeg
                : designRotDeg;
            Vector2 pos = center + calibOffset;
            // design size (axes swap on 90/270 quadrants)
            float w = (r.wid / m_ImgW) * size.x * designScale;
            float h = (r.len / m_ImgH) * size.y * designScale;
            if (q == 1 || q == 3) { var t = w; w = h; h = t; }

            // design sprite is chosen by FINGER identity (stable), not detection order
            var spr = designs != null && designs.Length > 0
                ? designs[FingerIndex(r.finger) % designs.Length] : null;
            var e = GetEntry(KeyFor(r, idx));
            e.pos = pos; e.size = new Vector2(w, h); e.rot = deg; e.sprite = spr;
            e.lastSeen = Time.time;
        }
    }

    // Stable identity key (hand+finger); positional fallback only if the server omits identity.
    private static string KeyFor(NailRoi r, int i)
    {
        string k = r.Key;
        return (k == null || k == ":") ? ("#" + i) : k;
    }

    private Entry GetEntry(string key)
    {
        if (!m_Entries.TryGetValue(key, out var e))
        {
            var go = new GameObject("nail_" + key, typeof(RectTransform), typeof(Image));
            go.transform.SetParent(cameraViewRect, false);
            var img = go.GetComponent<Image>();
            img.raycastTarget = false;
            e = new Entry { img = img };
            m_Entries.Add(key, e);
        }
        return e;
    }

    void Update()
    {
        float k = 1f - Mathf.Exp(-smoothing * Time.deltaTime);   // frame-rate independent lerp
        foreach (var e in m_Entries.Values)
        {
            bool expired = !show || (Time.time - e.lastSeen) > holdSec;
            if (expired) { if (e.img.enabled) { e.img.enabled = false; e.placed = false; } continue; }
            e.img.enabled = true;
            e.img.sprite = e.sprite;
            var rt = e.img.rectTransform;
            // snap into place the first time this finger appears, then smooth
            if (!e.placed) { rt.anchoredPosition = e.pos; rt.sizeDelta = e.size; e.placed = true; }
            rt.anchoredPosition = Vector2.Lerp(rt.anchoredPosition, e.pos, k);
            rt.sizeDelta = Vector2.Lerp(rt.sizeDelta, e.size, k);
            rt.localRotation = Quaternion.Slerp(rt.localRotation, Quaternion.Euler(0, 0, e.rot), k);
        }
    }
}
