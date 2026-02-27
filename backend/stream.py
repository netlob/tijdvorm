import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger("tijdvorm.stream")

router = APIRouter()


class FrameBuffer:
    """Thread-safe frame buffer for MJPEG streaming.

    The generator pushes JPEG frames here. Connected MJPEG clients
    are notified and receive the latest frame.
    """

    def __init__(self):
        self.current_frame: bytes | None = None
        self._condition = asyncio.Condition()
        self._frame_count = 0

    async def push_frame(self, jpeg_bytes: bytes):
        async with self._condition:
            self.current_frame = jpeg_bytes
            self._frame_count += 1
            self._condition.notify_all()

    async def wait_for_frame(self, last_count: int = -1) -> tuple[bytes, int]:
        """Wait for a new frame. Returns (jpeg_bytes, frame_count)."""
        async with self._condition:
            while self._frame_count == last_count or self.current_frame is None:
                await self._condition.wait()
            return self.current_frame, self._frame_count


# Singleton — set by app.py on startup
frame_buffer: FrameBuffer | None = None


def get_frame_buffer() -> FrameBuffer:
    assert frame_buffer is not None, "FrameBuffer not initialized"
    return frame_buffer


async def _mjpeg_generator():
    fb = get_frame_buffer()
    last_count = -1
    boundary = b"frame"

    while True:
        jpeg_bytes, last_count = await fb.wait_for_frame(last_count)
        yield (
            b"--" + boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpeg_bytes)).encode() + b"\r\n"
            b"\r\n" + jpeg_bytes + b"\r\n"
        )


@router.get("/stream")
async def stream():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
