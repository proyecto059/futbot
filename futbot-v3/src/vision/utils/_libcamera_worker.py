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

import mmap
import os
import select
import struct
import sys
import time

import libcamera as lc

MAGIC = b"\xf8\xb4\xc2\x0d"
HEADER_FMT = "<4sIIII"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


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


def _process_command(cmd: str, cam) -> None:
    if cmd is None or cmd == "":
        return
    if cmd == "QUIT":
        raise SystemExit(0)
    if cmd.startswith("EXPOSURE "):
        value_us = int(cmd.split()[1])
        try:
            ctrls = lc.ControlList()
            ctrls.set(lc.controls.AeEnable, False)
            ctrls.set(lc.controls.ExposureTime, value_us)
            cam.controls.set(controls=ctrls)
        except Exception:
            pass
    elif cmd.startswith("AE "):
        enable = cmd.split()[1] == "1"
        try:
            ctrls = lc.ControlList()
            ctrls.set(lc.controls.AeEnable, enable)
            cam.controls.set(controls=ctrls)
        except Exception:
            pass


def main() -> None:
    width = int(sys.argv[1]) if len(sys.argv) > 1 else 320
    height = int(sys.argv[2]) if len(sys.argv) > 2 else 240
    warmup = int(sys.argv[3]) if len(sys.argv) > 3 else 10

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
        cam.queue_request(req)

    for _ in range(warmup):
        deadline = time.time() + 2.0
        while time.time() < deadline:
            ready = cm.get_ready_requests()
            if ready:
                for r in ready:
                    r.reuse()
                    cam.queue_request(r)
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
            req.reuse()
            cam.queue_request(req)
            continue
        fb = req.buffers.get(stream)
        if fb is None:
            req.reuse()
            cam.queue_request(req)
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
        req.reuse()
        cam.queue_request(req)
        ae_settle += 1
        if brightness > 15:
            break

    for _ in range(warmup):
        ready = cm.get_ready_requests()
        if ready:
            for r in ready:
                r.reuse()
                cam.queue_request(r)

    sys.stderr.write(f"READY {w} {h} {stride}\n")
    sys.stderr.flush()

    try:
        while True:
            cmd = _read_command(timeout_s=0.0)
            if cmd is not None:
                _process_command(cmd, cam)

            ready = cm.get_ready_requests()
            if not ready:
                time.sleep(0.001)
                continue

            for req in ready:
                if req.status != lc.Request.Status.Complete:
                    req.reuse()
                    cam.queue_request(req)
                    continue

                fb = req.buffers.get(stream)
                if fb is None:
                    req.reuse()
                    cam.queue_request(req)
                    continue

                try:
                    fd = fb.planes[0].fd
                    length = fb.planes[0].length
                    mm = mmap.mmap(fd, length)
                    payload = mm[:frame_size]
                    _send_xrgb(w, h, stride, payload)
                    mm.close()
                except Exception:
                    req.reuse()
                    cam.queue_request(req)
                    continue

                req.reuse()
                cam.queue_request(req)
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
