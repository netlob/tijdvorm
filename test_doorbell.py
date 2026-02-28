#!/usr/bin/env python3
"""
Test Reolink doorbell RTSP stream via ffmpeg.

Connects directly to the doorbell camera (bypassing NVR) and reports
connection time, frame rate, frame sizes, and any ffmpeg errors.

Usage:
    python test_doorbell.py                          # defaults from .env
    python test_doorbell.py --url rtsp://admin:pass@10.0.1.45:554/h264Preview_01_main
    python test_doorbell.py --transport tcp           # try TCP instead of UDP
    python test_doorbell.py --raw                     # skip crop/scale, just decode
    python test_doorbell.py --save                    # save first frame as doorbell_test.jpg
"""

import argparse
import asyncio
import os
import sys
import time

# Try loading .env for defaults
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_URL = os.environ.get(
    "NVR_RTSP_URL",
    "rtsp://admin:peepeeDoorbell%24123poopoo@10.0.1.45:554/h264Preview_01_main",
)

OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
VIDEO_FILTER = f"crop=in_w:in_h-60:0:60,scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}"


async def test_stream(
    url: str,
    transport: str = "udp",
    duration: float = 10.0,
    raw: bool = False,
    save_first: bool = False,
):
    print(f"{'=' * 60}")
    print(f"Reolink Doorbell RTSP Test")
    print(f"{'=' * 60}")
    print(f"URL:       {url}")
    print(f"Transport: {transport}")
    print(f"Filter:    {'none (raw)' if raw else VIDEO_FILTER}")
    print(f"Duration:  {duration}s")
    print(f"{'=' * 60}")
    print()

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

    print(f"[CMD] {' '.join(cmd)}")
    print()

    t_start = time.monotonic()

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Drain stderr in background and collect lines
    stderr_lines = []

    async def drain_stderr():
        async for line in process.stderr:
            text = line.decode(errors="replace").rstrip()
            stderr_lines.append(text)
            # Print important lines immediately
            if any(kw in text.lower() for kw in ["error", "fail", "refused", "timeout", "401", "403", "404"]):
                print(f"  [STDERR] {text}")

    stderr_task = asyncio.create_task(drain_stderr())

    # Parse JPEG frames from stdout
    buf = bytearray()
    frames = []
    t_first_frame = None
    first_frame_bytes = None

    try:
        deadline = time.monotonic() + duration

        while time.monotonic() < deadline:
            try:
                chunk = await asyncio.wait_for(process.stdout.read(65536), timeout=2.0)
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - t_start
                if not frames:
                    print(f"  [{elapsed:.1f}s] Still waiting for data...")
                continue

            if not chunk:
                print(f"  ffmpeg stdout closed (exit code: {process.returncode})")
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

                now = time.monotonic()
                if not frames:
                    t_first_frame = now
                    first_frame_bytes = jpeg_bytes
                    latency = now - t_start
                    print(f"  ✓ First frame received in {latency:.2f}s ({len(jpeg_bytes):,} bytes)")

                frames.append((now, len(jpeg_bytes)))

                # Progress every 30 frames
                if len(frames) % 30 == 0:
                    elapsed = now - t_start
                    fps = len(frames) / (now - t_first_frame) if t_first_frame and now > t_first_frame else 0
                    print(f"  [{elapsed:.1f}s] {len(frames)} frames, {fps:.1f} FPS")

    except KeyboardInterrupt:
        print("\n  Interrupted by user")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
        stderr_task.cancel()

    # Results
    t_end = time.monotonic()
    total_time = t_end - t_start

    print()
    print(f"{'=' * 60}")
    print(f"Results")
    print(f"{'=' * 60}")
    print(f"Total time:     {total_time:.1f}s")
    print(f"Frames:         {len(frames)}")

    if frames:
        stream_duration = frames[-1][0] - frames[0][0]
        avg_fps = (len(frames) - 1) / stream_duration if stream_duration > 0 and len(frames) > 1 else 0
        sizes = [s for _, s in frames]
        print(f"Avg FPS:        {avg_fps:.1f}")
        print(f"First frame:    {(t_first_frame - t_start):.2f}s latency")
        print(f"Frame size:     {min(sizes):,} - {max(sizes):,} bytes (avg {sum(sizes)//len(sizes):,})")
        print(f"Bandwidth:      {sum(sizes) / stream_duration / 1024:.0f} KB/s" if stream_duration > 0 else "")
    else:
        print(f"** NO FRAMES RECEIVED **")

    # Show ffmpeg stderr summary
    if stderr_lines:
        print()
        print(f"ffmpeg output ({len(stderr_lines)} lines):")
        # Show first 5 and last 5 lines
        show = stderr_lines[:5]
        if len(stderr_lines) > 10:
            show += ["  ..."]
            show += stderr_lines[-5:]
        elif len(stderr_lines) > 5:
            show += stderr_lines[5:]
        for line in show:
            print(f"  {line}")

    # Save first frame
    if save_first and first_frame_bytes:
        out_path = "doorbell_test.jpg"
        with open(out_path, "wb") as f:
            f.write(first_frame_bytes)
        print(f"\nFirst frame saved to {out_path}")

    print()
    return len(frames) > 0


async def main():
    parser = argparse.ArgumentParser(description="Test Reolink doorbell RTSP stream")
    parser.add_argument("--url", default=DEFAULT_URL, help="RTSP URL")
    parser.add_argument("--transport", default="udp", choices=["udp", "tcp"], help="RTSP transport")
    parser.add_argument("--duration", type=float, default=10.0, help="Test duration in seconds")
    parser.add_argument("--raw", action="store_true", help="Skip crop/scale filter")
    parser.add_argument("--save", action="store_true", help="Save first frame as doorbell_test.jpg")
    parser.add_argument("--both", action="store_true", help="Test both UDP and TCP")
    args = parser.parse_args()

    if args.both:
        print("\n>>> Testing UDP transport <<<\n")
        udp_ok = await test_stream(args.url, "udp", args.duration, args.raw, args.save)

        print("\n>>> Testing TCP transport <<<\n")
        tcp_ok = await test_stream(args.url, "tcp", args.duration, args.raw, args.save)

        print(f"\nSummary: UDP={'OK' if udp_ok else 'FAIL'}  TCP={'OK' if tcp_ok else 'FAIL'}")
    else:
        await test_stream(args.url, args.transport, args.duration, args.raw, args.save)


if __name__ == "__main__":
    asyncio.run(main())
