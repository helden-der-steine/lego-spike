"""
Zone navigation, strict directional ring transitions, edge avoidance, and obstacle avoidance.

Pure Python so it can run on both the Pybricks hub (MicroPython) and host unit tests.
"""

import random

from shared.enums import AgentType, NavState, Zone
from shared.sim_config import NAV_CONFIG, ZONE_ORDER_CW

# Driving & avoidance tuning parameters (loaded from config.toml)
DRIVE_SPEED_MM_S = NAV_CONFIG.drive_speed_mm_s
DRIVE_ACCEL_MM_S2 = NAV_CONFIG.drive_accel_mm_s2
TURN_SPEED_DEG_S = NAV_CONFIG.turn_speed_deg_s
TURN_ACCEL_DEG_S2 = NAV_CONFIG.turn_accel_deg_s2

EDGE_CONFIRM_MS = NAV_CONFIG.edge_confirm_ms
BACKUP_DURATION_MS = NAV_CONFIG.backup_duration_ms
EDGE_TURN_MIN_DEG = NAV_CONFIG.edge_turn_min_deg
EDGE_TURN_MAX_DEG = NAV_CONFIG.edge_turn_max_deg
ZONE_DEBOUNCE_SAMPLES = NAV_CONFIG.zone_debounce_samples
DISALLOWED_CONFIRM_MS = NAV_CONFIG.disallowed_confirm_ms

OBSTACLE_STOP_MM = NAV_CONFIG.obstacle_stop_mm
OBSTACLE_RESUME_MM = NAV_CONFIG.obstacle_resume_mm
OBSTACLE_CLEAR_SAMPLES = NAV_CONFIG.obstacle_clear_samples

MIN_TURN_CHECK_MS = 100
TURN_TIMEOUT_BUFFER_MS = 2000


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
    step = 1 if agent_type == AgentType.CLOCKWISE else -1
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
    return angle if agent_type == AgentType.CLOCKWISE else -angle


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
        self.state = NavState.DRIVE
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
        self.state = NavState.DRIVE
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
        self.state = NavState.BACKUP
        self.state_start_ms = now_ms
        self.seen_cur_backup = False
        self._drive_reverse()

    def _start_obstacle_backup(self, now_ms, in_current_zone):
        self._reset_debounces()
        self.state = NavState.OBSTACLE_BACKUP
        self.state_start_ms = now_ms
        self.seen_cur_obstacle_backup = in_current_zone
        self.obstacle_clear_count = 0
        self._drive_reverse()

    def _start_turn(self, now_ms):
        self._reset_debounces()
        angle = pick_edge_turn_angle(self.agent_type)
        self.state = NavState.TURN
        self.state_start_ms = now_ms
        self.turn_timeout_ms = int(abs(angle) * 1000 / TURN_SPEED_DEG_S) + TURN_TIMEOUT_BUFFER_MS
        if self.drive_base:
            self.drive_base.stop()
            self.drive_base.turn(angle, wait=False)

    def _resume_drive(self, now_ms):
        self._reset_debounces()
        self.state = NavState.DRIVE
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
            if movement_enabled and self.has_color_sensor and current_zone_val != Zone.UNKNOWN:
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
            if self.state == NavState.OBSTACLE_BACKUP:
                self._step_obstacle_backup(now_ms, current_zone_val, detected, distance_mm)
                return None

            if self.state == NavState.DRIVE and distance_mm is not None and distance_mm < OBSTACLE_STOP_MM:
                self._start_obstacle_backup(now_ms, detected == current_zone_val)
                return None

            if self.state == NavState.BACKUP:
                self._step_backup(now_ms, current_zone_val, detected)
                return None

            if self.state == NavState.TURN:
                self._step_turn(now_ms)
                return None

        return self._handle_zone_reading(now_ms, current_zone_val, detected, movement_enabled)
