// AndroidManifestCameraPermission.cs (Editor) — post-processes Unity's GENERATED
// AndroidManifest at build time to make the app a proper RayNeo OpenXR app:
//   1) Launch activity -> com.rayneo.openxradapter.UnityOpenXrActivity
//      (RayNeo's adapter activity sets up the runtime/launcher IPC connection BEFORE
//       OpenXR init. Without it the app starts as a flat mobile app and the OpenXR
//       runtime handshake returns null -> native SIGSEGV at XRSDKPreInit /
//       xrGetInstanceProcAddr. Per RayNeo/Qualcomm X3 Pro dev guide.)
//   2) CAMERA + INTERNET permissions (ShareCamera needs CAMERA; edge needs INTERNET)
//   3) usesCleartextTraffic (local self-signed / adb-reverse edge server)
// Surgical (edits the generated manifest in place) so RayNeo <queries>/OpenXR entries
// are preserved. Idempotent.
#if UNITY_ANDROID
using System.IO;
using System.Xml;
using UnityEditor.Android;
using UnityEngine;

public class AndroidManifestCameraPermission : IPostGenerateGradleAndroidProject
{
    public int callbackOrder => 1;

    const string AndroidNs = "http://schemas.android.com/apk/res/android";
    const string UnityActivity  = "com.unity3d.player.UnityPlayerActivity";
    const string RayNeoActivity = "com.rayneo.openxradapter.UnityOpenXrActivity";

    public void OnPostGenerateGradleAndroidProject(string gradleProjectPath)
    {
        string manifestPath = Path.Combine(gradleProjectPath, "src", "main", "AndroidManifest.xml");
        if (!File.Exists(manifestPath))
        {
            Debug.LogWarning("[NailAR] manifest not found at " + manifestPath);
            return;
        }

        var doc = new XmlDocument();
        doc.Load(manifestPath);
        var manifest = doc.DocumentElement; // <manifest>

        // 1) swap the launch activity to RayNeo's adapter activity
        int renamed = 0;
        foreach (XmlElement act in manifest.GetElementsByTagName("activity"))
        {
            if (act.GetAttribute("name", AndroidNs) == UnityActivity)
            {
                act.SetAttribute("name", AndroidNs, RayNeoActivity);
                renamed++;
            }
        }

        // 2) permissions
        AddUsesPermission(doc, manifest, "android.permission.CAMERA");
        AddUsesPermission(doc, manifest, "android.permission.INTERNET");

        // 3) cleartext for the local edge server
        // 4) com.rayneo.mercury.app=true  — marks us a NATIVE RayNeo (Mercury) app so the
        //    App Lab launcher opens us DIRECTLY (immersive OpenXR) instead of wrapping us in
        //    the ffcontainer 2D "mini-app" (sbsMode) that duplicates the mirror per eye.
        //    RayNeo's own apps (media/record/...) all declare this; sideloaded apps that
        //    lack it get the 2D container. (Reverse-engineered from AppContainer, 2026-07-04.)
        if (manifest.SelectSingleNode("application") is XmlElement app)
        {
            app.SetAttribute("usesCleartextTraffic", AndroidNs, "true");
            AddApplicationMetaData(doc, app, "com.rayneo.mercury.app", "true");
        }

        doc.Save(manifestPath);
        Debug.Log($"[NailAR] Manifest patched: launchActivity->RayNeo ({renamed}), CAMERA/INTERNET + mercury.app added @ {manifestPath}");
    }

    void AddUsesPermission(XmlDocument doc, XmlElement manifest, string permName)
    {
        foreach (XmlElement e in manifest.GetElementsByTagName("uses-permission"))
            if (e.GetAttribute("name", AndroidNs) == permName) return; // already present

        var el = doc.CreateElement("uses-permission");
        el.SetAttribute("name", AndroidNs, permName);
        manifest.AppendChild(el);
    }

    void AddApplicationMetaData(XmlDocument doc, XmlElement app, string name, string value)
    {
        foreach (XmlElement e in app.GetElementsByTagName("meta-data"))
            if (e.GetAttribute("name", AndroidNs) == name) { e.SetAttribute("value", AndroidNs, value); return; }

        var el = doc.CreateElement("meta-data");
        el.SetAttribute("name", AndroidNs, name);
        el.SetAttribute("value", AndroidNs, value);
        app.AppendChild(el);
    }
}
#endif
