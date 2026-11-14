#!/usr/bin/env python3
"""
KIT SYDSEN Seminar - Lecture 2: Data-Driven ABM & Digital Twin
Central Hub: 100% Connectionless BLE Broadcast Controller & Telemetry Receiver

Architecture (No BLE GATT Connections):
- Outgoing (Channel 0):
  Uses Windows WinRT BluetoothLEAdvertisementPublisher to broadcast START (1)
  and STOP (2) commands on Pybricks BLE Channel 0 (Manufacturer ID 0x0397).
  All robots observe ONLY Channel 0.
- Incoming (Channels 1..10):
  Uses BleakScanner to passively observe telemetry broadcasts emitted by
  Robots 1..10 on Channels 1..10.
- Auto-Save:
  Saves each run to logs/run_XX_YYYYMMDD_HHMMSS.json when stopped or after
  10 seconds without telemetry packets.
"""

import asyncio
import os
import sys
import time
import json
import struct
from datetime import datetime
from bleak import BleakScanner

# ==============================================================================
# Pybricks BLE Broadcast Constants & Channel Allocation
# ==============================================================================
LEGO_COMPANY_ID = 0x0397          # LEGO System A/S (0x97, 0x03 little-endian)
LAPTOP_BROADCAST_CHANNEL = 0      # Laptop broadcasts commands on Channel 0
ROBOT_OBSERVE_CHANNELS = set(range(1, 11))  # Laptop listens to Channels 1..10

CMD_START = 1
CMD_STOP = 2

INACTIVITY_TIMEOUT_SECONDS = 10.0
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


# ==============================================================================
# Pybricks BLE Broadcast Payload Encoder & Decoder (Channel + Typed Values)
# ==============================================================================
def _encode_single_value(val) -> bytes:
    """Encodes a single Python scalar value using the Pybricks BLE header format."""
    if val is True:
        return bytes([(1 << 5) | 0])
    elif val is False:
        return bytes([(2 << 5) | 0])
    elif isinstance(val, int):
        if -128 <= val <= 127:
            return bytes([(3 << 5) | 1]) + struct.pack("<b", val)
        elif -32768 <= val <= 32767:
            return bytes([(3 << 5) | 2]) + struct.pack("<h", val)
        else:
            return bytes([(3 << 5) | 4]) + struct.pack("<i", val)
    elif isinstance(val, float):
        return bytes([(4 << 5) | 4]) + struct.pack("<f", val)
    elif isinstance(val, str):
        raw = val.encode("utf-8")[:31]
        return bytes([(5 << 5) | len(raw)]) + raw
    elif isinstance(val, (bytes, bytearray)):
        raw = bytes(val)[:31]
        return bytes([(6 << 5) | len(raw)]) + raw
    else:
        raise TypeError(f"Unsupported Pybricks broadcast type: {type(val)}")


def encode_pybricks_payload(channel: int, data) -> bytes:
    """
    Encodes a channel (0..255) and data object/tuple into the raw payload bytes
    for Manufacturer Specific Data (Company ID 0x0397).
    """
    if not (0 <= channel <= 255):
        raise ValueError("Channel must be between 0 and 255")

    out = bytearray([channel])
    if isinstance(data, (tuple, list)):
        for item in data:
            out.extend(_encode_single_value(item))
    else:
        # SINGLE_OBJECT indicator (type=0, length=0 -> 0x00)
        out.append(0x00)
        out.extend(_encode_single_value(data))

    if len(out) > 26:
        raise ValueError(f"Encoded Pybricks broadcast payload exceeds 26 bytes ({len(out)} bytes)")
    return bytes(out)


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
                val = struct.unpack("<b", raw_val)[0]
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


# ==============================================================================
# Connectionless BLE Broadcaster (Channel 0 -> All Robots)
# ==============================================================================
def _create_winrt_publisher(payload: bytes):
    """
    Creates a Windows BluetoothLEAdvertisementPublisher configured with
    LEGO Company ID (0x0397) and the given Pybricks payload bytes.
    Uses winrt (installed automatically with bleak on Windows) or winsdk.
    """
    try:
        from winrt.windows.devices.bluetooth.advertisement import (
            BluetoothLEAdvertisementPublisher,
            BluetoothLEManufacturerData,
        )
        from winrt.windows.storage.streams import Buffer, DataWriter

        try:
            buf = Buffer(len(payload))
            buf.length = buf.capacity
            with memoryview(buf) as mv:
                mv[:] = payload
        except Exception:
            writer = DataWriter()
            writer.write_bytes(payload)
            buf = writer.detach_buffer()

        mfg = BluetoothLEManufacturerData(LEGO_COMPANY_ID, buf)
        pub = BluetoothLEAdvertisementPublisher()
        pub.advertisement.manufacturer_data.append(mfg)
        return pub
    except ImportError:
        from winsdk.windows.devices.bluetooth.advertisement import (
            BluetoothLEAdvertisementPublisher,
            BluetoothLEManufacturerData,
        )
        from winsdk.windows.storage.streams import DataWriter

        writer = DataWriter()
        writer.write_bytes(list(payload))
        buf = writer.detach_buffer()

        mfg = BluetoothLEManufacturerData()
        mfg.company_id = LEGO_COMPANY_ID
        mfg.data = buf

        pub = BluetoothLEAdvertisementPublisher()
        pub.advertisement.manufacturer_data.append(mfg)
        return pub


class ChannelZeroBroadcaster:
    """Broadcasts connectionless Pybricks commands on BLE Channel 0."""

    def __init__(self, channel: int = LAPTOP_BROADCAST_CHANNEL):
        self.channel = channel
        self._publisher = None

    def stop(self):
        if self._publisher is not None:
            try:
                self._publisher.stop()
            except Exception:
                pass
            self._publisher = None

    async def broadcast_command(self, value, duration_s: float = 1.8) -> bool:
        """
        Broadcasts `value` on Channel 0 for `duration_s` seconds, then stops.
        Returns True if transmitted over BLE hardware, False if unsupported OS.
        """
        self.stop()
        payload = encode_pybricks_payload(self.channel, value)

        if sys.platform != "win32":
            print(
                f"⚠️ [OS Notice] Raw BLE Manufacturer Data advertising requires Windows (current OS: {sys.platform}).\n"
                f"   Encoded Channel {self.channel} payload: {payload.hex()}"
            )
            return False

        try:
            pub = _create_winrt_publisher(payload)
            pub.start()
            self._publisher = pub
            await asyncio.sleep(duration_s)
            return True
        except Exception as e:
            print(f"❌ Failed to broadcast on BLE Channel {self.channel}: {type(e).__name__}: {e}")
            return False
        finally:
            self.stop()


# ==============================================================================
# Central Hub Logger (Observes Channels 1..10, Broadcasts on Channel 0)
# ==============================================================================
class CentralHub:
    def __init__(
        self,
        timeout_s=INACTIVITY_TIMEOUT_SECONDS,
        output_dir=OUTPUT_DIR,
        observe_channels=ROBOT_OBSERVE_CHANNELS,
    ):
        self.timeout_s = timeout_s
        self.output_dir = output_dir
        self.observe_channels = set(observe_channels)
        self.broadcaster = ChannelZeroBroadcaster(LAPTOP_BROADCAST_CHANNEL)

        self.standby_robots = {}     # robot_id -> (channel, sir_state, last_seen)
        self.current_run_entries = []
        self.seen_signatures = set() # (robot_id, seq_num)
        self.last_packet_time = None
        self.run_started = False
        self.run_number = 1
        self._running = True

    def record_entry(self, entry, seq_num=None):
        """Deduplicates and stores a telemetry event from Channels 1..10."""
        sig = (
            (entry["ID"], seq_num)
            if seq_num is not None
            else (entry["ID"], entry["Time_Stamp"], entry["Event"])
        )
        if sig in self.seen_signatures:
            return

        self.seen_signatures.add(sig)
        self.current_run_entries.append(entry)
        self.last_packet_time = time.time()
        self.run_started = True

        time_str = datetime.now().strftime("%H:%M:%S")
        print(
            f"[{time_str}] 📡 Ch {entry['ID']:2d} | Robot {entry['ID']} | "
            f"t={entry['Time_Stamp']:5.1f}s | State: {entry['SIR_State']:1} | "
            f"Zone: {entry['Zone']} | Type: {entry['Agent_Type']}"
        )

    def handle_broadcast_packet(self, channel: int, values: list):
        """
        Processes connectionless BLE broadcast advertisements.
        Strictly listens ONLY to Channels 1..10 (ignores Channel 0).
        """
        if channel not in self.observe_channels or not values:
            return

        # Case 1: STANDBY heartbeat from robot ("STANDBY", ROBOT_ID, sir_state)
        if values[0] == "STANDBY":
            rid = int(values[1]) if len(values) >= 2 else channel
            state = str(values[2]) if len(values) >= 3 else "?"
            is_new = rid not in self.standby_robots
            self.standby_robots[rid] = (channel, state, time.time())
            if is_new:
                time_str = datetime.now().strftime("%H:%M:%S")
                print(
                    f"[{time_str}] 🟠 Robot {rid} (Channel {channel}) READY in Standby | SIR State: {state}"
                )
            return

        # Case 2: Telemetry tuple: (robot_id, elapsed_s, sir_state, zone, seq_num)
        if len(values) >= 4 and not isinstance(values[0], str):
            robot_id = int(values[0])
            elapsed_s = float(values[1])
            sir_state = str(values[2])
            zone = str(values[3])
            seq_num = int(values[4]) if len(values) >= 5 else None

            self.record_entry(
                {
                    "Time_Stamp": elapsed_s,
                    "ID": robot_id,
                    "Event": "Sample",
                    "Zone": zone,
                    "SIR_State": sir_state,
                    "Contact_ID": "—",
                    "Agent_Type": "A" if robot_id % 2 == 1 else "B",
                    "Vaccinated": "No",
                },
                seq_num=seq_num,
            )

    async def start_all(self):
        """Broadcasts START command on BLE Channel 0 to all robots."""
        print("\n" + "=" * 60)
        print(f"🚀 BROADCASTING 'START' ON BLE CHANNEL {LAPTOP_BROADCAST_CHANNEL} TO ALL ROBOTS...")
        print("=" * 60)

        self.run_started = True
        self.last_packet_time = time.time()

        ok = await self.broadcaster.broadcast_command(CMD_START, duration_s=1.8)
        if ok:
            print(f"✅ START broadcast finished! Run #{self.run_number} is now live (listening on Ch 1..10).\n")

    async def stop_all(self):
        """Broadcasts STOP command on BLE Channel 0 to all robots."""
        print("\n" + "=" * 60)
        print(f"🛑 BROADCASTING 'STOP' ON BLE CHANNEL {LAPTOP_BROADCAST_CHANNEL} TO ALL ROBOTS...")
        print("=" * 60)

        ok = await self.broadcaster.broadcast_command(CMD_STOP, duration_s=1.8)
        if ok:
            print("✅ STOP broadcast finished! All robots halted.")

        await asyncio.sleep(0.5)
        if self.current_run_entries:
            self.save_run()
        else:
            self.run_started = False
            self.last_packet_time = None

    def save_run(self):
        """Saves current run entries into a timestamped JSON file."""
        if not self.current_run_entries:
            return None

        os.makedirs(self.output_dir, exist_ok=True)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"run_{self.run_number:02d}_{timestamp_str}.json"
        filepath = os.path.join(self.output_dir, filename)

        sorted_entries = sorted(
            self.current_run_entries, key=lambda x: (x["Time_Stamp"], x["ID"])
        )

        with open(filepath, "w") as f:
            json.dump(sorted_entries, f, indent=2)

        robot_counts = {}
        for e in sorted_entries:
            rid = e["ID"]
            robot_counts[rid] = robot_counts.get(rid, 0) + 1

        print("\n" + "=" * 60)
        print(f"✅ RUN #{self.run_number} COMPLETE & SAVED!")
        print(f"📁 File: {filepath}")
        print(f"📊 Total log entries: {len(sorted_entries)}")
        for rid, count in sorted(robot_counts.items()):
            print(f"   • Robot {rid} (Channel {rid}): {count} rows")
        print("=" * 60 + "\n")

        self.run_number += 1
        self.current_run_entries = []
        self.seen_signatures.clear()
        self.standby_robots.clear()
        self.last_packet_time = None
        self.run_started = False
        print("🎯 Ready for the next run. Press 's' + ENTER to broadcast START!\n")
        return filepath


# ==============================================================================
# Interactive Terminal & Async Event Loop
# ==============================================================================
def print_help():
    print(
        """
================================================================
  KIT SYDSEN - LEGO SPIKE Digital Twin Central Hub (Broadcast)
  • Outgoing Control : BLE Channel 0 (All robots observe Ch 0)
  • Incoming Logs    : BLE Channels 1..10 (1 channel per robot)
  • Connections      : NONE (100% Connectionless BLE Broadcast)
================================================================
  [s] or ENTER : Broadcast START on Channel 0 (starts all robots)
  [x] or [q]   : Broadcast STOP on Channel 0 (halts all robots)
  [status]     : Show standby robots & current run statistics
  [save]       : Force save current run to JSON immediately
  [help]       : Show this menu
  [exit]       : Quit program
  Auto-Save    : Automatically saves run after 10s without logs
================================================================
"""
    )


def print_status(hub: CentralHub):
    print("\n--- Central Hub Broadcast Status ---")
    print(f"Outgoing Channel : {LAPTOP_BROADCAST_CHANNEL}")
    print(f"Listening Channels: 1..10")
    print(f"Robots Seen in Standby ({len(hub.standby_robots)}):")
    if not hub.standby_robots:
        print("  • (None detected yet - start agent_robot.py on the hubs)")
    else:
        for rid, (ch, state, ts) in sorted(hub.standby_robots.items()):
            ago = time.time() - ts
            print(f"  • Robot {rid} (Channel {ch}) | State: {state} | seen {ago:.0f}s ago")
    print(f"Current Run      : #{hub.run_number}")
    print(f"Run Active       : {'YES' if hub.run_started else 'NO (Standby)'}")
    print(f"Buffered Entries : {len(hub.current_run_entries)}")
    print("------------------------------------\n")


async def keyboard_listener(hub: CentralHub):
    """Non-blocking console command loop."""
    print_help()
    while hub._running:
        try:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                break
            cmd = line.strip().lower()

            if cmd in ("s", "start", ""):
                await hub.start_all()
            elif cmd in ("x", "stop", "q"):
                await hub.stop_all()
            elif cmd in ("status", "list"):
                print_status(hub)
            elif cmd in ("save",):
                hub.save_run()
            elif cmd in ("h", "help"):
                print_help()
            elif cmd in ("exit", "quit"):
                hub._running = False
                break
        except Exception as e:
            print(f"Input error: {e}")


async def run_central_hub():
    hub = CentralHub()

    def ble_detection_callback(device, advertisement_data):
        mfg_data = advertisement_data.manufacturer_data
        if LEGO_COMPANY_ID in mfg_data:
            raw_bytes = mfg_data[LEGO_COMPANY_ID]
            decoded = decode_pybricks_payload(raw_bytes)
            if decoded is not None:
                channel, values = decoded
                hub.handle_broadcast_packet(channel, values)

    scanner = BleakScanner(detection_callback=ble_detection_callback)
    await scanner.start()
    print("📡 Passive BLE Scanner active on Channels 1..10 (waiting for robots in Standby)...")

    kb_task = asyncio.create_task(keyboard_listener(hub))

    try:
        while hub._running:
            await asyncio.sleep(0.5)

            # Auto-save after 10s of inactivity once telemetry has been received
            if (
                hub.run_started
                and hub.current_run_entries
                and hub.last_packet_time is not None
            ):
                elapsed = time.time() - hub.last_packet_time
                if elapsed >= hub.timeout_s:
                    print(
                        f"\n[AUTO-SAVE] No broadcasts on Channels 1..10 for {elapsed:.1f}s. Ending run..."
                    )
                    hub.save_run()

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nShutting down Central Hub...")
    finally:
        hub._running = False
        hub.broadcaster.stop()
        kb_task.cancel()
        await scanner.stop()
        if hub.current_run_entries:
            hub.save_run()
        print("Central Hub stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(run_central_hub())
    except KeyboardInterrupt:
        pass
