# LEGO SPIKE Prime - Agentic Robot (Pybricks Edition)

This code uses **Pybricks firmware** to enable **true wireless Bluetooth Low Energy (BLE) broadcast synchronization** between multiple SPIKE Prime robots.

---

## 1. Quick Setup: Flash Pybricks (Takes 2 minutes)

1. Open Chrome or Edge and go to **[https://beta.pybricks.com/](https://beta.pybricks.com/)**.
2. Connect your SPIKE Prime Hub via USB-C cable.
3. Click the **gear icon (Settings)** $\to$ **"Install Pybricks firmware"** and follow the on-screen steps.
4. Do this for both **Robot 1** and **Robot 2**.
   *(Note: You can revert back to official LEGO firmware at any time with one click if needed).*

---

## 2. Configure & Run the Script (`agent_robot.py`)

Create a new file in the Pybricks web editor and paste [`agent_robot.py`](agent_robot.py):

### For Robot 1 (The Master / Initiator):
```python
ROBOT_ID = 1
AGENT_TYPE = "A"            # "A" (turns right) or "B" (turns left)
INITIAL_INFECTED = True     # True = "I" (Red), False = "S" (Blue)
VACCINATED = "No"
```

### For Robot 2 (The Receiver / Follower):
```python
ROBOT_ID = 2
AGENT_TYPE = "B"            # "A" (turns right) or "B" (turns left)
INITIAL_INFECTED = False    # True = "I" (Red), False = "S" (Blue)
VACCINATED = "No"
```

---

## 3. Laptop Central Hub Workflow (`live_ble_receiver.py`)

Your laptop is now the **command center**: it starts and stops all robots wirelessly and automatically compiles each run into a clean JSON dataset.

### Step 1: Put Robots in Standby
1. Start [`agent_robot.py`](agent_robot.py) on **Robot 1** and **Robot 2** (via Pybricks web IDE or on boot):
   - Both robots initialize their motors and display their centered `"I"`, `"S"`, or `"R"` icon with an **Orange** status light.
   - **Neither robot moves.** They wait in standby for the wireless START trigger.

### Step 2: Launch the Central Hub on your Laptop
In your terminal, run:
```bash
./.venv/bin/python3 live_ble_receiver.py
```
*(or `source .venv/bin/activate && python3 live_ble_receiver.py`)*

The Central Hub automatically discovers nearby SPIKE Prime robots and connects to them:
```text
================================================================
  KIT SYDSEN - LEGO SPIKE Digital Twin Central Hub
================================================================
  [s] or ENTER : START ALL ROBOTS (Synchronized wireless trigger)
  [x] or [q]   : STOP ALL ROBOTS (Halts motors & logs)
  [c] or scan  : SCAN & CONNECT to active Pybricks Hubs
  [status]     : Show connected robots & run statistics
  [save]       : Force save current run immediately
  Auto-Save    : Runs automatically save 10s after last log
================================================================
🔍 Scanning for Pybricks Hubs...
✨ Discovered 2 Pybricks Hub(s). Establishing links...
🟢 Successfully connected to Robot 1!
🟢 Successfully connected to Robot 2!
```

---

## 4. Running Experiments

### Start All Robots:
Press **`s`** (or press **`ENTER`**) in the terminal:
- The laptop transmits the start signal to all connected robots simultaneously.
- All robots synchronize their timers to $t = 0.0\text{ s}$, play a beep, turn on their state lights, and begin moving at the exact same instant!
- Real-time telemetry is streamed live to your laptop console:
  ```text
  [16:45:01] 📡 Robot 1 | t= 1.0s | State: I | Zone: 0 | Type: A
  [16:45:01] 📡 Robot 2 | t= 1.0s | State: S | Zone: 0 | Type: B
  [16:45:02] 📡 Robot 1 | t= 2.0s | State: I | Zone: 0 | Type: A
  [16:45:02] 📡 Robot 2 | t= 2.0s | State: S | Zone: 0 | Type: B
  ```

### Stop All Robots:
Press **`x`** (or **`q`**) in the terminal:
- The laptop sends the stop signal to all robots.
- The robots immediately stop their motors and finalize their logs.
- The run is automatically compiled and saved to:
  ```text
  logs/run_01_YYYYMMDD_HHMMSS.json
  ```
- The Central Hub immediately readies itself for Run 2! (Press `s` whenever you are ready for the next test).

*(Physical fallback: Pressing the `+` Right button on Robot 1 will also start the experiment, and `-` Left button will stop).*
