#!/usr/bin/env python3
"""Standalone libcamera capture worker — runs under the system Python.

Launched as a subprocess by ``_LibcameraCap``.  Only depends on ``libcamera``
(system package).  Does NOT require cv2 or numpy — sends raw XRGB8888 frames
and the parent process handles conversion to BGR.

Protocol (stdout — binary, little-endian):
    FRAME header:  b'\\xf8\\xb4\\xc2\\x0d' (4 bytes magic)
                   + width   (4 bytes uint32)
                   + height  (4 bytes uint32)
                   + stride  (4 bytes uint32)  — row pitch in bytes
                   + size    (4 bytes uint32)  — payload size
                   + <size> bytes of raw XRGB8888 data

Protocol (stdin — text, newline-delimited commands):
    EXPOSURE <int>\n   — set manual exposure (µs)
    AE <0|1>\n         — disable/enable auto-exposure
    QUIT\n             — clean shutdown

Usage (internal):
    /usr/bin/python3 _libcamera_worker.py <width> <height> [warmup_frames]
"""

import argparse
import mmap
import os
import select
import struct
import sys
import time

MAGIC = b"\xf8\xb4\xc2\x0d"
HEADER_FMT = "<4sIIII"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

NOISE_REDUCTION_MODES = {
    "off": ("Off", 0),
    "fast": ("Fast", 1),
    "high_quality": ("HighQuality", 2),
    "minimal": ("Minimal", 3),
    "zsl": ("Zsl", 4),
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("width", type=int, nargs="?", default=320)
    parser.add_argument("height", type=int, nargs="?", default=240)
    parser.add_argument("warmup_frames", type=int, nargs="?", default=10)
    parser.add_argument("--sharpness", type=float, default=None)
    parser.add_argument(
        "--denoise",
        choices=tuple(NOISE_REDUCTION_MODES),
        default=None,
    )
    parser.add_argument("--exposure-us", type=int, default=None)
    parser.add_argument("--gain", type=float, default=None)
    return parser


def _send_xrgb(w: int, h: int, stride: int, data: bytes) -> None:
    header = struct.pack(HEADER_FMT, MAGIC, w, h, stride, len(data))
    os.write(sys.stdout.fileno(), header + data)


def _read_command(timeout_s: float = 0.0):
    fd = sys.stdin.fileno()
    ready, _, _ = select.select([fd], [], [], timeout_s)
    if not ready:
        return None
    line = b""
    while True:
        ch = os.read(fd, 1)
        if not ch:
            return "QUIT"
        if ch == b"\n":
            break
        line += ch
    return line.decode("ascii", errors="ignore").strip()


def _resolve_noise_reduction_mode(lc, mode: str):
    enum_name, fallback = NOISE_REDUCTION_MODES[mode]
    enum = getattr(lc.controls.draft, "NoiseReductionModeEnum", None)
    if enum is not None and hasattr(enum, enum_name):
        return getattr(enum, enum_name)
    return fallback


def _build_startup_controls(lc, args) -> dict:
    controls = {}
    if args.sharpness is not None:
        controls[lc.controls.Sharpness] = float(args.sharpness)
    if args.denoise is not None:
        controls[lc.controls.draft.NoiseReductionMode] = _resolve_noise_reduction_mode(
            lc,
            args.denoise,
        )
    if args.exposure_us is not None:
        controls[lc.controls.AeEnable] = False
        controls[lc.controls.ExposureTime] = int(args.exposure_us)
    if args.gain is not None:
        controls[lc.controls.AnalogueGain] = float(args.gain)
    return controls


def _apply_controls_to_request(req, controls: dict) -> None:
    for control_id, value in controls.items():
        req.set_control(control_id, value)


def _reuse_and_queue(cam, req, controls: dict) -> None:
    req.reuse()
    _apply_controls_to_request(req, controls)
    cam.queue_request(req)


def _process_command(cmd: str, controls: dict, lc) -> None:
    if cmd is None or cmd == "":
        return
    if cmd == "QUIT":
        raise SystemExit(0)
    if cmd.startswith("EXPOSURE "):
        value_us = int(cmd.split()[1])
        controls[lc.controls.AeEnable] = False
        controls[lc.controls.ExposureTime] = value_us
    elif cmd.startswith("AE "):
        enable = cmd.split()[1] == "1"
        controls[lc.controls.AeEnable] = enable


def main() -> None:
    args = build_arg_parser().parse_args()
    width = args.width
    height = args.height
    warmup = args.warmup_frames

    import libcamera as lc

    cm = lc.CameraManager.singleton()
    if not cm.cameras:
        sys.stderr.write("libcamera: no cameras found\n")
        sys.exit(1)

    cam = cm.cameras[0]
    cam.acquire()

    cfg = cam.generate_configuration([lc.StreamRole.Viewfinder])
    sc = cfg.at(0)
    sc.size = lc.Size(width, height)
    sc.pixel_format = lc.formats.XRGB8888
    cfg.validate()
    cam.configure(cfg)
    runtime_controls = _build_startup_controls(lc, args)

    w, h = sc.size.width, sc.size.height
    stride = sc.stride
    frame_size = sc.frame_size

    stream = cfg.at(0).stream
    alloc = lc.FrameBufferAllocator(cam)
    alloc.allocate(stream)
    bufs = alloc.buffers(stream)

    cam.start()

    for b in bufs:
        req = cam.create_request()
        req.add_buffer(stream, b)
        _apply_controls_to_request(req, runtime_controls)
        cam.queue_request(req)

    for _ in range(warmup):
        deadline = time.time() + 2.0
        while time.time() < deadline:
            ready = cm.get_ready_requests()
            if ready:
                for r in ready:
                    _reuse_and_queue(cam, r, runtime_controls)
                break
            time.sleep(0.005)

    ae_settle = 0
    ae_limit = 30
    while ae_settle < ae_limit:
        deadline = time.time() + 2.0
        req = None
        while time.time() < deadline:
            ready = cm.get_ready_requests()
            if ready:
                req = ready[0]
                break
            time.sleep(0.005)
        if req is None:
            break
        if req.status != lc.Request.Status.Complete:
            _reuse_and_queue(cam, req, runtime_controls)
            continue
        fb = req.buffers.get(stream)
        if fb is None:
            _reuse_and_queue(cam, req, runtime_controls)
            continue
        try:
            fd = fb.planes[0].fd
            length = fb.planes[0].length
            mm = mmap.mmap(fd, length)
            payload = mm[:frame_size]
            brightness = sum(payload[::64]) / max(1, len(payload[::64]))
            mm.close()
        except Exception:
            brightness = 0
        _reuse_and_queue(cam, req, runtime_controls)
        ae_settle += 1
        if brightness > 15:
            break

    for _ in range(warmup):
        ready = cm.get_ready_requests()
        if ready:
            for r in ready:
                _reuse_and_queue(cam, r, runtime_controls)

    sys.stderr.write(f"READY {w} {h} {stride}\n")
    sys.stderr.flush()

    try:
        while True:
            cmd = _read_command(timeout_s=0.0)
            if cmd is not None:
                _process_command(cmd, runtime_controls, lc)

            ready = cm.get_ready_requests()
            if not ready:
                time.sleep(0.001)
                continue

            for req in ready:
                if req.status != lc.Request.Status.Complete:
                    _reuse_and_queue(cam, req, runtime_controls)
                    continue

                fb = req.buffers.get(stream)
                if fb is None:
                    _reuse_and_queue(cam, req, runtime_controls)
                    continue

                try:
                    fd = fb.planes[0].fd
                    length = fb.planes[0].length
                    mm = mmap.mmap(fd, length)
                    payload = mm[:frame_size]
                    _send_xrgb(w, h, stride, payload)
                    mm.close()
                except Exception:
                    _reuse_and_queue(cam, req, runtime_controls)
                    continue

                _reuse_and_queue(cam, req, runtime_controls)
                break

    except (SystemExit, KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        try:
            cam.stop()
            cam.release()
        except Exception:
            pass
        try:
            del alloc
        except Exception:
            pass
        try:
            del cm
        except Exception:
            pass


if __name__ == "__main__":
    main()
