// CIBuild.cs (Editor) — headless Android APK builds for autonomous iteration.
//   Main app:  -executeMethod CIBuild.BuildAndroid   -> TEST_AUTO.apk   (com.DefaultCompany.Nail)
//   Calib app: -executeMethod CIBuild.BuildCalib      -> NailCalib_AUTO.apk (com.DefaultCompany.NailCalib)
// The calib app is the SAME code under a DIFFERENT package/name so it installs SIDE-BY-SIDE with the
// main app; run it and push {"mode":3} to enter the reverse-SPAAM crosshair. IL2CPP + ARM64 (RayNeo).
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

public static class CIBuild
{
    public static void BuildAndroid() => Build("TEST_AUTO.apk", null, null, null);

    // Separate-package calibration app: CALIB_APP define makes it launch straight into the crosshair
    // and ONLY do calibration (no mode cycling, no mirror/grid/design). Installs side-by-side.
    public static void BuildCalib() => Build("NailCalib_AUTO.apk", "com.DefaultCompany.NailCalib", "NailCalib", "CALIB_APP");

    // Separate-package curved-mesh app: MESH_APP boots straight into ARMesh and disables mode
    // cycling (mesh demo only). NOTE: own package = own files dir -> push nail_bake/ + calib to
    // /sdcard/Android/data/com.DefaultCompany.NailMesh/files/ .
    public static void BuildMesh() => Build("NailMesh_AUTO.apk", "com.DefaultCompany.NailMesh", "NailMesh", "MESH_APP");

    static void Build(string outName, string overridePackage, string overrideProduct, string extraDefine)
    {
        PlayerSettings.SetScriptingBackend(BuildTargetGroup.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;

        // swap identity + defines for a side-by-side build, restore afterwards
        string prevPkg = PlayerSettings.GetApplicationIdentifier(BuildTargetGroup.Android);
        string prevProduct = PlayerSettings.productName;
        string prevDefines = PlayerSettings.GetScriptingDefineSymbolsForGroup(BuildTargetGroup.Android);
        if (overridePackage != null) PlayerSettings.SetApplicationIdentifier(BuildTargetGroup.Android, overridePackage);
        if (overrideProduct != null) PlayerSettings.productName = overrideProduct;
        if (extraDefine != null)
            PlayerSettings.SetScriptingDefineSymbolsForGroup(BuildTargetGroup.Android,
                string.IsNullOrEmpty(prevDefines) ? extraDefine : prevDefines + ";" + extraDefine);

        var scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
        if (scenes.Length == 0) scenes = new[] { "Assets/Scenes/NailAR.unity" };

        string outPath = Path.GetFullPath(outName);
        var opts = new BuildPlayerOptions
        {
            scenes = scenes,
            locationPathName = outPath,
            target = BuildTarget.Android,
            options = BuildOptions.None,
        };

        BuildReport report = BuildPipeline.BuildPlayer(opts);

        // restore main-app identity + defines
        if (overridePackage != null) PlayerSettings.SetApplicationIdentifier(BuildTargetGroup.Android, prevPkg);
        if (overrideProduct != null) PlayerSettings.productName = prevProduct;
        if (extraDefine != null) PlayerSettings.SetScriptingDefineSymbolsForGroup(BuildTargetGroup.Android, prevDefines);

        BuildSummary s = report.summary;
        Debug.Log($"[CIBuild] result={s.result} errors={s.totalErrors} size={s.totalSize} pkg={overridePackage ?? prevPkg} out={outPath}");
        EditorApplication.Exit(s.result == BuildResult.Succeeded ? 0 : 1);
    }
}
