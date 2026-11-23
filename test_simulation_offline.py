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
        from agent_robot import ICON_I, ICON_S, ICON_R, ICON_V, CONTROL_CHANNEL

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
            by_id = {row["ID"]: row for row in saved_data}
            self.assertEqual(by_id[1]["Agent_Type"], "A")
            self.assertEqual(by_id[2]["Agent_Type"], "A")
            self.assertEqual(by_id[10]["Agent_Type"], "B")

    def test_config_from_hub_name(self):
        from agent_robot import (
            ROBOT_STATS,
            config_from_hub_name,
            get_robot_stats,
            parse_robot_id,
        )

        self.assertEqual(len(ROBOT_STATS), 11)
        self.assertIsNone(ROBOT_STATS[0])
        for rid in range(1, 11):
            self.assertIn(ROBOT_STATS[rid]["agent_type"], ("A", "B"))
            self.assertIsInstance(ROBOT_STATS[rid]["initial_infected"], bool)
            self.assertIn(ROBOT_STATS[rid]["vaccinated"], ("Yes", "No"))
            self.assertEqual(get_robot_stats(rid), live_ble_receiver.get_robot_stats(rid))

        self.assertEqual(parse_robot_id("Held 1"), 1)
        self.assertEqual(parse_robot_id("Held 10"), 10)
        self.assertEqual(parse_robot_id("", default=1), 1)

        self.assertEqual(config_from_hub_name("Held 1"), (1, "A", False))
        self.assertEqual(config_from_hub_name("Held 2"), (2, "A", True))
        self.assertEqual(config_from_hub_name("Held 4"), (4, "A", False))
        self.assertEqual(config_from_hub_name("Held 5"), (5, "B", False))
        self.assertEqual(config_from_hub_name("Held 10"), (10, "B", False))

    def test_zone_order_and_allowed_transitions(self):
        from agent_robot import (
            ENABLE_MOVEMENT,
            DRIVE_SPEED_MM_S,
            ZONE_ORDER_CW,
            get_allowed_next_zone,
            is_zone_transition_allowed,
            pick_edge_turn_angle,
        )

        self.assertTrue(ENABLE_MOVEMENT)
        self.assertLessEqual(DRIVE_SPEED_MM_S, 50)
        self.assertEqual(ZONE_ORDER_CW, ("White", "Blue", "Green", "Red"))

        # Type A: strictly clockwise
        cw_pairs = [("White", "Blue"), ("Blue", "Green"), ("Green", "Red"), ("Red", "White")]
        for cur, nxt in cw_pairs:
            self.assertEqual(get_allowed_next_zone(cur, "A"), nxt)
            self.assertTrue(is_zone_transition_allowed(cur, nxt, "A"))
            for other in ZONE_ORDER_CW:
                if other != nxt:
                    self.assertFalse(is_zone_transition_allowed(cur, other, "A"))

        # Type B: strictly counter-clockwise
        ccw_pairs = [("White", "Red"), ("Red", "Green"), ("Green", "Blue"), ("Blue", "White")]
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

        # Edge turn angles: 90..180 deg, clockwise (+) for A, counter-clockwise (-) for B
        for _ in range(50):
            ang_a = pick_edge_turn_angle("A")
            self.assertGreaterEqual(ang_a, 90)
            self.assertLessEqual(ang_a, 180)
            ang_b = pick_edge_turn_angle("B")
            self.assertLessEqual(ang_b, -90)
            self.assertGreaterEqual(ang_b, -180)

    def test_zone_navigator_transitions_and_edge_bounces(self):
        from agent_robot import (
            BACKUP_DURATION_MS,
            DISALLOWED_CONFIRM_MS,
            DRIVE_SPEED_MM_S,
            EDGE_CONFIRM_MS,
            ZONE_DEBOUNCE_SAMPLES,
            ZoneNavigator,
        )

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

        # 1. Type A moves White -> Blue, rejects White -> Red (turns +90..+180)
        db_a = FakeDriveBase()
        nav_a = ZoneNavigator("A", drive_base_obj=db_a, has_color_sensor=True)
        nav_a.start(now_ms=0)
        self.assertEqual(db_a.drives[-1], (DRIVE_SPEED_MM_S, 0))

        # Disallowed zone (Red from White for Type A) triggers backup & CW turn after DISALLOWED_CONFIRM_MS
        t = 20
        nav_a.step(t, "White", "Red")
        self.assertEqual(nav_a.state, "DRIVE")
        t += DISALLOWED_CONFIRM_MS
        res = nav_a.step(t, "White", "Red")
        self.assertIsNone(res)
        self.assertEqual(nav_a.state, "BACKUP")
        self.assertEqual(db_a.drives[-1], (-DRIVE_SPEED_MM_S, 0))

        # Complete backup -> enters TURN with +90..+180 deg
        t += BACKUP_DURATION_MS
        nav_a.step(t, "White", "White")
        self.assertEqual(nav_a.state, "TURN")
        self.assertEqual(len(db_a.turns), 1)
        turn_angle, wait_flag = db_a.turns[-1]
        self.assertFalse(wait_flag)
        self.assertTrue(90 <= turn_angle <= 180)

        # Complete turn -> resumes slow forward drive
        db_a.is_done = True
        t += 200
        nav_a.step(t, "White", "White")
        self.assertEqual(nav_a.state, "DRIVE")
        self.assertEqual(db_a.drives[-1], (DRIVE_SPEED_MM_S, 0))

        # Crossing a seam (< EDGE_CONFIRM_MS) into allowed Blue commits without backing up
        for _ in range(6):
            t += 50
            self.assertIsNone(nav_a.step(t, "White", None))
            self.assertEqual(nav_a.state, "DRIVE")
        for i in range(ZONE_DEBOUNCE_SAMPLES):
            t += 20
            res = nav_a.step(t, "White", "Blue")
            if i < ZONE_DEBOUNCE_SAMPLES - 1:
                self.assertIsNone(res)
            else:
                self.assertEqual(res, "Blue")
        self.assertEqual(nav_a.state, "DRIVE")

        # Brief seam misclassification (e.g. White for 150ms on Green->Red seam) must NOT stop Green->Red
        nav_a.step(t + 20, "Green", "White")
        nav_a.step(t + 120, "Green", "White")
        self.assertEqual(nav_a.state, "DRIVE")
        for i in range(ZONE_DEBOUNCE_SAMPLES):
            res = nav_a.step(t + 140 + i * 20, "Green", "Red")
        self.assertEqual(res, "Red")

        # 2. Type B hitting outer edge (None for >= EDGE_CONFIRM_MS) backs up, turns -90..-180,
        #    and stops backup early if crossing back out
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
        nav_b.step(t, "Red", "White")
        self.assertEqual(nav_b.state, "TURN")
        self.assertTrue(-180 <= db_b.turns[-1][0] <= -90)

        # 3. No color sensor: None must not trigger edge bounces
        db_none = FakeDriveBase()
        nav_none = ZoneNavigator("A", drive_base_obj=db_none, has_color_sensor=False)
        nav_none.start(now_ms=0)
        for i in range(10):
            nav_none.step(i * 20, "White", None)
        self.assertEqual(nav_none.state, "DRIVE")
        self.assertEqual(len(db_none.turns), 0)

        # 4. Distance sensor obstacle stop, backup, and turn away (150 mm / 190 mm thresholds)
        from agent_robot import OBSTACLE_CLEAR_SAMPLES, OBSTACLE_RESUME_MM, OBSTACLE_STOP_MM

        self.assertEqual(OBSTACLE_STOP_MM, 150)
        self.assertEqual(OBSTACLE_RESUME_MM, 190)
        db_obs = FakeDriveBase()
        nav_obs = ZoneNavigator("A", drive_base_obj=db_obs, has_color_sensor=True)
        nav_obs.start(now_ms=0)

        # Obstacle detected closer than 150 mm -> stops immediately and backs up
        stops_before = db_obs.stops
        nav_obs.step(20, "White", "White", distance_mm=OBSTACLE_STOP_MM - 10)
        self.assertEqual(nav_obs.state, "OBSTACLE_BACKUP")
        self.assertEqual(db_obs.stops, stops_before + 1)
        self.assertEqual(db_obs.drives[-1], (-DRIVE_SPEED_MM_S, 0))
        self.assertEqual(len(db_obs.turns), 0)

        # Still inside hysteresis band (< 190 mm) -> keeps backing up
        nav_obs.step(40, "White", "White", distance_mm=OBSTACLE_RESUME_MM - 5)
        self.assertEqual(nav_obs.state, "OBSTACLE_BACKUP")
        self.assertEqual(db_obs.drives[-1], (-DRIVE_SPEED_MM_S, 0))

        # Obstacle cleared (>= 190 mm) for OBSTACLE_CLEAR_SAMPLES -> transitions to TURN away
        for i in range(OBSTACLE_CLEAR_SAMPLES):
            nav_obs.step(60 + i * 20, "White", "White", distance_mm=OBSTACLE_RESUME_MM)
        self.assertEqual(nav_obs.state, "TURN")
        self.assertEqual(len(db_obs.turns), 1)
        self.assertTrue(90 <= db_obs.turns[-1][0] <= 180)

        # Complete turn -> resumes forward drive
        db_obs.is_done = True
        nav_obs.step(300, "White", "White", distance_mm=OBSTACLE_RESUME_MM)
        self.assertEqual(nav_obs.state, "DRIVE")
        self.assertEqual(db_obs.drives[-1], (DRIVE_SPEED_MM_S, 0))

    def test_logging_interval_and_infection_timing(self):
        import agent_robot as ar

        self.assertEqual(ar.LOG_INTERVAL_MS, 5000)
        self.assertEqual(ar.INFECTION_CONTACT_MS, 30000)
        self.assertEqual(ar.INFECTION_CHECK_INTERVAL_MS, 1000)
        self.assertEqual(ar.INFECTION_PROB_PER_SEC, 0.05)
        self.assertEqual(
            (ar.STATE_SUSCEPTIBLE, ar.STATE_INFECTED, ar.STATE_RECOVERED, ar.STATE_VACCINATED),
            ("S", "I", "R", "V"),
        )

        orig_observe = ar.hub.ble.observe
        orig_random = ar.random.random
        orig_time = ar.stopwatch.time
        try:
            ar._clear_peer_contact()
            ar.peer_last_seen.clear()
            ar.peer_states.clear()
            ar.peer_zones.clear()
            ar.ever_saw_infected = False
            ar.no_infected_since = None
            ar.current_zone = "Red"
            ar.sir_state = ar.STATE_SUSCEPTIBLE
            ar.stopwatch.time = lambda: 31000
            ar.hub.ble.observe = lambda ch: (2, 1.0, ar.STATE_INFECTED, "Red", 1) if ch == 2 else None

            ar.random.random = lambda: 0.0
            ar.check_zone_infection(0)
            ar.check_zone_infection(29999)
            self.assertEqual(ar.sir_state, ar.STATE_SUSCEPTIBLE)

            ar.random.random = lambda: 0.99
            ar.check_zone_infection(30000)
            self.assertEqual(ar.sir_state, ar.STATE_SUSCEPTIBLE)

            ar.random.random = lambda: 0.0
            ar.check_zone_infection(30500)
            self.assertEqual(ar.sir_state, ar.STATE_SUSCEPTIBLE)

            ar.check_zone_infection(31000)
            self.assertEqual(ar.sir_state, ar.STATE_INFECTED)
        finally:
            ar.hub.ble.observe = orig_observe
            ar.random.random = orig_random
            ar.stopwatch.time = orig_time

    def test_simulation_ends_when_no_infected_remain(self):
        import agent_robot as ar

        orig_observe = ar.hub.ble.observe
        try:
            ar._clear_peer_contact()
            ar.peer_last_seen.clear()
            ar.peer_states.clear()
            ar.peer_zones.clear()
            ar.sir_state = ar.STATE_SUSCEPTIBLE
            ar.ever_saw_infected = False
            ar.no_infected_since = None

            # Never saw an infected robot -> must NOT end
            ar.hub.ble.observe = lambda ch: None
            ar.observe_peers(0)
            self.assertFalse(ar.is_simulation_finished(60000))

            # Peer 2 is infected -> simulation stays active
            ar.hub.ble.observe = lambda ch: (2, 1.0, ar.STATE_INFECTED, "Red", 1) if ch == 2 else None
            ar.observe_peers(1000)
            self.assertTrue(ar.ever_saw_infected)
            self.assertFalse(ar.is_simulation_finished(1000))

            # Peer 2 recovers -> finishes after NO_INFECTED_END_MS confirmation
            ar.hub.ble.observe = lambda ch: (2, 5.0, ar.STATE_RECOVERED, "Red", 2) if ch == 2 else None
            ar.observe_peers(2000)
            self.assertFalse(ar.is_simulation_finished(2000))
            self.assertFalse(ar.is_simulation_finished(2000 + ar.NO_INFECTED_END_MS - 1))
            self.assertTrue(ar.is_simulation_finished(2000 + ar.NO_INFECTED_END_MS))

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
        finally:
            ar.hub.ble.observe = orig_observe

    def test_recovery_after_120_seconds(self):
        import agent_robot as ar

        self.assertEqual(ar.RECOVERY_DURATION_MS, 120000)

        orig_observe = ar.hub.ble.observe
        orig_random = ar.random.random
        orig_time = ar.stopwatch.time
        orig_broadcast = ar.hub.ble.broadcast
        broadcasts = []
        try:
            ar.hub.ble.broadcast = lambda payload: broadcasts.append(payload)
            ar.log_entries.clear()

            # 1. Susceptible robot does not recover
            ar.sir_state = ar.STATE_SUSCEPTIBLE
            ar.infected_since_ms = None
            self.assertFalse(ar.check_recovery(200000))
            self.assertEqual(ar.sir_state, ar.STATE_SUSCEPTIBLE)

            # 2. Initially infected robot recovers at exactly 120000 ms
            ar.sir_state = ar.STATE_INFECTED
            ar.infected_since_ms = 0
            ar.current_zone = "Red"
            ar.stopwatch.time = lambda: 120000
            self.assertFalse(ar.check_recovery(119999))
            self.assertEqual(ar.sir_state, ar.STATE_INFECTED)
            self.assertTrue(ar.check_recovery(120000))
            self.assertEqual(ar.sir_state, ar.STATE_RECOVERED)
            self.assertIsNone(ar.infected_since_ms)
            self.assertEqual(ar.log_entries[-1]["Event"], "Recovery")
            self.assertEqual(ar.log_entries[-1]["SIR_State"], ar.STATE_RECOVERED)
            self.assertEqual(broadcasts[-1][2], ar.STATE_RECOVERED)
            self.assertEqual(broadcasts[-1][5], "R")

            # Subsequent calls while recovered do nothing
            self.assertFalse(ar.check_recovery(250000))
            self.assertEqual(ar.sir_state, ar.STATE_RECOVERED)

            # 3. Robot infected during the run recovers 120s after infection time
            ar._clear_peer_contact()
            ar.peer_last_seen.clear()
            ar.peer_states.clear()
            ar.peer_zones.clear()
            ar.sir_state = ar.STATE_SUSCEPTIBLE
            ar.infected_since_ms = None
            ar.current_zone = "Blue"
            ar.hub.ble.observe = lambda ch: (2, 1.0, ar.STATE_INFECTED, "Blue", 1) if ch == 2 else None
            ar.random.random = lambda: 0.0
            ar.stopwatch.time = lambda: 31000

            ar.check_zone_infection(1000)
            ar.check_zone_infection(31000)
            self.assertEqual(ar.sir_state, ar.STATE_INFECTED)
            self.assertEqual(ar.infected_since_ms, 31000)

            self.assertFalse(ar.check_recovery(31000 + ar.RECOVERY_DURATION_MS - 1))
            self.assertEqual(ar.sir_state, ar.STATE_INFECTED)

            ar.stopwatch.time = lambda: 31000 + ar.RECOVERY_DURATION_MS
            self.assertTrue(ar.check_recovery(31000 + ar.RECOVERY_DURATION_MS))
            self.assertEqual(ar.sir_state, ar.STATE_RECOVERED)

            # 4. Recovered robot cannot be re-infected
            ar.check_zone_infection(200000)
            ar.check_zone_infection(240000)
            self.assertEqual(ar.sir_state, ar.STATE_RECOVERED)
        finally:
            ar.hub.ble.observe = orig_observe
            ar.random.random = orig_random
            ar.stopwatch.time = orig_time
            ar.hub.ble.broadcast = orig_broadcast


if __name__ == "__main__":
    unittest.main()
