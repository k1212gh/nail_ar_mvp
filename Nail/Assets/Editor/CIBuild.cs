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

    // 기존 NailMesh 를 덮어쓰지 않는 별도 패키지(side-by-side). 코드 동일(MESH_APP 재사용 -> 재컴파일 없음).
    // 설치 후 nail_calib.json 으로 mode=5(MirrorMesh: 매직미러+디자인) push.
    public static void BuildMirror() => Build("NailMirror_AUTO.apk", "com.DefaultCompany.NailMirror", "NailMirror", "MESH_APP");

    // ★ 개발용 미러 테스트 빌드 — MIRROR_APP: 부팅 즉시 MirrorMesh(매직미러+디자인)로 진입,
    // 모드 순환/그리드/calib/enroll 없음 = 실패 지점 최소. Development Build 라 Debug.Log 가
    // logcat(태그 Unity)에 나온다(Release 는 싱크 꺼짐). 확인: adb logcat -s Unity. 배포는 BuildMirror.
    public static void BuildMirrorDev() => Build("NailMirror_AUTO.apk", "com.DefaultCompany.NailMirror", "NailMirror", "MIRROR_APP", dev: true);

    // ★ 가이드 앱(정밀 작업 보조) — 부팅 즉시 "단안 확대 루페": 한 눈은 손톱 확대+디자인 가이드,
    // 다른 눈은 실제 손을 그대로 본다. 별도 패키지라 미러 앱과 side-by-side 설치.
    // 런타임 조절: push_calib guide/guideZoom/mono/zoom.
    public static void BuildGuideDev() => Build("NailGuide_AUTO.apk", "com.DefaultCompany.NailGuide", "NailGuide", "MIRROR_APP;GUIDE_APP", dev: true);

    static void Build(string outName, string overridePackage, string overrideProduct, string extraDefine,
                      bool dev = false)
    {
        PlayerSettings.SetScriptingBackend(BuildTargetGroup.Android, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
        // RayNeo OpenXR 검증이 Target SDK 30 을 강제 -> 30 유지(임베디드 SDK엔 30이 없어 실패했었음).
        PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevel30;

        // 배치모드엔 External Tools UI가 없어 SDK를 명시해야 함. platform-30 있는 사용자 SDK 우선,
        // 없으면 임베디드. NDK/JDK 는 항상 임베디드(사용자 SDK엔 없을 수 있음).
        string apRoot = Path.Combine(EditorApplication.applicationContentsPath, "PlaybackEngines", "AndroidPlayer");
        string local = System.Environment.GetEnvironmentVariable("LOCALAPPDATA")
                       ?? System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData);
        string userSdk = Path.Combine(local, "Android", "Sdk");
        bool userHas30 = Directory.Exists(Path.Combine(userSdk, "platforms", "android-30"));
        string sdkRoot = userHas30 ? userSdk : Path.Combine(apRoot, "SDK");
        UnityEngine.Debug.Log($"[CIBuild] SDK root -> {sdkRoot} (userHas30={userHas30}, local={local})");
        EditorPrefs.SetString("AndroidSdkRoot", sdkRoot);
        EditorPrefs.SetString("AndroidNdkRoot", Path.Combine(apRoot, "NDK"));
        EditorPrefs.SetString("AndroidNdkRootR23b", Path.Combine(apRoot, "NDK"));
        EditorPrefs.SetString("JdkPath", Path.Combine(apRoot, "OpenJDK"));
        // "임베디드 사용" 불리언이 켜져있으면 위 SdkRoot 경로를 무시하고 임베디드(30 없음)를 씀 -> 끈다.
        EditorPrefs.SetBool("SdkUseEmbedded", !userHas30);   // 사용자 SDK에 30 있으면 그걸 쓰게
        EditorPrefs.SetBool("NdkUseEmbedded", true);         // NDK/JDK 는 임베디드 사용
        EditorPrefs.SetBool("JdkUseEmbedded", true);

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
            // Development = Debug.Log 가 logcat 으로 나감(+프로파일러 연결). 개발 중 필수.
            options = dev ? (BuildOptions.Development | BuildOptions.AllowDebugging) : BuildOptions.None,
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
