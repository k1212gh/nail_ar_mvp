"""nails_seg.onnx INT8 정적 양자화 — 640² 정확도 유지하며 가속 목표.
캘리브레이션은 안경 실캡처 프레임 사용(전처리는 onnx_infer letterbox와 동일).

사용: python tools/onnx_edge/quantize_int8.py --frames <폴더> [--src web/nails_seg.onnx] [--out web/nails_seg_int8.onnx]
"""
import argparse
import glob
import os

import cv2
import numpy as np
from onnxruntime.quantization import (CalibrationDataReader, QuantFormat, QuantType,
                                      quantize_static)
from onnxruntime.quantization.shape_inference import quant_pre_process

S = 640


def letterbox(im):
    h, w = im.shape[:2]
    r = min(S / w, S / h)
    nw, nh = round(w * r), round(h * r)
    px, py = (S - nw) // 2, (S - nh) // 2
    c = np.full((S, S, 3), 114, np.uint8)
    c[py:py + nh, px:px + nw] = cv2.resize(im, (nw, nh))
    return np.ascontiguousarray(np.transpose(c[:, :, ::-1].astype(np.float32) / 255.0, (2, 0, 1))[None])


class Reader(CalibrationDataReader):
    def __init__(self, files, inp):
        self.files = files
        self.inp = inp
        self.i = 0

    def get_next(self):
        while self.i < len(self.files):
            im = cv2.imread(self.files[self.i])
            self.i += 1
            if im is not None:
                return {self.inp: letterbox(im)}
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--src", default=os.path.join("web", "nails_seg.onnx"))
    ap.add_argument("--out", default=os.path.join("web", "nails_seg_int8.onnx"))
    ap.add_argument("--n", type=int, default=80, help="캘리브레이션 프레임 수")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.frames, "raw_1*.jpg")))[:a.n]  # 손 있는 프레임(100~)
    if not files:
        files = sorted(glob.glob(os.path.join(a.frames, "*.jpg")))[:a.n]
    print("calib frames:", len(files))

    prep = a.src.replace(".onnx", "_prep.onnx")
    print("pre-process(shape inference)…")
    quant_pre_process(a.src, prep)

    import onnxruntime as ort
    inp = ort.InferenceSession(prep, providers=["CPUExecutionProvider"]).get_inputs()[0].name
    print("input:", inp, "— quantize_static (QDQ, per-channel, int8)…")
    quantize_static(prep, a.out, Reader(files, inp),
                    quant_format=QuantFormat.QDQ, per_channel=True,
                    weight_type=QuantType.QInt8, activation_type=QuantType.QInt8)
    try:
        os.remove(prep)
    except OSError:
        pass
    print("quantized ->", a.out, os.path.getsize(a.out), "bytes",
          f"({os.path.getsize(a.out)/os.path.getsize(a.src)*100:.0f}% of fp32)")


if __name__ == "__main__":
    main()
