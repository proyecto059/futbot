# Raspberry Pi 3 deployment and performance guide

This is a practical runbook for deploying `futbot` on Raspberry Pi 3 and tuning runtime behavior.

## Runtime env vars and tuning knobs

### Detection backend and thresholds

- `DETECTOR_BACKEND=hsv|bgr` (default: `hsv`)
- `BGR_R_MIN` (default: `120`)
- `BGR_G_MIN` (default: `55`)
- `BGR_B_MAX` (default: `140`)
- `BGR_RG_DELTA_MIN` (default: `25`)
- `BGR_RB_DELTA_MIN` (default: `45`)
- `BGR_GB_DELTA_MIN` (default: `5`)
- `VISION_FUSED=true|false` (default: `false`, experimental fused BGR path)

### Kernel validation safety checks

- `VISION_VALIDATE_KERNEL=true|false` (default: `false`)
- `VISION_VALIDATE_MISMATCH_THRESHOLD=<float>` (default: `0.03`)

When validation is enabled, SIMD output is compared against scalar output and falls back if mismatch exceeds threshold.

### AI scheduling knobs

- `AI_STRIDE=<n>` (default: `1`, clamped to minimum `1`)
  - `1` = submit every frame
  - `2` = submit every 2nd frame (lower CPU load)
- `AI_USE_ROI=true|false` (default: `false`)
  - Uses local crop submission when tracking is stable.

### Logging examples

- Info-level operational logs:

```bash
RUST_LOG=info ./target/release/futbot
```

- Debug-level detector/AI detail:

```bash
RUST_LOG=debug ./target/release/futbot
```

## RPi3 deploy checklist (ONNX Runtime shared library)

1. Build with AI enabled:

```bash
cargo build --release --features ai
```

2. Install `libonnxruntime.so` into a system library path on the Pi (for example `/usr/local/lib` or distro lib path).
3. Refresh linker cache:

```bash
sudo ldconfig
```

4. Verify the library is visible system-wide:

```bash
ldconfig -p | rg onnxruntime
```

5. Verify your binary resolves ONNX Runtime:

```bash
ldd ./target/release/futbot | rg onnxruntime
```

If steps 2-5 succeed, you do not need `ORT_DYLIB_PATH`.

Use `ORT_DYLIB_PATH=/absolute/path/libonnxruntime.so` only when running with a non-system install location.

## Recommended run profiles

### 1) Stable competition mode

Use this for predictable match behavior and conservative CPU usage.

```bash
RUST_LOG=info \
DETECTOR_BACKEND=hsv \
AI_STRIDE=2 \
AI_USE_ROI=true \
VISION_VALIDATE_KERNEL=false \
./target/release/futbot
```

### 2) Profiling mode

Use this to inspect timing and detector/AI behavior.

```bash
RUST_LOG=debug \
DETECTOR_BACKEND=hsv \
AI_STRIDE=1 \
AI_USE_ROI=false \
VISION_VALIDATE_KERNEL=true \
VISION_VALIDATE_MISMATCH_THRESHOLD=0.03 \
./target/release/futbot --ui
```

### 3) Experimental mode (BGR + fused)

Use this only when actively tuning BGR thresholds.

```bash
RUST_LOG=debug \
DETECTOR_BACKEND=bgr \
VISION_FUSED=true \
BGR_R_MIN=120 \
BGR_G_MIN=55 \
BGR_B_MAX=140 \
BGR_RG_DELTA_MIN=25 \
BGR_RB_DELTA_MIN=45 \
BGR_GB_DELTA_MIN=5 \
AI_STRIDE=2 \
AI_USE_ROI=true \
./target/release/futbot --ui
```

## Troubleshooting

### No AI logs / no AI detections

- Confirm build used `--features ai`.
- Confirm `model.onnx` exists in working directory.
- Run with `RUST_LOG=debug` and check for `[AI]` startup/load warnings.
- Check runtime linking with `ldd ./target/release/futbot | rg onnxruntime`.
- If linker cannot resolve, set `ORT_DYLIB_PATH` to full `.so` path or install system-wide and run `ldconfig`.

### Oversized AI boxes

- Usually caused by model mismatch or incorrect output interpretation.
- Verify model input/output format matches expected YOLO output.
- Temporarily run `AI_USE_ROI=false` to rule out ROI mapping side effects.
- Keep `RUST_LOG=debug` and inspect repeated `[ai] ball @ ... w=... h=...` values.

### Stale AI (old detections persist)

- Increase freshness by lowering `AI_STRIDE` (for example `2 -> 1`).
- Disable ROI temporarily (`AI_USE_ROI=false`) if the object exits local crop too often.
- Confirm camera feed is live and main loop FPS is healthy in `[main]` logs.

### Performance drops on RPi3

- Start from stable profile (`AI_STRIDE=2`, `AI_USE_ROI=true`, `RUST_LOG=info`).
- Disable validation in production (`VISION_VALIDATE_KERNEL=false`).
- Avoid `--ui` during matches.
- If experimenting with BGR path, compare `VISION_FUSED=false` vs `true`; keep whichever gives stable FPS.
