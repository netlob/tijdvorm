#!/usr/bin/env python3
"""
Quick DLNA Test Script
Simple, fast testing of DLNA functionality to Samsung Frame TV
"""

import asyncio
import time
import sys
import os

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)
os.chdir(project_root)

from backend.config import TV_IP
from backend.integrations.dlna import play_url_via_dlna

async def quick_test(url: str = None):
    """Run a quick DLNA test."""
    if url is None:
        # Default test image
        url = "https://picsum.photos/1920/1080.jpg"

    print("🧪 Quick DLNA Test")
    print(f"TV IP: {TV_IP}")
    print(f"URL: {url}")
    print()

    start_time = time.time()

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, play_url_via_dlna, url, TV_IP
        )

        end_time = time.time()
        duration = end_time - start_time

        if result:
            print("✅ SUCCESS")
            print(".2f")
            print("📺 Check your TV - content should be displayed!")
        else:
            print("❌ FAILED")
            print(".2f")
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        print("❌ ERROR")
        print(".2f")
        print(f"Error: {e}")

def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = None

    try:
        asyncio.run(quick_test(url))
    except KeyboardInterrupt:
        print("\n🛑 Test cancelled")

if __name__ == "__main__":
    main()
