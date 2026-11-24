"""
Shared BLE broadcast protocol constants, event mappings, and telemetry builders.

This module is pure Python (no Pybricks or host-only imports) so it can run
on both the LEGO SPIKE Prime hub (MicroPython) and the host PC.
"""

from shared.sim_config import MAX_ROBOTS, NO_CONTACT_ID

# LEGO System A/S Bluetooth SIG Company ID (0x97, 0x03 little-endian)
LEGO_COMPANY_ID = 0x0397

# Connectionless BLE channel allocation
CONTROL_CHANNEL = 0  # Laptop broadcasts START/STOP on Channel 0
ROBOT_CHANNELS = tuple(range(1, MAX_ROBOTS + 1))

# Control commands broadcast on Channel 0
CMD_START = 1
CMD_STOP = 2
CMD_START_STR = "START"
CMD_STOP_STR = "STOP"

# Standby heartbeat tag broadcast by robots on their own channel
STANDBY_TAG = "STANDBY"

# Telemetry event names
EVENT_SAMPLE = "Sample"
EVENT_START = "Start"
EVENT_CHANGE_ZONE = "change_zone"
EVENT_INFECTION = "Infection"
EVENT_RECOVERY = "Recovery"

# Compact single-character event codes transmitted over BLE
EVENT_CODE_SAMPLE = "S"
EVENT_CODE_START = "A"
EVENT_CODE_CHANGE_ZONE = "Z"
EVENT_CODE_INFECTION = "I"
EVENT_CODE_RECOVERY = "R"

EVENT_NAME_TO_CODE = {
    EVENT_SAMPLE: EVENT_CODE_SAMPLE,
    EVENT_START: EVENT_CODE_START,
    EVENT_CHANGE_ZONE: EVENT_CODE_CHANGE_ZONE,
    EVENT_INFECTION: EVENT_CODE_INFECTION,
    EVENT_RECOVERY: EVENT_CODE_RECOVERY,
}

EVENT_CODE_TO_NAME = {
    code: name for name, code in EVENT_NAME_TO_CODE.items()
}


def event_code_from_name(event_name):
    """Maps a human-readable event name to its compact 1-char BLE event code."""
    return EVENT_NAME_TO_CODE.get(event_name, EVENT_CODE_SAMPLE)


def event_name_from_code(event_code):
    """Maps a compact 1-char BLE event code back to its event name."""
    return EVENT_CODE_TO_NAME.get(event_code, EVENT_SAMPLE)


def build_log_entry(
    timestamp_s,
    robot_id,
    event_name,
    zone,
    sir_state,
    agent_type,
    vaccinated,
    contact_id=NO_CONTACT_ID,
):
    """Builds a standardized telemetry log dictionary."""
    return {
        "Time_Stamp": timestamp_s,
        "ID": robot_id,
        "Event": event_name,
        "Zone": zone,
        "SIR_State": sir_state,
        "Contact_ID": contact_id,
        "Agent_Type": agent_type,
        "Vaccinated": vaccinated,
    }
