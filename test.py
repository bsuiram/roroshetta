import asyncio
from bleak import BleakClient, BleakScanner
import struct
from datetime import datetime
import csv

DEVICE_NAME = "Roroshetta Sense"
BEEF = "0000BEEF-1212-EFDE-1523-785FEF13D123" # notify env

def decode_env1(data: bytes):
    """
    Decode 0000BEEF environmental payload (≈ 54 bytes).
    Uses confirmed field order and scaling from dumps and app screenshots.
    """
    global call_count
    call_count += 1
    output_env = True
    print_bit  = False
    print_all  = False

    def get_u16_le(offset,w_len=2): return int.from_bytes(data[offset:offset+w_len], "little")

    # monitor values from specific bytes in byte array (data)
    if print_bit:
        bits = [46,47]
        print("Dec: ", end="")
        for bit in bits:
            dec_val = data[bit]
            print(f"[{bit}]:{dec_val:<3} ", end="" )

        print("Hex: ", end="")
        for bit in bits:
            hex_val = hex(data[bit])
            print(f"[{bit}]:{hex_val:<5} ", end="" )            
        #print()
        dec_total_val = get_u16_le(46,2)
        print(f" dec value : {dec_total_val}")

    # monitor values from all values non mapped (known) bytes in byte array
    known=[0,1,2,3,4,5,10,11,13,14,15,16,17,18,36,37,38,44,45,46,47,53,56,59]
    if print_all:
        n=10
        if (call_count) % n == 0 or call_count == 1:
            for index, element in enumerate(data):
                if index not in known:
                    print(f"[{index:02}] " , end="")
            print()

        for index, element in enumerate(data):
            if index not in known:
                #print(element:02x)
                if element not in []:
                #if element not in [0,255]:
                    #print(f"[{index:02}]:{element:<3} " , end="")
                    print(f"{hex(element):<4} " , end="")
                    #print(f"- {element:08b} ", end ="")
        #line += 1
        print()
    
    # Read sensors:    
    temperature   = (get_u16_le(0,2) + 10000) /100 - 150
    heat_index    = (get_u16_le(2,2) + 10000) /100 - 150
    humidity      = get_u16_le(4,2) / 100
    aqi           = get_u16_le(10,2)
    pm25          = get_u16_le(13,2) / 1000
    co2           = get_u16_le(15,2)
    tvoc          = get_u16_le(17,2)
    uptime        = get_u16_le(36,3)
    alarm_level   = get_u16_le(44,1) # unsure
    activity      = get_u16_le(45,1) # unsure
    power         = get_u16_le(46,2)
    light         = get_u16_le(53,1) / 30
    fan           = get_u16_le(56,1) / 30
    grease_filter = get_u16_le(59,1) # unsure
    
    if output_env:
        env = {
            "Temperature (°C)": round(temperature, 1),
            "Heat Index": round(heat_index, 1),
            "Humidity (%)": round(humidity, 1),
            "CO₂ (ppm)": co2,
            "tVOC (µg/m³)": tvoc,
            "PM2.5 (µg/m³)": round(pm25, 1),
            "Air Quality Index": aqi,
            "Grease Filter (%)": grease_filter,
            "Light (level)": round(light),
            "Fan (level)": round(fan),
            "Activity": activity,
            "Alarm level (%)": alarm_level,
            "Power (W)": power,
            "Uptime (s)": uptime
        }
        print(f"{env}")


async def poll_all():
    print(f"🔍 Scanning for {DEVICE_NAME} ...")
    device = await BleakScanner.find_device_by_filter(lambda d, _: d.name == DEVICE_NAME)
    if not device:
        print("❌ Device not found. Make sure the hood is on and advertising.")
        return
    print(f"🔗 Found {DEVICE_NAME} ({device.address})")
    

    async with BleakClient(device.address, timeout=15.0) as client:
        print(f"✅ Connected to {DEVICE_NAME}")
        start_time = asyncio.get_event_loop().time()

        def handle_notify_env1(_, data):
            #decoded_env1 = decode_env1(data)
            decode_env1(data)

        try:
            await client.start_notify(BEEF, handle_notify_env1)
        except Exception as e:
            print("⚠️ Could not enable ENV1 notifications:", e)

# ------------------- Main -------------------

if __name__ == "__main__":
    call_count = 0
    asyncio.run(poll_all())
