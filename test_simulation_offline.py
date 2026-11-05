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
    "pybricks.geometry"
]:
    sys.modules[mod] = MagicMock()

# Mock Matrix to retain 2D structure
class MockMatrix:
    def __init__(self, grid):
        self.grid = grid

sys.modules["pybricks.geometry"].Matrix = MockMatrix

from download_log import save_json_log
import live_ble_receiver
from live_ble_receiver import CentralHub, CMD_START_STDIN, CMD_STOP_STDIN

class TestPybricksAgent(unittest.TestCase):
    def test_icons_dimensions(self):
        from agent_robot import ICON_I, ICON_S, ICON_R
        for name, icon in [("ICON_I", ICON_I), ("ICON_S", ICON_S), ("ICON_R", ICON_R)]:
            self.assertEqual(len(icon.grid), 5, f"{name} must have 5 rows")
            for row in icon.grid:
                self.assertEqual(len(row), 5, f"Each row in {name} must have 5 columns")
                for val in row:
                    self.assertIn(val, (0, 100), f"Pixel in {name} must be 0 or 100")

    def test_live_ble_receiver_decoding(self):
        payload = b'\x01' + b'\x61\x01' + b'\x84' + struct.pack('<f', 3.0) + b'\xA1S' + b'\xA11' + b'\x61\x02'
        channel, vals = live_ble_receiver.decode_pybricks_payload(payload)
        self.assertEqual(channel, 1)
        self.assertEqual(vals, [1, 3.0, 'S', '1', 2])

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

    def test_central_hub_commands(self):
        self.assertEqual(CMD_START_STDIN, b"\x06S")
        self.assertEqual(CMD_STOP_STDIN, b"\x06X")

    def test_central_hub_recording_and_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hub = CentralHub(output_dir=tmpdir)
            
            # Feed broadcast packet
            hub.handle_broadcast_packet(1, [1, 1.0, "I", "0", 1])
            hub.handle_broadcast_packet(2, [2, 1.0, "S", "0", 1])
            
            # Feed duplicate packet
            hub.handle_broadcast_packet(1, [1, 1.0, "I", "0", 1])

            self.assertEqual(len(hub.current_run_entries), 2)
            self.assertEqual(hub.current_run_entries[0]["ID"], 1)
            self.assertEqual(hub.current_run_entries[0]["SIR_State"], "I")
            self.assertEqual(hub.current_run_entries[1]["ID"], 2)
            self.assertEqual(hub.current_run_entries[1]["SIR_State"], "S")

            # Feed stdout notification
            stdout_raw = bytearray(b"\x012.0,1,Sample,0,I,\xe2\x80\x94,A,No\n")
            hub.handle_stdout_data(None, stdout_raw)
            self.assertEqual(len(hub.current_run_entries), 3)

            saved_path = hub.save_run()
            self.assertIsNotNone(saved_path)
            self.assertTrue(os.path.exists(saved_path))
            with open(saved_path, "r") as f:
                saved_data = json.load(f)
            self.assertEqual(len(saved_data), 3)

if __name__ == "__main__":
    unittest.main()
