import asyncio
import pyatv
import logging
import sys

# logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

async def debug():
    print("Scanning...")
    results = await pyatv.scan(loop=asyncio.get_event_loop())
    
    if results:
        conf = results[0] # Just pick first
        print(f"Connecting to {conf.name}...")
        try:
            atv = await pyatv.connect(conf, loop=asyncio.get_event_loop())
            print("Connected.")
            
            # Skip play_url for now, just test close
            print("Closing...")
            try:
                await atv.close()
                print("Closed successfully.")
            except TypeError as e:
                print(f"Close failed with TypeError: {e}")
            except Exception as e:
                print(f"Close failed with {type(e)}: {e}")
                
        except Exception as e:
            print(f"Connect failed: {e}")

if __name__ == "__main__":
    asyncio.run(debug())
