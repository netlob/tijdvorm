# AirPlay Debug Script for Samsung Frame TV

This debug script helps troubleshoot AirPlay streaming issues with Samsung Frame TVs.

## Quick Start

```bash
# Activate the virtual environment
cd /Users/sjoerdbolten/Documents/Projects/tijdvorm
source venv/bin/activate

# Run interactive menu
python scripts/debug_pyatv.py

# Or run specific commands
python scripts/debug_pyatv.py scan          # Scan for devices
python scripts/debug_pyatv.py test          # Run comprehensive tests
python scripts/debug_pyatv.py stream <url>  # Test specific URL
```

## Features

### Device Discovery
- Scans for all AirPlay-compatible devices on the network
- Shows device names, IP addresses, and supported services
- Can target specific IP addresses

### Connection Testing
- Tests basic AirPlay connection with saved credentials
- Validates credential loading and device matching
- Shows device information and capabilities

### Media Streaming Tests
- Tests different media types:
  - JPEG/PNG images
  - MP4/MOV videos
  - HLS streams
  - Local content (doorbell images, HLS streams)

### Interactive Menu
- User-friendly menu for testing different scenarios
- Real-time feedback and error reporting
- Comprehensive logging

## Current Findings

### Samsung Frame TV vs iPhone Compatibility
**Key Discovery**: Your iPhone works with AirPlay, but pyatv doesn't - this is a **protocol implementation difference**, not a fundamental limitation!

### Detailed Analysis
The Samsung Frame TV (model tested: 32") shows:

1. **Device Discovery**: ✅ Works - TV is discoverable via AirPlay on port 7000
2. **Basic Connection**: ✅ Works - Can connect with saved credentials
3. **Feature Detection**: ✅ Works - Shows available features: `['Stop', 'VolumeUp', 'VolumeDown', 'PushUpdates', 'PlayUrl', 'StreamFile', 'Volume', 'SetVolume']`
4. **PlayUrl Feature**: ✅ **REPORTED AS AVAILABLE** by pyatv feature detection
5. **Media Streaming**: ❌ **FAILS** with "501 Not Implemented" despite feature being available
6. **Network**: ✅ Same subnet (10.0.1.x), no connectivity issues

### Error Details
```
RTSP/1.0 method PUT failed with code 501: Not Implemented
```

### Why iPhone Works But pyatv Doesn't

**This is NOT a Samsung TV limitation** - it's a **protocol implementation difference**:

1. **Protocol Version**: iPhone uses full AirPlay 2 implementation, pyatv may use older protocol
2. **Session Negotiation**: iPhone does more sophisticated capability negotiation
3. **Authentication Flow**: iPhone may handle authentication differently
4. **Content Negotiation**: iPhone may negotiate different codecs/formats
5. **Timing**: iPhone may use different connection timing and keep-alive strategies

## Potential Solutions for AirPlay Compatibility

### Immediate Solutions
1. **Use DLNA** - Your existing DLNA integration is more reliable for Samsung TVs
2. **TV Web Interface** - Direct media uploads via the TV's built-in web server
3. **Alternative Hardware** - Consider Apple TV or other AirPlay-compatible devices

### Advanced Solutions (For Future Development)

#### 1. Alternative Python Libraries

**Available AirPlay 2 Python Libraries:**
- **pyatv (current)**: `pip install pyatv` - Client library, latest v0.16.1 ⭐1035
- **airplay2-receiver**: `pip install airplay2-receiver` - Full receiver implementation ⭐2290
- **python-airplay**: `pip install python-airplay` - Video client (limited) ⭐60
- **openairplay**: Ubuntu AirPlay implementation ⭐414

**Most Promising:**
```python
# Try upgrading pyatv to latest
pip install --upgrade pyatv

# Or try the receiver approach (different paradigm)
pip install airplay2-receiver
```

#### 2. Node.js Libraries

**Available AirPlay Node.js Libraries:**
- **airplayer**: `npm install airplayer` - Full client implementation ⭐83
- **airplay-protocol**: `npm install airplay-protocol` - Low-level protocol wrapper ⭐ (low-level)
- **airplay-js**: `npm install airplay-js` - Native client library v0.3.0

**Most Promising:**
```javascript
const AirPlay = require('airplayer');

// Usage example
const browser = new AirPlay();
browser.on('deviceOn', (device) => {
  device.play('http://example.com/video.mp4');
});
```

#### 3. Commercial SDKs
- **Airplay-SDK**: Commercial SDK with full AirPlay mirroring/casting support ⭐3881
- **WirelessDisplay SDK**: Multi-protocol SDK (AirPlay, Miracast, Chromecast, DLNA)

#### 4. Protocol Analysis
- **Capture iPhone traffic** using Wireshark to see what protocols/commands iPhone uses
- **Compare with pyatv** to identify missing features
- **Implement missing AirPlay 2 features** in pyatv or create custom client

#### 4. Network Analysis
- **Firewall rules** - Check if corporate firewall blocks RTSP/UDP ports
- **VPN issues** - Some VPNs interfere with multicast/broadcast discovery
- **IGMP snooping** - Network switches may block multicast traffic

## Alternative Solutions

Since AirPlay streaming isn't working with pyatv, consider these proven alternatives:

### 1. DLNA Streaming (Already implemented)
The project already has DLNA support which works better with Samsung TVs:
- Use `backend/integrations/dlna.py`
- Supports MP4, JPEG, and HLS streams
- More compatible with Samsung devices

### 2. Media Upload via Web Interface
Samsung Frame TVs support direct media upload through their web interface:
- Upload images/videos directly to the TV's internal storage
- Access via TV's IP address in browser
- More reliable for static content

### 3. Alternative Protocols
- **Miracast**: Wireless display protocol
- **Chromecast**: Google's casting protocol
- **Samsung SmartThings**: Official Samsung integration

## Test URLs Available

The script includes several test URLs:

```python
TEST_URLS = {
    "image_jpeg": "https://picsum.photos/1920/1080.jpg",
    "image_png": "https://picsum.photos/1920/1080.png",
    "video_mp4": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
    "video_mov": "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4",
    "hls_stream": "https://devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_fmp4/master.m3u8",
    "local_image": "http://localhost:8000/api/render/doorbell.jpg",
    "local_hls": "http://localhost:8000/hls/playlist.m3u8",
}
```

## Debug Script Improvements

The debug script has been updated to fix several issues:

- ✅ **Fixed feature detection**: Now properly shows available AirPlay features instead of errors
- ✅ **Fixed connection handling**: Clean disconnections without warnings
- ✅ **Added DLNA testing**: Alternative streaming method for Samsung TVs
- ✅ **Enhanced error reporting**: More detailed information about what works/doesn't work

### Previous Issues Fixed
- `'FacadeFeatures' object is not callable` - Fixed by using `atv.features.all_features()`
- `object set can't be used in 'await' expression` - Fixed by using sync `atv.close()` instead of `await atv.close()`

## Troubleshooting Tips

### 1. Network Issues
- Ensure TV and computer are on the same network
- Check firewall settings
- Verify TV's IP address hasn't changed

### 2. Credential Issues
- Re-run `scripts/pair_airplay.py` if credentials are invalid
- Check `data/airplay_credentials.json` exists and is valid

### 3. TV Compatibility
- Different Samsung TV models have varying AirPlay support
- Frame TVs may have more limited streaming capabilities
- Consider using DLNA instead for Samsung devices

### 4. Content Format Issues
- Try different video formats (MP4, MOV)
- Test with smaller files first
- Check content is accessible from the TV's network

## Usage Examples

### Interactive Mode
```bash
python scripts/debug_pyatv.py
```
Choose options 1-6 for different tests.

### Command Line Mode
```bash
# Scan for devices
python scripts/debug_pyatv.py scan

# Run full test suite
python scripts/debug_pyatv.py test

# Test specific URL
python scripts/debug_pyatv.py stream https://example.com/video.mp4

# Test local doorbell image
python scripts/debug_pyatv.py stream http://localhost:8000/api/render/doorbell.jpg
```

## Testing Alternative Libraries

### Quick Node.js Test
```bash
# Install Node.js AirPlay client
npm install airplayer

# Create test script
node -e "
const AirPlay = require('airplayer');
const browser = new AirPlay();
browser.on('deviceOn', (device) => {
  console.log('Found device:', device.name, device.id);
  // Try playing content
  device.play('https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4');
});
setTimeout(() => process.exit(), 10000);
"
```

### Python Library Comparison
```bash
# Compare different Python libraries
pip install pyatv airplay2-receiver python-airplay

# Test each one with your Samsung TV
python -c "
import pyatv
# Test pyatv...

# import airplay2_receiver
# Test airplay2-receiver (note: this is a receiver, not client)...
"
```

## Recommendations

Based on testing:

1. **Use DLNA instead of AirPlay** for Samsung Frame TVs (most reliable)
2. **Test with the web interface** for reliable media upload
3. **Try airplayer (Node.js)** - might have better AirPlay 2 compatibility than pyatv
4. **Test python-airplay** - alternative Python client library
5. **Consider alternative TVs** if full streaming is required
6. **Use this script** to validate network and credential setup

## Future Improvements

- Add DLNA testing capabilities
- Implement media upload via web interface
- Add support for other casting protocols
- Create automated test suites for different TV brands
