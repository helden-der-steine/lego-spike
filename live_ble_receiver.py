#!/usr/bin/env python3
"""
KIT SYDSEN Seminar - Lecture 2: Data-Driven ABM & Digital Twin
Central Hub: BLE Remote Controller & Telemetry Receiver for LEGO SPIKE Prime

Features:
1. Connects wirelessly to Pybricks Hubs over Bluetooth Low Energy (BLE).
2. Remote Start & Stop:
   - Press 's' (or ENTER): Sends wireless START signal to all robots simultaneously.
   - Press 'x' (or 'q'): Sends wireless STOP signal to all robots.
3. Live Telemetry Tracking:
   - Captures BLE broadcast advertising packets & GATT telemetry in real-time.
   - Deduplicates and formats tabular event logs.
4. Automatic Run Logger:
   - After 10s of inactivity (or upon stop), automatically compiles and saves
     the run to: logs/run_XX_YYYYMMDD_HHMMSS.json
   - Ready for consecutive experiment runs without restarting the script.
"""

import asyncio
import os
import sys
import time
import json
import struct
from datetime import datetime
from bleak import BleakScanner, BleakClient

# ==============================================================================
# Pybricks BLE UUIDs & Protocol Constants
# ==============================================================================
PYBRICKS_SERVICE_UUID = "c5f50001-8280-46da-89f4-6d8051e4aeef"
PYBRICKS_COMMAND_EVENT_UUID = "c5f50002-8280-46da-89f4-6d8051e4aeef"
PYBRICKS_HUB_CAPABILITIES_UUID = "c5f50003-8280-46da-89f4-6d8051e4aeef"
LEGO_COMPANY_ID = 0x0397  # LEGO System A/S

# Pybricks protocol command bytes:
# Command 0x06 = WRITE_STDIN, followed by input characters
CMD_START_STDIN = b"\x06S"
CMD_STOP_STDIN = b"\x06X"
CMD_STOP_PROGRAM = b"\x00"  # STOP_USER_PROGRAM opcode
CMD_START_PROGRAM = 0x01    # START_USER_PROGRAM opcode
STATUS_USER_PROGRAM_RUNNING = 0x40

INACTIVITY_TIMEOUT_SECONDS = 10.0
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# ==============================================================================
# Pybricks Broadcast Payload Decoder
# ==============================================================================
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

# ==============================================================================
# Central Hub Controller & Logger
# ==============================================================================
class CentralHub:
    def __init__(self, timeout_s=INACTIVITY_TIMEOUT_SECONDS, output_dir=OUTPUT_DIR):
        self.timeout_s = timeout_s
        self.output_dir = output_dir
        self.connected_clients = {}  # address -> BleakClient
        self.discovered_devices = {} # address -> BLEDevice
        self.hub_names = {}          # address -> name
        self.hub_num_slots = {}      # address -> int
        self.hub_selected_slot = {}  # address -> int
        self.hub_prog_running = {}   # address -> bool
        self.standby_robots = set()  # robot_ids detected via BLE broadcast
        self.current_run_entries = []
        self.seen_signatures = set()
        self.last_packet_time = None
        self.run_started = False
        self.run_number = 1
        self._running = True
        self.scanner = None
        self._scanner_active = False

    def record_entry(self, entry):
        """Deduplicates and stores a standard telemetry event."""
        sig = (entry["ID"], entry["Time_Stamp"], entry["Event"])
        if sig in self.seen_signatures:
            return

        self.seen_signatures.add(sig)
        self.current_run_entries.append(entry)
        self.last_packet_time = time.time()
        self.run_started = True

        time_str = datetime.now().strftime("%H:%M:%S")
        print(f"[{time_str}] 📡 Robot {entry['ID']} | t={entry['Time_Stamp']:4.1f}s | "
              f"State: {entry['SIR_State']:1} | Zone: {entry['Zone']} | Type: {entry['Agent_Type']}")

    def handle_broadcast_packet(self, channel, values):
        """Processes connectionless BLE broadcast advertisements."""
        if not values:
            return

        # Case 0: STANDBY broadcast heartbeat ("STANDBY", ROBOT_ID, sir_state)
        if values[0] == "STANDBY":
            rid = int(values[1]) if len(values) >= 2 else channel
            state = str(values[2]) if len(values) >= 3 else "?"
            if rid not in self.standby_robots:
                self.standby_robots.add(rid)
                time_str = datetime.now().strftime("%H:%M:%S")
                print(f"[{time_str}] 🟠 Robot {rid} detected in STANDBY via BLE broadcast (SIR State: {state})")
            return

        # Case 1: START broadcast signal (e.g. ["START"] or [CMD_START, "START"])
        if values == ["START"] or (len(values) <= 2 and "START" in values):
            if not self.run_started:
                time_str = datetime.now().strftime("%H:%M:%S")
                print(f"[{time_str}] ⚡ BLE START Broadcast detected on Channel {channel}!")
                self.record_entry({
                    "Time_Stamp": 0.0,
                    "ID": channel,
                    "Event": "Start_Signal",
                    "Zone": "0",
                    "SIR_State": "—",
                    "Contact_ID": "—",
                    "Agent_Type": "—",
                    "Vaccinated": "—"
                })
            return

        # Case 2: Telemetry tuple: (robot_id, elapsed_s, sir_state, zone, seq_num)
        if len(values) >= 4:
            robot_id = int(values[0])
            elapsed_s = float(values[1])
            sir_state = str(values[2])
            zone = str(values[3])

            self.record_entry({
                "Time_Stamp": elapsed_s,
                "ID": robot_id,
                "Event": "Sample",
                "Zone": zone,
                "SIR_State": sir_state,
                "Contact_ID": "—",
                "Agent_Type": "A" if robot_id % 2 == 1 else "B",
                "Vaccinated": "No"
            })

    def handle_stdout_data(self, sender, data: bytearray, address: str = None):
        """Parses status reports and stdout notifications from connected Pybricks hubs."""
        if not data:
            return

        # 0x00 is Event.STATUS_REPORT
        if data[0] == 0x00 and len(data) >= 5:
            flags = struct.unpack_from("<I", data, 1)[0]
            if address:
                self.hub_prog_running[address] = bool(flags & STATUS_USER_PROGRAM_RUNNING)
                if len(data) >= 7:
                    self.hub_selected_slot[address] = data[6]
            return

        if data[0] != 0x01:
            return  # 0x01 is WRITE_STDOUT

        text = data[1:].decode("utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("Time_Stamp") or line.startswith("==="):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 8:
                try:
                    entry = {
                        "Time_Stamp": float(parts[0]),
                        "ID": int(parts[1]),
                        "Event": parts[2],
                        "Zone": parts[3],
                        "SIR_State": parts[4],
                        "Contact_ID": parts[5],
                        "Agent_Type": parts[6],
                        "Vaccinated": parts[7]
                    }
                    self.record_entry(entry)
                except ValueError:
                    pass

    async def start_hub_program_if_needed(self, address, client):
        """Starts the stored user program on the hub so it enters Standby mode."""
        if self.hub_prog_running.get(address, False):
            return
        num_slots = self.hub_num_slots.get(address, 0)
        slot = self.hub_selected_slot.get(address, 0)
        cmd = struct.pack("<B", CMD_START_PROGRAM) if num_slots == 0 else struct.pack("<BB", CMD_START_PROGRAM, slot)
        try:
            await client.write_gatt_char(PYBRICKS_COMMAND_EVENT_UUID, cmd, response=True)
            await asyncio.sleep(0.4)
        except Exception:
            pass

    async def connect_to_hub(self, device):
        """Connects to a single Pybricks Hub."""
        address = device.address
        name = device.name or f"Pybricks Hub ({address[-5:]})"

        if address in self.connected_clients and self.connected_clients[address].is_connected:
            return

        print(f"🔗 Connecting to {name} [{address}]...")
        client = BleakClient(device, disconnected_callback=self._on_disconnect)
        try:
            await client.connect(timeout=10.0)
            self.connected_clients[address] = client
            self.hub_names[address] = name

            # Read hub capabilities to know if slot byte is required for START_USER_PROGRAM
            try:
                caps = await client.read_gatt_char(PYBRICKS_HUB_CAPABILITIES_UUID)
                self.hub_num_slots[address] = caps[10] if len(caps) == 11 else 0
            except Exception:
                self.hub_num_slots[address] = 0

            # Subscribe to status + stdout notifications
            try:
                await client.start_notify(
                    PYBRICKS_COMMAND_EVENT_UUID,
                    lambda s, d, a=address: self.handle_stdout_data(s, d, a),
                )
                await asyncio.sleep(0.2)
            except Exception:
                pass

            # Launch the stored user program into Standby (Orange light) if not already running
            await self.start_hub_program_if_needed(address, client)

            print(f"🟢 Successfully connected to {name}! (Ready in Standby)")
        except Exception as e:
            print(f"⚠️ Could not connect to {name}: {type(e).__name__} {e}")

    def _on_disconnect(self, client):
        address = client.address
        name = self.hub_names.get(address, address)
        print(f"\n🔌 Disconnected from {name}")
        self.connected_clients.pop(address, None)
        self.hub_prog_running.pop(address, None)

    def register_advertisement(self, device, advertisement_data):
        """Checks if an advertised device is a Pybricks/SPIKE hub and records it."""
        name = (device.name or getattr(advertisement_data, "local_name", None) or "").lower()
        uuids = [str(u).lower() for u in (getattr(advertisement_data, "service_uuids", None) or [])]
        mfg_data = getattr(advertisement_data, "manufacturer_data", None) or {}

        if (
            PYBRICKS_SERVICE_UUID.lower() in uuids
            or LEGO_COMPANY_ID in mfg_data
            or "pybrick" in name
            or "spike" in name
            or "robot" in name
        ):
            self.discovered_devices[device.address] = device

    async def scan_and_connect(self):
        """Scans for nearby Pybricks Hubs and connects to them."""
        print("🔍 Scanning for Pybricks Hubs (3s)...")
        if self._scanner_active:
            await asyncio.sleep(3.0)
        else:
            discovered = await BleakScanner.discover(timeout=3.0, return_adv=True)
            for addr, (d, adv) in discovered.items():
                self.register_advertisement(d, adv)

        unconnected = [
            d for addr, d in self.discovered_devices.items()
            if addr not in self.connected_clients or not self.connected_clients[addr].is_connected
        ]

        if not unconnected:
            if self.connected_clients:
                print(f"ℹ️ {len(self.connected_clients)} hub(s) already connected. No additional hubs found.")
            else:
                print("ℹ️ No connectable Pybricks Hubs found.")
                print("   💡 IMPORTANT: Make sure each hub has a BLUE light (stop any running program on the hub")
                print("      and disconnect it from the beta.pybricks.com browser tab), then type 'c' to scan!")
            return

        print(f"✨ Discovered {len(unconnected)} Pybricks Hub(s). Establishing links...")
        # Pause background scanner during GATT connection on macOS to prevent TimeoutError
        was_scanning = self._scanner_active
        if was_scanning and self.scanner is not None:
            try:
                await self.scanner.stop()
                self._scanner_active = False
            except Exception:
                pass

        for d in unconnected:
            await self.connect_to_hub(d)

        if was_scanning and self.scanner is not None:
            try:
                await self.scanner.start()
                self._scanner_active = True
            except Exception:
                pass

    async def start_all(self):
        """Sends START command to all connected robots."""
        if not self.connected_clients:
            print("\n⚠️ Warning: No hubs currently connected via BLE GATT.")
            print("   Scanning to discover active hubs first...")
            await self.scan_and_connect()
            if not self.connected_clients:
                print("❌ No hubs connected. Make sure hubs have a BLUE light (disconnected from browser) and type 'c'.\n")
                return

        print("\n" + "="*50)
        print(f"🚀 SENDING START TO ALL ROBOTS ({len(self.connected_clients)} connected)...")
        print("="*50)

        # Ensure user program is running (in Standby) on all connected hubs first
        start_prog_tasks = []
        for addr, client in list(self.connected_clients.items()):
            if client.is_connected and not self.hub_prog_running.get(addr, False):
                start_prog_tasks.append(self.start_hub_program_if_needed(addr, client))
        if start_prog_tasks:
            await asyncio.gather(*start_prog_tasks, return_exceptions=True)
            await asyncio.sleep(0.5)

        tasks = []
        for addr, client in list(self.connected_clients.items()):
            if client.is_connected:
                # Write 'S' to stdin via Pybricks Command characteristic (response=True required by Pybricks)
                tasks.append(client.write_gatt_char(PYBRICKS_COMMAND_EVENT_UUID, CMD_START_STDIN, response=True))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.run_started = True
        self.last_packet_time = time.time()
        print(f"✅ START command transmitted! Run {self.run_number} started.\n")

    async def stop_all(self):
        """Sends STOP command to all connected robots."""
        print("\n" + "="*50)
        print("🛑 SENDING STOP TO ALL ROBOTS...")
        print("="*50)

        tasks = []
        for addr, client in list(self.connected_clients.items()):
            if client.is_connected:
                # Send 'X' to stdin (response=True required by Pybricks)
                tasks.append(client.write_gatt_char(PYBRICKS_COMMAND_EVENT_UUID, CMD_STOP_STDIN, response=True))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        print("✅ STOP command transmitted to all hubs.")
        # If we have entries, save the run after a brief delay
        await asyncio.sleep(1.0)
        if self.current_run_entries:
            self.save_run()

    def save_run(self):
        """Saves current run entries into a timestamped JSON file."""
        if not self.current_run_entries:
            return None

        os.makedirs(self.output_dir, exist_ok=True)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"run_{self.run_number:02d}_{timestamp_str}.json"
        filepath = os.path.join(self.output_dir, filename)

        # Sort entries by Time_Stamp and ID
        sorted_entries = sorted(self.current_run_entries, key=lambda x: (x["Time_Stamp"], x["ID"]))

        with open(filepath, "w") as f:
            json.dump(sorted_entries, f, indent=2)

        robot_counts = {}
        for e in sorted_entries:
            rid = e["ID"]
            robot_counts[rid] = robot_counts.get(rid, 0) + 1

        print("\n" + "="*58)
        print(f"✅ RUN {self.run_number} COMPLETE & SAVED!")
        print(f"📁 File: {filepath}")
        print(f"📊 Total log entries: {len(sorted_entries)}")
        for rid, count in sorted(robot_counts.items()):
            print(f"   • Robot {rid}: {count} rows")
        print("="*58 + "\n")

        self.run_number += 1
        self.current_run_entries = []
        self.seen_signatures.clear()
        self.last_packet_time = None
        self.run_started = False
        print("🎯 Central Hub is ready for the next run. Press 's' to start!\n")
        return filepath

# ==============================================================================
# Interactive Terminal & Async Loops
# ==============================================================================
async def keyboard_listener(hub: CentralHub):
    """Asynchronous keyboard input handler."""
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
            elif cmd in ("c", "scan"):
                await hub.scan_and_connect()
            elif cmd in ("save",):
                hub.save_run()
            elif cmd in ("status", "list"):
                print_status(hub)
            elif cmd in ("h", "help"):
                print_help()
            elif cmd in ("exit", "quit"):
                hub._running = False
                break
        except Exception as e:
            print(f"Input error: {e}")

def print_help():
    print("""
================================================================
  KIT SYDSEN - LEGO SPIKE Digital Twin Central Hub
================================================================
  [s] or ENTER : START ALL ROBOTS (Synchronized wireless trigger)
  [x] or [q]   : STOP ALL ROBOTS (Halts motors & logs)
  [c] or scan  : SCAN & CONNECT to active Pybricks Hubs
  [status]     : Show connected robots & run statistics
  [save]       : Force save current run immediately
  [help]       : Show this menu
  Auto-Save    : Runs automatically save 10s after last log
================================================================
""")

def print_status(hub: CentralHub):
    print("\n--- Central Hub Status ---")
    print(f"Connected Hubs ({len(hub.connected_clients)}):")
    for addr, client in hub.connected_clients.items():
        name = hub.hub_names.get(addr, addr)
        status = "Active" if client.is_connected else "Disconnected"
        print(f"  • {name} [{addr}] - {status}")
    print(f"Current Run: #{hub.run_number}")
    print(f"Run Active:  {'YES' if hub.run_started else 'NO (Standby)'}")
    print(f"Buffered Entries: {len(hub.current_run_entries)}")
    print("--------------------------\n")

async def run_central_hub():
    hub = CentralHub()

    # BLE Broadcast detection callback
    def ble_detection_callback(device, advertisement_data):
        hub.register_advertisement(device, advertisement_data)
        mfg_data = advertisement_data.manufacturer_data
        if LEGO_COMPANY_ID in mfg_data:
            raw_bytes = mfg_data[LEGO_COMPANY_ID]
            decoded = decode_pybricks_payload(raw_bytes)
            if decoded is not None:
                channel, values = decoded
                hub.handle_broadcast_packet(channel, values)

    scanner = BleakScanner(detection_callback=ble_detection_callback)
    hub.scanner = scanner
    await scanner.start()
    hub._scanner_active = True

    # Initial scan & connect for Pybricks Hubs
    await hub.scan_and_connect()

    # Start keyboard listener in background
    kb_task = asyncio.create_task(keyboard_listener(hub))

    try:
        while hub._running:
            await asyncio.sleep(0.5)

            # Auto-save after 10s of inactivity
            if hub.run_started and hub.last_packet_time is not None:
                elapsed = time.time() - hub.last_packet_time
                if elapsed >= hub.timeout_s:
                    print(f"\n[AUTO-SAVE] Inactivity detected ({elapsed:.1f}s without logs). Closing run...")
                    hub.save_run()

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nShutting down Central Hub...")
    finally:
        hub._running = False
        kb_task.cancel()
        await scanner.stop()
        if hub.run_started and hub.current_run_entries:
            hub.save_run()
        for client in hub.connected_clients.values():
            if client.is_connected:
                await client.disconnect()
        print("Central Hub stopped cleanly.")

if __name__ == "__main__":
    try:
        asyncio.run(run_central_hub())
    except KeyboardInterrupt:
        pass
