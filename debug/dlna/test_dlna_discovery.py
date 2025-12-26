#!/usr/bin/env python3
"""
DLNA Device Discovery and Compatibility Test
Tests discovery speed and device compatibility for DLNA streaming
"""

import asyncio
import time
import sys
import os
from typing import List, Dict, Any

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)
os.chdir(project_root)

from backend.config import TV_IP

# Try to import upnpclient for DLNA discovery
try:
    import upnpclient
    UPNP_AVAILABLE = True
except ImportError:
    UPNP_AVAILABLE = False
    print("⚠️  upnpclient not available - install with: pip install upnpclient")

class DLNADiscoveryTester:
    def __init__(self):
        self.discovered_devices = []

    async def discover_devices(self, timeout: int = 10) -> List[Dict[str, Any]]:
        """Discover DLNA devices on the network."""
        if not UPNP_AVAILABLE:
            print("❌ Cannot perform discovery - upnpclient not installed")
            return []

        print(f"🔍 Discovering DLNA devices (timeout: {timeout}s)...")
        start_time = time.time()

        try:
            # Use asyncio to run the blocking discovery
            devices = await asyncio.get_event_loop().run_in_executor(
                None, lambda: list(upnpclient.discover(timeout=timeout))
            )

            discovery_time = time.time() - start_time

            print(".2f"            print(f"Found {len(devices)} DLNA device(s)")

            device_info = []
            for device in devices:
                info = {
                    "name": getattr(device, 'friendly_name', 'Unknown'),
                    "location": getattr(device, 'location', 'Unknown'),
                    "udn": getattr(device, 'udn', 'Unknown'),
                    "device_type": getattr(device, 'device_type', 'Unknown'),
                    "services": []
                }

                # Check for AVTransport service (required for media playback)
                if hasattr(device, 'services'):
                    for service in device.services:
                        service_info = {
                            "service_type": getattr(service, 'service_type', 'Unknown'),
                            "service_id": getattr(service, 'service_id', 'Unknown'),
                            "control_url": getattr(service, 'control_url', 'Unknown')
                        }
                        info["services"].append(service_info)

                        # Check if this is an AVTransport service
                        if 'AVTransport' in service_info['service_type']:
                            info["has_avtransport"] = True
                            info["avtransport_control"] = service_info['control_url']

                device_info.append(info)

            return device_info

        except Exception as e:
            discovery_time = time.time() - start_time
            print(f"❌ Discovery failed after {discovery_time:.2f}s: {e}")
            return []

    def analyze_devices(self, devices: List[Dict[str, Any]]):
        """Analyze discovered devices for Samsung TV compatibility."""
        print(f"\n📊 Device Analysis:")
        print("=" * 50)

        samsung_devices = []
        other_devices = []

        for device in devices:
            name = device['name']
            if 'samsung' in name.lower() or 'frame' in name.lower():
                samsung_devices.append(device)
            else:
                other_devices.append(device)

        print(f"📺 Samsung TVs found: {len(samsung_devices)}")
        for device in samsung_devices:
            has_av = device.get('has_avtransport', False)
            status = "✅ AVTransport ready" if has_av else "❌ Missing AVTransport"
            print(f"   • {device['name']} - {status}")

        print(f"📱 Other DLNA devices: {len(other_devices)}")
        for device in other_devices:
            has_av = device.get('has_avtransport', False)
            status = "✅ AVTransport ready" if has_av else "❌ Missing AVTransport"
            print(f"   • {device['name']} - {status}")

        # Check our target TV specifically
        target_tv_found = any(
            TV_IP in device.get('location', '') or TV_IP in str(device)
            for device in devices
        )

        if target_tv_found:
            print(f"\n🎯 Target TV ({TV_IP}): ✅ FOUND")
        else:
            print(f"\n🎯 Target TV ({TV_IP}): ❌ NOT FOUND")
            print("   💡 Check if TV is on and DLNA is enabled")

    async def test_connectivity(self, devices: List[Dict[str, Any]]):
        """Test connectivity to discovered Samsung devices."""
        print(f"\n🔌 Testing Connectivity:")
        print("=" * 30)

        samsung_devices = [
            d for d in devices
            if 'samsung' in d['name'].lower() or 'frame' in d['name'].lower()
        ]

        if not samsung_devices:
            print("❌ No Samsung devices found to test")
            return

        for device in samsung_devices:
            print(f"\nTesting {device['name']}...")
            start_time = time.time()

            # Try a simple test image
            test_url = "https://picsum.photos/800/600.jpg"

            try:
                from backend.integrations.dlna import play_url_via_dlna

                # Extract IP from device location
                location = device.get('location', '')
                if 'http://' in location:
                    # Parse IP from URL like http://192.168.1.100:9197/
                    ip = location.split('http://')[1].split(':')[0].split('/')[0]
                else:
                    ip = TV_IP  # Fallback

                result = await asyncio.get_event_loop().run_in_executor(
                    None, play_url_via_dlna, test_url, ip
                )

                end_time = time.time()
                duration = end_time - start_time

                if result:
                    print(".2f"                else:
                    print(".2f"
            except Exception as e:
                end_time = time.time()
                duration = end_time - start_time
                print(".2f"                print(f"   Error: {e}")

async def main():
    """Main test runner."""
    print("🔍 DLNA Device Discovery & Compatibility Test")
    print("=" * 50)

    tester = DLNADiscoveryTester()

    # Discover devices
    devices = await tester.discover_devices(timeout=15)

    if devices:
        # Analyze devices
        tester.analyze_devices(devices)

        # Test connectivity
        await tester.test_connectivity(devices)
    else:
        print("❌ No DLNA devices discovered")
        print("💡 Make sure:")
        print("   • Samsung TV is turned on")
        print("   • DLNA is enabled in TV settings")
        print("   • TV and computer are on same network")
        print("   • upnpclient is installed: pip install upnpclient")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Discovery cancelled")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
