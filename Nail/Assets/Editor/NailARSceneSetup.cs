// NailARSceneSetup.cs (Editor) — one click builds the nail-AR scene.
// Menu: NailAR > Setup Scene (v1: XR Plugin rig + Canvas + RawImage + NailARController).
// Proves glasses-camera access via ShareCamera first; overlay/designs wired if present.
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public static class NailARSceneSetup
{
    const string XR_PREFAB = "Packages/com.unity.xr.rayneo.openxr/SDK/Runtime/Resources/Prefab/XR Plugin.prefab";

    [MenuItem("NailAR/Setup Scene")]
    public static void Setup()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

        // 1) XR Plugin rig (provides the glasses HMD camera). Fallback: plain camera.
        var xrPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(XR_PREFAB);
        Camera headCam = null;
        if (xrPrefab != null)
        {
            var xr = (GameObject)PrefabUtility.InstantiatePrefab(xrPrefab);
            xr.name = "XR Plugin";
            headCam = xr.GetComponentInChildren<Camera>(true);
            Debug.Log("[NailAR] XR Plugin instantiated; headCam=" + (headCam ? headCam.name : "null"));
        }
        if (headCam == null)
        {
            Debug.LogWarning("[NailAR] XR Plugin prefab not found at " + XR_PREFAB + " — using a plain Camera.");
            headCam = new GameObject("Camera", typeof(Camera)).GetComponent<Camera>();
            headCam.tag = "MainCamera";
        }

        // 2) World-space Canvas in front of the head camera
        var canvasGO = new GameObject("NailCanvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        var canvas = canvasGO.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.WorldSpace;
        canvas.worldCamera = headCam;
        var crt = (RectTransform)canvasGO.transform;
        crt.SetParent(headCam.transform, false);
        crt.sizeDelta = new Vector2(1280, 480);
        crt.localScale = Vector3.one * 0.0016f;             // fit ~glasses FOV at 2m
        crt.localPosition = new Vector3(0f, 0f, 2f);

        // 3) RawImage that fills the canvas (ShareCamera target)
        var riGO = new GameObject("CameraView", typeof(RawImage));
        var ri = riGO.GetComponent<RawImage>();
        var rirt = ri.rectTransform;
        rirt.SetParent(crt, false);
        rirt.anchorMin = Vector2.zero; rirt.anchorMax = Vector2.one;
        rirt.offsetMin = Vector2.zero; rirt.offsetMax = Vector2.zero;

        // 4) Manager with our scripts, wired
        var mgr = new GameObject("NailAR", typeof(NailARController), typeof(NailOverlayRenderer));
        var ctrl = mgr.GetComponent<NailARController>();
        var ovr = mgr.GetComponent<NailOverlayRenderer>();
        ctrl.cameraView = ri;
        ctrl.overlay = ovr;
        ovr.cameraViewRect = rirt;

        // 5) HUD text (optional feedback) — skipped in v1 to avoid TMP deps.

        // 6) Save + add to build settings
        const string dir = "Assets/Scenes";
        if (!AssetDatabase.IsValidFolder(dir)) AssetDatabase.CreateFolder("Assets", "Scenes");
        string path = dir + "/NailAR.unity";
        EditorSceneManager.SaveScene(scene, path);
        var list = new System.Collections.Generic.List<EditorBuildSettingsScene>(EditorBuildSettings.scenes);
        if (!list.Exists(s => s.path == path)) list.Insert(0, new EditorBuildSettingsScene(path, true));
        EditorBuildSettings.scenes = list.ToArray();

        Debug.Log("[NailAR] Scene setup complete -> " + path + ". Now File > Build Settings > Build (Android).");
        EditorUtility.DisplayDialog("NailAR", "Scene 'NailAR' created and added to Build Settings.\n\nNext: File > Build Settings > Build.", "OK");
    }
}
