"""Doorbell camera feed — reads RTSP stream via ffmpeg and pushes JPEG frames."""

import asyncio
import logging

from backend.config import NVR_RTSP_URL, DOORBELL_FPS, OUTPUT_WIDTH, OUTPUT_HEIGHT

logger = logging.getLogger("tijdvorm.doorbell")

# Crop top 60px from NVR frame (camera timestamp bar), then scale to output size
_VIDEO_FILTER = f"crop=in_w:in_h-60:0:60,scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},fps={DOORBELL_FPS}"


async def doorbell_loop(frame_buffer, stop_event: asyncio.Event):
    """Read RTSP stream via ffmpeg subprocess, push JPEG frames to FrameBuffer.

    ffmpeg handles RTSP negotiation, H.264 decoding, cropping, scaling,
    FPS limiting, and JPEG encoding — all in C, no Python image processing.

    Reconnects automatically on stream failure.
    """
    logger.info(f"Doorbell RTSP stream starting ({DOORBELL_FPS} FPS)")

    while not stop_event.is_set():
        process = None
        try:
            cmd = [
                "ffmpeg",
                "-rtsp_transport", "tcp",
                "-fflags", "nobuffer",
                "-flags", "low_delay",
                "-i", NVR_RTSP_URL,
                "-vf", _VIDEO_FILTER,
                "-f", "image2pipe",
                "-vcodec", "mjpeg",
                "-q:v", "5",
                "-",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )

            buf = bytearray()

            while not stop_event.is_set():
                chunk = await process.stdout.read(65536)
                if not chunk:
                    break

                buf.extend(chunk)

                # Extract complete JPEG frames (SOI=0xFFD8, EOI=0xFFD9)
                while True:
                    soi = buf.find(b"\xff\xd8")
                    if soi == -1:
                        buf.clear()
                        break
                    eoi = buf.find(b"\xff\xd9", soi + 2)
                    if eoi == -1:
                        # Discard anything before SOI to keep buffer small
                        if soi > 0:
                            del buf[:soi]
                        break

                    jpeg_bytes = bytes(buf[soi:eoi + 2])
                    del buf[:eoi + 2]
                    await frame_buffer.push_frame(jpeg_bytes)

        except Exception as e:
            logger.error(f"RTSP stream error: {e}")
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()

        if not stop_event.is_set():
            logger.warning("RTSP stream disconnected, reconnecting in 2s...")
            await asyncio.sleep(2.0)

    logger.info("Doorbell stream stopped")
