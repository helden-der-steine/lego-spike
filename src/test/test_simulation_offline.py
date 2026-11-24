#!/usr/bin/env python3
import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Mock Pybricks modules for host PC testing
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

from host.ble_codec import decode_pybricks_payload, encode_pybricks_payload
from host.central_hub import CentralHub
from host.log_saver import save_json_log
from robot.hardware import ICON_I, ICON_R, ICON_S, ICON_V, detect_zone
from robot.navigation import (
    BACKUP_DURATION_MS,
    DISALLOWED_CONFIRM_MS,
    DRIVE_SPEED_MM_S,
    EDGE_CONFIRM_MS,
    OBSTACLE_CLEAR_SAMPLES,
    OBSTACLE_RESUME_MM,
    OBSTACLE_STOP_MM,
    ZONE_DEBOUNCE_SAMPLES,
    ZoneNavigator,
    get_allowed_next_zone,
    is_zone_transition_allowed,
    pick_edge_turn_angle,
)
from robot.sir_simulation import SIRSimulation
from shared.protocol import (
    CMD_START,
    CMD_STOP,
    CONTROL_CHANNEL,
    ROBOT_CHANNELS,
    event_code_from_name,
    event_name_from_code,
)
from shared.sim_config import (
    ENABLE_MOVEMENT,
    INFECTION_CHECK_INTERVAL_MS,
    INFECTION_CONTACT_MS,
    INFECTION_PROB_PER_SEC,
    LOG_INTERVAL_MS,
    NO_INFECTED_END_MS,
    RECOVERY_DURATION_MS,
    ROBOT_STATS,
    STATE_INFECTED,
    STATE_RECOVERED,
    STATE_SUSCEPTIBLE,
    STATE_VACCINATED,
    ZONE_ORDER_CW,
    config_from_hub_name,
    get_robot_stats,
    parse_robot_id,
)


class TestPybricksAgent(unittest.TestCase):
    def test_icons_dimensions(self):
        self.assertEqual(CONTROL_CHANNEL, 0)
        for name, icon in [("ICON_I", ICON_I), ("ICON_S", ICON_S), ("ICON_R", ICON_R), ("ICON_V", ICON_V)]:
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

    def test_protocol_event_mapping_roundtrip(self):
        for event_name in ("Sample", "Start", "change_zone", "Infection", "Recovery"):
            code = event_code_from_name(event_name)
            self.assertEqual(event_name_from_code(code), event_name)

    def test_save_json_log(self):
        sample_dump = """
=== JSON LOG DUMP START ===
[{"Time_Stamp": 0.0, "ID": 1, "Event": "Start", "Zone": "0", "SIR_State": "I", "Contact_ID": "—", "Agent_Type": "A", "Vaccinated": "No"}]
=== JSON LOG DUMP END ===
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = save_json_log(sample_dump, output_dir=tmpdir)
            self.assertIsNotNone(filepath)
            self.assertTrue(os.path.exists(filepath))
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["SIR_State"], "I")

    def test_central_hub_channels_1_to_10_and_deduplication(self):
        self.assertEqual(CONTROL_CHANNEL, 0)
        self.assertEqual(set(ROBOT_CHANNELS), set(range(1, 11)))

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
            with open(saved_path, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
            self.assertEqual(len(saved_data), 3)
            by_id = {row["ID"]: row for row in saved_data}
            self.assertEqual(by_id[1]["Agent_Type"], "A")
            self.assertEqual(by_id[2]["Agent_Type"], "A")
            self.assertEqual(by_id[10]["Agent_Type"], "B")

    def test_config_from_hub_name(self):
        self.assertEqual(len(ROBOT_STATS), 11)
        self.assertIsNone(ROBOT_STATS[0])
        for rid in range(1, 11):
            self.assertIn(ROBOT_STATS[rid]["agent_type"], ("A", "B"))
            self.assertIsInstance(ROBOT_STATS[rid]["initial_infected"], bool)
            self.assertIn(ROBOT_STATS[rid]["vaccinated"], ("Yes", "No"))

        self.assertEqual(parse_robot_id("Held 1"), 1)
        self.assertEqual(parse_robot_id("Held 10"), 10)
        self.assertEqual(parse_robot_id("", default=1), 1)

        self.assertEqual(config_from_hub_name("Held 1"), (1, "A", False))
        self.assertEqual(config_from_hub_name("Held 2"), (2, "A", True))
        self.assertEqual(config_from_hub_name("Held 4"), (4, "A", False))
        self.assertEqual(config_from_hub_name("Held 5"), (5, "B", False))
        self.assertEqual(config_from_hub_name("Held 10"), (10, "B", False))

    def test_zone_order_and_allowed_transitions(self):
        self.assertTrue(ENABLE_MOVEMENT)
        self.assertLessEqual(DRIVE_SPEED_MM_S, 50)
        self.assertEqual(ZONE_ORDER_CW, ("Yellow", "Blue", "Green", "Red"))

        # Type A: strictly clockwise
        cw_pairs = [("Yellow", "Blue"), ("Blue", "Green"), ("Green", "Red"), ("Red", "Yellow")]
        for cur, nxt in cw_pairs:
            self.assertEqual(get_allowed_next_zone(cur, "A"), nxt)
            self.assertTrue(is_zone_transition_allowed(cur, nxt, "A"))
            for other in ZONE_ORDER_CW:
                if other != nxt:
                    self.assertFalse(is_zone_transition_allowed(cur, other, "A"))

        # Type B: strictly counter-clockwise
        ccw_pairs = [("Yellow", "Red"), ("Red", "Green"), ("Green", "Blue"), ("Blue", "Yellow")]
        for cur, nxt in ccw_pairs:
            self.assertEqual(get_allowed_next_zone(cur, "B"), nxt)
            self.assertTrue(is_zone_transition_allowed(cur, nxt, "B"))
            for other in ZONE_ORDER_CW:
                if other != nxt:
                    self.assertFalse(is_zone_transition_allowed(cur, other, "B"))

        # Initial unknown zone '0' allows entering any valid zone
        for z in ZONE_ORDER_CW:
            self.assertTrue(is_zone_transition_allowed("0", z, "A"))
            self.assertTrue(is_zone_transition_allowed("0", z, "B"))

        # Edge turn angles: 45..110 deg, clockwise (+) for A, counter-clockwise (-) for B
        for _ in range(50):
            ang_a = pick_edge_turn_angle("A")
            self.assertGreaterEqual(ang_a, 45)
            self.assertLessEqual(ang_a, 110)
            ang_b = pick_edge_turn_angle("B")
            self.assertLessEqual(ang_b, -45)
            self.assertGreaterEqual(ang_b, -110)

    def test_zone_navigator_transitions_and_edge_bounces(self):
        class FakeDriveBase:
            def __init__(self):
                self.drives = []
                self.turns = []
                self.stops = 0
                self.is_done = False

            def settings(self, *args, **kwargs):
                pass

            def drive(self, speed, turn_rate):
                self.drives.append((speed, turn_rate))

            def turn(self, angle, wait=True):
                self.turns.append((angle, wait))
                self.is_done = False

            def done(self):
                return self.is_done

            def stop(self):
                self.stops += 1

        # 1. Type A moves Yellow -> Blue, rejects Yellow -> Red (turns +45..+110)
        db_a = FakeDriveBase()
        nav_a = ZoneNavigator("A", drive_base_obj=db_a, has_color_sensor=True)
        nav_a.start(now_ms=0)
        self.assertEqual(db_a.drives[-1], (DRIVE_SPEED_MM_S, 0))

        # Disallowed zone (Red from Yellow for Type A) triggers backup & CW turn after DISALLOWED_CONFIRM_MS
        t = 20
        nav_a.step(t, "Yellow", "Red")
        self.assertEqual(nav_a.state, "DRIVE")
        t += DISALLOWED_CONFIRM_MS
        res = nav_a.step(t, "Yellow", "Red")
        self.assertIsNone(res)
        self.assertEqual(nav_a.state, "BACKUP")
        self.assertEqual(db_a.drives[-1], (-DRIVE_SPEED_MM_S, 0))

        # Complete backup -> enters TURN with +45..+110 deg
        t += BACKUP_DURATION_MS
        nav_a.step(t, "Yellow", "Yellow")
        self.assertEqual(nav_a.state, "TURN")
        self.assertEqual(len(db_a.turns), 1)
        turn_angle, wait_flag = db_a.turns[-1]
        self.assertFalse(wait_flag)
        self.assertTrue(45 <= turn_angle <= 110)

        # Complete turn -> resumes slow forward drive
        db_a.is_done = True
        t += 200
        nav_a.step(t, "Yellow", "Yellow")
        self.assertEqual(nav_a.state, "DRIVE")
        self.assertEqual(db_a.drives[-1], (DRIVE_SPEED_MM_S, 0))

        # Crossing a seam (< EDGE_CONFIRM_MS) into allowed Blue commits without backing up
        for _ in range(6):
            t += 50
            self.assertIsNone(nav_a.step(t, "Yellow", None))
            self.assertEqual(nav_a.state, "DRIVE")
        for i in range(ZONE_DEBOUNCE_SAMPLES):
            t += 20
            res = nav_a.step(t, "Yellow", "Blue")
            if i < ZONE_DEBOUNCE_SAMPLES - 1:
                self.assertIsNone(res)
            else:
                self.assertEqual(res, "Blue")
        self.assertEqual(nav_a.state, "DRIVE")

        # Brief seam misclassification (e.g. Yellow for 150ms on Green->Red seam) must NOT stop Green->Red
        nav_a.step(t + 20, "Green", "Yellow")
        nav_a.step(t + 120, "Green", "Yellow")
        self.assertEqual(nav_a.state, "DRIVE")
        for i in range(ZONE_DEBOUNCE_SAMPLES):
            res = nav_a.step(t + 140 + i * 20, "Green", "Red")
        self.assertEqual(res, "Red")

        # 2. Type B hitting outer edge backs up, turns -45..-110, stops backup early if crossing back out
        db_b = FakeDriveBase()
        nav_b = ZoneNavigator("B", drive_base_obj=db_b, has_color_sensor=True)
        nav_b.start(now_ms=0)
        nav_b.step(20, "Red", None)
        self.assertEqual(nav_b.state, "DRIVE")
        t = 20 + EDGE_CONFIRM_MS
        nav_b.step(t, "Red", None)
        self.assertEqual(nav_b.state, "BACKUP")
        # Re-enters Red during backup, then hits opposite border -> turns immediately
        t += 20
        nav_b.step(t, "Red", "Red")
        t += 20
        nav_b.step(t, "Red", "Yellow")
        self.assertEqual(nav_b.state, "TURN")
        self.assertTrue(-110 <= db_b.turns[-1][0] <= -45)

        # 3. No color sensor: None must not trigger edge bounces
        db_none = FakeDriveBase()
        nav_none = ZoneNavigator("A", drive_base_obj=db_none, has_color_sensor=False)
        nav_none.start(now_ms=0)
        for i in range(10):
            nav_none.step(i * 20, "Yellow", None)
        self.assertEqual(nav_none.state, "DRIVE")
        self.assertEqual(len(db_none.turns), 0)

        # 4. Distance sensor obstacle stop, backup, and turn away (80 mm / 100 mm thresholds)
        self.assertEqual(OBSTACLE_STOP_MM, 80)
        self.assertEqual(OBSTACLE_RESUME_MM, 100)
        db_obs = FakeDriveBase()
        nav_obs = ZoneNavigator("A", drive_base_obj=db_obs, has_color_sensor=True)
        nav_obs.start(now_ms=0)

        # Obstacle detected closer than 80 mm -> stops immediately and backs up
        stops_before = db_obs.stops
        nav_obs.step(20, "White", "White", distance_mm=OBSTACLE_STOP_MM - 10)
        self.assertEqual(nav_obs.state, "OBSTACLE_BACKUP")
        self.assertEqual(db_obs.stops, stops_before + 1)
        self.assertEqual(db_obs.drives[-1], (-DRIVE_SPEED_MM_S, 0))
        self.assertEqual(len(db_obs.turns), 0)

        # Still inside hysteresis band (< 100 mm) -> keeps backing up
        nav_obs.step(40, "White", "White", distance_mm=OBSTACLE_RESUME_MM - 5)
        self.assertEqual(nav_obs.state, "OBSTACLE_BACKUP")
        self.assertEqual(db_obs.drives[-1], (-DRIVE_SPEED_MM_S, 0))

        # Obstacle cleared (>= 100 mm) for OBSTACLE_CLEAR_SAMPLES -> transitions to TURN away
        for i in range(OBSTACLE_CLEAR_SAMPLES):
            nav_obs.step(60 + i * 20, "White", "White", distance_mm=OBSTACLE_RESUME_MM)
        self.assertEqual(nav_obs.state, "TURN")
        self.assertEqual(len(db_obs.turns), 1)
        self.assertTrue(45 <= db_obs.turns[-1][0] <= 110)

        # Complete turn -> resumes forward drive
        db_obs.is_done = True
        nav_obs.step(300, "White", "White", distance_mm=OBSTACLE_RESUME_MM)
        self.assertEqual(nav_obs.state, "DRIVE")
        self.assertEqual(db_obs.drives[-1], (DRIVE_SPEED_MM_S, 0))

    def test_detect_zone_new_paper_hsv(self):
        class FakeHSV:
            def __init__(self, h, s, v):
                self.h, self.s, self.v = h, s, v

        class FakeSensor:
            def __init__(self, h, s, v):
                self._hsv = FakeHSV(h, s, v)

            def hsv(self):
                return self._hsv

        # Green readings from log
        for hsv in [(123, 57, 30), (120, 55, 30), (123, 55, 31)]:
            self.assertEqual(detect_zone(FakeSensor(*hsv)), "Green")

        # Blue readings from log
        for hsv in [(200, 89, 35), (199, 89, 30), (200, 89, 33)]:
            self.assertEqual(detect_zone(FakeSensor(*hsv)), "Blue")

        # Yellow readings from log
        for hsv in [(33, 79, 80), (32, 79, 58), (32, 79, 57)]:
            self.assertEqual(detect_zone(FakeSensor(*hsv)), "Yellow")

        # Red readings from log
        for hsv in [(356, 92, 35), (354, 92, 35), (356, 91, 35)]:
            self.assertEqual(detect_zone(FakeSensor(*hsv)), "Red")

        # Dark background / edge / transition readings from log -> None
        for hsv in [
            (40, 11, 15),
            (10, 5, 15),
            (60, 5, 15),
            (10, 0, 0),
            (120, 55, 1),
            (240, 100, 0),
            (180, 100, 0),
            (0, 92, 7),
            (354, 92, 10),
        ]:
            self.assertIsNone(detect_zone(FakeSensor(*hsv)))

    def test_logging_interval_and_infection_timing(self):
        import robot.sir_simulation as sir_simulation

        self.assertEqual(LOG_INTERVAL_MS, 5000)
        self.assertEqual(INFECTION_CONTACT_MS, 30000)
        self.assertEqual(INFECTION_CHECK_INTERVAL_MS, 1000)
        self.assertEqual(INFECTION_PROB_PER_SEC, 0.05)
        self.assertEqual(
            (STATE_SUSCEPTIBLE, STATE_INFECTED, STATE_RECOVERED, STATE_VACCINATED),
            ("S", "I", "R", "V"),
        )

        sim = SIRSimulation(initial_infected=False)
        sim.current_zone = "Red"

        orig_random = sir_simulation.random.random
        try:
            sim.observe_peer_packet(2, STATE_INFECTED, "Red", 0)
            sir_simulation.random.random = lambda: 0.0
            self.assertIsNone(sim.check_zone_infection(0))

            sim.observe_peer_packet(2, STATE_INFECTED, "Red", 29999)
            self.assertIsNone(sim.check_zone_infection(29999))
            self.assertEqual(sim.sir_state, STATE_SUSCEPTIBLE)

            sir_simulation.random.random = lambda: 0.99
            sim.observe_peer_packet(2, STATE_INFECTED, "Red", 30000)
            self.assertIsNone(sim.check_zone_infection(30000))
            self.assertEqual(sim.sir_state, STATE_SUSCEPTIBLE)

            sir_simulation.random.random = lambda: 0.0
            sim.observe_peer_packet(2, STATE_INFECTED, "Red", 30500)
            self.assertIsNone(sim.check_zone_infection(30500))
            self.assertEqual(sim.sir_state, STATE_SUSCEPTIBLE)

            sim.observe_peer_packet(2, STATE_INFECTED, "Red", 31000)
            self.assertEqual(sim.check_zone_infection(31000), 2)
            self.assertEqual(sim.sir_state, STATE_INFECTED)
        finally:
            sir_simulation.random.random = orig_random

    def test_simulation_ends_when_no_infected_remain(self):
        sim = SIRSimulation(initial_infected=False)

        # Never saw an infected robot -> must NOT end
        self.assertFalse(sim.is_finished(60000))

        # Peer 2 is infected -> simulation stays active
        sim.observe_peer_packet(2, STATE_INFECTED, "Red", 1000)
        self.assertTrue(sim.ever_saw_infected)
        self.assertFalse(sim.is_finished(1000))

        # Peer 2 recovers -> finishes after NO_INFECTED_END_MS confirmation
        sim.observe_peer_packet(2, STATE_RECOVERED, "Red", 2000)
        self.assertFalse(sim.is_finished(2000))
        self.assertFalse(sim.is_finished(2000 + NO_INFECTED_END_MS - 1))
        self.assertTrue(sim.is_finished(2000 + NO_INFECTED_END_MS))

        # CentralHub also detects end of simulation when all robots are non-infected
        with tempfile.TemporaryDirectory() as tmpdir:
            chub = CentralHub(output_dir=tmpdir)
            chub.handle_broadcast_packet(1, [1, 0.0, "S", "White", 1])
            chub.handle_broadcast_packet(2, [2, 0.0, "I", "Red", 1])
            self.assertFalse(chub.is_simulation_finished(now=100.0, confirm_s=5.0))
            chub.handle_broadcast_packet(2, [2, 5.0, "R", "Red", 2, "R"])
            self.assertEqual(chub.current_run_entries[-1]["Event"], "Recovery")
            self.assertFalse(chub.is_simulation_finished(now=105.0, confirm_s=5.0))
            self.assertFalse(chub.is_simulation_finished(now=109.9, confirm_s=5.0))
            self.assertTrue(chub.is_simulation_finished(now=110.0, confirm_s=5.0))

    def test_recovery_after_120_seconds(self):
        import robot.sir_simulation as sir_simulation

        self.assertEqual(RECOVERY_DURATION_MS, 120000)

        sim = SIRSimulation(initial_infected=False)
        self.assertFalse(sim.check_recovery(200000))
        self.assertEqual(sim.sir_state, STATE_SUSCEPTIBLE)

        # Initially infected robot recovers at exactly 120000 ms
        sim_inf = SIRSimulation(initial_infected=True)
        self.assertFalse(sim_inf.check_recovery(119999))
        self.assertEqual(sim_inf.sir_state, STATE_INFECTED)
        self.assertTrue(sim_inf.check_recovery(120000))
        self.assertEqual(sim_inf.sir_state, STATE_RECOVERED)
        self.assertIsNone(sim_inf.infected_since_ms)
        self.assertFalse(sim_inf.check_recovery(250000))
        self.assertEqual(sim_inf.sir_state, STATE_RECOVERED)

        # Robot infected during run recovers 120s after infection time and cannot be re-infected
        sim_dyn = SIRSimulation(initial_infected=False)
        sim_dyn.current_zone = "Blue"
        orig_random = sir_simulation.random.random
        try:
            sir_simulation.random.random = lambda: 0.0
            sim_dyn.observe_peer_packet(2, STATE_INFECTED, "Blue", 1000)
            sim_dyn.check_zone_infection(1000)
            sim_dyn.observe_peer_packet(2, STATE_INFECTED, "Blue", 31000)
            self.assertEqual(sim_dyn.check_zone_infection(31000), 2)
            self.assertEqual(sim_dyn.sir_state, STATE_INFECTED)
            self.assertEqual(sim_dyn.infected_since_ms, 31000)

            self.assertFalse(sim_dyn.check_recovery(31000 + RECOVERY_DURATION_MS - 1))
            self.assertEqual(sim_dyn.sir_state, STATE_INFECTED)
            self.assertTrue(sim_dyn.check_recovery(31000 + RECOVERY_DURATION_MS))
            self.assertEqual(sim_dyn.sir_state, STATE_RECOVERED)

            self.assertIsNone(sim_dyn.check_zone_infection(200000))
            self.assertEqual(sim_dyn.sir_state, STATE_RECOVERED)
        finally:
            sir_simulation.random.random = orig_random

    def test_pybricks_module_discovery(self):
        """Verifies Pybricks ModuleFinder resolves all robot/* and shared/* imports."""
        from modulefinder import ModuleFinder

        for script_name in ("agent_robot.py", "color_sensor_logger.py"):
            finder = ModuleFinder([SRC_DIR])
            finder.run_script(os.path.join(SRC_DIR, script_name))
            self.assertIn("robot.hardware", finder.modules)
            if script_name == "agent_robot.py":
                self.assertIn("robot.controller", finder.modules)
                self.assertIn("robot.navigation", finder.modules)
                self.assertIn("robot.sir_simulation", finder.modules)
                self.assertIn("shared.protocol", finder.modules)
                self.assertIn("shared.sim_config", finder.modules)


if __name__ == "__main__":
    unittest.main()
