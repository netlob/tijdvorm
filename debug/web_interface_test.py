#!/usr/bin/env python3
"""
Samsung TV Web Interface Testing
Test direct HTTP uploads to Samsung Frame TV web interface
"""

import requests
import time
import sys
import os

# Add project root to path and change working directory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)
os.chdir(project_root)

# Import TV_IP directly
TV_IP = "10.0.1.111"  # Hardcoded for testing

def test_web_interface_access():
    """Test if we can access the TV's web interface."""
    print("🌐 Testing Samsung TV Web Interface Access")
    print("=" * 50)

    # Common Samsung TV web interface URLs
    test_urls = [
        f"http://{TV_IP}:8001",  # Samsung Smart TV web interface
        f"http://{TV_IP}:8080",  # Alternative port
        f"http://{TV_IP}",       # Default HTTP port
    ]

    for url in test_urls:
        try:
            print(f"\n🔍 Testing {url}...")
            response = requests.get(url, timeout=5)
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                print(f"   ✅ Web interface accessible at {url}")
                print(f"   Content preview: {response.text[:200]}...")
                return url
            elif response.status_code == 401:
                print(f"   ⚠️  Web interface exists but requires authentication at {url}")
                print("   This is GOOD news - the web server is running!")
                return url
            elif response.status_code == 403:
                print(f"   ⚠️  Web interface exists but access forbidden at {url}")
                return url

        except requests.exceptions.RequestException as e:
            print(f"   ❌ Connection failed: {e}")

    print("\n❌ No web interface found on common ports")
    print("💡 Samsung TVs typically use port 8001 for web interface")
    return None

def test_media_upload_endpoint(base_url):
    """Test potential media upload endpoints."""
    print(f"\n📤 Testing Media Upload Endpoints")
    print("=" * 40)

    # Common Samsung TV upload endpoints
    endpoints = [
        "/ws/app/PictureShare",
        "/ws/app/ImageShow",
        "/ws/app/MediaRenderer",
        "/api/v1/media",
        "/upload",
        "/image",
    ]

    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        try:
            print(f"\n🔍 Testing {endpoint}...")
            response = requests.get(url, timeout=5)
            print(f"   Status: {response.status_code}")

            if response.status_code in [200, 401, 403]:
                print(f"   ✅ Endpoint exists: {endpoint}")
                return url

        except requests.exceptions.RequestException as e:
            print(f"   ❌ Failed: {e}")

    print("\n❌ No upload endpoints found")
    return None

def test_basic_connectivity():
    """Test basic network connectivity to TV."""
    print(f"\n🔌 Testing Basic Network Connectivity")
    print("=" * 40)

    import socket

    try:
        # Test basic TCP connectivity to common ports
        ports_to_test = [80, 443, 8001, 8080, 9197]

        for port in ports_to_test:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((TV_IP, port))
                sock.close()

                if result == 0:
                    print(f"   ✅ Port {port}: OPEN")
                    return port
                else:
                    print(f"   ❌ Port {port}: CLOSED")

            except Exception as e:
                print(f"   ❌ Port {port}: ERROR - {e}")

    except Exception as e:
        print(f"❌ Network test failed: {e}")

    print(f"\n💡 TV IP: {TV_IP}")
    print("💡 Check if TV is powered on and on the same network")
    return None

def main():
    """Main test function."""
    print("📺 Samsung Frame TV Web Interface Investigation")
    print("=" * 55)
    print(f"Target TV IP: {TV_IP}")
    print()

    # Test 1: Basic connectivity
    open_port = test_basic_connectivity()
    if not open_port:
        print("\n❌ Cannot connect to TV - check network and power")
        return

    # Test 2: Web interface access
    web_url = test_web_interface_access()
    if web_url:
        print(f"\n🎉 SUCCESS! Samsung TV web interface found at: {web_url}")
        print("   Status: Web server is running and responding")
        print("   Next step: Investigate authentication and upload endpoints")
    else:
        print("\n❌ Web interface not accessible")
        print("💡 Samsung Frame TVs typically have web interfaces on port 8001")
        print("💡 Make sure web browser is enabled in TV settings:")
        print("   TV Menu → Settings → General → System Manager → Samsung Apps → Web Browser")
        return

    # Test 3: Upload endpoints
    upload_url = test_media_upload_endpoint(web_url)
    if upload_url:
        print("\n🎉 SUCCESS! Found upload endpoint:")
        print(f"   {upload_url}")
        print("   This can be used for direct media uploads!")
    else:
        print("\n⚠️  Web interface accessible but no upload endpoints found")
        print("💡 Manual upload via TV browser may still work")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Test cancelled")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
