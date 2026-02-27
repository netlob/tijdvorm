"""Doorbell camera feed — reads RTSP stream via ffmpeg and pushes JPEG frames."""

import asyncio
import logging

from backend.config import NVR_RTSP_URL, OUTPUT_WIDTH, OUTPUT_HEIGHT

logger = logging.getLogger("tijdvorm.doorbell")

# Crop top 60px (camera timestamp bar), scale to portrait output
_VIDEO_FILTER = f"crop=in_w:in_h-60:0:60,scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}"


async def doorbell_loop(frame_buffer, stop_event: asyncio.Event):
    """Read RTSP stream via ffmpeg subprocess, push JPEG frames to FrameBuffer.

    Uses UDP transport to avoid the NVR dumping its entire TCP replay buffer
    (~15-20s of old video) on connect. With UDP, old packets are simply lost
    and we start from the live edge immediately.

    Reconnects automatically on stream failure.
    """
    logger.info("Doorbell RTSP stream starting")

    while not stop_event.is_set():
        process = None
        try:
            cmd = [
                "ffmpeg",
                # Input: UDP transport to skip NVR replay buffer
                "-rtsp_transport", "udp",
                "-fflags", "nobuffer+discardcorrupt",
                "-flags", "low_delay",
                "-probesize", "32",
                "-analyzeduration", "0",
                "-reorder_queue_size", "0",
                "-max_delay", "0",
                "-i", NVR_RTSP_URL,
                # Processing: crop timestamp bar, scale to output
                "-vf", _VIDEO_FILTER,
                # Output: MJPEG frames to pipe
                "-f", "image2pipe",
                "-vcodec", "mjpeg",
                "-q:v", "5",
                "-fps_mode", "drop",
                "-flush_packets", "1",
                "-threads", "2",
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
