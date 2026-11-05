from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor
from pybricks.parameters import Port, Button, Color, Direction
from pybricks.robotics import DriveBase
from pybricks.tools import wait, StopWatch, read_input_byte
from pybricks.geometry import Matrix
import random
import json

# Fallback for older Pybricks versions without read_input_byte
try:
    read_input_byte
except NameError:
    from usys import stdin
    from uselect import poll
    _poll = poll()
    _poll.register(stdin)
    def read_input_byte(last=False, chr=False):
        if _poll.poll(0):
            b = stdin.buffer.read(1)
            if b:
                return chr(b[0]) if chr else b[0]
        return None

# ==============================================================================
# 1. SETTINGS (Change these for each robot)
# ==============================================================================
ROBOT_ID = 3                # 1 for Robot 1, 2 for Robot 2, etc.
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
# Laptop broadcasts commands on Channel 0 (e.g. 1 = START, 2 = STOP)
# Each robot broadcasts its telemetry on its own ROBOT_ID channel
CONTROL_CHANNEL = 0
BROADCAST_CHANNEL = ROBOT_ID
OBSERVE_CHANNELS = [0, 1, 2, 3]

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
# Each robot broadcasts telemetry on its own channel and listens on OBSERVE_CHANNELS
hub = PrimeHub(broadcast_channel=BROADCAST_CHANNEL, observe_channels=OBSERVE_CHANNELS)

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
    Logs snapshot row and broadcasts it over BLE.
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

    # Broadcast over BLE: compact tuple (ROBOT_ID, elapsed_s, sir_state, current_zone, seq_num)
    try:
        hub.ble.broadcast((ROBOT_ID, elapsed_s, sir_state, current_zone, seq_num))
    except Exception:
        pass

def check_laptop_command():
    """
    Checks for START / STOP commands from the laptop:
    1. Over BLE GATT connection / stdin: 'S' or '1' = Start, 'X' or '2' = Stop
    2. Over BLE broadcast channels (0, 1, 2): CMD_START (1) or CMD_STOP (2)
    3. Physical button fallback: RIGHT (+) button starts, LEFT (-) button stops
    """
    # Check stdin (direct BLE GATT / USB connection from laptop)
    while True:
        try:
            byte_in = read_input_byte(chr=True)
        except Exception:
            break
        if not byte_in:
            break
        if byte_in in ("S", "s", "1"):
            return CMD_START
        elif byte_in in ("X", "x", "2", "Q", "q"):
            return CMD_STOP

    # Check BLE broadcast on observed channels
    for ch in OBSERVE_CHANNELS:
        try:
            obs = hub.ble.observe(ch)
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
# 4. STANDBY MODE (Waits for Laptop Start Command)
# ==============================================================================
def wait_for_start():
    """
    Robot sits stationary in standby.
    Starts automatically when laptop sends START command (or user presses RIGHT button).
    """
    show_state(sir_state)
    hub.light.on(Color.ORANGE)  # Orange light indicates Standby

    # Broadcast STANDBY presence so the laptop sees this robot immediately without connecting
    try:
        hub.ble.broadcast(("STANDBY", ROBOT_ID, sir_state))
    except Exception:
        pass

    print(f"\n[ROBOT {ROBOT_ID}] Ready in Standby. Waiting for START command from laptop...")

    while True:
        cmd = check_laptop_command()
        if cmd == CMD_START or Button.RIGHT in hub.buttons.pressed():
            print(f"[ROBOT {ROBOT_ID}] START command received! Starting experiment...")
            # Relay start broadcast to any peer robots listening
            try:
                for _ in range(3):
                    hub.ble.broadcast((CMD_START, "START"))
                    wait(30)
            except Exception:
                pass
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

    # Run until STOP command from laptop OR LEFT button pressed on hub
    while True:
        cmd = check_laptop_command()
        if cmd == CMD_STOP or Button.LEFT in hub.buttons.pressed():
            print(f"[ROBOT {ROBOT_ID}] STOP command received! Halting...")
            try:
                for _ in range(3):
                    hub.ble.broadcast((CMD_STOP, "STOP"))
                    wait(30)
            except Exception:
                pass
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
