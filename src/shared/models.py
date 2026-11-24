"""
Shared dataclass models for configuration, telemetry, and peer state.

On CPython (host PC), uses stdlib `dataclasses.dataclass`.
On Pybricks MicroPython (which omits `dataclasses`), uses a lightweight
fallback decorator supporting keyword initialization, equality, and repr.
"""

from shared.enums import AgentType, EventName, SIRState, VaccinatedStatus, Zone

NO_CONTACT_ID = "—"

try:
    from dataclasses import dataclass
except ImportError:
    def dataclass(cls=None, **_kwargs):
        def wrap(c):
            defaults = {}
            for k, v in c.__dict__.items():
                if (
                    not k.startswith("__")
                    and not callable(v)
                    and not isinstance(v, (staticmethod, classmethod, property))
                ):
                    defaults[k] = v

            def __init__(self, **kwargs):
                for k, default in defaults.items():
                    setattr(self, k, kwargs[k] if k in kwargs else default)

            def __repr__(self):
                fields = ", ".join(f"{k}={repr(getattr(self, k))}" for k in defaults)
                return f"{c.__name__}({fields})"

            def __eq__(self, other):
                if not isinstance(other, c):
                    return False
                return all(getattr(self, k) == getattr(other, k) for k in defaults)

            c.__init__ = __init__
            c.__repr__ = __repr__
            c.__eq__ = __eq__
            return c

        return wrap if cls is None else wrap(cls)


@dataclass(frozen=True)
class SimulationConfig:
    enable_movement: bool = True
    max_robots: int = 10
    zone_order_cw: tuple = (Zone.YELLOW, Zone.BLUE, Zone.GREEN, Zone.RED)
    infection_contact_ms: int = 30000
    infection_check_interval_ms: int = 1000
    infection_prob_per_sec: float = 0.05
    recovery_duration_ms: int = 120000
    log_interval_ms: int = 5000
    peer_contact_timeout_ms: int = 2500
    peer_state_timeout_ms: int = 15000
    no_infected_end_ms: int = 3000


@dataclass(frozen=True)
class NavigationConfig:
    drive_speed_mm_s: int = 35
    drive_accel_mm_s2: int = 100
    turn_speed_deg_s: int = 45
    turn_accel_deg_s2: int = 120
    edge_confirm_ms: int = 400
    backup_duration_ms: int = 1000
    edge_turn_min_deg: int = 45
    edge_turn_max_deg: int = 110
    zone_debounce_samples: int = 3
    disallowed_confirm_ms: int = 350
    obstacle_stop_mm: int = 80
    obstacle_resume_mm: int = 100
    obstacle_clear_samples: int = 3
    loop_tick_ms: int = 20


@dataclass(frozen=True)
class SpeakerConfig:
    start_freq_hz: int = 1000
    start_duration_ms: int = 200
    infection_freq_hz: int = 600
    recovery_freq_hz: int = 800
    event_duration_ms: int = 150
    stop_freq_hz: int = 400
    stop_duration_ms: int = 300


@dataclass(frozen=True)
class RedHSVConfig:
    hue_low_max: int = 15
    hue_high_min: int = 330
    min_saturation: int = 65


@dataclass(frozen=True)
class YellowHSVConfig:
    hue_min: int = 20
    hue_max: int = 55
    min_saturation: int = 55
    min_value: int = 35


@dataclass(frozen=True)
class GreenHSVConfig:
    hue_min: int = 95
    hue_max: int = 165
    min_saturation: int = 35


@dataclass(frozen=True)
class BlueHSVConfig:
    hue_min: int = 175
    hue_max: int = 235
    min_saturation: int = 60


@dataclass(frozen=True)
class ColorHSVConfig:
    min_zone_value: int = 22
    red: RedHSVConfig = None
    yellow: YellowHSVConfig = None
    green: GreenHSVConfig = None
    blue: BlueHSVConfig = None


@dataclass(frozen=True)
class HardwareConfig:
    left_motor_port: str = "C"
    right_motor_port: str = "D"
    color_sensor_port: str = "B"
    distance_sensor_port: str = "A"
    wheel_diameter_mm: int = 56
    axle_track_mm: int = 112
    color_logger_sample_interval_ms: int = 500
    speaker: SpeakerConfig = None
    color_hsv: ColorHSVConfig = None


@dataclass(frozen=True)
class HostConfig:
    inactivity_timeout_ms: int = 15000
    no_infected_end_ms: int = 5000
    broadcast_duration_ms: int = 1800
    poll_interval_ms: int = 500
    post_stop_flush_ms: int = 500
    logs_dir: str = "logs"


@dataclass(frozen=True)
class RobotConfig:
    agent_type: str = AgentType.CLOCKWISE
    initial_infected: bool = False
    vaccinated: bool = False

    @property
    def vaccinated_label(self):
        """Human-readable vaccination label emitted in telemetry logs."""
        return VaccinatedStatus.YES if self.vaccinated else VaccinatedStatus.NO


@dataclass(frozen=True)
class AppConfig:
    simulation: SimulationConfig = None
    navigation: NavigationConfig = None
    hardware: HardwareConfig = None
    host: HostConfig = None
    default_robot: RobotConfig = None
    robots: dict = None

    def robot_for(self, robot_id):
        """Returns the RobotConfig for `robot_id`, falling back to `default_robot`."""
        if self.robots and robot_id in self.robots:
            return self.robots[robot_id]
        return self.default_robot


@dataclass(frozen=True)
class TelemetryEntry:
    """Standardized telemetry snapshot or event emitted by a robot."""

    time_stamp: float = 0.0
    robot_id: int = 1
    event: str = EventName.SAMPLE
    zone: str = Zone.UNKNOWN
    sir_state: str = SIRState.SUSCEPTIBLE
    contact_id: object = NO_CONTACT_ID
    agent_type: str = AgentType.CLOCKWISE
    vaccinated: str = VaccinatedStatus.NO

    def to_dict(self):
        """Serializes to the JSON telemetry log schema."""
        return {
            "Time_Stamp": self.time_stamp,
            "ID": self.robot_id,
            "Event": self.event,
            "Zone": self.zone,
            "SIR_State": self.sir_state,
            "Contact_ID": self.contact_id,
            "Agent_Type": self.agent_type,
            "Vaccinated": self.vaccinated,
        }


@dataclass
class PeerStatus:
    """Tracks the latest observed state, zone, and co-location timers of a peer robot."""

    state: str = SIRState.SUSCEPTIBLE
    zone: str = Zone.UNKNOWN
    last_seen_ms: int = 0
    contact_start_ms: int = None
    last_roll_ms: int = None
