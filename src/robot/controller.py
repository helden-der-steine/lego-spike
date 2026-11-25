"""
LEGO SPIKE Prime Robot Controller (Pybricks Edition).

Orchestrates connectionless BLE standby/telemetry, zone navigation,
and the SIR epidemic state machine on the hub.
"""

import gc
import json

from pybricks.hubs import PrimeHub
from pybricks.parameters import Color
from pybricks.tools import StopWatch, wait

from robot.hardware import (
    BEEP_EVENT_DURATION_MS,
    BEEP_INFECTION_FREQ_HZ,
    BEEP_RECOVERY_FREQ_HZ,
    BEEP_START_DURATION_MS,
    BEEP_START_FREQ_HZ,
    BEEP_STOP_DURATION_MS,
    BEEP_STOP_FREQ_HZ,
    detect_zone,
    get_hub_name,
    init_color_sensor,
    init_distance_sensor,
    init_drive_base,
    read_distance_mm,
    show_state,
)
from robot.navigation import ZoneNavigator
from robot.sir_simulation import SIRSimulation
from shared.enums import ControlCommand, EventName
from shared.models import NO_CONTACT_ID
from shared.protocol import (
    CMD_START_STR,
    CMD_STOP_STR,
    CONTROL_CHANNEL,
    ROBOT_CHANNELS,
    STANDBY_TAG,
    build_telemetry_entry,
    event_code_from_name,
)
from shared.sim_config import (
    ENABLE_MOVEMENT,
    LOG_DUMP_END_MARKER,
    LOG_DUMP_START_MARKER,
    LOG_INTERVAL_MS,
    NAV_CONFIG,
    config_from_hub_name,
    get_robot_stats,
)

LOOP_TICK_MS = NAV_CONFIG.loop_tick_ms
HUB_LOG_FILENAME = "log.json"
CSV_HEADER = "Time_Stamp,ID,Event,Zone,SIR_State,Contact_ID,Agent_Type,Vaccinated"

# Probe the hub's Bluetooth name first so we can bind its dedicated BLE channel
_probe_hub = PrimeHub(observe_channels=[CONTROL_CHANNEL] + list(ROBOT_CHANNELS))    # type: ignore[call-arg]
HUB_NAME = get_hub_name(_probe_hub)
ROBOT_ID, AGENT_TYPE, INITIAL_INFECTED = config_from_hub_name(HUB_NAME)
VACCINATED = get_robot_stats(ROBOT_ID).vaccinated_label
BROADCAST_CHANNEL = ROBOT_ID
del _probe_hub
gc.collect()

PEER_CHANNELS = [ch for ch in ROBOT_CHANNELS if ch != BROADCAST_CHANNEL]
OBSERVE_CHANNELS = [CONTROL_CHANNEL] + PEER_CHANNELS

# pybricks-stubs omits BLE kwargs and `PrimeHub.ble` even though hub firmware supports them
hub = PrimeHub(broadcast_channel=BROADCAST_CHANNEL, observe_channels=OBSERVE_CHANNELS)  # type: ignore[call-arg]
ble = hub.ble  # type: ignore[attr-defined]
stopwatch = StopWatch()
sim = SIRSimulation(initial_infected=INITIAL_INFECTED)
log_entries = []
seq_num = 0
_observe_error_logged = False

drive_base = init_drive_base()
color_sensor = init_color_sensor()
distance_sensor = init_distance_sensor()


def log_sample(event_name=EventName.SAMPLE, contact_id=NO_CONTACT_ID):
    """Records a telemetry row locally and broadcasts it on channel ROBOT_ID."""
    global seq_num
    elapsed_s = round(stopwatch.time() / 1000.0, 1)
    entry = build_telemetry_entry(
        timestamp_s=elapsed_s,
        robot_id=ROBOT_ID,
        event_name=event_name,
        zone=sim.current_zone,
        sir_state=sim.sir_state,
        agent_type=AGENT_TYPE,
        vaccinated=VACCINATED,
        contact_id=contact_id,
    )
    log_entries.append(entry)
    seq_num += 1

    print("{:.1f},{},{},{},{},{},{},{}".format(
        elapsed_s,
        ROBOT_ID,
        event_name,
        sim.current_zone,
        sim.sir_state,
        contact_id,
        AGENT_TYPE,
        VACCINATED,
    ))

    event_code = event_code_from_name(event_name)
    try:
        ble.broadcast((ROBOT_ID, elapsed_s, sim.sir_state, sim.current_zone, seq_num, event_code))
    except Exception:
        pass


def observe_peers(now_ms):
    """Reads peer BLE channels and updates/expires peer SIR state."""
    for ch in PEER_CHANNELS:
        try:
            obs = ble.observe(ch)
        except Exception:
            obs = None

        if isinstance(obs, tuple) and len(obs) >= 4 and not isinstance(obs[0], str):
            sim.observe_peer_packet(
                other_id=obs[0],
                other_state=obs[2],
                other_zone=obs[3],
                now_ms=now_ms,
            )
        else:
            sim.expire_stale_peer(ch, now_ms)


def _matches_command(obs, int_cmd, str_cmd):
    if obs == int_cmd or obs == str_cmd:
        return True
    if isinstance(obs, tuple) and len(obs) > 0:
        return obs[0] == int_cmd or obs[0] == str_cmd
    return False


def check_laptop_command():
    """Observes BLE Channel 0 for CMD_START or CMD_STOP from the central hub."""
    global _observe_error_logged
    try:
        obs = ble.observe(CONTROL_CHANNEL)
    except Exception as exc:
        if not _observe_error_logged:
            print(f"[ROBOT {ROBOT_ID}] BLE observe(Ch {CONTROL_CHANNEL}) error: {exc}")
            _observe_error_logged = True
        return None

    if obs is None:
        return None
    if _matches_command(obs, ControlCommand.START, CMD_START_STR):
        return ControlCommand.START
    if _matches_command(obs, ControlCommand.STOP, CMD_STOP_STR):
        return ControlCommand.STOP
    return None


def wait_for_start():
    """Sits in Standby mode until START arrives from the host on Channel 0."""
    show_state(hub, sim.sir_state)
    hub.light.on(Color.ORANGE)

    try:
        ble.broadcast((STANDBY_TAG, ROBOT_ID, sim.sir_state))
    except Exception:
        pass

    print(
        f"\n[ROBOT {ROBOT_ID}] Standby (listening on BLE Channel {CONTROL_CHANNEL}, broadcasting on Channel {BROADCAST_CHANNEL})..."
    )

    while True:
        if check_laptop_command() == ControlCommand.START:
            print(f"[ROBOT {ROBOT_ID}] START broadcast received on Channel {CONTROL_CHANNEL}! Starting...")
            break
        wait(LOOP_TICK_MS)

    stopwatch.reset()
    sim.reset_run()
    show_state(hub, sim.sir_state)
    hub.speaker.beep(frequency=BEEP_START_FREQ_HZ, duration=BEEP_START_DURATION_MS)


def _shutdown():
    """Stops motors, clears BLE broadcast, and persists/prints the run log."""
    if drive_base:
        drive_base.stop()
    try:
        ble.broadcast(None)
    except Exception:
        pass
    hub.display.off()
    hub.speaker.beep(frequency=BEEP_STOP_FREQ_HZ, duration=BEEP_STOP_DURATION_MS)

    serialized_logs = [entry.to_dict() for entry in log_entries]
    try:
        with open(HUB_LOG_FILENAME, "w") as f:
            json.dump(serialized_logs, f)
    except Exception:
        pass

    print(f"\n{LOG_DUMP_START_MARKER}")
    print(json.dumps(serialized_logs))
    print(LOG_DUMP_END_MARKER)


def main():
    """Runs the standby -> active simulation -> shutdown lifecycle."""
    wait_for_start()

    initial_zone = detect_zone(color_sensor)
    if initial_zone is not None:
        sim.current_zone = initial_zone

    print(CSV_HEADER)
    log_sample(EventName.START)

    navigator = ZoneNavigator(
        AGENT_TYPE,
        drive_base_obj=drive_base,
        has_color_sensor=(color_sensor is not None),
    )
    if ENABLE_MOVEMENT:
        navigator.start(now_ms=0)

    last_log_ms = 0

    while True:
        if check_laptop_command() == ControlCommand.STOP:
            print(f"[ROBOT {ROBOT_ID}] STOP broadcast received on Channel {CONTROL_CHANNEL}! Halting...")
            break

        now_ms = stopwatch.time()

        # 0. Zone detection, directional transitions, and obstacle/edge avoidance
        detected = detect_zone(color_sensor)
        distance_mm = read_distance_mm(distance_sensor)
        new_zone = navigator.step(
            now_ms,
            sim.current_zone,
            detected,
            movement_enabled=ENABLE_MOVEMENT,
            distance_mm=distance_mm,
        )
        if new_zone is not None:
            sim.current_zone = new_zone
            sim.clear_peer_contact()
            log_sample(EventName.CHANGE_ZONE)

        # 1. Peer observation and co-location infection check
        observe_peers(now_ms)
        contact_id = sim.check_zone_infection(now_ms)
        if contact_id is not None:
            show_state(hub, sim.sir_state)
            hub.speaker.beep(frequency=BEEP_INFECTION_FREQ_HZ, duration=BEEP_EVENT_DURATION_MS)
            log_sample(EventName.INFECTION, contact_id=contact_id)

        # 2. Recovery check
        if sim.check_recovery(now_ms):
            show_state(hub, sim.sir_state)
            hub.speaker.beep(frequency=BEEP_RECOVERY_FREQ_HZ, duration=BEEP_EVENT_DURATION_MS)
            log_sample(EventName.RECOVERY)

        # 3. Periodic telemetry snapshot
        if now_ms - last_log_ms >= LOG_INTERVAL_MS:
            log_sample(EventName.SAMPLE)
            last_log_ms = now_ms

        wait(LOOP_TICK_MS)

    _shutdown()


if __name__ == "__main__":
    main()
