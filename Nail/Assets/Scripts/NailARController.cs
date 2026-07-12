// NailARController.cs — glasses-camera nail-AR via RayNeo ShareCamera + PC edge.
// Uses the REAL ARDK API (verified against SDK/.../ShareCamera + Samples~/HelloRayNeo).
// Flow: request CAMERA permission -> ShareCamera.OpenCamera(RGB, RawImage) -> each frame
// UpdateT2d() refreshes the RawImage; every N s grab the texture -> POST /infer -> ROIs
// -> NailOverlayRenderer draws the design on each nail.
using System;
using System.Collections;
using System.IO;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Android;
using RayNeo.API;      // ShareCamera, XRCameraType, XRCameraHandler
using static com.rayneo.xr.extensions.XRCamera;   // XRResolution (nested class)

public class NailARController : MonoBehaviour
{
    [Header("Refs")]
    public RawImage cameraView;                 // ShareCamera target (shows glasses camera)
    public NailOverlayRenderer overlay;         // draws design on nails (flat sprites)
    public NailGridRenderer grid;               // graph-paper grid per nail (사장님 PoC); created at runtime if null
    public NailMeshRenderer meshR;              // curved per-nail mesh + baked textures; created at runtime if null
    [Header("Edge")]
    public string edgeUrl = "https://127.0.0.1:8443/infer";  // edge_serve.py (adb reverse tcp:8443)
    public float inferIntervalSec = 0.15f;
    [Header("AR mode")]
    // false = optical see-through: DON'T paint the camera onto the display, so the real
    // hand is visible through the waveguide and we overlay ONLY the design (true AR).
    // The camera keeps streaming into m_Handler.texture for detection either way.
    public bool showCameraFeed = false;

    private XRCameraType m_CamType = XRCameraType.RGB;   // 12MP main (VGA = spatial)
    [Header("Camera resolution")]                        // 640x400 = the ONLY size that renders SINGLE on the
    public int camW = 640, camH = 400;                   // waveguide (1280 doubles per eye); measured 2026-07-04.
                                                         // live-tunable via calib {"camW":..,"camH":..} but reopen
                                                         // is unreliable on-device, so this default is what ships.
    private XRCameraHandler m_Handler;

    private XRCameraHandler OpenCam()
    {
        // Try requested res; if the SDK rejects it (returns null), fall back to the safe 640x400.
        var h = ShareCamera.OpenCamera(m_CamType, new XRResolution(Mathf.Max(320, camW), Mathf.Max(240, camH)), cameraView);
        if (h == null && (camW != 640 || camH != 400))
        {
            Debug.LogError($"[NailAR] {camW}x{camH} unsupported -> fallback 640x400");
            camW = 640; camH = 400;
            h = ShareCamera.OpenCamera(m_CamType, new XRResolution(640, 400), cameraView);
        }
        return h;
    }

    // Re-open the camera at a new resolution (calib change). Returns true on success.
    private bool ReopenCam(int w, int h)
    {
        if (w == camW && h == camH && m_Handler != null) return false;
        camW = w; camH = h;
        if (m_Handler != null) { ShareCamera.CloseCamera(m_Handler); m_Handler = null; }
        m_Handler = OpenCam();
        Debug.LogError($"[NailAR] reopened cam at {camW}x{camH} -> {(m_Handler != null ? "ok" : "FAILED")}");
        return m_Handler != null;
    }
    private readonly EdgeClient m_Edge = new EdgeClient();
    private bool m_Running;
    private Texture2D m_Grab;

    // --- Dynamic depth: render the design AT the hand's distance so focus/stereo matches
    // it regardless of how near/far the hand is. Distance comes from the server's absolute
    // estimate (MediaPipe metric World Landmarks + pinhole); distScale absorbs focal error. ---
    private bool m_DynDepth = true;
    private float m_DistScale = 1.0f;    // multiplies server distM (tune once for single vision)
    private float m_DepthK = 4.0f;       // fallback: depth(m) = depthK / avgNailLenPx
    private float m_DepthMin = 0.07f, m_DepthMax = 1.5f;
    private float m_TargetDepth = 0.3f, m_CurDepth = 0.3f;
    private int m_LogTick;

    // --- Modular modes: cycle in-app (tap) or select via calib {"mode":N}. Each mode is a
    // full config preset so 형 can A/B test approaches quickly. ---
    // Cycle with a tap, or select via calib {"mode":N}. Calib exists only for the separate
    // NailCalib app (CALIB_APP forces it). ARMesh/Enroll appended AFTER Calib so pushed
    // calib files keep their old numeric meaning (mode:2 = Calib).
    //   ARMesh = curved per-nail mesh + baked per-finger textures ("측정->베이킹->포즈만")
    //   Enroll = magic-mirror + server-side mm measurement -> nail_profile.json
    //   MirrorMesh = magic-mirror + curved mesh design ON the feed (정합 정확·VAC 없음). append 유지.
    public enum NailMode { ARGrid, ARDesign, Calib, ARMesh, Enroll, MirrorMesh }
    private const int MODE_COUNT = 6;                       // enum size (modulo safety)
    private static readonly int[] k_TapCycle = { (int)NailMode.ARGrid, (int)NailMode.ARDesign, (int)NailMode.ARMesh };
    [Header("Modes")] public int startMode = 0;   // 0 = magic-mirror upright (recommended)
    private int m_Mode = -1, m_LastCalibMode = -999;
    private float m_TapDebounce, m_HudUntil;
    private UnityEngine.UI.Text m_Hud;

    void Start()
    {
        m_Edge.url = edgeUrl;
        // (double-tap-to-quit was a Samples-only helper; omitted. Add later if needed.)
        StartCoroutine(EnsurePermissionThenOpen());
        StartCoroutine(PollCalib());   // live-tune alignment via adb-pushed nail_calib.json
    }

    // --- Live calibration (no rebuild): push nail_calib.json to the app's EXTERNAL files
    // dir (readable by the app w/o permission; writable by adb push):
    //   adb push nail_calib.json /sdcard/Android/data/com.DefaultCompany.Nail/files/
    [Serializable]
    class CalibData
    {
        public float offsetX, offsetY, scale = 1f, designScale;
        public int rot = -999;                 // rotQuadrant (0..3); -999 = leave as-is
        public bool mirrorX, mirrorY, showFeed;
        public float depthM = -1f;             // MANUAL canvas distance (m); used only if dynamicDepth=false
        public float smoothing = -1f;          // overlay lerp speed; <=0 = leave
        public float holdSec = -1f;            // keep design on detection gap; <0 = leave
        public int dynDepth = -1;              // 1=depth follows hand distance, 0=manual depthM, -1=leave
        public float depthK = -1f;             // fallback: depth(m) = depthK / avgNailLenPx; <=0 = leave
        public float distScale = -1f;          // multiplies server absolute distM; <=0 = leave
        public float canvasRot = -999f;        // rotate whole canvas (feed+overlay) in deg; MIRROR mode:
                                               // camera is mounted 90 deg, so 90/-90 makes the feed upright
        public int mode = -1;                  // select a full mode preset (see NailMode); -1 = leave
        public float designRot = -999f;        // extra design spin (deg); fixes tip-direction; -999 = leave
        public int flipX = -1;                 // 1=mirror canvas horizontally, 0=no, -1=leave
        public int flipY = -1;                 // 1=mirror canvas vertically, 0=no, -1=leave
        // --- grid (사장님 PoC) live knobs ---
        public int gridOn = -1;                // 1=show grid in ANY mode, 0=hide, -1=mode default
        public float cellMm = -1f;             // metric cell size in mm; <=0 = leave
        public float gridAlpha = -1f;          // 0..1 line opacity; <0 = leave
        public float gridRot = -999f;          // grid rotation (deg); -999 = leave
        public float gridScale = -1f;          // fudge on metric size; <=0 = leave
        public int gridFollow = -1;            // 1=grid spins with nail, 0=axis-aligned(stable), -1=leave
        public float gridOffX = -99999f, gridOffY = -99999f;  // grid position shift (display px); sentinel=leave
        public float gridPosScale = -1f;       // spread grids out from center (camera FOV>display FOV); <=0=leave
        public float gridMinCutoff = -1f;      // One-Euro minCutoff (lower=calmer jitter, more lag); <=0=leave
        public float gridBeta = -1f;           // One-Euro beta (higher=less lag on fast moves); <0=leave
        // --- reverse-SPAAM calibration crosshair (solved mapping reuses existing offsetX/offsetY/scale) ---
        public int crossOn = -1;               // 1=show calib crosshair (see-through, hide all else), 0=off, -1=leave
        public float crossX = -99999f, crossY = -99999f;  // crosshair canvas-local pos (px); sentinel=leave
        public int camW = -1, camH = -1;       // request camera resolution; -1 = leave (reopens camera)
        public float stretchX = -1f, stretchY = -1f;  // aspect correction (canvas non-uniform scale); <=0 = leave
        // --- curved-mesh (ARMesh) live knobs ---
        public float meshGloss = -1f;          // gloss strength; <0 = leave
        public float meshGlossPow = -1f;       // gloss specular power; <=0 = leave
        public int meshTilt = -1;              // 1=pitch from foreshortening, 0=off, -1=leave
        public float meshTiltSign = 0f;        // +1/-1 flip tilt direction; 0 = leave
        public float meshCurve = -1f;          // fallback curve (sag/width) when no bake; <=0 = leave
        public float meshScale = -1f;          // mesh design scale; <=0 = leave
        public float meshBulge = 0f;           // +1/-1 bulge direction; 0 = leave
        public int bakeReload = -1;            // CHANGE the value to re-read nail_bake dir; -1 = leave
        // --- distance-adaptive parallax model: offset(d) = A + B/d (display px, px·m) ---
        public int meshParallaxOn = -1;        // 1=use A+B/d per frame, 0=static offset, -1=leave
        public float pAx = -99999f, pAy = -99999f;  // parallax constant A; sentinel=leave
        public float pBx = -99999f, pBy = -99999f;  // parallax coeff B; sentinel=leave
    }
    private int m_LastBakeReload = -1;

    private IEnumerator PollCalib()
    {
        // try external app dir first (adb-push target), then Unity's persistentDataPath
        string[] paths = {
            "/sdcard/Android/data/" + Application.identifier + "/files/nail_calib.json",
            Path.Combine(Application.persistentDataPath, "nail_calib.json"),
        };
        var wait = new WaitForSeconds(0.7f);
        while (true) { foreach (var p in paths) if (ApplyCalibFile(p)) break; yield return wait; }
    }

    private bool ApplyCalibFile(string path)
    {
        try
        {
            if (overlay == null || !File.Exists(path)) return false;
            var c = JsonUtility.FromJson<CalibData>(File.ReadAllText(path));
            if (c == null) return false;
            // mode selector (full preset) — apply only when the file's mode value changes,
            // so in-app tap-cycling isn't overwritten every poll.
            if (c.mode != -1 && c.mode != m_LastCalibMode) { m_LastCalibMode = c.mode; ApplyMode(c.mode); }
            // fine-tune overrides applied on top of the current mode
            overlay.calibOffset = new Vector2(c.offsetX, c.offsetY);
            if (c.scale > 0f) overlay.calibScale = c.scale;
            if (c.designScale > 0f) overlay.designScale = c.designScale;
            if (c.smoothing > 0f) overlay.smoothing = c.smoothing;
            if (c.holdSec >= 0f) overlay.holdSec = c.holdSec;
            if (c.depthK > 0f) m_DepthK = c.depthK;
            if (c.distScale > 0f) m_DistScale = c.distScale;
            // advanced per-field overrides (optional; the mode owns these by default)
            if (c.rot != -999) overlay.rotQuadrant = c.rot;
            if (c.designRot != -999f) overlay.designRotDeg = c.designRot;
            if (c.canvasRot != -999f) SetCanvasRot(c.canvasRot);
            if (c.flipX != -1 || c.flipY != -1)
                SetCanvasFlip(c.flipX != -1 ? c.flipX == 1 : m_FlipX, c.flipY != -1 ? c.flipY == 1 : m_FlipY);
            if (c.camW > 0 && c.camH > 0 && (c.camW != camW || c.camH != camH)) ReopenCam(c.camW, c.camH);
            if (c.stretchX > 0f || c.stretchY > 0f) SetStretch(c.stretchX, c.stretchY);
            if (grid != null)
            {
                if (c.gridOn != -1) grid.show = c.gridOn == 1;
                if (c.cellMm > 0f) grid.cellMm = c.cellMm;
                if (c.gridAlpha >= 0f) grid.gridAlpha = c.gridAlpha;
                if (c.gridRot != -999f) grid.gridRotDeg = c.gridRot;
                if (c.gridScale > 0f) grid.gridScale = c.gridScale;
                if (c.gridFollow != -1) grid.followNail = c.gridFollow == 1;
                if (c.gridOffX > -99998f) grid.gridOffset.x = c.gridOffX;
                if (c.gridOffY > -99998f) grid.gridOffset.y = c.gridOffY;
                if (c.gridPosScale > 0f) grid.posScale = c.gridPosScale;
                if (c.gridMinCutoff > 0f) grid.minCutoff = c.gridMinCutoff;
                if (c.gridBeta >= 0f) grid.beta = c.gridBeta;
            }
            // reverse-SPAAM calibration crosshair
            if (meshR != null)
            {
                // shared alignment (same canvas-local mapping as the sprite overlay)
                meshR.calibOffset = new Vector2(c.offsetX, c.offsetY);
                if (c.scale > 0f) meshR.calibScale = c.scale;
                if (c.smoothing > 0f) meshR.smoothing = c.smoothing;
                if (c.holdSec >= 0f) meshR.holdSec = c.holdSec;
                if (c.rot != -999) meshR.rotQuadrant = c.rot;
                if (c.designRot != -999f) meshR.designRotDeg = c.designRot;
                // mesh-specific knobs
                if (c.meshGloss >= 0f) meshR.glossStrength = c.meshGloss;
                if (c.meshGlossPow > 0f) meshR.glossPower = c.meshGlossPow;
                if (c.meshTilt != -1) meshR.tiltEnable = c.meshTilt == 1;
                if (c.meshTiltSign != 0f) meshR.tiltSign = Mathf.Sign(c.meshTiltSign);
                if (c.meshCurve > 0f) meshR.defaultCurve = c.meshCurve;
                if (c.meshScale > 0f) meshR.designScale = c.meshScale;
                if (c.meshBulge != 0f) meshR.bulgeSign = Mathf.Sign(c.meshBulge);
                // distance-adaptive parallax model
                if (c.meshParallaxOn != -1) meshR.parallaxEnable = c.meshParallaxOn == 1;
                if (c.pAx > -99998f) meshR.parallaxA.x = c.pAx;
                if (c.pAy > -99998f) meshR.parallaxA.y = c.pAy;
                if (c.pBx > -99998f) meshR.parallaxB.x = c.pBx;
                if (c.pBy > -99998f) meshR.parallaxB.y = c.pBy;
                if (c.bakeReload != -1 && c.bakeReload != m_LastBakeReload)
                { m_LastBakeReload = c.bakeReload; meshR.ReloadBake(); }
            }
            if (c.crossX > -99998f) m_CrossX = c.crossX;
            if (c.crossY > -99998f) m_CrossY = c.crossY;
            if (c.crossOn != -1)
            {
                m_CrossOn = c.crossOn == 1;
                if (!m_CrossOn) { SetCross(false, 0f, 0f); ApplyMode(m_Mode); }  // restore current mode
            }
            if (m_CrossOn) SetCross(true, m_CrossX, m_CrossY);
            if (c.dynDepth != -1) m_DynDepth = c.dynDepth == 1;
            if (!m_DynDepth && c.depthM > 0f) SetCanvasDepth(c.depthM);
            return true;
        }
        catch (Exception e) { Debug.LogWarning("[NailAR] calib parse: " + e.Message); return false; }
    }

    // Move the world-space canvas (camera view + overlay) to `depthM` metres in front of
    // the head, rescaling to keep filling the FOV. Base rig = 0.0016 scale @ 2 m.
    private float m_Depth = 4f;
    private bool m_FlipX, m_FlipY;   // mirror the whole canvas (feed+overlay together, stays aligned)
    // Aspect correction: camera (1280x720=1.78) is stretched into the 1280x480 canvas (2.67) then
    // rotated 90deg -> objects look horizontally squished. stretchX/Y counter it (live-tunable).
    private float m_StretchX = 1f, m_StretchY = 1f;
    private void SetCanvasDepth(float depthM)
    {
        m_Depth = depthM;
        ApplyCanvasXform();
    }
    // Horizontal/vertical mirror of the mirror panel. A pure canvasRot can only reach 4 of the
    // 8 orientations; adding a flip lets us get "upright AND correct handedness".
    private void SetCanvasFlip(bool flipX, bool flipY)
    {
        m_FlipX = flipX; m_FlipY = flipY;
        ApplyCanvasXform();
    }
    private void ApplyCanvasXform()
    {
        if (cameraView == null || cameraView.canvas == null) return;
        var ct = cameraView.canvas.transform;
        var lp = ct.localPosition;
        ct.localPosition = new Vector3(lp.x, lp.y, m_Depth);
        float s = 0.0008f * m_Depth;   // 0.0016 @ 2 m -> keep angular size constant
        ct.localScale = new Vector3((m_FlipX ? -s : s) * m_StretchX, (m_FlipY ? -s : s) * m_StretchY, s);
    }
    private void SetStretch(float sx, float sy)
    {
        if (sx > 0f) m_StretchX = sx;
        if (sy > 0f) m_StretchY = sy;
        ApplyCanvasXform();
    }

    // Rotate the whole world-space canvas (feed + overlay together) about the view axis.
    // MIRROR mode: the RayNeo RGB camera is mounted rotated ~90deg, so canvasRot=90 or -90
    // presents the mirror feed upright while keeping designs aligned to it.
    private float m_CanvasRot;
    private void SetCanvasRot(float deg)
    {
        m_CanvasRot = deg;
        if (cameraView != null && cameraView.canvas != null)
            cameraView.canvas.transform.localRotation = Quaternion.Euler(0f, 0f, deg);
    }

    private void SetFeed(bool on)
    {
        // SetActive the feed RawImage GameObject. The OES camera texture ignores color.a AND even
        // Graphic.enabled=false kept rendering it, so deactivating the GameObject is the only reliable
        // way to get TRUE see-through. Overlay/grid are reparented to the CANVAS (not this RawImage)
        // in EnsurePermissionThenOpen, so they're unaffected. Detection still runs (UpdateT2d fires
        // from the SDK updater regardless; GrabJpeg reads m_Handler.texture, not this Graphic).
        if (cameraView != null) cameraView.gameObject.SetActive(on);
    }

    // Apply a full mode preset. Each mode is a self-contained config so 형 can A/B test.
    private void ApplyMode(int m)
    {
        m_Mode = ((m % MODE_COUNT) + MODE_COUNT) % MODE_COUNT;
        if (overlay != null) overlay.show = true;            // defaults; grid/calib modes override below
        if (grid != null) grid.show = false;
        if (meshR != null) meshR.show = false;
        m_CrossOn = false; if (m_Cross != null) m_Cross.gameObject.SetActive(false);   // crosshair off unless Calib
        bool enroll = (NailMode)m_Mode == NailMode.Enroll;
        if (m_Edge != null) { m_Edge.enroll = enroll; m_Edge.enrollResetPending = enroll; }
        switch ((NailMode)m_Mode)
        {
            // canvasRot 270 = upright; under a 270° spin Unity's scale-before-rotate makes the LOCAL-Y
            // flip un-mirror left/right on screen (measured on-device). All modes share this transform
            // so the overlay orientation is identical; only feed on/off + which overlay differ.
            case NailMode.ARDesign:  // SEE-THROUGH: real hand (feed off) + nail design. Needs cam->eye calib to align.
                SetFeed(false); SetCanvasRot(270f); SetCanvasFlip(false, true); m_DynDepth = false; SetCanvasDepth(100f);
                SetOverlay(0, false, false, 0f);
                if (overlay != null) overlay.show = true;
                SetGrid(false, 0, false, false); break;
            case NailMode.ARGrid:    // SEE-THROUGH: real hand (feed off) + metric grid per nail. 사장님 PoC.
                SetFeed(false); SetCanvasRot(270f); SetCanvasFlip(false, true); m_DynDepth = false; SetCanvasDepth(100f);
                if (overlay != null) overlay.show = false;
                SetGrid(true, 0, false, false); break;
            case NailMode.Calib:     // reverse-SPAAM: see-through + ONE fixed crosshair (crossX,crossY).
                SetFeed(false); SetCanvasRot(270f); SetCanvasFlip(false, true); m_DynDepth = false; SetCanvasDepth(100f);
                if (overlay != null) overlay.show = false;
                SetGrid(false, 0, false, false);
                m_CrossOn = true; SetCross(true, m_CrossX, m_CrossY); break;
            case NailMode.ARMesh:    // SEE-THROUGH: curved per-nail mesh + baked textures + gloss sweep.
                SetFeed(false); SetCanvasRot(270f); SetCanvasFlip(false, true); m_DynDepth = false; SetCanvasDepth(100f);
                SetOverlay(0, false, false, 0f);
                if (overlay != null) overlay.show = false;
                SetGrid(false, 0, false, false);
                if (meshR != null) { meshR.show = true; meshR.ReloadBake(); } break;
            case NailMode.Enroll:    // MAGIC-MIRROR: feed on + server measures per-finger mm -> nail_profile.json.
                SetFeed(true); SetCanvasRot(270f); SetCanvasFlip(false, true); m_DynDepth = false; SetCanvasDepth(100f);
                if (overlay != null) overlay.show = false;
                SetGrid(false, 0, false, false); break;
            case NailMode.MirrorMesh: // MAGIC-MIRROR + DESIGN: feed on + 곡면 메시 디자인을 '피드 위'에 렌더.
                                      // 정합 정확·VAC 없음(먼 패널). see-through 대안 — "디자인을 손톱 위에"를 깨끗하게.
                SetFeed(true); SetCanvasRot(270f); SetCanvasFlip(false, true); m_DynDepth = false; SetCanvasDepth(100f);
                if (overlay != null) overlay.show = false;
                SetGrid(false, 0, false, false);
                if (meshR != null) { meshR.show = true; meshR.parallaxEnable = false; meshR.calibOffset = Vector2.zero; meshR.ReloadBake(); }
                break;
        }
        ShowHud(enroll ? $"[{m_Mode}] Enroll — 손등을 15~50cm에서 천천히" : $"[{m_Mode}] {(NailMode)m_Mode}");
        Debug.Log($"[NailAR] mode -> {m_Mode} {(NailMode)m_Mode}");
    }

    private void SetOverlay(int rotQ, bool mx, bool my, float designRot = 0f)
    {
        if (overlay != null)
        {
            overlay.rotQuadrant = rotQ; overlay.mirrorX = mx; overlay.mirrorY = my;
            overlay.designRotDeg = designRot;
        }
        // mesh renderer shares the overlay's coordinate mapping (same SPAAM calibration)
        if (meshR != null)
        {
            meshR.rotQuadrant = rotQ; meshR.mirrorX = mx; meshR.mirrorY = my;
            meshR.designRotDeg = designRot;
        }
    }

    private void SetGrid(bool on, int rotQ, bool mx, bool my)
    {
        if (grid == null) return;
        grid.show = on; grid.rotQuadrant = rotQ; grid.mirrorX = mx; grid.mirrorY = my;
    }

    // --- Reverse-SPAAM calibration crosshair ---------------------------------------------------
    // A single crosshair at a KNOWN canvas-local position (crossX,crossY). The user aligns their
    // fingertip to it (dominant eye); we then know display-pos <-> camera-detected fingertip-pos,
    // and solve the camera->eye mapping (overlay calibScale/Offset). Child of the canvas, so it
    // shares canvasRot/flip with the overlay -> both live in the same canvas-local space.
    private UnityEngine.UI.RawImage m_Cross;
    private Texture2D m_CrossTex;
    private bool m_CrossOn;
    private float m_CrossX, m_CrossY;
    private void SetCross(bool on, float x, float y)
    {
        if (m_Cross == null && cameraView != null && cameraView.canvas != null)
        {
            var go = new GameObject("CalibCross", typeof(RectTransform), typeof(UnityEngine.UI.RawImage));
            go.transform.SetParent(cameraView.canvas.transform, false);
            m_Cross = go.GetComponent<UnityEngine.UI.RawImage>();
            m_Cross.texture = MakeCrossTex();
            m_Cross.raycastTarget = false;
            m_Cross.color = new Color(0f, 1f, 1f, 0.95f);
            m_Cross.rectTransform.sizeDelta = new Vector2(140f, 140f);
        }
        if (m_Cross != null)
        {
            m_Cross.gameObject.SetActive(on);
            if (on) m_Cross.rectTransform.anchoredPosition = new Vector2(x, y);
        }
        // calibration state: see-through + only the crosshair (hide feed/overlay/grid/mesh)
        if (on)
        {
            SetFeed(false);
            if (overlay != null) overlay.show = false;
            if (grid != null) grid.show = false;
            if (meshR != null) meshR.show = false;
        }
    }
    private Texture2D MakeCrossTex()
    {
        if (m_CrossTex != null) return m_CrossTex;
        int sz = 141, c = sz / 2;
        var t = new Texture2D(sz, sz, TextureFormat.RGBA32, false);
        var px = new Color32[sz * sz];
        var clear = new Color32(255, 255, 255, 0);
        var line = new Color32(255, 255, 255, 255);
        for (int i = 0; i < px.Length; i++) px[i] = clear;
        for (int y = 0; y < sz; y++)
            for (int x = 0; x < sz; x++)
            {
                bool cross = (Mathf.Abs(x - c) <= 1 || Mathf.Abs(y - c) <= 1);   // full-length thin cross
                bool dot = (x - c) * (x - c) + (y - c) * (y - c) <= 16;          // small center dot ring
                bool ring = System.Math.Abs((x - c) * (x - c) + (y - c) * (y - c) - 900) <= 120; // r~30 ring
                if (cross || dot || ring) px[y * sz + x] = line;
            }
        t.SetPixels32(px); t.Apply(false); t.wrapMode = TextureWrapMode.Clamp;
        m_CrossTex = t; return t;
    }

    // Cyan HUD text (top center) showing the current mode, auto-hides after a few seconds.
    private void ShowHud(string s)
    {
        if (m_Hud == null && cameraView != null && cameraView.canvas != null)
        {
            var go = new GameObject("ModeHUD", typeof(RectTransform), typeof(UnityEngine.UI.Text));
            go.transform.SetParent(cameraView.canvas.transform, false);
            m_Hud = go.GetComponent<UnityEngine.UI.Text>();
            m_Hud.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            m_Hud.fontSize = 30; m_Hud.color = Color.cyan; m_Hud.alignment = TextAnchor.UpperCenter;
            m_Hud.horizontalOverflow = HorizontalWrapMode.Overflow;
            var rt = m_Hud.rectTransform;
            rt.anchorMin = rt.anchorMax = new Vector2(0.5f, 1f); rt.pivot = new Vector2(0.5f, 1f);
            rt.anchoredPosition = new Vector2(0f, -30f); rt.sizeDelta = new Vector2(900f, 60f);
        }
        if (m_Hud != null) { m_Hud.text = s; m_Hud.enabled = true; m_HudUntil = Time.time + 3f; }
    }

    private IEnumerator EnsurePermissionThenOpen()
    {
        // Docs: "Add dynamic camera permission request."
        if (!Permission.HasUserAuthorizedPermission(Permission.Camera))
        {
            Permission.RequestUserPermission(Permission.Camera);
            while (!Permission.HasUserAuthorizedPermission(Permission.Camera)) yield return null;
        }
        // Log what the RGB camera can do (surfaces in logcat as errors so release builds show it),
        // then open at the requested resolution. Higher res = sharper mirror + finer nail detection
        // (sensor runs 1920x1080; default 640x400 was upscaled -> soft).
        var supp = ShareCamera.getSupportResolutions(m_CamType);
        if (supp != null) foreach (var r in supp) Debug.LogError($"[NailAR] cam supports {r.width}x{r.height}");
        m_Handler = OpenCam();
        if (m_Handler == null) { Debug.LogError("ShareCamera.OpenCamera failed (permission?)"); yield break; }

        // AR mode: hide the camera image so the REAL hand shows through the display.
        // (Detection still works — GrabJpeg reads m_Handler.texture, not the RawImage.)
        if (cameraView != null)
            cameraView.color = showCameraFeed ? Color.white : new Color(1f, 1f, 1f, 0f);

        // Load nail designs (Assets/Resources/designs/*.png) if none wired in the scene.
        if (overlay != null && (overlay.designs == null || overlay.designs.Length == 0))
            overlay.LoadDesignsFromResources();

        // Grid renderer isn't wired in the (pre-existing) scene: create it at runtime.
        if (grid == null && overlay != null && overlay.cameraViewRect != null)
        {
            grid = overlay.gameObject.AddComponent<NailGridRenderer>();
            grid.cameraViewRect = overlay.cameraViewRect;
        }

        // Curved-mesh renderer (ARMesh mode): same runtime-creation pattern as the grid.
        if (meshR == null && overlay != null && overlay.cameraViewRect != null)
        {
            meshR = overlay.gameObject.AddComponent<NailMeshRenderer>();
            meshR.cameraViewRect = overlay.cameraViewRect;
        }

        // Reparent the overlay/grid coordinate-space from the feed RawImage to the CANVAS (its parent,
        // same rect/size). Then SetFeed can deactivate the feed RawImage GameObject for true see-through
        // WITHOUT hiding the overlay/grid. Do this before ApplyMode so new design/grid children land here.
        if (overlay != null && cameraView != null && cameraView.canvas != null)
        {
            var canvasRT = cameraView.canvas.GetComponent<RectTransform>();
            if (canvasRT != null)
            {
                overlay.cameraViewRect = canvasRT;
                if (grid != null) grid.cameraViewRect = canvasRT;
                if (meshR != null) meshR.cameraViewRect = canvasRT;
            }
        }

#if CALIB_APP
        startMode = (int)NailMode.Calib;   // calib app: ONLY the crosshair, nothing else
#elif MESH_APP
        startMode = (int)NailMode.ARMesh;  // mesh app: boots straight into the curved-mesh AR
#endif
        ApplyMode(startMode);            // set the initial mode preset
        m_LastCalibMode = startMode;

        m_Running = true;
        StartCoroutine(InferLoop());
    }

    void Update()
    {
        // push the latest camera frame into the RawImage/texture
        if (m_Handler != null) m_Handler.UpdateT2d();
        // smoothly move the overlay to the estimated hand distance each frame
        if (m_DynDepth)
        {
            m_CurDepth = Mathf.Lerp(m_CurDepth, m_TargetDepth, 1f - Mathf.Exp(-6f * Time.deltaTime));
            SetCanvasDepth(m_CurDepth);
        }
#if !CALIB_APP && !MESH_APP
        // cycle modes with a screen/touchpad tap (debounced) — disabled in the single-mode apps
        if (Time.time - m_TapDebounce > 0.4f &&
            (Input.GetMouseButtonDown(0) || (Input.touchCount > 0 && Input.GetTouch(0).phase == TouchPhase.Began)))
        {
            m_TapDebounce = Time.time;
            int ci = Array.IndexOf(k_TapCycle, m_Mode);            // -1 (e.g. Enroll) -> cycle[0]
            ApplyMode(k_TapCycle[(ci + 1) % k_TapCycle.Length]);   // ARGrid -> ARDesign -> ARMesh
        }
#endif
        if (m_Hud != null && m_Hud.enabled && Time.time > m_HudUntil) m_Hud.enabled = false;
    }

    private IEnumerator InferLoop()
    {
        var wait = new WaitForSeconds(inferIntervalSec);
        while (m_Running)
        {
            yield return wait;
            byte[] jpeg = GrabJpeg();
            if (jpeg == null) continue;
            yield return m_Edge.Infer(jpeg, res =>
            {
                if (res == null || !res.ok || overlay == null) return;
                overlay.SetResults(res.nails, res.w, res.h);
                if (grid != null) grid.SetResults(res.nails, res.w, res.h);
                if (meshR != null) meshR.SetResults(res.nails, res.w, res.h);
                // enrollment progress -> HUD (server-composed line, e.g. "[Right] T12 I40 ... /40")
                if (m_Mode == (int)NailMode.Enroll && res.enroll != null && res.enroll.active
                    && !string.IsNullOrEmpty(res.enroll.msg))
                    ShowHud(res.enroll.done ? res.enroll.msg + "  → PC: bake 후 push" : res.enroll.msg);
                if (m_DynDepth && res.nails != null && res.nails.Count > 0)
                {
                    // prefer the server's absolute distance (World Landmarks); fall back to nail size
                    float distSum = 0f; int distN = 0, i = 0;
                    float lenSum = 0f;
                    foreach (var n in res.nails) { if (n.distM > 0.01f) { distSum += n.distM; distN++; } lenSum += n.len; i++; }
                    if (distN > 0)
                    {
                        m_TargetDepth = Mathf.Clamp((distSum / distN) * m_DistScale, m_DepthMin, m_DepthMax);
                        if ((m_LogTick++ % 15) == 0)
                            Debug.Log($"[NailAR] distM={(distSum/distN):F3} x{m_DistScale} -> depth={m_TargetDepth:F3}m");
                    }
                    else if (i > 0)
                    {
                        float avg = lenSum / i;
                        if (avg > 0.5f) m_TargetDepth = Mathf.Clamp(m_DepthK / avg, m_DepthMin, m_DepthMax);
                    }
                }
            });
        }
    }

    /// <summary>Read the camera texture into a JPEG (blit->ReadPixels; safe for OES textures).</summary>
    private byte[] GrabJpeg()
    {
        var tex = m_Handler != null ? m_Handler.texture : null;
        if (tex == null) return null;
        var rt = RenderTexture.GetTemporary(tex.width, tex.height, 0, RenderTextureFormat.ARGB32);
        Graphics.Blit(tex, rt);
        var prev = RenderTexture.active; RenderTexture.active = rt;
        if (m_Grab == null || m_Grab.width != tex.width || m_Grab.height != tex.height)
            m_Grab = new Texture2D(tex.width, tex.height, TextureFormat.RGB24, false);
        m_Grab.ReadPixels(new Rect(0, 0, tex.width, tex.height), 0, 0);
        m_Grab.Apply(false);
        RenderTexture.active = prev; RenderTexture.ReleaseTemporary(rt);
        return m_Grab.EncodeToJPG(80);
    }

    void OnDestroy()
    {
        m_Running = false;
        if (m_Handler != null) { ShareCamera.CloseCamera(m_Handler); m_Handler = null; }
    }
}
