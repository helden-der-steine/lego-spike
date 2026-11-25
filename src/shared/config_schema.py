"""
Schema validation and normalization for `config.toml` into `AppConfig` dataclasses.

Validates types, allowed values, and ranges on the host PC so invalid settings
fail fast before running experiments or deploying to SPIKE Prime hubs.
"""

from shared.enums import AgentType, PortLetter, Zone
from shared.models import (
    AppConfig,
    BlueHSVConfig,
    ColorHSVConfig,
    GreenHSVConfig,
    HardwareConfig,
    HostConfig,
    NavigationConfig,
    RedHSVConfig,
    RobotConfig,
    SimulationConfig,
    SpeakerConfig,
    YellowHSVConfig,
)

REQUIRED_SECTIONS = ("simulation", "navigation", "hardware", "host", "robots")


def _require_section(parent, key, path):
    val = parent.get(key)
    if not isinstance(val, dict):
        raise ValueError(f"Missing or invalid config table [{path}]")
    return val


def _require_bool(section, key, path):
    val = section.get(key)
    if not isinstance(val, bool):
        raise ValueError(f"Config '{path}.{key}' must be a boolean, got {repr(val)}")
    return val


def _require_int(section, key, path, min_val=None, max_val=None):
    val = section.get(key)
    if isinstance(val, bool) or not isinstance(val, int):
        raise ValueError(f"Config '{path}.{key}' must be an integer, got {repr(val)}")
    if min_val is not None and val < min_val:
        raise ValueError(f"Config '{path}.{key}' must be >= {min_val}, got {val}")
    if max_val is not None and val > max_val:
        raise ValueError(f"Config '{path}.{key}' must be <= {max_val}, got {val}")
    return val


def _require_float(section, key, path, min_val=None, max_val=None):
    val = section.get(key)
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValueError(f"Config '{path}.{key}' must be a number, got {repr(val)}")
    fval = float(val)
    if min_val is not None and fval < min_val:
        raise ValueError(f"Config '{path}.{key}' must be >= {min_val}, got {val}")
    if max_val is not None and fval > max_val:
        raise ValueError(f"Config '{path}.{key}' must be <= {max_val}, got {val}")
    return fval


def _require_str(section, key, path):
    val = section.get(key)
    if not isinstance(val, str) or not val:
        raise ValueError(f"Config '{path}.{key}' must be a non-empty string, got {repr(val)}")
    return val


def _require_enum(section, key, path, enum_cls):
    val = _require_str(section, key, path)
    if val not in enum_cls:
        allowed = tuple(str(member) for member in enum_cls)
        raise ValueError(f"Config '{path}.{key}' must be one of {allowed}, got {repr(val)}")
    return enum_cls(val)


def _validate_robot_entry(entry, path):
    return RobotConfig(
        agent_type=_require_enum(entry, "agent_type", path, AgentType),
        initial_infected=_require_bool(entry, "initial_infected", path),
        vaccinated=_require_bool(entry, "vaccinated", path),
    )


def _validate_simulation(raw_sim):
    valid_zones = {z for z in Zone if z != Zone.UNKNOWN}
    zone_order = raw_sim.get("zone_order_cw")
    if not isinstance(zone_order, list) or len(zone_order) != len(valid_zones) or set(zone_order) != valid_zones:
        raise ValueError(
            f"Config 'simulation.zone_order_cw' must be a permutation of {sorted(str(z) for z in valid_zones)}"
        )

    return SimulationConfig(
        enable_movement=_require_bool(raw_sim, "enable_movement", "simulation"),
        max_robots=_require_int(raw_sim, "max_robots", "simulation", min_val=1, max_val=20),
        zone_order_cw=tuple(Zone(z) for z in zone_order),
        infection_contact_ms=_require_int(raw_sim, "infection_contact_ms", "simulation", min_val=0),
        infection_check_interval_ms=_require_int(
            raw_sim, "infection_check_interval_ms", "simulation", min_val=1
        ),
        infection_prob_per_sec=_require_float(
            raw_sim, "infection_prob_per_sec", "simulation", min_val=0.0, max_val=1.0
        ),
        recovery_duration_ms=_require_int(raw_sim, "recovery_duration_ms", "simulation", min_val=1),
        log_interval_ms=_require_int(raw_sim, "log_interval_ms", "simulation", min_val=1),
        peer_contact_timeout_ms=_require_int(raw_sim, "peer_contact_timeout_ms", "simulation", min_val=1),
        peer_state_timeout_ms=_require_int(raw_sim, "peer_state_timeout_ms", "simulation", min_val=1),
    )


def _validate_navigation(raw_nav):
    min_deg = _require_int(raw_nav, "edge_turn_min_deg", "navigation", min_val=1, max_val=360)
    max_deg = _require_int(raw_nav, "edge_turn_max_deg", "navigation", min_val=min_deg, max_val=360)
    stop_mm = _require_int(raw_nav, "obstacle_stop_mm", "navigation", min_val=0)
    resume_mm = _require_int(raw_nav, "obstacle_resume_mm", "navigation", min_val=stop_mm)

    return NavigationConfig(
        drive_speed_mm_s=_require_int(raw_nav, "drive_speed_mm_s", "navigation", min_val=1),
        drive_accel_mm_s2=_require_int(raw_nav, "drive_accel_mm_s2", "navigation", min_val=1),
        turn_speed_deg_s=_require_int(raw_nav, "turn_speed_deg_s", "navigation", min_val=1),
        turn_accel_deg_s2=_require_int(raw_nav, "turn_accel_deg_s2", "navigation", min_val=1),
        edge_confirm_ms=_require_int(raw_nav, "edge_confirm_ms", "navigation", min_val=0),
        backup_duration_ms=_require_int(raw_nav, "backup_duration_ms", "navigation", min_val=1),
        edge_turn_min_deg=min_deg,
        edge_turn_max_deg=max_deg,
        zone_debounce_samples=_require_int(raw_nav, "zone_debounce_samples", "navigation", min_val=1),
        disallowed_confirm_ms=_require_int(raw_nav, "disallowed_confirm_ms", "navigation", min_val=0),
        obstacle_stop_mm=stop_mm,
        obstacle_resume_mm=resume_mm,
        obstacle_clear_samples=_require_int(raw_nav, "obstacle_clear_samples", "navigation", min_val=1),
        loop_tick_ms=_require_int(raw_nav, "loop_tick_ms", "navigation", min_val=1),
    )


def _validate_hardware(raw_hw):
    raw_speaker = _require_section(raw_hw, "speaker", "hardware.speaker")
    raw_hsv = _require_section(raw_hw, "color_hsv", "hardware.color_hsv")

    red = _require_section(raw_hsv, "Red", "hardware.color_hsv.Red")
    yellow = _require_section(raw_hsv, "Yellow", "hardware.color_hsv.Yellow")
    green = _require_section(raw_hsv, "Green", "hardware.color_hsv.Green")
    blue = _require_section(raw_hsv, "Blue", "hardware.color_hsv.Blue")

    speaker = SpeakerConfig(
        start_freq_hz=_require_int(raw_speaker, "start_freq_hz", "hardware.speaker", min_val=20),
        start_duration_ms=_require_int(raw_speaker, "start_duration_ms", "hardware.speaker", min_val=1),
        infection_freq_hz=_require_int(raw_speaker, "infection_freq_hz", "hardware.speaker", min_val=20),
        recovery_freq_hz=_require_int(raw_speaker, "recovery_freq_hz", "hardware.speaker", min_val=20),
        event_duration_ms=_require_int(raw_speaker, "event_duration_ms", "hardware.speaker", min_val=1),
        stop_freq_hz=_require_int(raw_speaker, "stop_freq_hz", "hardware.speaker", min_val=20),
        stop_duration_ms=_require_int(raw_speaker, "stop_duration_ms", "hardware.speaker", min_val=1),
    )

    color_hsv = ColorHSVConfig(
        min_zone_value=_require_int(raw_hsv, "min_zone_value", "hardware.color_hsv", min_val=0, max_val=100),
        red=RedHSVConfig(
            hue_low_max=_require_int(red, "hue_low_max", "hardware.color_hsv.Red", 0, 360),
            hue_high_min=_require_int(red, "hue_high_min", "hardware.color_hsv.Red", 0, 360),
            min_saturation=_require_int(red, "min_saturation", "hardware.color_hsv.Red", 0, 100),
        ),
        yellow=YellowHSVConfig(
            hue_min=_require_int(yellow, "hue_min", "hardware.color_hsv.Yellow", 0, 360),
            hue_max=_require_int(yellow, "hue_max", "hardware.color_hsv.Yellow", 0, 360),
            min_saturation=_require_int(yellow, "min_saturation", "hardware.color_hsv.Yellow", 0, 100),
            min_value=_require_int(yellow, "min_value", "hardware.color_hsv.Yellow", 0, 100),
        ),
        green=GreenHSVConfig(
            hue_min=_require_int(green, "hue_min", "hardware.color_hsv.Green", 0, 360),
            hue_max=_require_int(green, "hue_max", "hardware.color_hsv.Green", 0, 360),
            min_saturation=_require_int(green, "min_saturation", "hardware.color_hsv.Green", 0, 100),
        ),
        blue=BlueHSVConfig(
            hue_min=_require_int(blue, "hue_min", "hardware.color_hsv.Blue", 0, 360),
            hue_max=_require_int(blue, "hue_max", "hardware.color_hsv.Blue", 0, 360),
            min_saturation=_require_int(blue, "min_saturation", "hardware.color_hsv.Blue", 0, 100),
        ),
    )

    return HardwareConfig(
        left_motor_port=_require_enum(raw_hw, "left_motor_port", "hardware", PortLetter),
        right_motor_port=_require_enum(raw_hw, "right_motor_port", "hardware", PortLetter),
        color_sensor_port=_require_enum(raw_hw, "color_sensor_port", "hardware", PortLetter),
        distance_sensor_port=_require_enum(raw_hw, "distance_sensor_port", "hardware", PortLetter),
        wheel_diameter_mm=_require_int(raw_hw, "wheel_diameter_mm", "hardware", min_val=1),
        axle_track_mm=_require_int(raw_hw, "axle_track_mm", "hardware", min_val=1),
        color_logger_sample_interval_ms=_require_int(
            raw_hw, "color_logger_sample_interval_ms", "hardware", min_val=1
        ),
        speaker=speaker,
        color_hsv=color_hsv,
    )


def _validate_host(raw_host):
    return HostConfig(
        inactivity_timeout_ms=_require_int(raw_host, "inactivity_timeout_ms", "host", min_val=1),
        no_infected_end_ms=_require_int(raw_host, "no_infected_end_ms", "host", min_val=0),
        broadcast_duration_ms=_require_int(raw_host, "broadcast_duration_ms", "host", min_val=1),
        poll_interval_ms=_require_int(raw_host, "poll_interval_ms", "host", min_val=1),
        post_stop_flush_ms=_require_int(raw_host, "post_stop_flush_ms", "host", min_val=0),
        logs_dir=_require_str(raw_host, "logs_dir", "host"),
    )


def _validate_robots(raw_robots, max_robots):
    default_entry = _validate_robot_entry(
        _require_section(raw_robots, "default", "robots.default"), "robots.default"
    )
    robots = {}
    for key, val in raw_robots.items():
        if key == "default":
            continue
        if not key.isdigit() or not (1 <= int(key) <= max_robots):
            raise ValueError(
                f"Invalid robot table '[robots.{key}]'; expected 'default' or '1'..'{max_robots}'"
            )
        if not isinstance(val, dict):
            raise ValueError(f"Config '[robots.{key}]' must be a table")
        robots[int(key)] = _validate_robot_entry(val, f"robots.{key}")
    return default_entry, robots


def validate_and_normalize(raw) -> AppConfig:
    """Validates raw parsed TOML config and returns an `AppConfig` dataclass."""
    if not isinstance(raw, dict):
        raise ValueError("Top-level config must be a TOML table")
    for sec in REQUIRED_SECTIONS:
        _require_section(raw, sec, sec)

    sim = _validate_simulation(raw["simulation"])
    default_robot, robots = _validate_robots(raw["robots"], sim.max_robots)
    return AppConfig(
        simulation=sim,
        navigation=_validate_navigation(raw["navigation"]),
        hardware=_validate_hardware(raw["hardware"]),
        host=_validate_host(raw["host"]),
        default_robot=default_robot,
        robots=robots,
    )
