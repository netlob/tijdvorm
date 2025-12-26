import asyncio
import sys
import os
import json
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pyatv
from pyatv import scan
from backend.config import TV_IP, DATA_DIR

CREDENTIALS_FILE = os.path.join(DATA_DIR, "airplay_credentials.json")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("airplay_pair")

async def pair_device():
    print(f"Scanning for AirPlay devices (looking for TV at {TV_IP})...")
    results = await scan(loop=asyncio.get_event_loop())

    target_device = None
    
    if not results:
        print("No devices found.")
        return

    # Try to match by IP first
    for dev in results:
        if str(dev.address) == TV_IP:
            target_device = dev
            break
    
    # If not found by IP, list all and ask user
    if not target_device:
        print(f"Could not find device with IP {TV_IP}. Found devices:")
        for i, dev in enumerate(results):
            print(f"{i + 1}: {dev.name} ({dev.address})")
        
        try:
            selection = int(input("Select device number (or 0 to exit): "))
            if selection == 0:
                return
            target_device = results[selection - 1]
        except (ValueError, IndexError):
            print("Invalid selection.")
            return

    print(f"Selected device: {target_device.name} ({target_device.address})")

    # Start pairing
    pairing_handler = await pyatv.pair(
        config=target_device,
        protocol=pyatv.Protocol.AirPlay,
        loop=asyncio.get_event_loop()
    )

    print("--- PAIRING STARTED ---")
    print("Please check your TV for a PIN code.")
    
    await pairing_handler.begin()
    
    pin = input("Enter PIN code from TV: ")
    pairing_handler.pin(pin)

    await pairing_handler.finish()

    print("--- PAIRING SUCCESSFUL ---")
    
    # Save credentials
    creds = {
        "address": str(target_device.address),
        "name": target_device.name,
        "credentials": pairing_handler.service.credentials,
        "identifier": target_device.identifier
    }
    
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(creds, f, indent=2)
    
    print(f"Credentials saved to {CREDENTIALS_FILE}")
    print("You can now stream to the TV using AirPlay.")

if __name__ == "__main__":
    try:
        asyncio.run(pair_device())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")

