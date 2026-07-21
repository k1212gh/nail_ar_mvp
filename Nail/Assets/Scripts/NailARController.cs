// NailARController.cs — glasses-camera nail-AR via RayNeo ShareCamera + PC edge.
// Uses the REAL ARDK API (verified against SDK/.../ShareCamera + Samples~/HelloRayNeo).
// Flow: request CAMERA permission -> ShareCamera.OpenCamera(RGB, RawImage) -> each frame
// UpdateT2d() refreshes the RawImage; every N s grab the texture -> POST /infer -> ROIs
// -> NailOverlayRenderer draws the design on each nail.
using System;
using System.Collections;
using System.Collections.Generic;
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
        // Log AROUND the native OpenCamera call: if we see "calling" but never "returned",
        // the RayNeo camera HAL is wedged (native blocks) -> needs a device reboot + single launch.
        int rw = Mathf.Max(320, camW), rh = Mathf.Max(240, camH);
        Debug.Log($"[NailAR] ShareCamera.OpenCamera calling ({rw}x{rh})…");
        var h = ShareCamera.OpenCamera(m_CamType, new XRResolution(rw, rh), cameraView);
        Debug.Log($"[NailAR] ShareCamera.OpenCamera returned {(h != null ? "handle" : "null")}");
        if (h == null && (camW != 640 || camH != 400))
        {
            Debug.LogError($"[NailAR] {camW}x{camH} unsupported -> fallback 640x400");
            camW = 640; camH = 400;
            h = ShareCamera.OpenCamera(m_CamType, new XRResolution(640, 400), cameraView);
            Debug.Log($"[NailAR] fallback OpenCamera returned {(h != null ? "handle" : "null")}");
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
    private readonly EdgeSocketClient m_Sock = new EdgeSocketClient();   // raw TCP fast path (B')
    private bool m_UseSocket;
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
        public float alongTip = -99f;          // shift design along the nail axis (+tip/-base, frac of
                                               // length). Fixes "design sits below the nail". -99 = leave
        // --- viewing comfort ---
        public float zoom = -1f;               // manual mirror zoom (crop-in). 1=as-is, 1.5=bigger; <=0 leave
        public int mono = -1;                  // 0=both eyes, 1=LEFT eye only, 2=RIGHT eye only, -1=leave
        // GUIDE (digital loupe): centre the view on ONE nail and magnify -> a working close-up for
        // drawing (start point / outline guidance). Feed+design share the canvas, so both magnify
        // together and stay registered.
        public int guide = -1;                 // 1=crop to the target nail, 0=whole hand, -1=leave
        public float guideZoom = -1f;          // magnification used while guiding; <=0 = leave
        public float predictMs = -1f;          // latency compensation (ms). 0=off, ~150 = cancel the
                                               // offload lag so the design keeps up with the hand
        public float meshBulge = 0f;           // +1/-1 bulge direction; 0 = leave
        public int bakeReload = -1;            // CHANGE the value to re-read nail_bake dir; -1 = leave
        // --- distance-adaptive parallax model: offset(d) = A + B/d (display px, px·m) ---
        public int meshParallaxOn = -1;        // 1=use A+B/d per frame, 0=static offset, -1=leave
        public float pAx = -99999f, pAy = -99999f;  // parallax constant A; sentinel=leave
        public float pBx = -99999f, pBy = -99999f;  // parallax coeff B; sentinel=leave
        // --- TRANSPORT: swap the edge endpoint without rebuilding (USB now, phone/LAN later) ---
        public string edgeUrl = "";            // ""=leave. USB: https://127.0.0.1:8443/infer, LAN: https://<ip>:8443/infer
        // --- raw TCP socket transport (B'): kills per-frame TLS handshake -> higher fps ---
        public int useSocket = -1;             // 1=socket(fast), 0=HTTP, -1=leave
        public string sockHost = "";           // ""=leave; USB=127.0.0.1, LAN=<pc-ip>
        public int sockPort = -1;              // -1=leave (default 8444)
        public float inferInterval = -1f;      // <0=leave; loop wait sec (fps cap). 0=as fast as possible
        // --- LIFE-SIZE preview (reference-card scale) ---
        public int lifesize = -1;              // 1=match the real hand's apparent size, 0=off, -1=leave
        public float panelRadPerPx = -1f;      // radians subtended by ONE canvas px (the single unknown
                                               // constant of the life-size equation). ~0.0008; <=0 = leave.
                                               // TUNE THIS LIVE until the virtual hand matches the real one.
        public float lifesizeMax = -1f;        // clamp on the zoom (safety); <=0 = leave
        // --- RENDER GATING: hide designs while the hand moves (kills latency ghosting) ---
        public int gate = -1;                  // 1=only render nails the server marks stable, 0=off, -1=leave
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
                if (c.alongTip > -98f) meshR.alongTip = c.alongTip;   // live-tune the axis shift
                if (c.predictMs >= 0f) meshR.predictSec = c.predictMs * 0.001f;   // latency compensation
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
            // --- transport: hot-swap the edge endpoint (USB <-> phone/LAN) without a rebuild ---
            if (!string.IsNullOrEmpty(c.edgeUrl) && m_Edge != null && m_Edge.url != c.edgeUrl)
            {
                m_Edge.url = c.edgeUrl;
                Debug.Log($"[NailAR] edge endpoint -> {c.edgeUrl}");
            }
            // raw TCP socket transport (fast path) — live-swappable
            if (c.inferInterval >= 0f) inferIntervalSec = c.inferInterval;
            if (!string.IsNullOrEmpty(c.sockHost)) m_Sock.host = c.sockHost;
            if (c.sockPort > 0) m_Sock.port = c.sockPort;
            if (c.useSocket != -1 && (c.useSocket == 1) != m_UseSocket)
            {
                m_UseSocket = c.useSocket == 1;
                if (m_UseSocket) m_Sock.Start();
                Debug.Log($"[NailAR] transport -> {(m_UseSocket ? "SOCKET" : "HTTP")}");
            }
            // --- life-size preview + render gating (log only on CHANGE, not every 0.7s poll) ---
            if (c.lifesize != -1 && (c.lifesize == 1) != m_LifesizeOn)
            {
                m_LifesizeOn = c.lifesize == 1;
                if (!m_LifesizeOn) { m_LifesizeZoom = 1f; ApplyCanvasXform(); }
                Debug.Log($"[NailAR] lifesize -> {m_LifesizeOn}");
            }
            if (c.panelRadPerPx > 0f && !Mathf.Approximately(c.panelRadPerPx, m_PanelRadPerPx))
            { m_PanelRadPerPx = c.panelRadPerPx; Debug.Log($"[NailAR] panelRadPerPx -> {m_PanelRadPerPx:F6}"); }
            if (c.lifesizeMax > 0f) m_LifesizeMax = c.lifesizeMax;
            if (c.gate != -1 && (c.gate == 1) != m_GateOn) { m_GateOn = c.gate == 1; Debug.Log($"[NailAR] gate -> {m_GateOn}"); }
            // --- viewing: manual zoom / guide loupe / mono ---
            if (c.zoom > 0f && !Mathf.Approximately(c.zoom, m_ManualZoom))
            { m_ManualZoom = c.zoom; ApplyCanvasXform(); Debug.Log($"[NailAR] zoom -> {m_ManualZoom:F2}"); }
            if (c.guideZoom > 0f && !Mathf.Approximately(c.guideZoom, m_GuideZoom))
            { m_GuideZoom = c.guideZoom; ApplyCanvasXform(); Debug.Log($"[NailAR] guideZoom -> {m_GuideZoom:F2}"); }
            if (c.guide != -1 && (c.guide == 1) != m_GuideOn)
            {
                m_GuideOn = c.guide == 1;
                if (!m_GuideOn) m_HaveGuideCenter = false;   // back to whole-hand view
                ApplyCanvasXform();
                Debug.Log($"[NailAR] guide(loupe) -> {m_GuideOn}");
            }
            if (c.mono != -1 && c.mono != m_MonoMode) SetMono(c.mono);
            if (m_Edge != null) m_Edge.wantCard = m_LifesizeOn;   // only ask for card scale when needed
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
    // --- LIFE-SIZE preview state ---------------------------------------------------------------
    // Goal: the hand shown in the mirror subtends the SAME angle as the user's real hand, so the
    // preview reads as "my actual hand at actual size" instead of a webcam thumbnail.
    //   real hand angular size  = (P px * mmPerPx / 1000) / distM      [rad]
    //   shown hand angular size = P px * zoom * panelRadPerPx          [rad]
    //   => zoom = mmPerPx / (1000 * distM * panelRadPerPx)
    // mmPerPx comes from the reference card (server), distM from the detector; panelRadPerPx is the
    // one device constant — live-tunable via nail_calib.json so it can be dialled in on-device.
    private bool m_LifesizeOn;
    private float m_PanelRadPerPx = 0.0008f;   // matches the canvas rig (0.0008 * depth scale)
    private float m_LifesizeMax = 6f;          // clamp so a bad card read can't blow up the panel
    private float m_LifesizeZoom = 1f;         // smoothed, applied in ApplyCanvasXform
    private bool m_GateOn;                     // render gating (only stable nails)
    // --- viewing: manual zoom, GUIDE loupe (centre on one nail), mono/stereo ---
    private float m_ManualZoom = 1f;           // crop-in magnification of the mirror
    private bool m_GuideOn;                    // digital loupe: centre + magnify one nail
    private float m_GuideZoom = 3f;
    private Vector2 m_GuideCenter;             // canvas-local position of the tracked nail
    private bool m_HaveGuideCenter;
    private int m_MonoMode;                    // 0=both eyes, 1=left, 2=right
    private Camera m_MonoCam;
    private const int k_MonoLayer = 31;        // dedicated layer so only the mono camera draws the canvas
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
        float s = 0.0008f * m_Depth;   // 0.0016 @ 2 m -> keep angular size constant
        s *= m_LifesizeZoom;           // life-size: scales feed AND overlay together (stays aligned)
        s *= m_ManualZoom;             // manual crop-in
        if (m_GuideOn) s *= m_GuideZoom;                       // loupe magnification
        // GUIDE: slide the canvas so the tracked nail sits at the centre of view. Because the feed
        // and the design are both children of this canvas, they magnify/shift together -> the design
        // stays glued to the nail no matter how far we zoom in.
        Vector2 shift = Vector2.zero;
        if (m_GuideOn && m_HaveGuideCenter)
        {
            var c = m_GuideCenter;
            shift = new Vector2(-c.x * (m_FlipX ? -s : s) * m_StretchX,
                                -c.y * (m_FlipY ? -s : s) * m_StretchY);
            shift = Quaternion.Euler(0f, 0f, m_CanvasRot) * shift;   // canvas is rotated; rotate the shift too
        }
        ct.localPosition = new Vector3(shift.x, shift.y, m_Depth);
        ct.localScale = new Vector3((m_FlipX ? -s : s) * m_StretchX, (m_FlipY ? -s : s) * m_StretchY, s);
    }
    // MONO: draw the mirror/guide into ONE eye only. The other eye keeps a clear view of the real
    // hand — the jeweller's-loupe pattern, and it sidesteps stereo fusion discomfort entirely.
    // Implemented by moving the canvas to its own layer that only a per-eye camera renders.
    // Fully reversible at runtime (push mono=0) so a bad result never needs a rebuild.
    private void SetMono(int mode)
    {
        if (cameraView == null || cameraView.canvas == null) return;
        var canvasGo = cameraView.canvas.gameObject;
        var main = Camera.main;
        m_MonoMode = mode;
        if (mode <= 0)
        {
            SetLayerRecursive(canvasGo, 0);
            if (main != null) main.cullingMask |= (1 << k_MonoLayer) | 1;
            if (m_MonoCam != null) { Destroy(m_MonoCam.gameObject); m_MonoCam = null; }
            Debug.Log("[NailAR] mono -> BOTH eyes");
            return;
        }
        if (main == null) { Debug.LogWarning("[NailAR] mono: no Camera.main"); return; }
        SetLayerRecursive(canvasGo, k_MonoLayer);
        main.cullingMask &= ~(1 << k_MonoLayer);      // stereo camera stops drawing the canvas
        if (m_MonoCam == null)
        {
            var go = new GameObject("MonoCanvasCam");
            go.transform.SetParent(main.transform, false);
            m_MonoCam = go.AddComponent<Camera>();
            m_MonoCam.clearFlags = CameraClearFlags.Nothing;
            m_MonoCam.cullingMask = 1 << k_MonoLayer;
            m_MonoCam.depth = main.depth + 1;
            m_MonoCam.nearClipPlane = main.nearClipPlane;
            m_MonoCam.farClipPlane = main.farClipPlane;
        }
        m_MonoCam.stereoTargetEye = (mode == 2) ? StereoTargetEyeMask.Right : StereoTargetEyeMask.Left;
        Debug.Log($"[NailAR] mono -> {(mode == 2 ? "RIGHT" : "LEFT")} eye only");
    }
    private static void SetLayerRecursive(GameObject go, int layer)
    {
        go.layer = layer;
        foreach (Transform t in go.transform) SetLayerRecursive(t.gameObject, layer);
    }

    // GUIDE loupe: track the nail nearest the image centre (the one being worked on) and remember
    // where it lands on the canvas, so ApplyCanvasXform can centre + magnify on it.
    private void UpdateGuideCenter(InferResult res)
    {
        if (!m_GuideOn || res.nails == null || res.nails.Count == 0) return;
        if (cameraView == null || cameraView.canvas == null) return;
        var rect = cameraView.canvas.GetComponent<RectTransform>();
        if (rect == null) return;
        var size = rect.rect.size;
        float cxImg = res.w * 0.5f, cyImg = res.h * 0.5f;
        float bestD = float.MaxValue; float bx = 0f, by = 0f; bool found = false;
        foreach (var n in res.nails)
        {
            float dx = n.cx - cxImg, dy = n.cy - cyImg, d = dx * dx + dy * dy;
            if (d < bestD) { bestD = d; bx = n.cx; by = n.cy; found = true; }
        }
        if (!found) return;
        float nx = Mathf.Clamp01(bx / Mathf.Max(1, res.w)), ny = Mathf.Clamp01(by / Mathf.Max(1, res.h));
        var target = new Vector2((nx - 0.5f) * size.x, -(ny - 0.5f) * size.y);   // mirror mapping (q=0)
        m_GuideCenter = m_HaveGuideCenter ? Vector2.Lerp(m_GuideCenter, target, 0.3f) : target;
        m_HaveGuideCenter = true;
        ApplyCanvasXform();
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
        // SetActive the feed RawImage GameObject (see-through modes deactivate it). CRITICAL: also
        // set the color OPAQUE when showing — EnsurePermissionThenOpen leaves it transparent (alpha 0)
        // for see-through, so without this the MIRROR feed stays invisible and only the design shows
        // ("one dot" symptom). The ShareCamera Texture2D respects color.a (unlike a raw OES texture).
        if (cameraView != null)
        {
            cameraView.gameObject.SetActive(on);
            if (on) cameraView.color = Color.white;   // opaque = show the mirror image
        }
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
                // FULLY specify the mapping — mirror must NOT inherit stale see-through calibration
                // (rotQuadrant defaults to 1, calibScale/mirror may carry over from another mode).
                // That inheritance was the root cause of the small mis-alignments.
                SetOverlay(0, false, false, 0f);          // rotQuadrant=0 -> 1:1 with the feed image
                if (meshR != null)
                {
                    meshR.show = true;
                    meshR.mirrorMode = true;              // image-space compositing: no parallax/metric
                    meshR.parallaxEnable = false;
                    meshR.calibOffset = Vector2.zero;
                    meshR.calibScale = 1f;                // no SPAAM spread in mirror
                    meshR.ReloadBake();
                }
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
        Debug.Log("[NailAR] === EnsurePermissionThenOpen START ===");
        // Dynamic camera permission. Poll with a timeout instead of an unbounded wait so a missed
        // grant-event can't hang the coroutine forever (was a real failure mode on this device).
        if (!Permission.HasUserAuthorizedPermission(Permission.Camera))
        {
            Debug.Log("[NailAR] requesting CAMERA permission");
            Permission.RequestUserPermission(Permission.Camera);
            float tw = 0f;
            while (!Permission.HasUserAuthorizedPermission(Permission.Camera) && tw < 15f)
            { tw += Time.deltaTime; yield return null; }
        }
        Debug.Log($"[NailAR] CAMERA permission granted = {Permission.HasUserAuthorizedPermission(Permission.Camera)}");
        yield return new WaitForSeconds(0.5f);   // let the camera service settle after grant/unlock
        var supp = ShareCamera.getSupportResolutions(m_CamType);
        Debug.Log($"[NailAR] getSupportResolutions -> {(supp == null ? "null" : supp.Length + " modes")}");
        // Retry open: the RayNeo camera HAL is often transiently not-ready right after launch/unlock.
        for (int attempt = 0; attempt < 8 && m_Handler == null; attempt++)
        {
            Debug.Log($"[NailAR] --- OpenCam attempt {attempt} ---");
            m_Handler = OpenCam();
            if (m_Handler == null) yield return new WaitForSeconds(1f);
        }
        if (m_Handler == null) { Debug.LogError("[NailAR] OpenCamera failed after 8 retries — reboot glasses + single launch"); yield break; }
        Debug.Log("[NailAR] === CAMERA OPEN OK ===");

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
#elif MIRROR_APP
        startMode = (int)NailMode.MirrorMesh;  // ★ mirror test app: boots STRAIGHT into magic-mirror+design
#elif MESH_APP
        startMode = (int)NailMode.ARMesh;  // mesh app: boots straight into the curved-mesh AR
#endif
        Debug.Log($"[NailAR] boot startMode = {startMode} ({(NailMode)startMode})");
        ApplyMode(startMode);            // set the initial mode preset
#if GUIDE_APP
        // GUIDE app = single-eye magnified working view (jeweller's-loupe pattern): one eye shows the
        // zoomed nail + design guide, the other keeps a clear view of the real hand.
        m_GuideOn = true;
        m_GateOn = false;                // never hide the guide while the hand moves
        SetMono(1);                      // LEFT eye only (push mono=0/2 to change at runtime)
        ApplyCanvasXform();
        Debug.Log("[NailAR] GUIDE app: loupe + mono(left)");
#endif
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
#if !CALIB_APP && !MESH_APP && !MIRROR_APP
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
        while (m_Running)
        {
            if (inferIntervalSec > 0f) yield return new WaitForSeconds(inferIntervalSec);  // live-tunable fps cap
            else yield return null;
            byte[] jpeg = GrabJpeg();
            if (jpeg == null) continue;
            if (m_UseSocket)
            {
                // raw TCP fast path: submit on the worker thread, poll for the response (frames-in-flight=1)
                m_Sock.wantCard = m_LifesizeOn;
                m_Sock.Submit(jpeg);
                float t0 = Time.realtimeSinceStartup;
                while (!m_Sock.Done && Time.realtimeSinceStartup - t0 < 2f) yield return null;
                InferResult res = null;
                if (m_Sock.Done && !m_Sock.Err)
                    try { res = JsonUtility.FromJson<InferResult>(m_Sock.Resp); }
                    catch (Exception e) { Debug.LogWarning("[NailAR] sock parse: " + e.Message); }
                HandleResult(res);
            }
            else
            {
                yield return m_Edge.Infer(jpeg, HandleResult);   // HTTP path
            }
        }
    }

    // Apply one inference result (shared by socket + HTTP paths).
    private void HandleResult(InferResult res)
    {
        if (res == null || !res.ok || overlay == null) return;
        UpdateLifesize(res);                        // card scale -> life-size preview zoom
        var shown = GateNails(res.nails);           // render gating (hide moving nails)
        overlay.SetResults(shown, res.w, res.h);
        if (grid != null) grid.SetResults(shown, res.w, res.h);
        if (meshR != null) meshR.SetResults(shown, res.w, res.h);
        UpdateGuideCenter(res);                     // loupe: re-centre on the worked nail
        // designs are created at runtime as canvas children -> they land on the DEFAULT layer and
        // would leak into both eyes. Re-stamp the mono layer after each update.
        if (m_MonoMode > 0 && cameraView != null && cameraView.canvas != null)
            SetLayerRecursive(cameraView.canvas.gameObject, k_MonoLayer);
        if (m_Mode == (int)NailMode.Enroll && res.enroll != null && res.enroll.active
            && !string.IsNullOrEmpty(res.enroll.msg))
            ShowHud(res.enroll.done ? res.enroll.msg + "  -> PC: bake 후 push" : res.enroll.msg);
        if (m_DynDepth && res.nails != null && res.nails.Count > 0)
        {
            float distSum = 0f; int distN = 0, i = 0; float lenSum = 0f;
            foreach (var n in res.nails) { if (n.distM > 0.01f) { distSum += n.distM; distN++; } lenSum += n.len; i++; }
            if (distN > 0)
            {
                m_TargetDepth = Mathf.Clamp((distSum / distN) * m_DistScale, m_DepthMin, m_DepthMax);
                if ((m_LogTick++ % 15) == 0)
                    Debug.Log($"[NailAR] distM={(distSum / distN):F3} x{m_DistScale} -> depth={m_TargetDepth:F3}m");
            }
            else if (i > 0)
            {
                float avg = lenSum / i;
                if (avg > 0.5f) m_TargetDepth = Mathf.Clamp(m_DepthK / avg, m_DepthMin, m_DepthMax);
            }
        }
    }

    /// <summary>Render gating — drop nails the server marked unstable (hand moving).
    /// Offload latency means a moving nail's design lags behind the hand; hiding it while in motion
    /// is far less objectionable than a design sliding off the finger.</summary>
    private List<NailRoi> GateNails(List<NailRoi> nails)
    {
        if (!m_GateOn || nails == null || nails.Count == 0) return nails;
        var keep = new List<NailRoi>(nails.Count);
        foreach (var n in nails) if (n.stable) keep.Add(n);
        return keep;
    }

    /// <summary>Life-size preview — scale the mirror so the shown hand subtends the same angle as
    /// the real hand.  zoom = mmPerPx / (1000 * distM * panelRadPerPx)   (see field docs).
    /// Needs a reference card in frame for mmPerPx; otherwise the previous zoom is kept.</summary>
    private void UpdateLifesize(InferResult res)
    {
        if (!m_LifesizeOn || res.card == null || !res.card.found || res.card.mmPerPx <= 0f) return;
        if (res.nails == null || res.nails.Count == 0) return;
        float dSum = 0f; int dN = 0;
        foreach (var n in res.nails) if (n.distM > 0.01f) { dSum += n.distM; dN++; }
        if (dN == 0) return;                       // no absolute distance -> can't solve the angle
        float distM = dSum / dN;
        float target = res.card.mmPerPx / (1000f * distM * Mathf.Max(1e-6f, m_PanelRadPerPx));
        target = Mathf.Clamp(target, 0.1f, m_LifesizeMax);
        m_LifesizeZoom = Mathf.Lerp(m_LifesizeZoom, target, 0.25f);   // smooth out card-read jitter
        ApplyCanvasXform();
        if ((m_LogTick++ % 15) == 0)
            Debug.Log($"[NailAR] lifesize mmPerPx={res.card.mmPerPx:F4} dist={distM:F3} zoom={m_LifesizeZoom:F3}");
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
        m_Sock.Stop();
        if (m_Handler != null) { ShareCamera.CloseCamera(m_Handler); m_Handler = null; }
    }
}
