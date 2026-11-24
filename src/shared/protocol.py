"""
Shared BLE broadcast protocol constants, event mappings, and telemetry builders.

This module is pure Python (no Pybricks or host-only imports) so it can run
on both the LEGO SPIKE Prime hub (MicroPython) and the host PC.
"""

from shared.enums import ControlCommand, EventCode, EventName
from shared.models import NO_CONTACT_ID, TelemetryEntry
from shared.sim_config import MAX_ROBOTS

# LEGO System A/S Bluetooth SIG Company ID (0x97, 0x03 little-endian)
LEGO_COMPANY_ID = 0x0397

# Connectionless BLE channel allocation
CONTROL_CHANNEL = 0  # Laptop broadcasts START/STOP on Channel 0
ROBOT_CHANNELS = tuple(range(1, MAX_ROBOTS + 1))

# Legacy string command forms accepted from Channel 0
CMD_START_STR = "START"
CMD_STOP_STR = "STOP"

# Standby heartbeat tag broadcast by robots on their own channel
STANDBY_TAG = "STANDBY"

EVENT_NAME_TO_CODE = {
    EventName.SAMPLE: EventCode.SAMPLE,
    EventName.START: EventCode.START,
    EventName.CHANGE_ZONE: EventCode.CHANGE_ZONE,
    EventName.INFECTION: EventCode.INFECTION,
    EventName.RECOVERY: EventCode.RECOVERY,
}

EVENT_CODE_TO_NAME = {
    code: name for name, code in EVENT_NAME_TO_CODE.items()
}


def event_code_from_name(event_name):
    """Maps a human-readable event name to its compact 1-char BLE event code."""
    return EVENT_NAME_TO_CODE.get(event_name, EventCode.SAMPLE)


def event_name_from_code(event_code):
    """Maps a compact 1-char BLE event code back to its event name."""
    return EVENT_CODE_TO_NAME.get(event_code, EventName.SAMPLE)


def build_telemetry_entry(
    timestamp_s,
    robot_id,
    event_name,
    zone,
    sir_state,
    agent_type,
    vaccinated,
    contact_id=NO_CONTACT_ID,
):
    """Constructs a standardized `TelemetryEntry` dataclass."""
    return TelemetryEntry(
        time_stamp=timestamp_s,
        robot_id=robot_id,
        event=event_name,
        zone=zone,
        sir_state=sir_state,
        contact_id=contact_id,
        agent_type=agent_type,
        vaccinated=vaccinated,
    )
