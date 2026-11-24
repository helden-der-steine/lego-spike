"""
Zone navigation, strict directional ring transitions, edge avoidance, and obstacle avoidance.

Pure Python so it can run on both the Pybricks hub (MicroPython) and host unit tests.
"""

import random

from shared.sim_config import AGENT_TYPE_CW, ZONE_ORDER_CW, ZONE_UNKNOWN

# Driving & avoidance tuning parameters
DRIVE_SPEED_MM_S = 35       # Slow forward/reverse speed (mm/s)
DRIVE_ACCEL_MM_S2 = 100     # Straight-line acceleration (mm/s^2)
TURN_SPEED_DEG_S = 45       # In-place turn speed (deg/s)
TURN_ACCEL_DEG_S2 = 120     # Angular acceleration (deg/s^2)

EDGE_CONFIRM_MS = 400       # Cross touching zone seams (~14 mm) before treating None as table edge
BACKUP_DURATION_MS = 1000   # Max reverse time (~35 mm) when backing away from an edge/disallowed zone
EDGE_TURN_MIN_DEG = 45
EDGE_TURN_MAX_DEG = 110
ZONE_DEBOUNCE_SAMPLES = 3
DISALLOWED_CONFIRM_MS = 350

OBSTACLE_STOP_MM = 80       # Trigger backup when obstacle is closer than 80 mm
OBSTACLE_RESUME_MM = 100    # Hysteresis clear distance (100 mm) before turning away
OBSTACLE_CLEAR_SAMPLES = 3

MIN_TURN_CHECK_MS = 100
TURN_TIMEOUT_BUFFER_MS = 2000

# Navigator state machine states
NAV_DRIVE = "DRIVE"
NAV_BACKUP = "BACKUP"
NAV_TURN = "TURN"
NAV_OBSTACLE_BACKUP = "OBSTACLE_BACKUP"


def get_allowed_next_zone(current, agent_type):
    """
    Returns the single allowed next zone from `current`:
    - Type A moves clockwise: Yellow -> Blue -> Green -> Red -> Yellow
    - Type B moves counter-clockwise: Yellow -> Red -> Green -> Blue -> Yellow
    Returns None if `current` is not yet one of the 4 zones (e.g. '0').
    """
    if current not in ZONE_ORDER_CW:
        return None
    idx = ZONE_ORDER_CW.index(current)
    step = 1 if agent_type == AGENT_TYPE_CW else -1
    return ZONE_ORDER_CW[(idx + step) % len(ZONE_ORDER_CW)]


def is_zone_transition_allowed(current, detected, agent_type):
    """Returns True only if moving from `current` into `detected` is permitted."""
    if detected is None or detected == current:
        return False
    allowed = get_allowed_next_zone(current, agent_type)
    if allowed is None:
        return detected in ZONE_ORDER_CW
    return detected == allowed


def pick_edge_turn_angle(agent_type):
    """
    Picks a random 45-110 degree turn angle:
    - Type A turns clockwise (+45..+110)
    - Type B turns counter-clockwise (-45..-110)
    """
    angle = random.randint(EDGE_TURN_MIN_DEG, EDGE_TURN_MAX_DEG)
    return angle if agent_type == AGENT_TYPE_CW else -angle


class ZoneNavigator:
    """
    Drives slowly inside the current zone, allows transitions ONLY into the
    next zone in the configured direction (A: clockwise, B: counter-clockwise),
    and backs up + turns away when hitting an edge, disallowed zone, or obstacle.
    """

    def __init__(self, agent_type, drive_base_obj=None, has_color_sensor=True):
        self.agent_type = agent_type
        self.drive_base = drive_base_obj
        self.has_color_sensor = has_color_sensor
        self.state = NAV_DRIVE
        self.state_start_ms = 0
        self.turn_timeout_ms = 0
        self.seen_cur_backup = False
        self.pending_zone = None
        self.pending_count = 0
        self.edge_start_ms = None
        self.disallowed_start_ms = None
        self.seen_cur_obstacle_backup = False
        self.obstacle_clear_count = 0

    def start(self, now_ms=0):
        """Configures slow DriveBase settings and begins driving straight."""
        if self.drive_base:
            try:
                self.drive_base.settings(
                    DRIVE_SPEED_MM_S, DRIVE_ACCEL_MM_S2, TURN_SPEED_DEG_S, TURN_ACCEL_DEG_S2
                )
            except Exception:
                pass
            self.drive_base.drive(speed=DRIVE_SPEED_MM_S, turn_rate=0)
        self.state = NAV_DRIVE
        self.state_start_ms = now_ms

    def _reset_debounces(self):
        self.pending_zone = None
        self.pending_count = 0
        self.edge_start_ms = None
        self.disallowed_start_ms = None

    def _drive_reverse(self):
        if self.drive_base:
            self.drive_base.stop()
            self.drive_base.drive(speed=-DRIVE_SPEED_MM_S, turn_rate=0)

    def _start_backup(self, now_ms):
        self._reset_debounces()
        self.state = NAV_BACKUP
        self.state_start_ms = now_ms
        self.seen_cur_backup = False
        self._drive_reverse()

    def _start_obstacle_backup(self, now_ms, in_current_zone):
        self._reset_debounces()
        self.state = NAV_OBSTACLE_BACKUP
        self.state_start_ms = now_ms
        self.seen_cur_obstacle_backup = in_current_zone
        self.obstacle_clear_count = 0
        self._drive_reverse()

    def _start_turn(self, now_ms):
        self._reset_debounces()
        angle = pick_edge_turn_angle(self.agent_type)
        self.state = NAV_TURN
        self.state_start_ms = now_ms
        self.turn_timeout_ms = int(abs(angle) * 1000 / TURN_SPEED_DEG_S) + TURN_TIMEOUT_BUFFER_MS
        if self.drive_base:
            self.drive_base.stop()
            self.drive_base.turn(angle, wait=False)

    def _resume_drive(self, now_ms):
        self._reset_debounces()
        self.state = NAV_DRIVE
        self.state_start_ms = now_ms
        if self.drive_base:
            self.drive_base.drive(speed=DRIVE_SPEED_MM_S, turn_rate=0)

    def _step_obstacle_backup(self, now_ms, current_zone_val, detected, distance_mm):
        # Stop reversing early if we cross out the opposite side of our current zone
        if detected == current_zone_val:
            self.seen_cur_obstacle_backup = True
        elif self.seen_cur_obstacle_backup and detected is not None:
            self._start_turn(now_ms)
            return

        if distance_mm is None or distance_mm >= OBSTACLE_RESUME_MM:
            self.obstacle_clear_count += 1
            if self.obstacle_clear_count >= OBSTACLE_CLEAR_SAMPLES:
                self.obstacle_clear_count = 0
                self._start_turn(now_ms)
        else:
            self.obstacle_clear_count = 0

    def _step_backup(self, now_ms, current_zone_val, detected):
        if detected == current_zone_val:
            self.seen_cur_backup = True
        elif self.seen_cur_backup and detected is not None:
            # Stop backing up before crossing out the opposite side of the zone
            self._start_turn(now_ms)
            return

        if now_ms - self.state_start_ms >= BACKUP_DURATION_MS:
            self._start_turn(now_ms)

    def _step_turn(self, now_ms):
        elapsed = now_ms - self.state_start_ms
        turn_done = self.drive_base is None or (elapsed >= MIN_TURN_CHECK_MS and self.drive_base.done())
        if turn_done or elapsed >= self.turn_timeout_ms:
            self._resume_drive(now_ms)

    def _handle_zone_reading(self, now_ms, current_zone_val, detected, movement_enabled):
        if detected is None:
            self.pending_zone = None
            self.pending_count = 0
            self.disallowed_start_ms = None
            if movement_enabled and self.has_color_sensor and current_zone_val != ZONE_UNKNOWN:
                if self.edge_start_ms is None:
                    self.edge_start_ms = now_ms
                elif now_ms - self.edge_start_ms >= EDGE_CONFIRM_MS:
                    self._start_backup(now_ms)
            return None

        self.edge_start_ms = None

        if detected == current_zone_val:
            self.pending_zone = None
            self.pending_count = 0
            self.disallowed_start_ms = None
            return None

        if is_zone_transition_allowed(current_zone_val, detected, self.agent_type):
            self.disallowed_start_ms = None
            if detected == self.pending_zone:
                self.pending_count += 1
            else:
                self.pending_zone = detected
                self.pending_count = 1
            if self.pending_count >= ZONE_DEBOUNCE_SAMPLES:
                self._reset_debounces()
                return detected
            return None

        # Disallowed zone border: do not enter; back up and turn away after confirmation
        self.pending_zone = None
        self.pending_count = 0
        if movement_enabled:
            if self.disallowed_start_ms is None:
                self.disallowed_start_ms = now_ms
            elif now_ms - self.disallowed_start_ms >= DISALLOWED_CONFIRM_MS:
                self._start_backup(now_ms)
        return None

    def step(self, now_ms, current_zone_val, detected, movement_enabled=True, distance_mm=None):
        """
        Advances movement and zone transition state by one tick.
        Returns the new zone name if an allowed zone transition occurred, else None.
        """
        if movement_enabled:
            if self.state == NAV_OBSTACLE_BACKUP:
                self._step_obstacle_backup(now_ms, current_zone_val, detected, distance_mm)
                return None

            if self.state == NAV_DRIVE and distance_mm is not None and distance_mm < OBSTACLE_STOP_MM:
                self._start_obstacle_backup(now_ms, detected == current_zone_val)
                return None

            if self.state == NAV_BACKUP:
                self._step_backup(now_ms, current_zone_val, detected)
                return None

            if self.state == NAV_TURN:
                self._step_turn(now_ms)
                return None

        return self._handle_zone_reading(now_ms, current_zone_val, detected, movement_enabled)
