#!/usr/bin/env python3
import subprocess
import time

def main():
    gst_cmd = [
        "gst-launch-1.0", 
        "v4l2src", "device=/dev/video0", "num-buffers=1",
        "!", "videoconvert",
        "!", "jpegenc",
        "!", "filesink", "location=captured_image.jpg"
    ]
    result = subprocess.run(gst_cmd, capture_output=True, timeout=15)
    print('Image saved as captured_image.jpg')

if __name__ == '__main__':
    main()