#!/usr/bin/env python3
"""
Pybricks BLE Broadcast Receiver & Live Logger for Host PC (macOS / Linux / Windows)
KIT SYDSEN Seminar - Lecture 2: Data-Driven ABM & Digital Twin

Listens for BLE broadcast advertisements from Pybricks robots (Channel 1, 2, ...).
Decodes telemetry tuples: (robot_id, time_stamp, sir_state, zone, seq_num)
Writes entries in real-time.
When no broadcast is received for INACTIVITY_TIMEOUT_SECONDS (default 10s),
it closes and saves the run into a timestamped JSON file.
"""

import asyncio
import os
import sys
import time
import json
import struct
from datetime import datetime
from bleak import BleakScanner

LEGO_COMPANY_ID = 0x0397  # LEGO System A/S (0x97, 0x03 in little-endian)
INACTIVITY_TIMEOUT_SECONDS = 10.0
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

def decode_pybricks_payload(data: bytes):
    """
    Decodes Pybricks Manufacturer Specific Data payload according to the
    Pybricks BLE Broadcast/Observe specification.
    Returns: (channel, list_of_decoded_values) or None
    """
    if len(data) < 1:
        return None

    channel = data[0]
    index = 1
    values = []

    while index < len(data):
        header = data[index]
        index += 1

        val_type = header >> 5
        length = header & 0x1F

        if index + length > len(data):
            break

        raw_val = data[index : index + length]
        index += length

        if val_type == 0:  # SINGLE_OBJECT flag
            continue
        elif val_type == 1:  # True
            values.append(True)
        elif val_type == 2:  # False
            values.append(False)
        elif val_type == 3:  # int
            if length == 1:
                val = struct.unpack("b", raw_val)[0]
            elif length == 2:
                val = struct.unpack("<h", raw_val)[0]
            elif length == 4:
                val = struct.unpack("<i", raw_val)[0]
            else:
                val = int.from_bytes(raw_val, "little", signed=True)
            values.append(val)
        elif val_type == 4:  # float
            if length == 4:
                val = round(struct.unpack("<f", raw_val)[0], 2)
                values.append(val)
        elif val_type == 5:  # string
            try:
                values.append(raw_val.decode("utf-8"))
            except Exception:
                values.append(str(raw_val))
        elif val_type == 6:  # bytes
            values.append(raw_val)

    return channel, values

class RunLogger:
    def __init__(self, timeout_s=INACTIVITY_TIMEOUT_SECONDS, output_dir=OUTPUT_DIR):
        self.timeout_s = timeout_s
        self.output_dir = output_dir
        self.current_run_entries = []
        self.seen_signatures = set()
        self.last_packet_time = None
        self.run_started = False
        self.run_number = 1

    def handle_packet(self, channel, values):
        now = time.time()

        # Handle Start signal or telemetry tuple
        # Values can be ["START"] or [robot_id, time_stamp, sir_state, zone, seq_num]
        if not values:
            return

        # Case 1: START broadcast
        if values[0] == "START" or (len(values) == 1 and values[0] == "START"):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚡ BLE START Broadcast detected on Channel {channel}!")
            self.last_packet_time = now
            self.run_started = True
            entry = {
                "Time_Stamp": 0.0,
                "ID": channel,
                "Event": "Start_Signal",
                "Zone": "0",
                "SIR_State": "—",
                "Contact_ID": "—",
                "Agent_Type": "—",
                "Vaccinated": "—"
            }
            self.current_run_entries.append(entry)
            return

        # Case 2: Telemetry tuple: (robot_id, elapsed_s, sir_state, zone, seq_num)
        if len(values) >= 5:
            robot_id, elapsed_s, sir_state, zone, seq = values[:5]

            # Deduplicate repeated advertising packets
            sig = (robot_id, seq)
            if sig in self.seen_signatures:
                return
            self.seen_signatures.add(sig)

            self.last_packet_time = now
            self.run_started = True

            entry = {
                "Time_Stamp": float(elapsed_s),
                "ID": int(robot_id),
                "Event": "Sample",
                "Zone": str(zone),
                "SIR_State": str(sir_state),
                "Contact_ID": "—",
                "Agent_Type": "A" if int(robot_id) % 2 == 1 else "B",
                "Vaccinated": "No"
            }
            self.current_run_entries.append(entry)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📡 Received Robot {robot_id} | t={elapsed_s:4.1f}s | Zone {zone} | State {sir_state}")

    def save_run(self):
        if not self.current_run_entries:
            return None

        os.makedirs(self.output_dir, exist_ok=True)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"run_{self.run_number:02d}_{timestamp_str}.json"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w") as f:
            json.dump(self.current_run_entries, f, indent=2)

        print(f"\n==========================================")
        print(f"✅ RUN {self.run_number} SAVED: {filepath}")
        print(f"📊 Total log entries collected: {len(self.current_run_entries)}")
        print(f"==========================================\n")

        self.run_number += 1
        self.current_run_entries = []
        self.seen_signatures.clear()
        self.last_packet_time = None
        self.run_started = False
        return filepath

async def run_ble_listener():
    logger = RunLogger()

    def detection_callback(device, advertisement_data):
        mfg_data = advertisement_data.manufacturer_data
        if LEGO_COMPANY_ID in mfg_data:
            raw_bytes = mfg_data[LEGO_COMPANY_ID]
            decoded = decode_pybricks_payload(raw_bytes)
            if decoded is not None:
                channel, values = decoded
                logger.handle_packet(channel, values)

    scanner = BleakScanner(detection_callback=detection_callback)
    print("================================================================")
    print("  Pybricks BLE Live Receiver & Auto-Run Saver")
    print("  Listening for Robot 1, 2, ... broadcasts...")
    print(f"  Timeout: Saves run automatically after {INACTIVITY_TIMEOUT_SECONDS}s of no logs.")
    print("================================================================\n")

    await scanner.start()
    try:
        while True:
            await asyncio.sleep(1.0)
            if logger.run_started and logger.last_packet_time is not None:
                elapsed_since_last = time.time() - logger.last_packet_time
                if elapsed_since_last >= INACTIVITY_TIMEOUT_SECONDS:
                    print(f"\n[TIMEOUT] No broadcast received for {elapsed_since_last:.1f}s. Ending run...")
                    logger.save_run()
                    print("Listening for the next run...\n")
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopping BLE listener...")
        if logger.run_started and logger.current_run_entries:
            logger.save_run()
    finally:
        await scanner.stop()

if __name__ == "__main__":
    try:
        asyncio.run(run_ble_listener())
    except KeyboardInterrupt:
        pass

