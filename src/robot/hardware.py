"""
Hardware abstraction for the LEGO SPIKE Prime hub, motors, sensors, and 5x5 display.

Runs on the Pybricks hub (MicroPython). All ports, geometry, speaker tones, and HSV
thresholds are loaded from `shared.sim_config.HW_CONFIG` (sourced from `config.toml`).
"""

from pybricks.geometry import Matrix
from pybricks.parameters import Color, Direction, Port
from pybricks.pupdevices import ColorSensor, Motor, UltrasonicSensor
from pybricks.robotics import DriveBase

from shared.enums import PortLetter, SIRState, Zone
from shared.sim_config import HW_CONFIG

PORT_MAP = {
    PortLetter.A: Port.A,
    PortLetter.B: Port.B,
    PortLetter.C: Port.C,
    PortLetter.D: Port.D,
    PortLetter.E: Port.E,
    PortLetter.F: Port.F,
}

# Hardware port assignments
LEFT_MOTOR_PORT = PORT_MAP[HW_CONFIG.left_motor_port]
RIGHT_MOTOR_PORT = PORT_MAP[HW_CONFIG.right_motor_port]
COLOR_SENSOR_PORT = PORT_MAP[HW_CONFIG.color_sensor_port]
DISTANCE_SENSOR_PORT = PORT_MAP[HW_CONFIG.distance_sensor_port]
SCAN_PORTS = (Port.A, Port.B, Port.E, Port.F, Port.C, Port.D)

# Standard SPIKE Prime wheel geometry (mm)
WHEEL_DIAMETER_MM = HW_CONFIG.wheel_diameter_mm
AXLE_TRACK_MM = HW_CONFIG.axle_track_mm

# Speaker feedback tones
_SPEAKER = HW_CONFIG.speaker
BEEP_START_FREQ_HZ = _SPEAKER.start_freq_hz
BEEP_START_DURATION_MS = _SPEAKER.start_duration_ms
BEEP_INFECTION_FREQ_HZ = _SPEAKER.infection_freq_hz
BEEP_RECOVERY_FREQ_HZ = _SPEAKER.recovery_freq_hz
BEEP_EVENT_DURATION_MS = _SPEAKER.event_duration_ms
BEEP_STOP_FREQ_HZ = _SPEAKER.stop_freq_hz
BEEP_STOP_DURATION_MS = _SPEAKER.stop_duration_ms

# Calibrated HSV thresholds for zone classification
_HSV = HW_CONFIG.color_hsv
MIN_ZONE_VALUE = _HSV.min_zone_value
RED_HUE_LOW_MAX = _HSV.red.hue_low_max
RED_HUE_HIGH_MIN = _HSV.red.hue_high_min
RED_MIN_SATURATION = _HSV.red.min_saturation
YELLOW_HUE_MIN = _HSV.yellow.hue_min
YELLOW_HUE_MAX = _HSV.yellow.hue_max
YELLOW_MIN_SATURATION = _HSV.yellow.min_saturation
YELLOW_MIN_VALUE = _HSV.yellow.min_value
GREEN_HUE_MIN = _HSV.green.hue_min
GREEN_HUE_MAX = _HSV.green.hue_max
GREEN_MIN_SATURATION = _HSV.green.min_saturation
BLUE_HUE_MIN = _HSV.blue.hue_min
BLUE_HUE_MAX = _HSV.blue.hue_max
BLUE_MIN_SATURATION = _HSV.blue.min_saturation

# 5x5 LED matrix icons (pixel brightness 0..100)
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

ICON_V = Matrix([
    [100,   0,   0,   0, 100],
    [100,   0,   0,   0, 100],
    [100,   0,   0,   0, 100],
    [  0, 100,   0, 100,   0],
    [  0,   0, 100,   0,   0],
])

STATE_DISPLAY_MAP = {
    SIRState.INFECTED: (Color.RED, ICON_I),
    SIRState.RECOVERED: (Color.GREEN, ICON_R),
    SIRState.VACCINATED: (Color.CYAN, ICON_V),
    SIRState.SUSCEPTIBLE: (Color.BLUE, ICON_S),
}


def get_hub_name(hub_obj):
    """Returns the hub's Bluetooth name across Pybricks firmware versions."""
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


def show_state(hub, state):
    """Updates the hub status light and 5x5 LED matrix icon for `state`."""
    light_color, icon = STATE_DISPLAY_MAP.get(state, (Color.BLUE, ICON_S))
    hub.light.on(light_color)
    hub.display.icon(icon)


def init_drive_base():
    """Initializes DriveBase on default ports, falling back to any two detected motors."""
    try:
        left_motor = Motor(LEFT_MOTOR_PORT, Direction.COUNTERCLOCKWISE)
        right_motor = Motor(RIGHT_MOTOR_PORT, Direction.CLOCKWISE)
        return DriveBase(left_motor, right_motor, WHEEL_DIAMETER_MM, AXLE_TRACK_MM)
    except Exception:
        pass

    found_motors = []
    for port in SCAN_PORTS:
        try:
            found_motors.append(Motor(port))
        except Exception:
            pass
    if len(found_motors) >= 2:
        return DriveBase(found_motors[0], found_motors[1], WHEEL_DIAMETER_MM, AXLE_TRACK_MM)

    print("No motors found! Running in simulation/logging only mode.")
    return None


def find_color_sensor(preferred_port=COLOR_SENSOR_PORT):
    """Returns `(ColorSensor, Port)` trying `preferred_port` first, then scanning all ports."""
    ports_to_try = [preferred_port] + [p for p in SCAN_PORTS if p != preferred_port]
    for port in ports_to_try:
        try:
            return ColorSensor(port), port
        except Exception:
            pass
    return None, None


def init_color_sensor():
    """Initializes the ColorSensor, returning None if none is attached."""
    sensor, _ = find_color_sensor()
    if sensor is None:
        print("No ColorSensor found! Zone detection disabled.")
    return sensor


def init_distance_sensor():
    """Initializes the UltrasonicSensor on DISTANCE_SENSOR_PORT, returning None if absent."""
    try:
        sensor = UltrasonicSensor(DISTANCE_SENSOR_PORT)
        print(f"UltrasonicSensor detected on {DISTANCE_SENSOR_PORT}")
        return sensor
    except Exception:
        print(f"No UltrasonicSensor found on {DISTANCE_SENSOR_PORT}! Obstacle stopping disabled.")
        return None


def read_distance_mm(sensor):
    """Returns distance in mm from UltrasonicSensor, or None if unavailable."""
    if sensor is None:
        return None
    try:
        return sensor.distance()
    except Exception:
        return None


def detect_zone(sensor):
    """
    Classifies the current zone from the ColorSensor's HSV reading.

    Returns one of `ZONE_NAMES` ('Red', 'Green', 'Blue', 'Yellow'),
    or None if over a border, dark surface, or transition artifact.
    """
    if sensor is None:
        return None
    try:
        hsv = sensor.hsv()
    except Exception:
        return None

    h, s, v = hsv.h, hsv.s, hsv.v
    if v < MIN_ZONE_VALUE:
        return None

    # Red wraps around 0/360 degrees on the hue wheel
    if (h <= RED_HUE_LOW_MAX or h >= RED_HUE_HIGH_MIN) and s >= RED_MIN_SATURATION:
        return Zone.RED
    if YELLOW_HUE_MIN <= h <= YELLOW_HUE_MAX and s >= YELLOW_MIN_SATURATION and v >= YELLOW_MIN_VALUE:
        return Zone.YELLOW
    if GREEN_HUE_MIN <= h <= GREEN_HUE_MAX and s >= GREEN_MIN_SATURATION:
        return Zone.GREEN
    if BLUE_HUE_MIN <= h <= BLUE_HUE_MAX and s >= BLUE_MIN_SATURATION:
        return Zone.BLUE

    return None
