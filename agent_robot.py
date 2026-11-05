from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor
from pybricks.parameters import Port, Button, Color, Direction
from pybricks.robotics import DriveBase
from pybricks.tools import wait, StopWatch
from pybricks.geometry import Matrix
import random
import json

# ==============================================================================
# 1. SETTINGS (Change these for each robot)
# ==============================================================================
ROBOT_ID = 1                # Set to 1 for Robot 1, 2 for Robot 2, etc.
AGENT_TYPE = "A"            # "A" (turns right) or "B" (turns left)
INITIAL_INFECTED = False    # True = "I" (Red), False = "S" (Blue)
VACCINATED = "No"           # "Yes" or "No"

# Default motor ports
LEFT_MOTOR_PORT = Port.C
RIGHT_MOTOR_PORT = Port.D

# DriveBase wheel dimensions (Standard SPIKE Prime wheels: 56 mm, track: 112 mm)
WHEEL_DIAMETER = 56
AXLE_TRACK = 112

# BLE Broadcast & Observe channels (1-255)
# Robot 1 broadcasts on Channel 1; Robot 2 broadcasts on Channel 2, etc.
# Both observe Channel 1 for the start synchronization signal.
SYNC_CHANNEL = 1
BROADCAST_CHANNEL = ROBOT_ID

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
# Each robot broadcasts telemetry on its own channel (ROBOT_ID) and listens on Channel 1
hub = PrimeHub(broadcast_channel=BROADCAST_CHANNEL, observe_channels=[SYNC_CHANNEL])

sir_state = "I" if INITIAL_INFECTED else "S"
current_zone = "0"
log_entries = []
seq_num = 0
stopwatch = StopWatch()

# Setup Motors and DriveBase (graceful fallback if disconnected during testing)
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
    Logs snapshot row and broadcasts it over BLE.
    Laptop BLE listener picks up this broadcast packet in real-time.
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

    # Broadcast over BLE: compact tuple (ROBOT_ID, elapsed_s, sir_state, current_zone, seq_num)
    try:
        hub.ble.broadcast((ROBOT_ID, elapsed_s, sir_state, current_zone, seq_num))
    except Exception:
        pass

# ==============================================================================
# 4. START SYNCHRONIZATION OVER BLE
# ==============================================================================
def wait_for_start_sync():
    """
    Standby mode:
    Both robots start without moving.
    - Robot 1: Waits until you press the RIGHT (+) button, then broadcasts "START" via BLE.
    - Robot 2 (and others): Observes Channel 1 via BLE. When it hears "START", it starts on its own.
    Both robots reset their StopWatch to 0.0s simultaneously.
    """
    show_state(sir_state)
    hub.light.on(Color.ORANGE)  # Orange status light indicates Standby

    if ROBOT_ID == 1:
        print("\n[ROBOT 1 - MASTER] Ready in Standby. Press RIGHT (+) button to start all robots...")
        while Button.RIGHT not in hub.buttons.pressed():
            wait(20)

        # Debounce button
        while Button.RIGHT in hub.buttons.pressed():
            wait(10)

        # Broadcast start signal repeatedly over BLE for 300 ms so all hubs receive it
        print("Broadcasting START signal over BLE...")
        for _ in range(15):
            hub.ble.broadcast("START")
            wait(20)

    else:
        print(f"\n[ROBOT {ROBOT_ID} - LISTENER] Ready in Standby. Waiting for BLE START broadcast from Robot 1...")
        while True:
            # Check for broadcast from Robot 1 on Channel 1
            data = hub.ble.observe(SYNC_CHANNEL)
            if data == "START":
                print(f"BLE START signal received on Robot {ROBOT_ID}!")
                break
            wait(15)

    # Both robots synchronize t = 0.0s here
    stopwatch.reset()
    show_state(sir_state)
    hub.speaker.beep(frequency=1000, duration=200)

# ==============================================================================
# 5. MAIN PROGRAM
# ==============================================================================
def main():
    wait_for_start_sync()

    print("Time_Stamp,ID,Event,Zone,SIR_State,Contact_ID,Agent_Type,Vaccinated")
    log_sample("Start")

    if drive_base:
        drive_base.drive(speed=200, turn_rate=0)

    last_log_ms = 0
    step_start_ms = 0
    phase = 0  # 0 = straight, 1 = pause, 2 = turn, 3 = pause
    step_duration_ms = 2000

    # Run until the LEFT button is pressed (or stop via center button / Pybricks UI)
    while Button.LEFT not in hub.buttons.pressed():
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

    # Stop motors
    if drive_base:
        drive_base.stop()
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
