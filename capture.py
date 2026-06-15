#!/usr/bin/env python3
import libcamera as lc
import mmap
import os
import time
import argparse
import numpy as np
from PIL import Image


def capture(output, width, height, warmup, quality):
    cm = lc.CameraManager.singleton()
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

    alloc = lc.FrameBufferAllocator(cam)
    stream = cfg.at(0).stream
    alloc.allocate(stream)
    bufs = alloc.buffers(stream)

    cam.start()

    for b in bufs:
        req = cam.create_request()
        req.add_buffer(stream, b)
        cam.queue_request(req)

    total = 0
    saved = False
    deadline = time.time() + 30

    while time.time() < deadline and not saved:
        ready = cm.get_ready_requests()
        if not ready:
            time.sleep(0.01)
            continue

        for req in ready:
            total += 1

            if total <= warmup:
                req.reuse()
                cam.queue_request(req)
                if total == warmup:
                    print(f"Warmup done ({warmup} frames)")
                continue

            if req.status == lc.Request.Status.Complete:
                for s, fb in req.buffers.items():
                    fd = fb.planes[0].fd
                    length = fb.planes[0].length
                    mm = mmap.mmap(fd, length)
                    data = bytes(mm[:frame_size])
                    mm.close()
                    arr = np.frombuffer(data, dtype=np.uint8).reshape(
                        (h, stride // 4, 4)
                    )
                    arr = arr[:h, :w, :]
                    img = Image.fromarray(arr[:, :, :3].copy(), "RGB")
                    img.save(output, quality=quality)
                    print(f"Saved: {output} ({img.size[0]}x{img.size[1]})")
                    saved = True
                break

            req.reuse()
            cam.queue_request(req)

    cam.stop()
    cam.release()
    del alloc
    del cm

    if saved:
        print(f"OK - captured frame {total} ({warmup} warmup)")
    else:
        print("FAIL - no frame captured")
        exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture image from IMX219 on RPi 5")
    parser.add_argument(
        "-o",
        "--output",
        default=os.path.expanduser("~/capture.jpg"),
        help="Output file path",
    )
    parser.add_argument(
        "-W", "--width", type=int, default=1640, help="Width (default: 1640)"
    )
    parser.add_argument(
        "-H", "--height", type=int, default=1232, help="Height (default: 1232)"
    )
    parser.add_argument(
        "-w",
        "--warmup",
        type=int,
        default=30,
        help="Warmup frames for AE/AWB (default: 30)",
    )
    parser.add_argument(
        "-q", "--quality", type=int, default=95, help="JPEG quality (default: 95)"
    )
    args = parser.parse_args()
    capture(args.output, args.width, args.height, args.warmup, args.quality)
