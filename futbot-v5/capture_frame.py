import sys
import os
import time

sys.path.insert(0, "/home/raspi/futbot-v2/src")

from vision import HybridVisionService
import cv2

vision = HybridVisionService()

time.sleep(3)

for i in range(5):
    snap = vision.tick()
    ball = snap.get("ball")
    print("tick", i, "ball:", ball)

frame = vision.last_frame()
if frame is not None:
    out_dir = "/home/raspi/futbot-v2/src/output"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "capture.jpg")
    cv2.imwrite(out_path, frame)
    print("Saved:", out_path, "shape:", frame.shape)
else:
    print("No frame available")

vision.close()
