"""nails_seg 모델을 320² onnx로 재export (폰 속도 ~4배 목표). torch/ultralytics 사용(노트북).
결과: web/nails_seg_320.onnx  (640² 원본 web/nails_seg.onnx 는 그대로 둠)"""
import os
import shutil
from ultralytics import YOLO

ROOT = r"C:\Users\k1212\Desktop\TOY\nail_ar_mvp"
PT = os.path.join(ROOT, "models", "nails_seg_s_yolov8_v1.pt")

m = YOLO(PT)
out = m.export(format="onnx", imgsz=320, opset=12)   # 반환: 내보낸 onnx 경로
print("exported:", out)
dst = os.path.join(ROOT, "web", "nails_seg_320.onnx")
shutil.copy(out, dst)
print("copied ->", dst, os.path.getsize(dst), "bytes")
