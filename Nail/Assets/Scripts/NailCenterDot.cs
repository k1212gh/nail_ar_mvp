// NailCenterDot.cs — 손톱 중앙에 '십자선(crosshair)'을 그려 그리기 시작점/축을 안내한다.
//
// 완성 디자인 대신, 손톱의 중심 + 장축/단축을 보여주는 십자를 얹어(형 요청) 붓질 기준을 준다.
// 근거리 OST 대신 매직미러(피드) 위에 그리면 시차 문제 없이 손톱에 정확히 붙는다.
//
// 좌표/방향 매핑은 NailOverlayRenderer 와 동일(같은 calib라야 어긋나지 않음): 손톱 center 와
// tip(center+axis*len/2)을 같은 파이프라인으로 매핑해 base->tip 방향으로 십자를 회전시킨다.
// 크기는 손톱 len×wid 에 맞춰 십자가 손톱을 가로지른다. 스프라이트는 런타임 생성(에셋 불필요).
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

public class NailCenterDot : MonoBehaviour
{
    [Header("Refs (NailOverlayRenderer 와 동일하게)")]
    public RectTransform cameraViewRect;
    public bool show = true;

    [Header("Crosshair")]
    public Color color = new Color(0.16f, 1f, 0.42f, 0.95f);   // 초록
    [Range(0.4f, 1.5f)] public float sizeScale = 1.0f;         // 손톱 대비 십자 길이 배율
    public float minPx = 26f;                                  // 너무 작지 않게 하한

    [Header("AR calibration (NailOverlayRenderer 와 같은 값)")]
    public int rotQuadrant = 1;
    public Vector2 calibOffset = Vector2.zero;
    [Range(0.2f, 3f)] public float calibScale = 1f;
    public bool mirrorX = false, mirrorY = false;

    [Header("Stability")]
    public float smoothing = 12f;
    public float holdSec = 0.4f;

    class Entry { public Image img; public Vector2 pos, size; public float rot; public bool hasRot; public float lastSeen = -999f; public bool placed; }

    [Header("Rotation stability")]
    [Tooltip("장축/단축 비가 이 미만이면 방향 애매 → 회전 고정(둥근 손톱 지터 방지)")]
    public float elongMin = 1.25f;
    [Tooltip("이 각도(deg) 미만 변화는 무시(가만히 있을 때 미세 지터 제거). 손 돌리면 이보다 크게 변해 따라감")]
    public float rotDeadzoneDeg = 7f;
    private readonly Dictionary<string, Entry> m_Entries = new Dictionary<string, Entry>();
    private int m_ImgW = 1, m_ImgH = 1;
    private Sprite m_Cross;

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
        if (rois == null || rois.Count == 0) return;
        var size = cameraViewRect.rect.size;
        int q = ((rotQuadrant % 4) + 4) % 4;
        for (int i = 0; i < rois.Count; i++)
        {
            var r = rois[i];
            float nx = Mathf.Clamp01(r.cx / m_ImgW), ny = Mathf.Clamp01(r.cy / m_ImgH);
            Vector2 center = MapNormToLocal(nx, ny, q, size);
            // 장축(base->tip) 방향 — 십자 회전에 사용
            float tnx = Mathf.Clamp01((r.cx + r.ex * r.len * 0.5f) / m_ImgW);
            float tny = Mathf.Clamp01((r.cy + r.ey * r.len * 0.5f) / m_ImgH);
            Vector2 axis = MapNormToLocal(tnx, tny, q, size) - center;
            float deg = (axis.sqrMagnitude > 1e-4f) ? Mathf.Atan2(-axis.x, axis.y) * Mathf.Rad2Deg : 0f;
            // 십자 크기 = 손톱 wid×len (축 스왑은 90/270에서)
            float w = Mathf.Max(minPx, (r.wid / m_ImgW) * size.x * calibScale * sizeScale);
            float h = Mathf.Max(minPx, (r.len / m_ImgH) * size.y * calibScale * sizeScale);
            if (q == 1 || q == 3) { var t = w; w = h; h = t; }
            var e = GetEntry(KeyFor(r, i));
            // --- 회전 안정화: 손 돌리면 따라가되, 가만히 있을 때 지터/스핀 제거 ---
            float elong = Mathf.Max(r.len, r.wid) / Mathf.Max(1f, Mathf.Min(r.len, r.wid));
            float stableDeg;
            if (elong < elongMin)
            {
                stableDeg = e.hasRot ? e.rot : 0f;            // 둥근 손톱=방향 애매 → 이전 유지(안 돎)
            }
            else if (!e.hasRot)
            {
                stableDeg = deg;                               // 첫 프레임
            }
            else
            {
                float d = Mathf.DeltaAngle(e.rot, deg);
                if (Mathf.Abs(d) > 90f) { deg += 180f; d = Mathf.DeltaAngle(e.rot, deg); }  // 180° 뒤집힘 해소
                stableDeg = (Mathf.Abs(d) < rotDeadzoneDeg) ? e.rot : deg;                   // 데드존: 미세변화 무시
            }
            e.pos = center + calibOffset; e.size = new Vector2(w, h);
            e.rot = stableDeg; e.hasRot = true;
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
            var go = new GameObject("cross_" + key, typeof(RectTransform), typeof(Image));
            go.transform.SetParent(cameraViewRect, false);
            var img = go.GetComponent<Image>();
            img.raycastTarget = false;
            img.sprite = CrossSprite();
            img.color = color;
            e = new Entry { img = img };
            m_Entries.Add(key, e);
        }
        return e;
    }

    // 런타임 '+' 스프라이트(가로/세로 얇은 바). 손톱 크기로 늘려 십자가 손톱을 가로지른다.
    private Sprite CrossSprite()
    {
        if (m_Cross != null) return m_Cross;
        const int S = 64; const int half = 3;   // 바 두께 = 2*half
        var tex = new Texture2D(S, S, TextureFormat.RGBA32, false) { filterMode = FilterMode.Bilinear };
        int c = S / 2;
        var px = new Color32[S * S];
        for (int y = 0; y < S; y++)
            for (int x = 0; x < S; x++)
            {
                bool onBar = (Mathf.Abs(x - c) <= half) || (Mathf.Abs(y - c) <= half);
                byte a = 0;
                if (onBar)
                {
                    // 중심에서 멀수록 살짝 페이드(끝을 부드럽게)
                    float d = Mathf.Max(Mathf.Abs(x - c), Mathf.Abs(y - c)) / (float)c;
                    a = (byte)(Mathf.Clamp01(1f - 0.15f * d) * 255);
                }
                px[y * S + x] = new Color32(255, 255, 255, a);
            }
        tex.SetPixels32(px); tex.Apply();
        m_Cross = Sprite.Create(tex, new Rect(0, 0, S, S), new Vector2(0.5f, 0.5f), 100f);
        return m_Cross;
    }

    void Update()
    {
        float k = 1f - Mathf.Exp(-smoothing * Time.deltaTime);
        foreach (var e in m_Entries.Values)
        {
            bool expired = !show || (Time.time - e.lastSeen) > holdSec;
            if (expired) { if (e.img.enabled) { e.img.enabled = false; e.placed = false; } continue; }
            e.img.enabled = true;
            e.img.color = color;
            var rt = e.img.rectTransform;
            if (!e.placed) { rt.anchoredPosition = e.pos; rt.sizeDelta = e.size; rt.localRotation = Quaternion.Euler(0, 0, e.rot); e.placed = true; }
            rt.anchoredPosition = Vector2.Lerp(rt.anchoredPosition, e.pos, k);
            rt.sizeDelta = Vector2.Lerp(rt.sizeDelta, e.size, k);
            rt.localRotation = Quaternion.Slerp(rt.localRotation, Quaternion.Euler(0, 0, e.rot), k);
        }
    }
}
