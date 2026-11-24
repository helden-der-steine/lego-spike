"""
Central Hub: 100% Connectionless BLE Broadcast Controller & Telemetry Receiver.

Architecture (No BLE GATT Connections):
- Outgoing (Channel 0):
  Uses Windows WinRT BluetoothLEAdvertisementPublisher to broadcast START (1)
  and STOP (2) commands on Pybricks BLE Channel 0 (Manufacturer ID 0x0397).
  All robots observe ONLY Channel 0.
- Incoming (Channels 1..10):
  Uses BleakScanner to passively observe telemetry broadcasts emitted by
  Robots 1..10 on Channels 1..10.
- Auto-Save:
  Saves each run to logs/run_XX_YYYYMMDD_HHMMSS.json when stopped, when all
  infected robots have recovered, or after 15 seconds without telemetry packets.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime

from bleak import BleakScanner

from host.ble_broadcaster import ChannelZeroBroadcaster, DEFAULT_BROADCAST_DURATION_S
from host.ble_codec import decode_pybricks_payload
from shared.protocol import (
    CMD_START,
    CMD_STOP,
    CONTROL_CHANNEL,
    EVENT_CODE_SAMPLE,
    EVENT_SAMPLE,
    LEGO_COMPANY_ID,
    ROBOT_CHANNELS,
    STANDBY_TAG,
    build_log_entry,
    event_name_from_code,
)
from shared.sim_config import STATE_INFECTED, STATE_UNKNOWN, get_robot_stats

INACTIVITY_TIMEOUT_SECONDS = 15.0
NO_INFECTED_END_SECONDS = 5.0
POLL_INTERVAL_SECONDS = 0.5
POST_STOP_FLUSH_SECONDS = 0.5
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "logs")

TIMESTAMP_FILE_FMT = "%Y%m%d_%H%M%S"
TIMESTAMP_LOG_FMT = "%H:%M:%S"
DIVIDER_LINE = "=" * 60

START_COMMANDS = ("s", "start", "")
STOP_COMMANDS = ("x", "stop", "q")
STATUS_COMMANDS = ("status", "list")
SAVE_COMMANDS = ("save",)
HELP_COMMANDS = ("h", "help")
EXIT_COMMANDS = ("exit", "quit")


class CentralHub:
    """Coordinates connectionless BLE broadcast runs and records robot telemetry."""

    def __init__(
        self,
        timeout_s: float = INACTIVITY_TIMEOUT_SECONDS,
        output_dir: str = OUTPUT_DIR,
        observe_channels=ROBOT_CHANNELS,
    ):
        self.timeout_s = timeout_s
        self.output_dir = output_dir
        self.observe_channels = set(observe_channels)
        self.broadcaster = ChannelZeroBroadcaster(CONTROL_CHANNEL)

        self.standby_robots = {}      # robot_id -> (channel, sir_state, last_seen)
        self.current_run_entries = []
        self.seen_signatures = set()  # (robot_id, seq_num)
        self.robot_states = {}        # robot_id -> latest SIR_State in current run
        self.ever_saw_infected = False
        self.no_infected_since = None
        self.last_packet_time = None
        self.run_started = False
        self.run_number = 1
        self._running = True

    def _reset_run_state(self) -> None:
        self.current_run_entries = []
        self.seen_signatures.clear()
        self.standby_robots.clear()
        self.robot_states.clear()
        self.ever_saw_infected = False
        self.no_infected_since = None
        self.last_packet_time = None
        self.run_started = False

    def is_simulation_finished(
        self, now: float | None = None, confirm_s: float = NO_INFECTED_END_SECONDS
    ) -> bool:
        """
        Returns True once at least one robot was infected in the current run
        and no tracked robot remains infected for `confirm_s` seconds.
        """
        if not self.run_started or not self.ever_saw_infected:
            self.no_infected_since = None
            return False
        if any(state == STATE_INFECTED for state in self.robot_states.values()):
            self.no_infected_since = None
            return False

        current_time = time.time() if now is None else now
        if self.no_infected_since is None:
            self.no_infected_since = current_time
            return False
        return (current_time - self.no_infected_since) >= confirm_s

    def record_entry(self, entry: dict, seq_num: int | None = None) -> None:
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
        self.robot_states[entry["ID"]] = entry["SIR_State"]
        if entry["SIR_State"] == STATE_INFECTED:
            self.ever_saw_infected = True
            self.no_infected_since = None
        self.last_packet_time = time.time()
        self.run_started = True

        time_str = datetime.now().strftime(TIMESTAMP_LOG_FMT)
        event_str = f" | Event: {entry['Event']}" if entry["Event"] != EVENT_SAMPLE else ""
        print(
            f"[{time_str}] 📡 Ch {entry['ID']:2d} | Robot {entry['ID']} | "
            f"t={entry['Time_Stamp']:5.1f}s | State: {entry['SIR_State']:1} | "
            f"Zone: {entry['Zone']} | Type: {entry['Agent_Type']}{event_str}"
        )

    def _handle_standby_packet(self, channel: int, values: list) -> None:
        rid = int(values[1]) if len(values) >= 2 else channel
        state = str(values[2]) if len(values) >= 3 else STATE_UNKNOWN
        is_new = rid not in self.standby_robots
        self.standby_robots[rid] = (channel, state, time.time())
        if is_new:
            time_str = datetime.now().strftime(TIMESTAMP_LOG_FMT)
            print(
                f"[{time_str}] 🟠 Robot {rid} (Channel {channel}) READY in Standby | SIR State: {state}"
            )

    def handle_broadcast_packet(self, channel: int, values: list) -> None:
        """
        Processes connectionless BLE broadcast advertisements.
        Strictly listens ONLY to `self.observe_channels` (ignores Channel 0).
        """
        if channel not in self.observe_channels or not values:
            return

        if values[0] == STANDBY_TAG:
            self._handle_standby_packet(channel, values)
            return

        # Telemetry tuple: (robot_id, elapsed_s, sir_state, zone[, seq_num[, event_code]])
        if len(values) >= 4 and not isinstance(values[0], str):
            robot_id = int(values[0])
            elapsed_s = float(values[1])
            sir_state = str(values[2])
            zone = str(values[3])
            seq_num = int(values[4]) if len(values) >= 5 else None
            event_code = str(values[5]) if len(values) >= 6 else EVENT_CODE_SAMPLE
            event_name = event_name_from_code(event_code)

            stats = get_robot_stats(robot_id)
            entry = build_log_entry(
                timestamp_s=elapsed_s,
                robot_id=robot_id,
                event_name=event_name,
                zone=zone,
                sir_state=sir_state,
                agent_type=stats["agent_type"],
                vaccinated=stats["vaccinated"],
            )
            self.record_entry(entry, seq_num=seq_num)

    async def start_all(self) -> None:
        """Broadcasts START command on BLE Channel 0 to all robots."""
        print(f"\n{DIVIDER_LINE}")
        print(f"🚀 BROADCASTING 'START' ON BLE CHANNEL {CONTROL_CHANNEL} TO ALL ROBOTS...")
        print(DIVIDER_LINE)

        self.robot_states.clear()
        self.ever_saw_infected = False
        self.no_infected_since = None
        self.run_started = True
        self.last_packet_time = time.time()

        ok = await self.broadcaster.broadcast_command(
            CMD_START, duration_s=DEFAULT_BROADCAST_DURATION_S
        )
        if ok:
            print(
                f"✅ START broadcast finished! Run #{self.run_number} is now live "
                f"(listening on Ch 1..{max(self.observe_channels)}).\n"
            )

    async def stop_all(self) -> None:
        """Broadcasts STOP command on BLE Channel 0 to all robots."""
        print(f"\n{DIVIDER_LINE}")
        print(f"🛑 BROADCASTING 'STOP' ON BLE CHANNEL {CONTROL_CHANNEL} TO ALL ROBOTS...")
        print(DIVIDER_LINE)

        ok = await self.broadcaster.broadcast_command(
            CMD_STOP, duration_s=DEFAULT_BROADCAST_DURATION_S
        )
        if ok:
            print("✅ STOP broadcast finished! All robots halted.")

        await asyncio.sleep(POST_STOP_FLUSH_SECONDS)
        if self.current_run_entries:
            self.save_run()
        else:
            self._reset_run_state()

    def save_run(self) -> str | None:
        """Saves current run entries into a timestamped JSON file."""
        if not self.current_run_entries:
            return None

        os.makedirs(self.output_dir, exist_ok=True)
        timestamp_str = datetime.now().strftime(TIMESTAMP_FILE_FMT)
        filename = f"run_{self.run_number:02d}_{timestamp_str}.json"
        filepath = os.path.join(self.output_dir, filename)

        sorted_entries = sorted(
            self.current_run_entries, key=lambda row: (row["Time_Stamp"], row["ID"])
        )

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(sorted_entries, f, indent=2)

        robot_counts = {}
        for entry in sorted_entries:
            rid = entry["ID"]
            robot_counts[rid] = robot_counts.get(rid, 0) + 1

        print(f"\n{DIVIDER_LINE}")
        print(f"✅ RUN #{self.run_number} COMPLETE & SAVED!")
        print(f"📁 File: {filepath}")
        print(f"📊 Total log entries: {len(sorted_entries)}")
        for rid, count in sorted(robot_counts.items()):
            print(f"   • Robot {rid} (Channel {rid}): {count} rows")
        print(f"{DIVIDER_LINE}\n")

        self.run_number += 1
        self._reset_run_state()
        print("🎯 Ready for the next run. Press 's' + ENTER to broadcast START!\n")
        return filepath


def print_help() -> None:
    """Prints the interactive Central Hub command menu."""
    print(
        f"""
================================================================
  KIT SYDSEN - LEGO SPIKE Digital Twin Central Hub (Broadcast)
  • Outgoing Control : BLE Channel {CONTROL_CHANNEL} (All robots observe Ch {CONTROL_CHANNEL})
  • Incoming Logs    : BLE Channels 1..10 (1 channel per robot)
  • Connections      : NONE (100% Connectionless BLE Broadcast)
================================================================
  [s] or ENTER : Broadcast START on Channel {CONTROL_CHANNEL} (starts all robots)
  [x] or [q]   : Broadcast STOP on Channel {CONTROL_CHANNEL} (halts all robots)
  [status]     : Show standby robots & current run statistics
  [save]       : Force save current run to JSON immediately
  [help]       : Show this menu
  [exit]       : Quit program
  Auto-Save    : Automatically saves run after {int(INACTIVITY_TIMEOUT_SECONDS)}s without logs (or when 0 infected)
================================================================
"""
    )


def print_status(hub: CentralHub) -> None:
    """Prints detected standby robots and current run statistics."""
    print("\n--- Central Hub Broadcast Status ---")
    print(f"Outgoing Channel  : {CONTROL_CHANNEL}")
    print("Listening Channels: 1..10")
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


async def keyboard_listener(hub: CentralHub) -> None:
    """Non-blocking console command loop."""
    print_help()
    while hub._running:
        try:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                break
            cmd = line.strip().lower()

            if cmd in START_COMMANDS:
                await hub.start_all()
            elif cmd in STOP_COMMANDS:
                await hub.stop_all()
            elif cmd in STATUS_COMMANDS:
                print_status(hub)
            elif cmd in SAVE_COMMANDS:
                hub.save_run()
            elif cmd in HELP_COMMANDS:
                print_help()
            elif cmd in EXIT_COMMANDS:
                hub._running = False
                break
        except Exception as exc:
            print(f"Input error: {exc}")


async def run_central_hub() -> None:
    """Starts the passive BLE scanner and manages the experiment lifecycle."""
    hub = CentralHub()

    def ble_detection_callback(_device, advertisement_data):
        mfg_data = advertisement_data.manufacturer_data
        if LEGO_COMPANY_ID in mfg_data:
            decoded = decode_pybricks_payload(mfg_data[LEGO_COMPANY_ID])
            if decoded is not None:
                channel, values = decoded
                hub.handle_broadcast_packet(channel, values)

    scanner = BleakScanner(detection_callback=ble_detection_callback)
    await scanner.start()
    print("📡 Passive BLE Scanner active on Channels 1..10 (waiting for robots in Standby)...")

    kb_task = asyncio.create_task(keyboard_listener(hub))

    try:
        while hub._running:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

            if hub.is_simulation_finished():
                print("\n[END] No infected robots remaining. Stopping all robots and saving run...")
                await hub.stop_all()
                continue

            if hub.run_started and hub.current_run_entries and hub.last_packet_time is not None:
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


def main() -> None:
    try:
        asyncio.run(run_central_hub())
    except KeyboardInterrupt:
        pass
