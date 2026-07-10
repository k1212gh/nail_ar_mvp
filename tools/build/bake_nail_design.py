#!/usr/bin/env python3
"""bake_nail_design.py — 프로파일 기반 손가락별 곡면 UV 텍스처 베이킹 (2단계).

"1회 측정 -> 베이킹 -> 런타임은 포즈만" 파이프라인의 2단계. edge_serve.py의 enroll이
기록한 nail_profile.json(손가락별 실측 mm)을 읽어, 평면 디자인을 각 손톱의
반원기둥(C커브) 전개면(arc-length UV)으로 리샘플해 굽는다. Unity의 NailMeshRenderer가
같은 curve 파라미터로 메쉬를 만들므로, 렌더 시 정면 투영이 원본 디자인과 일치한다.

수학: 단면 = 원호. 반폭 a, 새그 s=curve*폭 -> R=(a²+s²)/(2s), θ0=asin(a/R).
텍스처 u(호 균등) -> θ=(2u-1)θ0 -> 평면 디자인 x = 0.5 + R·sinθ/(2a) 에서 샘플.

사용:
  python tools/build/bake_nail_design.py [--profile nail_profile.json]
         [--design french|floral|dots] [--curve 0.22] [--out out/nail_bake] [--demo]
  --demo : 프로파일이 없어도 표준 치수로 10손가락 베이킹(측정 전 테스트용)
푸시 (스코프드 스토리지: mkdir 먼저, 디렉토리째 push는 거부됨):
  adb shell mkdir -p /sdcard/Android/data/com.DefaultCompany.Nail/files/nail_bake
  adb push out/nail_bake/. /sdcard/Android/data/com.DefaultCompany.Nail/files/nail_bake/
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import gen_nail_design as gen  # noqa: E402  (평면 디자인 드로잉 재사용)

TEXW = 256                     # 베이킹 텍스처 폭(호 방향). 높이는 실측 비율로.

# 측정 전 데모/폴백용 표준 치수(mm) — 성인 평균 근사
DEMO_MM = {"thumb": (14.0, 13.0), "index": (12.0, 10.0), "middle": (13.0, 10.5),
           "ring": (12.0, 9.5), "pinky": (9.5, 8.0)}


def flat_design(name: str) -> np.ndarray:
    """gen_nail_design과 같은 512x512 RGBA 평면 디자인 (행0=팁 .. 마지막 행=뿌리;
    french_tip이 이미지 상단을 칠한다 — Unity 텍스처 v=1이 이 상단 행)."""
    if name == "french":
        img = gen.gradient_base(gen._canvas())
        gen.french_tip(img)
    elif name == "floral":
        img = gen.gradient_base(gen._canvas(), c0=(210, 160, 235), c1=(250, 235, 255))
        gen.flower(img)
        gen.dots(img, n=3)
    elif name == "dots":
        img = gen.gradient_base(gen._canvas(), c0=(120, 90, 200), c1=(180, 140, 240))
        gen.dots(img)
    else:
        raise SystemExit(f"unknown design: {name}")
    gen.glossy(img)
    gen.nail_mask(img)
    return img


def bake_one(flat: np.ndarray, len_mm: float, wid_mm: float, curve: float) -> np.ndarray:
    """평면 디자인 -> 이 손톱의 전개면(arc-length) 텍스처."""
    S = flat.shape[0]
    texh = int(round(TEXW * max(0.6, min(2.5, len_mm / max(1e-3, wid_mm)))))
    a, s = 0.5, max(1e-4, curve)           # 단위 폭 기준 반폭/새그
    R = (a * a + s * s) / (2.0 * s)
    th0 = np.arcsin(min(1.0, a / R))
    u = (np.arange(TEXW, dtype=np.float32) + 0.5) / TEXW          # 호 균등
    x_flat = 0.5 + (R * np.sin((2.0 * u - 1.0) * th0)) / (2.0 * a)  # 정면 투영 x
    map_x = np.tile(x_flat * (S - 1), (texh, 1)).astype(np.float32)
    v = (np.arange(texh, dtype=np.float32) + 0.5) / texh
    map_y = np.tile((v * (S - 1))[:, None], (1, TEXW)).astype(np.float32)
    return cv2.remap(flat, map_x, map_y, cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=os.path.join(ROOT, "nail_profile.json"))
    ap.add_argument("--design", default="french", choices=["french", "floral", "dots"])
    ap.add_argument("--curve", type=float, default=0.22, help="새그/폭 비 (C커브 깊이)")
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "nail_bake"))
    ap.add_argument("--demo", action="store_true", help="프로파일 없이 표준 치수로 베이킹")
    args = ap.parse_args()

    if args.demo or not os.path.isfile(args.profile):
        if not args.demo:
            print(f"[bake] 프로파일 없음({args.profile}) -> --demo 치수 사용")
        nails = [{"hand": h, "finger": f, "lenMm": lw[0], "widMm": lw[1]}
                 for h in ("Left", "Right") for f, lw in DEMO_MM.items()]
    else:
        with open(args.profile, encoding="utf-8") as fp:
            nails = json.load(fp)["nails"]
        if not nails:
            raise SystemExit("[bake] 프로파일에 손가락이 없음 — enroll을 더 진행하세요")

    os.makedirs(args.out, exist_ok=True)
    flat = flat_design(args.design)
    manifest = {"version": 1, "design": args.design, "nails": []}
    for nd in nails:
        tex = bake_one(flat, nd["lenMm"], nd["widMm"], args.curve)
        name = f"bake_{nd['hand']}_{nd['finger']}.png"
        cv2.imwrite(os.path.join(args.out, name), tex)
        manifest["nails"].append({"hand": nd["hand"], "finger": nd["finger"],
                                  "lenMm": nd["lenMm"], "widMm": nd["widMm"],
                                  "curve": args.curve, "tex": name})
        print(f"[bake] {name}  {nd['lenMm']}x{nd['widMm']}mm  {tex.shape[1]}x{tex.shape[0]}px")
    with open(os.path.join(args.out, "nail_bake.json"), "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=1)
    print(f"[bake] manifest -> {os.path.join(args.out, 'nail_bake.json')}")
    print("[bake] push:  adb push", args.out,
          "/sdcard/Android/data/com.DefaultCompany.Nail/files/")


if __name__ == "__main__":
    main()
