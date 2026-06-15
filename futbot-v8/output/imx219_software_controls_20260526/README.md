# IMX219 Software Controls Capture

Captured from `raspi@raspi.local:/home/raspi/futbot-v2` using `scripts/focus_camera.py` after adding libcamera startup controls.

| File | Settings | Best sharpness |
| --- | --- | ---: |
| `01_320x240_default.png` | 320x240 default | 19.38 |
| `02_640x480_default.png` | 640x480 default | 9.23 |
| `03_640x480_sharp2_denoise_off.png` | 640x480, sharpness 2.0, denoise off | 15.14 |
| `04_640x480_sharp4_denoise_off.png` | 640x480, sharpness 4.0, denoise off | 26.83 |
| `05_640x480_short_exp_gain2.png` | 640x480, sharpness 2.0, denoise off, exposure 8000us, gain 2.0 | 9.87 |
| `06_1640x1232_sharp2_denoise_off.png` | 1640x1232, sharpness 2.0, denoise off | 15.98 |
| `07_320x240_sharp4_denoise_off.png` | 320x240, sharpness 4.0, denoise off | 73.91 |
| `08_1640x1232_sharp4_denoise_off.png` | 1640x1232, sharpness 4.0, denoise off | 29.59 |
| `09_3280x2464_sharp4_denoise_off.png` | 3280x2464, sharpness 4.0, denoise off | 562.47 |
| `10_3280x2464_default.png` | 3280x2464 default | 31.14 |

The full-resolution sharpness result shows the sensor/lens can produce much sharper images than the low-resolution capture path.
