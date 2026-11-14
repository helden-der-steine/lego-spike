from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor
from pybricks.parameters import Port, Button, Color, Direction
from pybricks.robotics import DriveBase
from pybricks.tools import wait, StopWatch
from pybricks.geometry import Matrix
import random
import json

# ==============================================================================
# 1. SETTINGS (Change these for each robot: ROBOT_ID = 1..10)
# ==============================================================================
ROBOT_ID = 1                # 1..10 (Robot broadcasts on Channel ROBOT_ID)
AGENT_TYPE = "A"            # "A" (turns right) or "B" (turns left)
INITIAL_INFECTED = False    # True = "I" (Red), False = "S" (Blue)
VACCINATED = "No"           # "Yes" or "No"

# Default motor ports
LEFT_MOTOR_PORT = Port.C
RIGHT_MOTOR_PORT = Port.D

# DriveBase wheel dimensions (Standard SPIKE Prime wheels: 56 mm, track: 112 mm)
WHEEL_DIAMETER = 56
AXLE_TRACK = 112

# ==============================================================================
# BLE Channels (100% Connectionless BLE Broadcast)
# - Laptop broadcasts commands on Channel 0 (robots listen ONLY to Channel 0)
# - Each robot broadcasts telemetry on its own channel: ROBOT_ID (1..10)
# ==============================================================================
CONTROL_CHANNEL = 0
BROADCAST_CHANNEL = ROBOT_ID

CMD_START = 1
CMD_STOP = 2

# ==============================================================================
# 2. 5x5 DISPLAY ICONS (Matrix pixel brightness 0 to 100)
# ==============================================================================
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

# ==============================================================================
# 3. INITIALIZATION
# ==============================================================================
# Broadcasts on channel ROBOT_ID (1..10) and observes ONLY channel 0 (laptop)
hub = PrimeHub(broadcast_channel=BROADCAST_CHANNEL, observe_channels=[CONTROL_CHANNEL])

sir_state = "I" if INITIAL_INFECTED else "S"
current_zone = "0"
log_entries = []
seq_num = 0
stopwatch = StopWatch()

# Setup Motors and DriveBase (graceful fallback if disconnected during bench testing)
drive_base = None
try:
    left_m = Motor(LEFT_MOTOR_PORT, Direction.COUNTERCLOCKWISE)
    right_m = Motor(RIGHT_MOTOR_PORT, Direction.CLOCKWISE)
    drive_base = DriveBase(left_m, right_m, WHEEL_DIAMETER, AXLE_TRACK)
except Exception:
    all_ports = [Port.A, Port.B, Port.C, Port.D, Port.E, Port.F]
    found_motors = []
    for p in all_ports:
        try:
            found_motors.append(Motor(p))
        except Exception:
            pass
    if len(found_motors) >= 2:
        drive_base = DriveBase(found_motors[0], found_motors[1], WHEEL_DIAMETER, AXLE_TRACK)
    else:
        print("No motors found! Running in simulation/logging only mode.")

def show_state(state):
    """Updates hub status light and 5x5 matrix icon."""
    if state == "I":
        hub.light.on(Color.RED)
        hub.display.icon(ICON_I)
    elif state == "R":
        hub.light.on(Color.GREEN)
        hub.display.icon(ICON_R)
    else:  # "S"
        hub.light.on(Color.BLUE)
        hub.display.icon(ICON_S)

def log_sample(event_name="Sample"):
    """
    Logs snapshot row and broadcasts it over BLE on channel ROBOT_ID (1..10).
    The laptop central hub picks up this broadcast packet in real-time.
    """
    global seq_num
    elapsed_s = round(stopwatch.time() / 1000.0, 1)
    entry = {
        "Time_Stamp": elapsed_s,
        "ID": ROBOT_ID,
        "Event": event_name,
        "Zone": current_zone,
        "SIR_State": sir_state,
        "Contact_ID": "—",
        "Agent_Type": AGENT_TYPE,
        "Vaccinated": VACCINATED
    }
    log_entries.append(entry)
    seq_num += 1

    # Print to console
    print("{:.1f},{},{},{},{},—,{},{}".format(
        elapsed_s, ROBOT_ID, event_name, current_zone, sir_state, AGENT_TYPE, VACCINATED
    ))

    # Broadcast over BLE on Channel ROBOT_ID: (ROBOT_ID, elapsed_s, sir_state, current_zone, seq_num)
    try:
        hub.ble.broadcast((ROBOT_ID, elapsed_s, sir_state, current_zone, seq_num))
    except Exception:
        pass

def check_laptop_command():
    """
    Observes BLE broadcast Channel 0 from the laptop:
    - CMD_START (1 or "START") -> Start experiment
    - CMD_STOP  (2 or "STOP")  -> Stop experiment
    """
    try:
        obs = hub.ble.observe(CONTROL_CHANNEL)
    except Exception:
        obs = None

    if obs is not None:
        if obs == CMD_START or obs == "START":
            return CMD_START
        if isinstance(obs, tuple) and len(obs) > 0 and (obs[0] == CMD_START or obs[0] == "START"):
            return CMD_START
        if obs == CMD_STOP or obs == "STOP":
            return CMD_STOP
        if isinstance(obs, tuple) and len(obs) > 0 and (obs[0] == CMD_STOP or obs[0] == "STOP"):
            return CMD_STOP

    return None

# ==============================================================================
# 4. STANDBY MODE (Waits for Laptop BLE Broadcast on Channel 0)
# ==============================================================================
def wait_for_start():
    """
    Robot sits stationary in standby and broadcasts its presence on Channel ROBOT_ID.
    Starts automatically when the laptop broadcasts START on Channel 0.
    """
    show_state(sir_state)
    hub.light.on(Color.ORANGE)  # Orange light indicates Standby

    # Broadcast STANDBY presence on Channel ROBOT_ID so laptop sees this robot is ready
    try:
        hub.ble.broadcast(("STANDBY", ROBOT_ID, sir_state))
    except Exception:
        pass

    print(f"\n[ROBOT {ROBOT_ID}] Standby (listening on BLE Channel 0, broadcasting on Channel {BROADCAST_CHANNEL})...")

    while True:
        cmd = check_laptop_command()
        if cmd == CMD_START or Button.RIGHT in hub.buttons.pressed():
            print(f"[ROBOT {ROBOT_ID}] START broadcast received on Channel 0! Starting...")
            break
        wait(20)

    # Synchronize t = 0.0s
    stopwatch.reset()
    show_state(sir_state)
    hub.speaker.beep(frequency=1000, duration=200)

# ==============================================================================
# 5. MAIN PROGRAM
# ==============================================================================
def main():
    wait_for_start()

    print("Time_Stamp,ID,Event,Zone,SIR_State,Contact_ID,Agent_Type,Vaccinated")
    log_sample("Start")

    if drive_base:
        drive_base.drive(speed=200, turn_rate=0)

    last_log_ms = 0
    step_start_ms = 0
    phase = 0  # 0 = straight, 1 = pause, 2 = turn, 3 = pause
    step_duration_ms = 2000

    # Run until STOP broadcast on Channel 0 (or LEFT button pressed on hub)
    while True:
        cmd = check_laptop_command()
        if cmd == CMD_STOP or Button.LEFT in hub.buttons.pressed():
            print(f"[ROBOT {ROBOT_ID}] STOP broadcast received on Channel 0! Halting...")
            break

        now_ms = stopwatch.time()

        # 1. Periodic snapshot log every 1000 ms (1.0 s)
        if now_ms - last_log_ms >= 1000:
            log_sample("Sample")
            last_log_ms = now_ms

        # 2. Movement state machine with stochastic timing
        if now_ms - step_start_ms >= step_duration_ms:
            phase = (phase + 1) % 4
            step_start_ms = now_ms

            if phase == 0:
                # Drive straight (random 1.5s - 2.5s)
                step_duration_ms = random.randint(1500, 2500)
                if drive_base:
                    drive_base.drive(speed=200, turn_rate=0)
            elif phase in (1, 3):
                # Short pause (0.8s)
                step_duration_ms = 800
                if drive_base:
                    drive_base.stop()
            elif phase == 2:
                # Turn (Type A turns right +60 deg/s, Type B turns left -60 deg/s)
                step_duration_ms = random.randint(800, 1300)
                turn_rate = 60 if AGENT_TYPE == "A" else -60
                if drive_base:
                    drive_base.drive(speed=0, turn_rate=turn_rate)

        wait(20)

    # Stop motors and stop BLE telemetry broadcasting
    if drive_base:
        drive_base.stop()
    try:
        hub.ble.broadcast(None)
    except Exception:
        pass
    hub.display.off()
    hub.speaker.beep(frequency=400, duration=300)

    # Save JSON log on hub flash and print dump to terminal
    try:
        with open("log.json", "w") as f:
            json.dump(log_entries, f)
    except Exception:
        pass

    print("\n=== JSON LOG DUMP START ===")
    print(json.dumps(log_entries))
    print("=== JSON LOG DUMP END ===")

if __name__ == "__main__":
    main()
