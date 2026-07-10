// NailBakedGloss.shader — baked nail texture + view-space specular sweep.
// Lives in Resources/ so Resources.Load<Shader> works in player builds without
// scene references (NailMeshRenderer creates its materials at runtime).
// Gloss uses the VIEW-SPACE normal, so the highlight sweeps across the curved
// nail as the hand (or head) tilts — the "living gel nail" effect.
Shader "NailAR/BakedGloss"
{
    Properties
    {
        _MainTex ("Baked Nail Texture", 2D) = "white" {}
        _Ambient ("Ambient", Range(0, 2)) = 1.0
        _GlossStrength ("Gloss Strength", Range(0, 3)) = 0.9
        _GlossPower ("Gloss Power", Range(2, 128)) = 28
        _LightDir ("View-space Light Dir", Vector) = (0.35, 0.55, 0.75, 0)
        _Alpha ("Overall Alpha", Range(0, 1)) = 1.0
    }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" "IgnoreProjector"="True" }
        Blend SrcAlpha OneMinusSrcAlpha
        ZWrite Off
        Cull Off        // parent canvas may mirror-scale (negative y) -> winding flips

        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"

            sampler2D _MainTex;
            float4 _MainTex_ST;
            half _Ambient, _GlossStrength, _GlossPower, _Alpha;
            half4 _LightDir;

            struct appdata
            {
                float4 vertex : POSITION;
                float3 normal : NORMAL;
                float2 uv : TEXCOORD0;
            };
            struct v2f
            {
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 nView : TEXCOORD1;
            };

            v2f vert(appdata v)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                o.nView = mul((float3x3)UNITY_MATRIX_IT_MV, v.normal);
                return o;
            }

            fixed4 frag(v2f i) : SV_Target
            {
                fixed4 c = tex2D(_MainTex, i.uv);
                half3 n = normalize(i.nView);
                if (n.z < 0) n = -n;               // camera-facing side (bulge sign agnostic)
                half3 L = normalize(_LightDir.xyz);
                half3 V = half3(0, 0, 1);          // view space: surface->camera = +z
                half3 H = normalize(L + V);
                half spec = pow(saturate(dot(n, H)), _GlossPower) * _GlossStrength;
                c.rgb = c.rgb * _Ambient + spec;
                c.a *= _Alpha;
                return c;
            }
            ENDCG
        }
    }
}
