"""
Domain enums shared across the host PC and LEGO SPIKE Prime hubs.

On CPython (host PC), these inherit from `enum.IntEnum` / `enum.StrEnum`.
On Pybricks MicroPython (which omits stdlib `enum` to save flash/RAM),
they fall back to lightweight attribute classes with identical string/int values.
"""

try:
    from enum import IntEnum, StrEnum
except ImportError:
    IntEnum = object
    StrEnum = object


class AgentType(StrEnum):
    """Robot traversal direction around the 4-zone ring."""

    CLOCKWISE = "A"
    COUNTER_CLOCKWISE = "B"


class PortLetter(StrEnum):
    """Valid SPIKE Prime hub hardware port letters."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"


class Zone(StrEnum):
    """Arena color zones and initial unknown zone marker."""

    RED = "Red"
    GREEN = "Green"
    BLUE = "Blue"
    YELLOW = "Yellow"
    UNKNOWN = "0"


class SIRState(StrEnum):
    """Epidemiological SIR states."""

    SUSCEPTIBLE = "S"
    INFECTED = "I"
    RECOVERED = "R"
    VACCINATED = "V"  # Defined for state support; no vaccination behavior yet
    UNKNOWN = "?"


class VaccinatedStatus(StrEnum):
    """Human-readable vaccination flag emitted in telemetry logs."""

    YES = "Yes"
    NO = "No"


class ControlCommand(IntEnum):
    """Commands broadcast by the host PC on BLE Channel 0."""

    START = 1
    STOP = 2


class EventName(StrEnum):
    """Telemetry log event names."""

    SAMPLE = "Sample"
    START = "Start"
    CHANGE_ZONE = "change_zone"
    INFECTION = "Infection"
    RECOVERY = "Recovery"


class EventCode(StrEnum):
    """Compact 1-character event codes transmitted over BLE."""

    SAMPLE = "S"
    START = "A"
    CHANGE_ZONE = "Z"
    INFECTION = "I"
    RECOVERY = "R"


class NavState(StrEnum):
    """ZoneNavigator state-machine states."""

    DRIVE = "DRIVE"
    BACKUP = "BACKUP"
    TURN = "TURN"
    OBSTACLE_BACKUP = "OBSTACLE_BACKUP"
