"""
Shared simulation configuration and robot roster definitions.

On the host PC (CPython 3.12+), loads and validates `config.toml` live into `AppConfig`.
On the LEGO SPIKE Prime hub (MicroPython, no `tomllib`), imports the pre-synced
`shared.generated_config` module generated at deploy time.
"""

try:
    from pathlib import Path as _Path
    import tomllib as _tomllib
    from shared.config_schema import validate_and_normalize as _validate_and_normalize

    _PROJECT_ROOT = _Path(__file__).resolve().parents[2]
    _CONFIG_PATH = _PROJECT_ROOT / "config.toml"
    with _CONFIG_PATH.open("rb") as _cfg_file:
        CONFIG = _validate_and_normalize(_tomllib.load(_cfg_file))
except ImportError as exc:
    print(f"[INFO] Live config.toml import unavailable ({exc}); using pre-synced shared.generated_config.")
    from shared.generated_config import CONFIG

SIM_CONFIG = CONFIG.simulation
NAV_CONFIG = CONFIG.navigation
HW_CONFIG = CONFIG.hardware
HOST_CONFIG = CONFIG.host

ENABLE_MOVEMENT = SIM_CONFIG.enable_movement
MAX_ROBOTS = SIM_CONFIG.max_robots
DEFAULT_ROBOT_STATS = CONFIG.default_robot
ROBOT_STATS = [None] + [CONFIG.robot_for(rid) for rid in range(1, MAX_ROBOTS + 1)]
ZONE_ORDER_CW = SIM_CONFIG.zone_order_cw

# SIR simulation timing & probability parameters
INFECTION_CONTACT_MS = SIM_CONFIG.infection_contact_ms
INFECTION_CHECK_INTERVAL_MS = SIM_CONFIG.infection_check_interval_ms
INFECTION_PROB_PER_SEC = SIM_CONFIG.infection_prob_per_sec
RECOVERY_DURATION_MS = SIM_CONFIG.recovery_duration_ms

# Telemetry & peer-tracking timeouts
LOG_INTERVAL_MS = SIM_CONFIG.log_interval_ms
PEER_CONTACT_TIMEOUT_MS = SIM_CONFIG.peer_contact_timeout_ms
PEER_STATE_TIMEOUT_MS = SIM_CONFIG.peer_state_timeout_ms

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
    """Returns the RobotConfig dataclass for `robot_id` (1..MAX_ROBOTS), or default."""
    return CONFIG.robot_for(robot_id)


def config_from_hub_name(hub_name, default_id=1):
    """Returns (robot_id, agent_type, initial_infected) looked up from `hub_name`."""
    robot_id = parse_robot_id(hub_name, default=default_id)
    stats = get_robot_stats(robot_id)
    return robot_id, stats.agent_type, stats.initial_infected
