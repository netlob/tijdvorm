# Debug Tools

This directory contains debugging and troubleshooting tools for the tijdvorm project.

## Subdirectories

### `airplay/`
Comprehensive AirPlay debugging tools for Samsung Frame TV compatibility testing.

- `debug_pyatv.py` - Python script for testing pyatv library with Samsung TVs
- `test_airplayer.js` - Node.js alternative AirPlay client testing
- `README.md` - Detailed AirPlay troubleshooting guide

**Key findings:**
- DLNA works reliably with Samsung Frame TVs
- AirPlay works with iPhone but not with client libraries
- Issue is Samsung TV firmware/protocol compatibility

### `dlna/`
DLNA performance and reliability testing tools.

- `quick_test.py` - Fast DLNA functionality testing
- `test_dlna_performance.py` - Comprehensive performance benchmarking
- `test_dlna_discovery.py` - DLNA device discovery and compatibility testing
- `README.md` - DLNA testing guide and performance benchmarks

**Capabilities:**
- Speed testing (image/video loading times)
- Reliability testing (success rates over time)
- Device discovery validation
- Network diagnostics

### Other Files
- Various debug images and snapshots from camera testing
- Temporary files used for troubleshooting

## Quick Start

```bash
# AirPlay diagnostics
cd airplay
python debug_pyatv.py

# Node.js alternative
npm install
node test_airplayer.js
```
