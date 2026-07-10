#!/usr/bin/env python3
"""gen_nail_design.py — make transparent nail-design PNGs for the AR overlay.

Produces square RGBA PNGs (design occupies the frame; v=0 root .. v=1 tip, matching
the app's overlay convention). Not a photo — a vector-ish design the app warps onto
the nail. Options: french tip, gradient base, floral accents.

Usage: python gen_nail_design.py OUTDIR
"""
import sys, os
import numpy as np
import cv2

S = 512  # texture size


def _canvas():
    return np.zeros((S, S, 4), np.uint8)


def gradient_base(img, c0=(230, 180, 200), c1=(255, 245, 250)):
    # vertical gradient root(c0)->tip(c1); BGR
    for y in range(S):
        t = y / (S - 1)
        col = [int(c0[i] * (1 - t) + c1[i] * t) for i in range(3)]
        img[y, :, :3] = col
    img[:, :, 3] = 255
    return img


def french_tip(img, frac=0.30, color=(255, 255, 255)):
    # clean crescent 'smile line' at the tip. Fill above a downward ellipse arc.
    h = int(S * frac)
    tip = img.copy()
    tip[:, :, :3] = color
    tip[:, :, 3] = 255
    mask = np.zeros((S, S), np.uint8)
    # white region = everything above the smile arc (ellipse centered below the line)
    cv2.ellipse(mask, (S // 2, h + int(h * 0.15)), (int(S * 0.55), int(h * 0.9)),
                0, 180, 360, 255, -1)
    mask[:h // 3, :] = 255                         # solid very tip
    mask = cv2.GaussianBlur(mask, (0, 0), 3)
    a = (mask.astype(np.float32) / 255.0)[..., None]
    img[:] = (tip.astype(np.float32) * a + img.astype(np.float32) * (1 - a)).astype(np.uint8)
    return img


def glossy(img):
    """Soft off-center highlight streak -> shiny 3D nail look."""
    gl = np.zeros((S, S), np.float32)
    cv2.ellipse(gl, (int(S * 0.40), int(S * 0.38)), (int(S * 0.06), int(S * 0.30)),
                12, 0, 360, 1.0, -1)
    gl = cv2.GaussianBlur(gl, (0, 0), S * 0.035) * 0.33
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c].astype(np.float32) + gl * 255, 0, 255).astype(np.uint8)
    return img


def dots(img, color=(180, 60, 120), n=5):
    rng = [(0.5, 0.5), (0.32, 0.62), (0.68, 0.62), (0.4, 0.78), (0.6, 0.78)]
    for (u, v) in rng[:n]:
        cv2.circle(img, (int(u * S), int(v * S)), int(S * 0.03), (*color, 255), -1)
    return img


def flower(img, cx=0.5, cy=0.66, color=(80, 40, 200)):
    c = (int(cx * S), int(cy * S))
    r = int(S * 0.06)
    for a in range(0, 360, 72):
        rad = np.deg2rad(a)
        p = (int(c[0] + r * np.cos(rad)), int(c[1] + r * np.sin(rad)))
        cv2.circle(img, p, int(r * 0.7), (*color, 255), -1)
    cv2.circle(img, c, int(r * 0.5), (60, 220, 255, 255), -1)  # yellow center
    return img


def nail_mask(img):
    """Clip the design alpha to a nail shape (rounded top 'tip', softer edges),
    so the overlay reads as a painted nail rather than a rectangle."""
    m = np.zeros((S, S), np.float32)
    # vertical ellipse filling most of the frame = nail plate
    cv2.ellipse(m, (S // 2, int(S * 0.52)), (int(S * 0.42), int(S * 0.50)),
                0, 0, 360, 1.0, -1)
    m = cv2.GaussianBlur(m, (0, 0), S * 0.02)          # soft edge
    a = img[:, :, 3].astype(np.float32) * m
    img[:, :, 3] = np.clip(a, 0, 255).astype(np.uint8)
    return img


def save(img, path):
    glossy(img)
    nail_mask(img)
    cv2.imwrite(path, img)
    print("wrote", path, os.path.getsize(path), "bytes")


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    # 1) french + gradient (classic)
    a = gradient_base(_canvas())
    french_tip(a)
    save(a, os.path.join(out, "design_french.png"))
    # 2) gradient + floral accent
    b = gradient_base(_canvas(), c0=(210, 160, 235), c1=(250, 235, 255))
    flower(b); dots(b, n=3)
    save(b, os.path.join(out, "design_floral.png"))
    # 3) simple solid + dots
    c = gradient_base(_canvas(), c0=(120, 90, 200), c1=(180, 140, 240))
    dots(c)
    save(c, os.path.join(out, "design_dots.png"))


if __name__ == "__main__":
    main()
