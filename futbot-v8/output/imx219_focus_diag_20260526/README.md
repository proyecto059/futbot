# IMX219 Focus Diagnostic Crops

Captured from `raspi@raspi.local:/home/raspi/futbot-v2` with full-resolution `3280x2464` frames using `scripts/focus_camera.py --diag-grid`.

## Sets

- `sharp1_denoise_off/`: `--sharpness 1.0 --denoise off`
- `sharp4_denoise_off/`: `--sharpness 4.0 --denoise off`

Each set contains:

- `full.png`
- `center_640.png`
- `center_1024.png`
- `corner_tl.png`
- `corner_tr.png`
- `corner_bl.png`
- `corner_br.png`
- `metrics.json`

## Result

The center crops remain visually blurry even at full sensor resolution. Higher sharpness increases the numeric Laplacian score but does not recover real edges/details, which points to optical focus/lens/protector/smudge rather than only software scaling.

Use these crops to compare after physically adjusting/cleaning the lens.
