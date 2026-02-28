#!/usr/bin/env python3
"""
Test MJPEG server that proxies the Reolink doorbell RTSP feed.

Runs ffmpeg on the host (outside Docker) to grab the RTSP stream,
then serves it as MJPEG over HTTP so the Pi receiver can display it.

Usage:
    python test_doorbell_stream.py
    python test_doorbell_stream.py --url rtsp://admin:pass@10.0.1.45:554/h264Preview_01_main
    python test_doorbell_stream.py --port 8000
    python test_doorbell_stream.py --raw   # skip crop/scale
"""

import argparse
import asyncio
import io
import logging
import os
import signal
import sys
import time

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

# Try loading .env for defaults
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("doorbell_proxy")

DEFAULT_URL = os.environ.get(
    "NVR_RTSP_URL",
    "rtsp://admin:peepeeDoorbell%24123poopoo@10.0.1.45:554/h264Preview_01_main",
)

OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
VIDEO_FILTER = f"crop=in_w:in_h-60:0:60,scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}"

app = FastAPI(title="Doorbell MJPEG Proxy")

# Shared state — initialised in lifespan (must be created inside running loop)
_latest_frame = None   # bytes or None
_frame_count = 0
_condition = None      # asyncio.Condition, set in lifespan


async def _push_frame(jpeg_bytes: bytes):
    global _latest_frame, _frame_count
    async with _condition:
        _latest_frame = jpeg_bytes
        _frame_count += 1
        _condition.notify_all()


async def _wait_for_frame(last_count: int):
    """Wait for a new frame. Returns (jpeg_bytes, frame_count)."""
    async with _condition:
        while _frame_count == last_count or _latest_frame is None:
            await _condition.wait()
        return _latest_frame, _frame_count


async def ffmpeg_reader(url: str, transport: str, raw: bool):
    """Run ffmpeg and push JPEG frames to the shared buffer."""
    while True:
        process = None
        try:
            cmd = [
                "ffmpeg",
                "-rtsp_transport", transport,
                "-fflags", "nobuffer+discardcorrupt",
                "-flags", "low_delay",
                "-probesize", "32",
                "-analyzeduration", "0",
                "-reorder_queue_size", "0",
                "-max_delay", "0",
                "-i", url,
            ]
            if not raw:
                cmd += ["-vf", VIDEO_FILTER]
            cmd += [
                "-f", "image2pipe",
                "-vcodec", "mjpeg",
                "-q:v", "5",
                "-fps_mode", "drop",
                "-flush_packets", "1",
                "-threads", "2",
                "-",
            ]

            logger.info(f"Starting ffmpeg: {transport} → {url}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Drain stderr
            async def drain():
                async for line in process.stderr:
                    text = line.decode(errors="replace").rstrip()
                    if any(kw in text.lower() for kw in ["error", "fail", "refused"]):
                        logger.warning(f"ffmpeg: {text}")

            stderr_task = asyncio.create_task(drain())

            buf = bytearray()
            frames = 0
            t_start = time.monotonic()

            while True:
                chunk = await process.stdout.read(65536)
                if not chunk:
                    break

                buf.extend(chunk)

                while True:
                    soi = buf.find(b"\xff\xd8")
                    if soi == -1:
                        buf.clear()
                        break
                    eoi = buf.find(b"\xff\xd9", soi + 2)
                    if eoi == -1:
                        if soi > 0:
                            del buf[:soi]
                        break

                    jpeg_bytes = bytes(buf[soi:eoi + 2])
                    del buf[:eoi + 2]
                    frames += 1
                    await _push_frame(jpeg_bytes)

                    if frames == 1:
                        logger.info(f"First frame: {len(jpeg_bytes):,} bytes, {time.monotonic() - t_start:.1f}s")
                    elif frames % 100 == 0:
                        elapsed = time.monotonic() - t_start
                        logger.info(f"{frames} frames, {frames / elapsed:.1f} FPS")

            stderr_task.cancel()
            logger.warning(f"ffmpeg exited (code={process.returncode}), {frames} frames total")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"ffmpeg error: {e}")
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()

        logger.info("Reconnecting in 2s...")
        await asyncio.sleep(2.0)


async def mjpeg_generator():
    last_count = -1
    boundary = b"frame"
    while True:
        jpeg_bytes, last_count = await _wait_for_frame(last_count)
        yield (
            b"--" + boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpeg_bytes)).encode() + b"\r\n"
            b"\r\n" + jpeg_bytes + b"\r\n"
        )


@app.get("/stream")
async def stream():
    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/health")
async def health():
    return {"status": "ok", "frames": _frame_count}


def main():
    parser = argparse.ArgumentParser(description="MJPEG proxy for Reolink doorbell")
    parser.add_argument("--url", default=DEFAULT_URL, help="RTSP URL")
    parser.add_argument("--transport", default="udp", choices=["udp", "tcp"])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--raw", action="store_true", help="Skip crop/scale")
    args = parser.parse_args()

    import uvicorn
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        global _condition
        # Create Condition inside the running event loop (Python 3.9 compat)
        _condition = asyncio.Condition()
        task = asyncio.create_task(ffmpeg_reader(args.url, args.transport, args.raw))
        logger.info(f"Doorbell proxy on http://0.0.0.0:{args.port}/stream")
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app.router.lifespan_context = lifespan

    print(f"Doorbell MJPEG proxy → http://0.0.0.0:{args.port}/stream")
    print(f"RTSP: {args.url}")
    print(f"Transport: {args.transport}, Filter: {'raw' if args.raw else VIDEO_FILTER}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
