#!/usr/bin/env python3
"""
Comprehensive AirPlay debugging script for Samsung Frame TV streaming.
Tests device discovery, connection, and streaming of various media types.
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import List, Optional

# Add project root to path and change working directory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)
os.chdir(project_root)

import pyatv
from pyatv import scan
from backend.config import DATA_DIR, TV_IP
from backend.integrations.airplay import play_url_on_tv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

CREDENTIALS_FILE = os.path.join(DATA_DIR, "airplay_credentials.json")

# Test URLs for different media types
TEST_URLS = {
    # Images (iPhone compatible)
    "image_jpeg": "https://picsum.photos/1920/1080.jpg",  # Random landscape image
    "image_png": "https://picsum.photos/1920/1080.png",   # Random landscape image (PNG)
    "local_image": "http://localhost:8000/api/render/doorbell.jpg",  # Local doorbell image

    # Videos (iPhone compatible formats)
    "video_mp4": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    "video_mov": "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4",

    # HLS streams (iPhone preferred)
    "hls_stream": "https://devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_fmp4/master.m3u8",
    "local_hls": "http://localhost:8000/hls/playlist.m3u8",  # Local HLS stream

    # Apple TV+ style content (if iPhone works with these)
    "apple_sample": "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4",

    # Test alternative libraries
    "test_airplayer": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
}

class AirPlayDebugger:
    def __init__(self):
        self.loop = asyncio.get_event_loop()

    async def scan_devices(self, target_ip: Optional[str] = None) -> List:
        """Scan for AirPlay devices."""
        print("🔍 Scanning for AirPlay devices...")

        if target_ip:
            print(f"   Targeting IP: {target_ip}")
            results = await scan(loop=self.loop, hosts=[target_ip])
        else:
            print("   Broadcasting scan...")
            results = await scan(loop=self.loop)

        if results:
            print(f"✅ Found {len(results)} device(s):")
            for i, device in enumerate(results, 1):
                print(f"   {i}. {device.name} ({device.address}) - {device.identifier}")
                print(f"      Services: {[s.protocol.name for s in device.services]}")
        else:
            print("❌ No AirPlay devices found")

        return results

    async def test_connection(self, device_conf) -> bool:
        """Test basic connection to device."""
        print(f"🔌 Testing connection to {device_conf.name}...")

        try:
            atv = await pyatv.connect(device_conf, loop=self.loop)
            print("✅ Connected successfully")

            # Get device info
            try:
                all_features = atv.features.all_features()
                available_features = [name.name for name, info in all_features.items()
                                    if info.state.name == 'Available']
                print(f"   Available features: {available_features}")
            except Exception as e:
                print(f"   Could not get device features: {e}")

            try:
                atv.close()
                print("✅ Disconnected successfully")
            except Exception as e:
                print(f"⚠️  Disconnect warning: {e}")

            return True

        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False

    async def test_streaming(self, device_conf, url: str, description: str) -> bool:
        """Test streaming a specific URL."""
        print(f"🎬 Testing streaming: {description}")
        print(f"   URL: {url}")

        try:
            atv = await pyatv.connect(device_conf, loop=self.loop)
            print("✅ Connected for streaming")

            try:
                # Set a timeout for the streaming attempt
                await asyncio.wait_for(atv.stream.play_url(url), timeout=10.0)
                print("✅ Stream command sent successfully")
                print("   Note: Check your TV to see if content is playing")

                # Wait a moment to let the stream start
                await asyncio.sleep(2)

                return True

            except asyncio.TimeoutError:
                print("⏰ Stream command timed out (10s)")
                return False
            except Exception as e:
                print(f"❌ Stream command failed: {e}")
                return False
            finally:
                try:
                    atv.close()
                    print("✅ Disconnected after streaming")
                except Exception as e:
                    print(f"⚠️  Disconnect warning: {e}")

        except Exception as e:
            print(f"❌ Connection for streaming failed: {e}")
            return False

    def load_credentials(self):
        """Load saved AirPlay credentials."""
        if not os.path.exists(CREDENTIALS_FILE):
            print(f"❌ Credentials file not found: {CREDENTIALS_FILE}")
            print("   Run scripts/pair_airplay.py first to pair with your TV")
            return None

        try:
            with open(CREDENTIALS_FILE, "r") as f:
                creds_data = json.load(f)

            address = creds_data.get("address")
            credentials = creds_data.get("credentials")
            identifier = creds_data.get("identifier")
            name = creds_data.get("name", "Unknown Device")

            print("✅ Loaded credentials:")
            print(f"   Device: {name}")
            print(f"   Address: {address}")
            print(f"   Identifier: {identifier}")

            return creds_data

        except Exception as e:
            print(f"❌ Failed to load credentials: {e}")
            return None

    async def find_device_by_credentials(self, creds_data):
        """Find device using saved credentials."""
        address = creds_data.get("address")
        identifier = creds_data.get("identifier")

        print(f"🔍 Finding device (IP: {address}, ID: {identifier})...")

        # First try direct IP scan
        results = await scan(loop=self.loop, hosts=[address])
        if results:
            device_conf = results[0]
            print(f"✅ Found device by IP: {device_conf.name}")
            return device_conf

        # Fallback to broadcast scan
        print("   Direct IP scan failed, trying broadcast...")
        results = await scan(loop=self.loop)

        # Try to match by IP
        for res in results:
            if str(res.address) == address:
                print(f"✅ Found device by IP match: {res.name}")
                return res

        # Try to match by identifier
        if identifier:
            for res in results:
                if res.identifier == identifier:
                    print(f"✅ Found device by identifier match: {res.name}")
                    return res

        print("❌ Could not find device")
        return None

    async def run_device_tests(self, device_conf):
        """Run comprehensive tests on a device."""
        print(f"\n{'='*50}")
        print(f"🧪 RUNNING COMPREHENSIVE TESTS ON: {device_conf.name}")
        print(f"{'='*50}")

        # Test 1: Basic connection
        print("\n1. Testing basic connection...")
        if not await self.test_connection(device_conf):
            print("❌ Basic connection test failed, skipping other tests")
            return

        # Test 2: Device capabilities analysis
        print("\n2. Analyzing device capabilities...")
        await self.analyze_capabilities(device_conf)

        # Test 3: Different media types (start with what iPhone likely uses)
        print("\n3. Testing different media types...")

        # Start with HLS (iPhone preferred)
        await self.test_streaming(device_conf, TEST_URLS["hls_stream"], "HLS Stream (iPhone preferred)")

        # Wait between tests
        await asyncio.sleep(3)

        # Test MP4 (common format)
        await self.test_streaming(device_conf, TEST_URLS["video_mp4"], "MP4 Video")

        # Wait between tests
        await asyncio.sleep(3)

        # Test image
        await self.test_streaming(device_conf, TEST_URLS["image_jpeg"], "JPEG Image")

        print(f"\n{'='*50}")
        print("✅ All tests completed")
        print(f"{'='*50}")

    async def analyze_capabilities(self, device_conf):
        """Analyze what capabilities the device reports vs what actually works."""
        print(f"🔍 Analyzing capabilities for {device_conf.name}...")

        try:
            atv = await pyatv.connect(device_conf, loop=self.loop)

            # Get all features
            all_features = atv.features.all_features(include_unsupported=True)

            print("📋 Complete feature list:")
            for name, feature in all_features.items():
                status = "✅" if feature.state.name == "Available" else "❌" if feature.state.name == "Unsupported" else "⚠️"
                print(f"   {status} {name.name}: {feature.state.name}")
                if feature.options:
                    print(f"      Options: {feature.options}")

            # Check device info
            try:
                device_info = atv.device_info
                print(f"📱 Device info: {device_info}")
            except Exception as e:
                print(f"   Could not get device info: {e}")

            # Check what protocols are available
            print(f"🔌 Available services: {[s.protocol.name for s in device_conf.services]}")

            atv.close()

        except Exception as e:
            print(f"❌ Capability analysis failed: {e}")

    async def diagnose_iphone_compatibility(self, device_conf):
        """Diagnose why iPhone works but pyatv doesn't."""
        print(f"\n🔍 DIAGNOSTIC MODE: iPhone vs pyatv compatibility")
        print("=" * 60)

        print("📱 iPhone typically uses:")
        print("   • AirPlay 2 protocol")
        print("   • HLS streams preferred")
        print("   • Automatic codec negotiation")
        print("   • Different timing and session handling")
        print()

        # Test 1: Check if device supports AirPlay 2
        print("1. Checking AirPlay protocol support...")
        airplay_service = None
        for service in device_conf.services:
            if service.protocol == pyatv.Protocol.AirPlay:
                airplay_service = service
                break

        if airplay_service:
            print(f"   ✅ AirPlay service found on port {getattr(airplay_service, 'port', 'unknown')}")
        else:
            print("   ❌ No AirPlay service found")
            return

        # Test 2: Try different connection methods
        print("\n2. Testing different connection approaches...")

        # Method A: Standard connection (what we've been using)
        print("   Method A: Standard pyatv connection")
        try:
            atv = await pyatv.connect(device_conf, loop=self.loop)
            print("   ✅ Connected successfully")

            # Check if play_url is really available
            play_url_available = atv.features.in_state(
                pyatv.const.FeatureState.Available,
                pyatv.const.FeatureName.PlayUrl
            )
            print(f"   🎬 PlayUrl feature: {'✅ Available' if play_url_available else '❌ Not available'}")

            atv.close()
        except Exception as e:
            print(f"   ❌ Standard connection failed: {e}")

        # Test 3: Try with different timing
        print("\n3. Testing timing differences...")
        print("   iPhone might use different connection timing...")

        # Test 4: Check if it's a content format issue
        print("\n4. Testing content format compatibility...")
        print("   Trying content that definitely works on iPhone...")

        # Try Apple's own test stream
        apple_test_url = "https://devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_fmp4/master.m3u8"
        await self.test_streaming(device_conf, apple_test_url, "Apple Test Stream (iPhone compatible)")

        # Test 5: Check network/firewall issues
        print("\n5. Network diagnostics...")
        import socket
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            print(f"   🏠 Local IP: {local_ip}")
            print(f"   📺 TV IP: {device_conf.address}")
            print("   💡 Check: Can your computer reach the TV directly?")
            print("   💡 Check: Is there a firewall blocking pyatv but not iPhone?")
        except Exception as e:
            print(f"   ❌ Network check failed: {e}")

        # Test 6: Version/protocol differences
        print("\n6. Protocol analysis...")
        print("   📋 pyatv version info:")
        print(f"      pyatv version: {getattr(pyatv, '__version__', 'unknown')}")
        print("   📋 iPhone uses different protocol negotiation")
        print("   💡 Samsung TVs may require specific AirPlay 2 features that pyatv doesn't implement")

        print(f"\n{'='*60}")
        print("🎯 DIAGNOSTIC SUMMARY:")
        print("If iPhone works but pyatv doesn't, common causes:")
        print("   1. Protocol version differences (AirPlay 2 vs 1)")
        print("   2. Authentication/session handling differences")
        print("   3. Content format requirements (HLS preferred)")
        print("   4. Network/firewall blocking specific connections")
        print("   5. TV firmware requiring specific client features")
        print()
        print("💡 RECOMMENDATIONS:")
        print("   • Use DLNA instead (more reliable for Samsung)")
        print("   • Test with TV's web interface for uploads")
        print("   • Check if iPhone uses screen mirroring vs media streaming")
        print(f"{'='*60}")

    async def interactive_menu(self):
        """Run interactive debugging menu."""
        print("🎯 AirPlay & DLNA Debug Menu")
        print("=" * 35)

        while True:
            print("\nChoose an option:")
            print("1. Scan for devices")
            print("2. Test connection with saved credentials")
            print("3. Run comprehensive AirPlay streaming tests")
            print("4. Test specific AirPlay URL")
            print("5. Test DLNA streaming (recommended for Samsung)")
            print("6. Run iPhone compatibility diagnostics")
            print("7. Show device info")
            print("8. Exit")

            try:
                choice = input("\nEnter choice (1-8): ").strip()

                if choice == "1":
                    devices = await self.scan_devices()
                    if devices:
                        print(f"\nFound {len(devices)} device(s)")
                        for i, dev in enumerate(devices, 1):
                            print(f"{i}: {dev.name} ({dev.address})")

                elif choice == "2":
                    creds = self.load_credentials()
                    if creds:
                        device_conf = await self.find_device_by_credentials(creds)
                        if device_conf:
                            device_conf.set_credentials(pyatv.Protocol.AirPlay, creds["credentials"])
                            await self.test_connection(device_conf)

                elif choice == "3":
                    creds = self.load_credentials()
                    if creds:
                        device_conf = await self.find_device_by_credentials(creds)
                        if device_conf:
                            device_conf.set_credentials(pyatv.Protocol.AirPlay, creds["credentials"])
                            await self.run_device_tests(device_conf)

                elif choice == "4":
                    print("\nAvailable test URLs:")
                    for key, url in TEST_URLS.items():
                        print(f"  {key}: {url}")

                    url_key = input("\nEnter URL key or full URL: ").strip()
                    if url_key in TEST_URLS:
                        url = TEST_URLS[url_key]
                    else:
                        url = url_key

                    creds = self.load_credentials()
                    if creds:
                        device_conf = await self.find_device_by_credentials(creds)
                        if device_conf:
                            device_conf.set_credentials(pyatv.Protocol.AirPlay, creds["credentials"])
                            await self.test_streaming(device_conf, url, f"Custom URL: {url}")

                elif choice == "5":
                    print("\nTesting DLNA streaming (recommended for Samsung TVs)...")
                    from backend.integrations.dlna import play_url_via_dlna
                    from backend.config import TV_IP

                    print("Available test URLs:")
                    for key, url in TEST_URLS.items():
                        if "hls" not in key and "mov" not in key:  # DLNA works better with MP4/JPEG
                            print(f"  {key}: {url}")

                    url_key = input("\nEnter URL key or full URL: ").strip()
                    if url_key in TEST_URLS:
                        url = TEST_URLS[url_key]
                    else:
                        url = url_key

                    print(f"Testing DLNA streaming to {TV_IP}...")
                    success = play_url_via_dlna(url, TV_IP)
                    if success:
                        print("✅ DLNA streaming successful")
                    else:
                        print("❌ DLNA streaming failed")

                elif choice == "6":
                    print("\n🔬 Running iPhone compatibility diagnostics...")
                    creds = self.load_credentials()
                    if creds:
                        device_conf = await self.find_device_by_credentials(creds)
                        if device_conf:
                            device_conf.set_credentials(pyatv.Protocol.AirPlay, creds["credentials"])
                            await self.diagnose_iphone_compatibility(device_conf)

                elif choice == "7":
                    creds = self.load_credentials()
                    if creds:
                        print(f"\n📋 Device Info from credentials:")
                        print(f"   Name: {creds.get('name', 'Unknown')}")
                        print(f"   IP: {creds.get('address', 'Unknown')}")
                        print(f"   Identifier: {creds.get('identifier', 'Unknown')}")
                        print(f"   Credentials: {creds.get('credentials', 'Unknown')[:50]}...")

                elif choice == "8":
                    print("👋 Goodbye!")
                    break

                else:
                    print("❌ Invalid choice")

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")

async def main():
    """Main function."""
    print("🎬 AirPlay Debug Script for Samsung Frame TV")
    print("=" * 50)

    debugger = AirPlayDebugger()

    # Check if running with arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "scan":
            await debugger.scan_devices(TV_IP if len(sys.argv) > 2 and sys.argv[2] == "target" else None)

        elif command == "test":
            creds = debugger.load_credentials()
            if creds:
                device_conf = await debugger.find_device_by_credentials(creds)
                if device_conf:
                    device_conf.set_credentials(pyatv.Protocol.AirPlay, creds["credentials"])
                    await debugger.run_device_tests(device_conf)

        elif command == "stream":
            if len(sys.argv) < 3:
                print("Usage: python debug_pyatv.py stream <url>")
                return

            url = sys.argv[2]
            creds = debugger.load_credentials()
            if creds:
                device_conf = await debugger.find_device_by_credentials(creds)
                if device_conf:
                    device_conf.set_credentials(pyatv.Protocol.AirPlay, creds["credentials"])
                    await debugger.test_streaming(device_conf, url, f"Command line URL: {url}")

        elif command == "dlna":
            if len(sys.argv) < 3:
                print("Usage: python debug_pyatv.py dlna <url>")
                print("Testing DLNA streaming (recommended for Samsung TVs)...")
                return

            from backend.integrations.dlna import play_url_via_dlna
            from backend.config import TV_IP

            url = sys.argv[2]
            print(f"Testing DLNA streaming to {TV_IP}...")
            success = play_url_via_dlna(url, TV_IP)
            if success:
                print("✅ DLNA streaming successful")
            else:
                print("❌ DLNA streaming failed")

        elif command == "diagnose":
            print("🔬 Running iPhone compatibility diagnostics...")
            creds = debugger.load_credentials()
            if creds:
                device_conf = await debugger.find_device_by_credentials(creds)
                if device_conf:
                    device_conf.set_credentials(pyatv.Protocol.AirPlay, creds["credentials"])
                    await debugger.diagnose_iphone_compatibility(device_conf)

        else:
            print("Usage: python debug_pyatv.py [scan|test|stream <url>|dlna <url>|diagnose]")
            print("Or run without arguments for interactive menu")

    else:
        # Interactive menu
        await debugger.interactive_menu()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
