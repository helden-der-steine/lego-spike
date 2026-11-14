#!/usr/bin/env python3
import unittest
import os
import sys
import json
import struct
import tempfile
from unittest.mock import MagicMock

# Mock Pybricks modules for host PC testing
pybricks_mock = MagicMock()
for mod in [
    "pybricks",
    "pybricks.hubs",
    "pybricks.pupdevices",
    "pybricks.parameters",
    "pybricks.robotics",
    "pybricks.tools",
    "pybricks.geometry",
]:
    sys.modules[mod] = MagicMock()


class MockMatrix:
    def __init__(self, grid):
        self.grid = grid


sys.modules["pybricks.geometry"].Matrix = MockMatrix

from download_log import save_json_log
import live_ble_receiver
from live_ble_receiver import (
    CentralHub,
    CMD_START,
    CMD_STOP,
    LAPTOP_BROADCAST_CHANNEL,
    ROBOT_OBSERVE_CHANNELS,
    encode_pybricks_payload,
    decode_pybricks_payload,
)


class TestPybricksAgent(unittest.TestCase):
    def test_icons_dimensions(self):
        from agent_robot import ICON_I, ICON_S, ICON_R, CONTROL_CHANNEL

        self.assertEqual(CONTROL_CHANNEL, 0)
        for name, icon in [("ICON_I", ICON_I), ("ICON_S", ICON_S), ("ICON_R", ICON_R)]:
            self.assertEqual(len(icon.grid), 5, f"{name} must have 5 rows")
            for row in icon.grid:
                self.assertEqual(len(row), 5, f"Each row in {name} must have 5 columns")
                for val in row:
                    self.assertIn(val, (0, 100), f"Pixel in {name} must be 0 or 100")

    def test_encode_decode_roundtrip_channel_zero_and_telemetry(self):
        # Channel 0 START (1) and STOP (2)
        p_start = encode_pybricks_payload(0, CMD_START)
        ch, vals = decode_pybricks_payload(p_start)
        self.assertEqual(ch, 0)
        self.assertEqual(vals, [1])

        p_stop = encode_pybricks_payload(0, CMD_STOP)
        ch, vals = decode_pybricks_payload(p_stop)
        self.assertEqual(ch, 0)
        self.assertEqual(vals, [2])

        # Telemetry tuple on Channel 3: (robot_id, elapsed_s, sir_state, zone, seq_num)
        p_tel = encode_pybricks_payload(3, (3, 4.0, "S", "0", 5))
        ch, vals = decode_pybricks_payload(p_tel)
        self.assertEqual(ch, 3)
        self.assertEqual(vals, [3, 4.0, "S", "0", 5])

    def test_save_json_log(self):
        sample_dump = """
=== JSON LOG DUMP START ===
[{"Time_Stamp": 0.0, "ID": 1, "Event": "Start", "Zone": "0", "SIR_State": "I", "Contact_ID": "—", "Agent_Type": "A", "Vaccinated": "No"}]
=== JSON LOG DUMP END ===
"""
        filepath = save_json_log(sample_dump)
        self.assertIsNotNone(filepath)
        self.assertTrue(os.path.exists(filepath))
        with open(filepath, "r") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["SIR_State"], "I")
        os.remove(filepath)

    def test_central_hub_channels_1_to_10_and_deduplication(self):
        self.assertEqual(LAPTOP_BROADCAST_CHANNEL, 0)
        self.assertEqual(ROBOT_OBSERVE_CHANNELS, set(range(1, 11)))

        with tempfile.TemporaryDirectory() as tmpdir:
            hub = CentralHub(output_dir=tmpdir)

            # Channel 0 (laptop's own broadcast) and Channel 11 must be ignored
            hub.handle_broadcast_packet(0, [1])
            hub.handle_broadcast_packet(11, [11, 1.0, "I", "0", 1])
            self.assertEqual(len(hub.current_run_entries), 0)

            # Standby heartbeat on Channel 1
            hub.handle_broadcast_packet(1, ["STANDBY", 1, "I"])
            self.assertIn(1, hub.standby_robots)

            # Valid telemetry on Channels 1, 2, 10
            hub.handle_broadcast_packet(1, [1, 1.0, "I", "0", 1])
            hub.handle_broadcast_packet(2, [2, 1.0, "S", "0", 1])
            hub.handle_broadcast_packet(10, [10, 1.0, "S", "0", 1])

            # Duplicate packet on Channel 1 (seq_num=1) ignored
            hub.handle_broadcast_packet(1, [1, 1.0, "I", "0", 1])

            self.assertEqual(len(hub.current_run_entries), 3)
            saved_path = hub.save_run()
            self.assertIsNotNone(saved_path)
            with open(saved_path, "r") as f:
                saved_data = json.load(f)
            self.assertEqual(len(saved_data), 3)


if __name__ == "__main__":
    unittest.main()
