"""
Hardware abstraction for the LEGO SPIKE Prime hub, motors, sensors, and 5x5 display.

Runs on the Pybricks hub (MicroPython).
"""

from pybricks.geometry import Matrix
from pybricks.parameters import Color, Direction, Port
from pybricks.pupdevices import ColorSensor, Motor, UltrasonicSensor
from pybricks.robotics import DriveBase

from shared.sim_config import (
    STATE_INFECTED,
    STATE_RECOVERED,
    STATE_SUSCEPTIBLE,
    STATE_VACCINATED,
    ZONE_NAMES,
)

# Default hardware port assignments
LEFT_MOTOR_PORT = Port.C
RIGHT_MOTOR_PORT = Port.D
COLOR_SENSOR_PORT = Port.B
DISTANCE_SENSOR_PORT = Port.A
SCAN_PORTS = (Port.A, Port.B, Port.E, Port.F, Port.C, Port.D)

# Standard SPIKE Prime wheel geometry (mm)
WHEEL_DIAMETER_MM = 56
AXLE_TRACK_MM = 112

# Speaker feedback tones
BEEP_START_FREQ_HZ = 1000
BEEP_START_DURATION_MS = 200
BEEP_INFECTION_FREQ_HZ = 600
BEEP_RECOVERY_FREQ_HZ = 800
BEEP_EVENT_DURATION_MS = 150
BEEP_STOP_FREQ_HZ = 400
BEEP_STOP_DURATION_MS = 300

# Calibrated HSV thresholds for zone classification (observed on printed arena mats)
MIN_ZONE_VALUE = 22  # Ignore dark borders, black lines, and lift/transition artifacts
RED_HUE_LOW_MAX = 15
RED_HUE_HIGH_MIN = 330
RED_MIN_SATURATION = 65
YELLOW_HUE_MIN = 20
YELLOW_HUE_MAX = 55
YELLOW_MIN_SATURATION = 55
YELLOW_MIN_VALUE = 35
GREEN_HUE_MIN = 95
GREEN_HUE_MAX = 165
GREEN_MIN_SATURATION = 35
BLUE_HUE_MIN = 175
BLUE_HUE_MAX = 235
BLUE_MIN_SATURATION = 60

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
    STATE_INFECTED: (Color.RED, ICON_I),
    STATE_RECOVERED: (Color.GREEN, ICON_R),
    STATE_VACCINATED: (Color.CYAN, ICON_V),
    STATE_SUSCEPTIBLE: (Color.BLUE, ICON_S),
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
        return ZONE_NAMES["Red"]
    if YELLOW_HUE_MIN <= h <= YELLOW_HUE_MAX and s >= YELLOW_MIN_SATURATION and v >= YELLOW_MIN_VALUE:
        return ZONE_NAMES["Yellow"]
    if GREEN_HUE_MIN <= h <= GREEN_HUE_MAX and s >= GREEN_MIN_SATURATION:
        return ZONE_NAMES["Green"]
    if BLUE_HUE_MIN <= h <= BLUE_HUE_MAX and s >= BLUE_MIN_SATURATION:
        return ZONE_NAMES["Blue"]

    return None
