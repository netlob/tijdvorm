#!/usr/bin/env python3
"""
DLNA Performance and Reliability Testing Script
Tests speed, reliability, and compatibility of DLNA streaming to Samsung Frame TV
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any
import sys
import os

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)
os.chdir(project_root)

from backend.config import TV_IP
from backend.integrations.dlna import play_url_via_dlna

# Test content URLs (various formats and sizes)
TEST_CONTENT = {
    "small_jpg": {
        "url": "https://picsum.photos/800/600.jpg",
        "description": "Small JPEG (800x600)",
        "expected_size": "~50KB"
    },
    "medium_jpg": {
        "url": "https://picsum.photos/1920/1080.jpg",
        "description": "HD JPEG (1920x1080)",
        "expected_size": "~200KB"
    },
    "large_jpg": {
        "url": "https://picsum.photos/3840/2160.jpg",
        "description": "4K JPEG (3840x2160)",
        "expected_size": "~800KB"
    },
    "mp4_video": {
        "url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
        "description": "MP4 Video (Sample)",
        "expected_size": "~150MB"
    },
    "local_image": {
        "url": "http://localhost:8000/api/render/doorbell.jpg",
        "description": "Local Doorbell Image",
        "expected_size": "Dynamic"
    }
}

class DLNAPerformanceTester:
    def __init__(self):
        self.results = []
        self.tv_ip = TV_IP

    async def test_single_url(self, name: str, content: Dict[str, Any]) -> Dict[str, Any]:
        """Test streaming a single URL and measure performance."""
        print(f"\n🎬 Testing {name}: {content['description']}")
        print(f"   URL: {content['url']}")
        print(f"   Expected size: {content['expected_size']}")

        start_time = time.time()

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, play_url_via_dlna, content['url'], self.tv_ip
            )

            end_time = time.time()
            duration = end_time - start_time

            if result:
                status = "✅ SUCCESS"
                print(".2f"                print("   TV should now be displaying the content"            else:
                status = "❌ FAILED"
                print(".2f"
            return {
                "name": name,
                "description": content['description'],
                "url": content['url'],
                "success": result,
                "duration": duration,
                "timestamp": time.time()
            }

        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            print(f"❌ ERROR after {duration:.2f}s: {e}")
            return {
                "name": name,
                "description": content['description'],
                "url": content['url'],
                "success": False,
                "duration": duration,
                "error": str(e),
                "timestamp": time.time()
            }

    async def run_performance_test(self, iterations: int = 5):
        """Run comprehensive performance testing."""
        print("🚀 DLNA Performance & Reliability Test")
        print("=" * 50)
        print(f"TV IP: {self.tv_ip}")
        print(f"Iterations per content type: {iterations}")
        print()

        # Test each content type multiple times
        for content_name, content in TEST_CONTENT.items():
            print(f"\n{'='*40}")
            print(f"Testing {content_name.upper()}")
            print(f"{'='*40}")

            content_results = []
            for i in range(iterations):
                print(f"\n--- Iteration {i+1}/{iterations} ---")
                result = await self.test_single_url(content_name, content)
                content_results.append(result)

                # Add delay between tests to avoid overwhelming the TV
                if i < iterations - 1:
                    await asyncio.sleep(3)

            # Analyze results for this content type
            self.analyze_content_results(content_name, content_results)

    def analyze_content_results(self, content_name: str, results: List[Dict[str, Any]]):
        """Analyze results for a specific content type."""
        successes = [r for r in results if r['success']]
        failures = [r for r in results if not r['success']]

        success_rate = len(successes) / len(results) * 100
        success_times = [r['duration'] for r in successes]

        print(f"\n📊 Results for {content_name}:")
        print(f"   Success Rate: {success_rate:.1f}% ({len(successes)}/{len(results)})")

        if success_times:
            print(".2f"            print(".2f"            print(".2f"
        if failures:
            print(f"   Failures: {len(failures)}")
            for failure in failures:
                print(f"      - {failure.get('error', 'Unknown error')}")

    async def run_reliability_test(self, duration_minutes: int = 10):
        """Run long-term reliability test."""
        print(f"\n🔄 DLNA Long-term Reliability Test ({duration_minutes} minutes)")
        print("=" * 60)

        end_time = time.time() + (duration_minutes * 60)
        test_count = 0
        successes = 0

        # Use a reliable test image
        test_content = TEST_CONTENT["medium_jpg"]

        while time.time() < end_time:
            test_count += 1
            print(f"\n--- Test {test_count} ---")

            result = await self.test_single_url("reliability_test", test_content)
            if result['success']:
                successes += 1

            # Wait before next test
            remaining_time = end_time - time.time()
            if remaining_time > 10:
                print(f"⏱️  Waiting 10 seconds before next test...")
                await asyncio.sleep(10)
            elif remaining_time > 0:
                print(f"⏱️  Waiting {remaining_time:.1f} seconds before finishing...")
                await asyncio.sleep(remaining_time)

        # Final results
        reliability_rate = successes / test_count * 100
        print(f"\n🏁 Reliability Test Complete:")
        print(f"   Total Tests: {test_count}")
        print(f"   Success Rate: {reliability_rate:.1f}%")
        print(f"   Duration: {duration_minutes} minutes")

        if reliability_rate >= 95:
            print("   ✅ EXCELLENT reliability!")
        elif reliability_rate >= 85:
            print("   ⚠️  GOOD reliability")
        else:
            print("   ❌ POOR reliability - investigate issues")

    async def run_speed_comparison(self):
        """Compare loading speeds of different content types."""
        print(f"\n⚡ DLNA Speed Comparison Test")
        print("=" * 40)

        results = []

        # Test each content type once
        for content_name, content in TEST_CONTENT.items():
            if content_name == "local_image":
                continue  # Skip local image for speed comparison

            print(f"\nTesting {content_name}...")
            result = await self.test_single_url(content_name, content)
            results.append(result)

            # Wait between tests
            await asyncio.sleep(2)

        # Sort by speed
        successful_results = [r for r in results if r['success']]
        successful_results.sort(key=lambda x: x['duration'])

        print(f"\n🏆 Speed Rankings (fastest to slowest):")
        for i, result in enumerate(successful_results, 1):
            print("2d")

async def main():
    """Main test runner."""
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
    else:
        test_type = "performance"

    tester = DLNAPerformanceTester()

    if test_type == "performance":
        await tester.run_performance_test(iterations=3)
    elif test_type == "reliability":
        minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        await tester.run_reliability_test(duration_minutes=minutes)
    elif test_type == "speed":
        await tester.run_speed_comparison()
    else:
        print("Usage: python test_dlna_performance.py [performance|reliability|speed]")
        print("  performance: Test each content type multiple times")
        print("  reliability: Long-term reliability test (default 5 minutes)")
        print("  speed: Compare loading speeds of different content")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
