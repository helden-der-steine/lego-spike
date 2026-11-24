"""
Shared simulation configuration and robot roster definitions.

This module is pure Python (no Pybricks or host-only imports) so it can run
on both the LEGO SPIKE Prime hub (MicroPython) and the host PC.
"""

ENABLE_MOVEMENT = True
MAX_ROBOTS = 10

# Agent movement directions around the 4-zone ring
AGENT_TYPE_CW = "A"   # Clockwise: Yellow -> Blue -> Green -> Red
AGENT_TYPE_CCW = "B"  # Counter-clockwise: Yellow -> Red -> Green -> Blue

VACCINATED_YES = "Yes"
VACCINATED_NO = "No"

DEFAULT_ROBOT_STATS = {
    "agent_type": AGENT_TYPE_CW,
    "initial_infected": False,
    "vaccinated": VACCINATED_NO,
}

# Stats for Robots 1..10 (index 0 is unused so ROBOT_STATS[robot_id] maps 1-to-1)
ROBOT_STATS = [
    None,
    {"agent_type": AGENT_TYPE_CW,  "initial_infected": False, "vaccinated": VACCINATED_NO},  # Robot 1
    {"agent_type": AGENT_TYPE_CW,  "initial_infected": True,  "vaccinated": VACCINATED_NO},  # Robot 2
    {"agent_type": AGENT_TYPE_CW,  "initial_infected": False, "vaccinated": VACCINATED_NO},  # Robot 3
    {"agent_type": AGENT_TYPE_CW,  "initial_infected": False, "vaccinated": VACCINATED_NO},  # Robot 4
    {"agent_type": AGENT_TYPE_CCW, "initial_infected": False, "vaccinated": VACCINATED_NO},  # Robot 5
    {"agent_type": AGENT_TYPE_CCW, "initial_infected": False, "vaccinated": VACCINATED_NO},  # Robot 6
    {"agent_type": AGENT_TYPE_CCW, "initial_infected": False, "vaccinated": VACCINATED_NO},  # Robot 7
    {"agent_type": AGENT_TYPE_CCW, "initial_infected": False, "vaccinated": VACCINATED_NO},  # Robot 8
    {"agent_type": AGENT_TYPE_CCW, "initial_infected": False, "vaccinated": VACCINATED_NO},  # Robot 9
    {"agent_type": AGENT_TYPE_CCW, "initial_infected": False, "vaccinated": VACCINATED_NO},  # Robot 10
]

# Color zone identifiers
ZONE_RED = "Red"
ZONE_GREEN = "Green"
ZONE_BLUE = "Blue"
ZONE_YELLOW = "Yellow"
ZONE_UNKNOWN = "0"

ZONE_NAMES = {
    ZONE_RED: ZONE_RED,
    ZONE_GREEN: ZONE_GREEN,
    ZONE_BLUE: ZONE_BLUE,
    ZONE_YELLOW: ZONE_YELLOW,
}

# Clockwise zone sequence: Yellow -> Blue -> Green -> Red -> Yellow
ZONE_ORDER_CW = (ZONE_YELLOW, ZONE_BLUE, ZONE_GREEN, ZONE_RED)

# SIR epidemiological states
STATE_SUSCEPTIBLE = "S"
STATE_INFECTED = "I"
STATE_RECOVERED = "R"
STATE_VACCINATED = "V"  # Defined for state support; no vaccination behavior yet
STATE_UNKNOWN = "?"

# SIR simulation timing & probability parameters
INFECTION_CONTACT_MS = 30000        # Co-location duration (30 s) before infection rolls begin
INFECTION_CHECK_INTERVAL_MS = 1000  # Roll for infection once every 1 s after threshold
INFECTION_PROB_PER_SEC = 0.05       # Infection probability per second after 30 s contact
RECOVERY_DURATION_MS = 120000       # Duration (120 s) before 'I' -> 'R'

# Telemetry & peer-tracking timeouts
LOG_INTERVAL_MS = 5000              # Periodic snapshot log interval (5.0 s)
PEER_CONTACT_TIMEOUT_MS = 2500      # Drop zone-contact timer if peer silent > 2.5 s
PEER_STATE_TIMEOUT_MS = 15000       # Expire peer SIR state if silent > 15 s (3x log interval)
NO_INFECTED_END_MS = 3000           # Confirm 0 infected robots for 3 s before ending run

NO_CONTACT_ID = "—"

# Console log dump delimiters (used by robot/controller.py and host/log_saver.py)
LOG_DUMP_START_MARKER = "=== JSON LOG DUMP START ==="
LOG_DUMP_END_MARKER = "=== JSON LOG DUMP END ==="


def parse_robot_id(hub_name, default=1):
    """Extracts the first contiguous integer from a hub name like 'Held 1' or 'Held-10'."""
    if not isinstance(hub_name, str):
        return default
    digits = ""
    for ch in hub_name:
        if "0" <= ch <= "9":
            digits += ch
        elif digits:
            break
    return int(digits) if digits else default


def get_robot_stats(robot_id):
    """Returns the stats dict for `robot_id` (1..MAX_ROBOTS), or DEFAULT_ROBOT_STATS."""
    if 1 <= robot_id < len(ROBOT_STATS) and ROBOT_STATS[robot_id] is not None:
        return ROBOT_STATS[robot_id]
    return DEFAULT_ROBOT_STATS


def config_from_hub_name(hub_name, default_id=1):
    """Returns (robot_id, agent_type, initial_infected) looked up from `hub_name`."""
    robot_id = parse_robot_id(hub_name, default=default_id)
    stats = get_robot_stats(robot_id)
    return robot_id, stats["agent_type"], stats["initial_infected"]
