from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor, ColorSensor
from pybricks.parameters import Port, Button, Color, Direction
from pybricks.robotics import DriveBase
from pybricks.tools import wait, StopWatch
from pybricks.geometry import Matrix
import random
import json
import gc

# ==============================================================================
# 1. SETTINGS (Automatically derived from Hub Name: "Held 1", "Held 2", ...)
# ==============================================================================
VACCINATED = "No"           # "Yes" or "No"
ENABLE_MOVEMENT = True      # Set True to enable driving

# Default motor ports
LEFT_MOTOR_PORT = Port.C
RIGHT_MOTOR_PORT = Port.D
COLOR_SENSOR_PORT = Port.B

# HSV ranges for the 4 zones: (h_min, h_max, s_min, s_max, v_min, v_max)
# Note: Red wraps around 0/360, handled in detect_zone()
ZONE_NAMES = {
    "Red": "Red",
    "Green": "Green",
    "Blue": "Blue",
    "White": "White",
}

# Clockwise zone sequence: White -> Blue -> Green -> Red -> White
ZONE_ORDER_CW = ("White", "Blue", "Green", "Red")

# Slow driving & edge-avoidance parameters
DRIVE_SPEED_MM_S = 35       # Very slow forward/backup speed (mm/s)
TURN_SPEED_DEG_S = 45       # Slow in-place turn speed (deg/s)
EDGE_CONFIRM_MS = 400       # Cross touching zone seams (~14 mm) before treating None as dark table edge
BACKUP_DURATION_MS = 1000   # Max reverse time (~35 mm) when backing away from an edge/disallowed zone
EDGE_TURN_MIN_DEG = 90
EDGE_TURN_MAX_DEG = 180
ZONE_DEBOUNCE_SAMPLES = 3
DISALLOWED_CONFIRM_MS = 350

# DriveBase wheel dimensions (Standard SPIKE Prime wheels: 56 mm, track: 112 mm)
WHEEL_DIAMETER = 56
AXLE_TRACK = 112

# ==============================================================================
# BLE Channels (100% Connectionless BLE Broadcast)
# - Laptop broadcasts commands on Channel 0 (robots listen ONLY to Channel 0)
# - Each robot broadcasts telemetry on its own channel: ROBOT_ID (1..10)
# ==============================================================================
CONTROL_CHANNEL = 0
CMD_START = 1
CMD_STOP = 2
MAX_ROBOTS = 10
INFECTION_CONTACT_MS = 3000  # Co-location duration in ms before infection spreads


def get_hub_name(hub_obj):
    """Returns the hub's Bluetooth name across Pybricks versions."""
    try:
        info = hub_obj.system.info()
        if isinstance(info, dict) and info.get("name"):
            return info["name"]
    except Exception:
        pass
    try:
        name = hub_obj.system.name()
        if isinstance(name, str) and name:
            return name
    except Exception:
        pass
    return ""


def parse_robot_id(hub_name, default=1):
    """Extracts the robot number from a hub name like 'Held 1', 'Held 10', etc."""
    if not isinstance(hub_name, str):
        return default
    digits = ""
    for ch in hub_name:
        if "0" <= ch <= "9":
            digits += ch
        elif digits:
            break
    return int(digits) if digits else default


def config_from_hub_name(hub_name, default_id=1):
    """
    Derives (ROBOT_ID, AGENT_TYPE, INITIAL_INFECTED) from the hub name:
    - Held 1..4  -> Movement A (turns right), Held 5+ -> Movement B (turns left)
    - Held 1     -> Infected at start (True), others -> Susceptible (False)
    """
    robot_id = parse_robot_id(hub_name, default=default_id)
    agent_type = "B" if robot_id >= 5 else "A"
    initial_infected = (robot_id == 2)
    return robot_id, agent_type, initial_infected


_probe_hub = PrimeHub(observe_channels=list(range(0, MAX_ROBOTS + 1)))
HUB_NAME = get_hub_name(_probe_hub)
ROBOT_ID, AGENT_TYPE, INITIAL_INFECTED = config_from_hub_name(HUB_NAME)
BROADCAST_CHANNEL = ROBOT_ID
del _probe_hub
gc.collect()

# ==============================================================================
# 2. 5x5 DISPLAY ICONS (Matrix pixel brightness 0 to 100)
# ==============================================================================
ICON_I = Matrix([
    [0, 100, 100, 100, 0],
    [0,   0, 100,   0, 0],
    [0,   0, 100,   0, 0],
    [0,   0, 100,   0, 0],
    [0, 100, 100, 100, 0],
])

ICON_S = Matrix([
    [  0, 100, 100, 100,   0],
    [100,   0,   0,   0,   0],
    [  0, 100, 100, 100,   0],
    [  0,   0,   0,   0, 100],
    [  0, 100, 100, 100,   0],
])

ICON_R = Matrix([
    [100, 100, 100, 100,   0],
    [100,   0,   0,   0, 100],
    [100, 100, 100, 100,   0],
    [100,   0,   0, 100,   0],
    [100,   0,   0,   0, 100],
])

# ==============================================================================
# 3. INITIALIZATION
# ==============================================================================
# Broadcasts on channel ROBOT_ID (1..10) and observes Channel 0 (laptop) + peer channels (1..10)
PEER_CHANNELS = [ch for ch in range(1, MAX_ROBOTS + 1) if ch != BROADCAST_CHANNEL]
OBSERVE_CHANNELS = [CONTROL_CHANNEL] + PEER_CHANNELS
hub = PrimeHub(broadcast_channel=BROADCAST_CHANNEL, observe_channels=OBSERVE_CHANNELS)

sir_state = "I" if INITIAL_INFECTED else "S"
current_zone = "0"
log_entries = []
seq_num = 0
stopwatch = StopWatch()
peer_contact_start = {}
peer_last_seen = {}

# Setup Motors and DriveBase (graceful fallback if disconnected during bench testing)
drive_base = None
try:
    left_m = Motor(LEFT_MOTOR_PORT, Direction.COUNTERCLOCKWISE)
    right_m = Motor(RIGHT_MOTOR_PORT, Direction.CLOCKWISE)
    drive_base = DriveBase(left_m, right_m, WHEEL_DIAMETER, AXLE_TRACK)
except Exception:
    all_ports = [Port.A, Port.B, Port.C, Port.D, Port.E, Port.F]
    found_motors = []
    for p in all_ports:
        try:
            found_motors.append(Motor(p))
        except Exception:
            pass
    if len(found_motors) >= 2:
        drive_base = DriveBase(found_motors[0], found_motors[1], WHEEL_DIAMETER, AXLE_TRACK)
    else:
        print("No motors found! Running in simulation/logging only mode.")

# Setup ColorSensor (graceful fallback if disconnected)
color_sensor = None
try:
    color_sensor = ColorSensor(COLOR_SENSOR_PORT)
except Exception:
    for p in (Port.A, Port.B, Port.E, Port.F, Port.C, Port.D):
        try:
            color_sensor = ColorSensor(p)
            break
        except Exception:
            pass
if color_sensor is None:
    print("No ColorSensor found! Zone detection disabled.")

def detect_zone(sensor):
    """
    Classifies the current zone from the ColorSensor's HSV reading.
    Returns one of ZONE_NAMES values ('Red', 'Green', 'Blue', 'White'),
    or None if over a border/transition/unknown surface.
    """
    if sensor is None:
        return None
    try:
        hsv = sensor.hsv()
    except Exception:
        return None

    h, s, v = hsv.h, hsv.s, hsv.v

    # Ignore dark borders, black lines, and lift/transition artifacts
    if v < 25:
        return None

    # White: low saturation, high value (HSV observed: S=7..13, V=53..78)
    if s <= 16 and v >= 35:
        return ZONE_NAMES["White"]

    # Red: hue near 0/360, high saturation (HSV observed: H=10..14, S=87..89, V=40..51)
    if (h <= 30 or h >= 330) and s >= 60:
        return ZONE_NAMES["Red"]

    # Light Green: mid-green hue, moderate saturation (HSV observed: H=140..148, S=32..36, V=39..55)
    if 110 <= h <= 170 and 20 <= s <= 65:
        return ZONE_NAMES["Green"]

    # Blue: cyan-blue hue, high saturation (HSV observed: H=194..197, S=84..87, V=33..41)
    if 175 <= h <= 225 and s >= 60:
        return ZONE_NAMES["Blue"]

    return None

def show_state(state):
    """Updates hub status light and 5x5 matrix icon."""
    if state == "I":
        hub.light.on(Color.RED)
        hub.display.icon(ICON_I)
    elif state == "R":
        hub.light.on(Color.GREEN)
        hub.display.icon(ICON_R)
    else:  # "S"
        hub.light.on(Color.BLUE)
        hub.display.icon(ICON_S)

def log_sample(event_name="Sample", contact_id="—"):
    """
    Logs snapshot row and broadcasts it over BLE on channel ROBOT_ID (1..10).
    The laptop central hub picks up this broadcast packet in real-time.
    """
    global seq_num
    elapsed_s = round(stopwatch.time() / 1000.0, 1)
    entry = {
        "Time_Stamp": elapsed_s,
        "ID": ROBOT_ID,
        "Event": event_name,
        "Zone": current_zone,
        "SIR_State": sir_state,
        "Contact_ID": contact_id,
        "Agent_Type": AGENT_TYPE,
        "Vaccinated": VACCINATED
    }
    log_entries.append(entry)
    seq_num += 1

    # Print to console
    print("{:.1f},{},{},{},{},{},{},{}".format(
        elapsed_s, ROBOT_ID, event_name, current_zone, sir_state, contact_id, AGENT_TYPE, VACCINATED
    ))

    # Broadcast over BLE on Channel ROBOT_ID: (ROBOT_ID, elapsed_s, sir_state, current_zone, seq_num, event_code)
    event_code = (
        "Z" if event_name == "change_zone"
        else ("I" if event_name == "Infection" else ("A" if event_name == "Start" else "S"))
    )
    try:
        hub.ble.broadcast((ROBOT_ID, elapsed_s, sir_state, current_zone, seq_num, event_code))
    except Exception:
        pass


def check_zone_infection(now_ms):
    """
    Checks peer robot BLE broadcasts. If this robot is susceptible ('S') and
    shares the same valid zone with an infected robot ('I') for at least
    INFECTION_CONTACT_MS (3000 ms), this robot becomes infected ('I').
    """
    global sir_state
    if sir_state != "S" or current_zone == "0":
        peer_contact_start.clear()
        peer_last_seen.clear()
        return

    for ch in PEER_CHANNELS:
        try:
            obs = hub.ble.observe(ch)
        except Exception:
            obs = None

        if isinstance(obs, tuple) and len(obs) >= 4 and not isinstance(obs[0], str):
            other_id = obs[0]
            other_state = obs[2]
            other_zone = obs[3]

            if other_state == "I" and other_zone == current_zone:
                peer_last_seen[other_id] = now_ms
                if other_id not in peer_contact_start:
                    peer_contact_start[other_id] = now_ms
                elif now_ms - peer_contact_start[other_id] >= INFECTION_CONTACT_MS:
                    sir_state = "I"
                    show_state(sir_state)
                    hub.speaker.beep(frequency=600, duration=150)
                    peer_contact_start.clear()
                    peer_last_seen.clear()
                    log_sample("Infection", contact_id=other_id)
                    return
            else:
                peer_contact_start.pop(other_id, None)
                peer_last_seen.pop(other_id, None)
        else:
            # Expire stale contact timers if no packet seen from this peer for > 2.5s
            if ch in peer_contact_start and now_ms - peer_last_seen.get(ch, now_ms) > 2500:
                peer_contact_start.pop(ch, None)
                peer_last_seen.pop(ch, None)

_observe_error_logged = False


def check_laptop_command():
    """
    Observes BLE broadcast Channel 0 from the laptop:
    - CMD_START (1 or "START") -> Start experiment
    - CMD_STOP  (2 or "STOP")  -> Stop experiment
    """
    global _observe_error_logged
    try:
        obs = hub.ble.observe(CONTROL_CHANNEL)
    except Exception as e:
        if not _observe_error_logged:
            print(f"[ROBOT {ROBOT_ID}] BLE observe(Ch {CONTROL_CHANNEL}) error: {e}")
            _observe_error_logged = True
        obs = None

    if obs is not None:
        if obs == CMD_START or obs == "START":
            return CMD_START
        if isinstance(obs, tuple) and len(obs) > 0 and (obs[0] == CMD_START or obs[0] == "START"):
            return CMD_START
        if obs == CMD_STOP or obs == "STOP":
            return CMD_STOP
        if isinstance(obs, tuple) and len(obs) > 0 and (obs[0] == CMD_STOP or obs[0] == "STOP"):
            return CMD_STOP

    return None

# ==============================================================================
# 4. STANDBY MODE (Waits for Laptop BLE Broadcast on Channel 0)
# ==============================================================================
def wait_for_start():
    """
    Robot sits stationary in standby and broadcasts its presence on Channel ROBOT_ID.
    Starts automatically when the laptop broadcasts START on Channel 0.
    """
    show_state(sir_state)
    hub.light.on(Color.ORANGE)  # Orange light indicates Standby

    # Broadcast STANDBY presence on Channel ROBOT_ID so laptop sees this robot is ready
    try:
        hub.ble.broadcast(("STANDBY", ROBOT_ID, sir_state))
    except Exception:
        pass

    print(f"\n[ROBOT {ROBOT_ID}] Standby (listening on BLE Channel 0, broadcasting on Channel {BROADCAST_CHANNEL})...")

    while True:
        cmd = check_laptop_command()
        if cmd == CMD_START or Button.RIGHT in hub.buttons.pressed():
            print(f"[ROBOT {ROBOT_ID}] START broadcast received on Channel 0! Starting...")
            break
        wait(20)

    # Synchronize t = 0.0s
    stopwatch.reset()
    show_state(sir_state)
    hub.speaker.beep(frequency=1000, duration=200)

# ==============================================================================
# 5. ZONE NAVIGATION & EDGE AVOIDANCE
# ==============================================================================
def get_allowed_next_zone(current, agent_type):
    """
    Returns the single allowed next zone from `current`:
    - Type A moves clockwise: White -> Blue -> Green -> Red -> White
    - Type B moves counter-clockwise: White -> Red -> Green -> Blue -> White
    Returns None if `current` is not yet one of the 4 zones (e.g. '0').
    """
    if current not in ZONE_ORDER_CW:
        return None
    idx = ZONE_ORDER_CW.index(current)
    step = 1 if agent_type == "A" else -1
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
    Picks a random 90-180 degree turn angle:
    - Type A turns clockwise (+90..+180)
    - Type B turns counter-clockwise (-90..-180)
    """
    angle = random.randint(EDGE_TURN_MIN_DEG, EDGE_TURN_MAX_DEG)
    return angle if agent_type == "A" else -angle


class ZoneNavigator:
    """
    Drives slowly inside the current zone, allows transitions ONLY into the
    next zone in the configured direction (A: clockwise, B: counter-clockwise),
    and backs up + turns 90-180 deg when hitting an edge or disallowed zone.
    """

    def __init__(self, agent_type, drive_base_obj=None, has_color_sensor=True):
        self.agent_type = agent_type
        self.drive_base = drive_base_obj
        self.has_color_sensor = has_color_sensor
        self.state = "DRIVE"  # "DRIVE", "BACKUP", "TURN"
        self.state_start_ms = 0
        self.turn_timeout_ms = 0
        self.seen_cur_backup = False
        self.pending_zone = None
        self.pending_count = 0
        self.edge_start_ms = None
        self.disallowed_start_ms = None

    def start(self, now_ms=0):
        """Configures slow DriveBase settings and begins driving straight."""
        if self.drive_base:
            try:
                self.drive_base.settings(DRIVE_SPEED_MM_S, 100, TURN_SPEED_DEG_S, 120)
            except Exception:
                pass
            self.drive_base.drive(speed=DRIVE_SPEED_MM_S, turn_rate=0)
        self.state = "DRIVE"
        self.state_start_ms = now_ms

    def _reset_debounces(self):
        self.pending_zone = None
        self.pending_count = 0
        self.edge_start_ms = None
        self.disallowed_start_ms = None

    def _start_backup(self, now_ms):
        self._reset_debounces()
        self.state = "BACKUP"
        self.state_start_ms = now_ms
        self.seen_cur_backup = False
        if self.drive_base:
            self.drive_base.stop()
            self.drive_base.drive(speed=-DRIVE_SPEED_MM_S, turn_rate=0)

    def _start_turn(self, now_ms):
        self._reset_debounces()
        angle = pick_edge_turn_angle(self.agent_type)
        self.state = "TURN"
        self.state_start_ms = now_ms
        self.turn_timeout_ms = int(abs(angle) * 1000 / TURN_SPEED_DEG_S) + 2000
        if self.drive_base:
            self.drive_base.stop()
            self.drive_base.turn(angle, wait=False)

    def _resume_drive(self, now_ms):
        self._reset_debounces()
        self.state = "DRIVE"
        self.state_start_ms = now_ms
        if self.drive_base:
            self.drive_base.drive(speed=DRIVE_SPEED_MM_S, turn_rate=0)

    def step(self, now_ms, current_zone_val, detected, movement_enabled=True):
        """
        Advances movement and zone transition state by one tick.
        Returns the new zone name if an allowed zone transition occurred, else None.
        """
        if movement_enabled and self.state == "BACKUP":
            if detected == current_zone_val:
                self.seen_cur_backup = True
            elif self.seen_cur_backup and detected is not None:
                # Stop backing up before crossing out the opposite side of the zone
                self._start_turn(now_ms)
                return None

            if now_ms - self.state_start_ms >= BACKUP_DURATION_MS:
                self._start_turn(now_ms)
            return None

        if movement_enabled and self.state == "TURN":
            elapsed = now_ms - self.state_start_ms
            turn_done = self.drive_base is None or (elapsed >= 100 and self.drive_base.done())
            if turn_done or elapsed >= self.turn_timeout_ms:
                self._resume_drive(now_ms)
            return None

        if detected is None:
            self.pending_zone = None
            self.pending_count = 0
            self.disallowed_start_ms = None
            if movement_enabled and self.has_color_sensor and current_zone_val != "0":
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


# ==============================================================================
# 6. MAIN PROGRAM
# ==============================================================================
def main():
    global current_zone
    wait_for_start()

    initial_zone = detect_zone(color_sensor)
    if initial_zone is not None:
        current_zone = initial_zone

    print("Time_Stamp,ID,Event,Zone,SIR_State,Contact_ID,Agent_Type,Vaccinated")
    log_sample("Start")

    navigator = ZoneNavigator(
        AGENT_TYPE,
        drive_base_obj=drive_base,
        has_color_sensor=(color_sensor is not None),
    )
    if ENABLE_MOVEMENT:
        navigator.start(now_ms=0)

    last_log_ms = 0

    # Run until STOP broadcast on Channel 0 (or LEFT button pressed on hub)
    while True:
        cmd = check_laptop_command()
        if cmd == CMD_STOP or Button.LEFT in hub.buttons.pressed():
            print(f"[ROBOT {ROBOT_ID}] STOP broadcast received on Channel 0! Halting...")
            break

        now_ms = stopwatch.time()

        # 0. Zone detection, strict directional transitions, and slow edge-avoidance movement
        detected = detect_zone(color_sensor)
        new_zone = navigator.step(now_ms, current_zone, detected, movement_enabled=ENABLE_MOVEMENT)
        if new_zone is not None:
            current_zone = new_zone
            peer_contact_start.clear()
            peer_last_seen.clear()
            log_sample("change_zone")

        # 1. Check for co-location infection (3 seconds in same zone as an 'I' robot)
        check_zone_infection(now_ms)

        # 2. Periodic snapshot log every 1000 ms (1.0 s)
        if now_ms - last_log_ms >= 1000:
            log_sample("Sample")
            last_log_ms = now_ms

        wait(20)

    # Stop motors and stop BLE telemetry broadcasting
    if drive_base:
        drive_base.stop()
    try:
        hub.ble.broadcast(None)
    except Exception:
        pass
    hub.display.off()
    hub.speaker.beep(frequency=400, duration=300)

    # Save JSON log on hub flash and print dump to terminal
    try:
        with open("log.json", "w") as f:
            json.dump(log_entries, f)
    except Exception:
        pass

    print("\n=== JSON LOG DUMP START ===")
    print(json.dumps(log_entries))
    print("=== JSON LOG DUMP END ===")

if __name__ == "__main__":
    main()
