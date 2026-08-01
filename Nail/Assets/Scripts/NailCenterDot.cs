// NailCenterDot.cs — 손톱 '정중앙에 점 하나'를 안경 화면(OST)에 찍는 최소 렌더러.
//
// 왜 별도 파일: 완성 디자인 오버레이(NailOverlayRenderer) 대신, 먼저 '중앙점'만 정확히 찍어보는
// 단계(형 요청 "일단 손톱 정중앙에 제대로 점부터"). 근거리 OST는 4m 시차로 픽셀 정합이 불가하나
// (docs/DEEP_RESEARCH_NEARFIELD_OST), '점 하나 대략 위치'는 시차에 훨씬 관대하다.
//
// 좌표 매핑은 NailOverlayRenderer.MapNormToLocal 과 100% 동일(같은 calib 써야 디자인과 어긋나지 않음).
// 점 스프라이트는 런타임 생성(에셋 불필요). 스무딩/hold로 깜빡임·튐 방지.
//
// 통합(Unity 열었을 때, 3단계):
//   1) 씬에서 카메라뷰 캔버스(디자인 오버레이와 같은 RectTransform) GameObject에 이 컴포넌트 추가.
//   2) cameraViewRect 에 그 RectTransform 지정 + rotQuadrant/mirror/calibOffset/calibScale 을
//      NailOverlayRenderer 와 동일 값으로 맞춤(컨트롤러가 둘 다 세팅하도록 1줄 추가).
//   3) 검출 콜백에서 overlay.SetResults(...) 옆에 centerDot.SetResults(res.nails, res.w, res.h) 호출.
//      켜고/끄기는 push_calib 새 필드(예: dot=1)로 NailARController 가 centerDot.show 토글.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

public class NailCenterDot : MonoBehaviour
{
    [Header("Refs (NailOverlayRenderer 와 동일하게)")]
    public RectTransform cameraViewRect;         // 좌표 공간(디자인 오버레이와 같은 것)
    public bool show = true;

    [Header("Dot")]
    public float dotPx = 22f;                    // 점 지름(display px)
    public Color dotColor = new Color(0.16f, 1f, 0.42f, 0.95f);   // 초록
    public bool ring = true;                     // 가운데 구멍(도넛) — 손톱 중앙이 가려지지 않게

    [Header("AR calibration (camera px -> 눈에 보이는 위치)")]
    public int rotQuadrant = 1;                  // 0/1/2/3 = 0/90/180/270 deg
    public Vector2 calibOffset = Vector2.zero;
    [Range(0.2f, 3f)] public float calibScale = 1f;
    public bool mirrorX = false, mirrorY = false;

    [Header("Stability")]
    public float smoothing = 12f;
    public float holdSec = 0.4f;

    class Entry { public Image img; public Vector2 pos; public float lastSeen = -999f; public bool placed; }
    private readonly Dictionary<string, Entry> m_Entries = new Dictionary<string, Entry>();
    private int m_ImgW = 1, m_ImgH = 1;
    private Sprite m_Dot;

    // NailOverlayRenderer.MapNormToLocal 과 동일한 매핑(같은 calib라야 디자인 중앙과 일치).
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

    public void SetResults(List<NailRoi> rois, int imgW, int imgH)
    {
        m_ImgW = Mathf.Max(1, imgW); m_ImgH = Mathf.Max(1, imgH);
        if (rois == null || rois.Count == 0) return;   // 비면 유지 → Update가 holdSec 후 숨김
        var size = cameraViewRect.rect.size;
        int q = ((rotQuadrant % 4) + 4) % 4;
        for (int i = 0; i < rois.Count; i++)
        {
            var r = rois[i];
            float nx = Mathf.Clamp01(r.cx / m_ImgW), ny = Mathf.Clamp01(r.cy / m_ImgH);
            var e = GetEntry(KeyFor(r, i));
            e.pos = MapNormToLocal(nx, ny, q, size) + calibOffset;
            e.lastSeen = Time.time;
        }
    }

    private static string KeyFor(NailRoi r, int i)
    {
        string k = r.Key;
        return (k == null || k == ":") ? ("#" + i) : k;
    }

    private Entry GetEntry(string key)
    {
        if (!m_Entries.TryGetValue(key, out var e))
        {
            var go = new GameObject("dot_" + key, typeof(RectTransform), typeof(Image));
            go.transform.SetParent(cameraViewRect, false);
            var img = go.GetComponent<Image>();
            img.raycastTarget = false;
            img.sprite = DotSprite();
            img.color = dotColor;
            e = new Entry { img = img };
            m_Entries.Add(key, e);
        }
        return e;
    }

    // 런타임 원형(또는 도넛) 스프라이트 생성 — 에셋 불필요.
    private Sprite DotSprite()
    {
        if (m_Dot != null) return m_Dot;
        const int S = 64;
        var tex = new Texture2D(S, S, TextureFormat.RGBA32, false) { filterMode = FilterMode.Bilinear };
        float cx = (S - 1) * 0.5f, cy = (S - 1) * 0.5f, rOut = S * 0.46f, rIn = ring ? S * 0.24f : -1f;
        var px = new Color32[S * S];
        for (int y = 0; y < S; y++)
            for (int x = 0; x < S; x++)
            {
                float d = Mathf.Sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy));
                float a = Mathf.Clamp01(rOut - d);                 // 바깥 경계 안티앨리어스
                if (rIn > 0f) a *= Mathf.Clamp01(d - rIn);          // 안쪽 구멍(도넛)
                px[y * S + x] = new Color32(255, 255, 255, (byte)(Mathf.Clamp01(a) * 255));
            }
        tex.SetPixels32(px); tex.Apply();
        m_Dot = Sprite.Create(tex, new Rect(0, 0, S, S), new Vector2(0.5f, 0.5f), 100f);
        return m_Dot;
    }

    void Update()
    {
        float k = 1f - Mathf.Exp(-smoothing * Time.deltaTime);
        foreach (var e in m_Entries.Values)
        {
            bool expired = !show || (Time.time - e.lastSeen) > holdSec;
            if (expired) { if (e.img.enabled) { e.img.enabled = false; e.placed = false; } continue; }
            e.img.enabled = true;
            e.img.color = dotColor;
            var rt = e.img.rectTransform;
            if (!e.placed) { rt.anchoredPosition = e.pos; rt.sizeDelta = new Vector2(dotPx, dotPx); e.placed = true; }
            rt.anchoredPosition = Vector2.Lerp(rt.anchoredPosition, e.pos, k);
            rt.sizeDelta = Vector2.Lerp(rt.sizeDelta, new Vector2(dotPx, dotPx), k);
        }
    }
}
