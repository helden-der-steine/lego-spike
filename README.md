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

## 3. Simultaneous Startup Workflow

1. Click **Play** on **Robot 1** and **Robot 2**:
   - Both robots initialize their motors and show their centered `"I"`, `"S"`, or `"R"` icon with an **Orange** status light.
   - **Neither robot moves.**
   - Robot 2 passively listens on BLE Channel 1 for the start signal.
2. Press the **`+` (Right button)** on **Robot 1**:
   - Robot 1 broadcasts `"START"` over BLE.
   - Robot 2 receives the `"START"` broadcast wirelessly through the air.
   - **Both robots simultaneously reset their timers ($t = 0.0\text{ s}$), play a start beep, and start moving at the exact same moment on their own.**
3. **Stop the Run**:
   - Press the **`-` (Left button)** or the **Center button** on either hub.
   - The robot halts and outputs the JSON log to the Pybricks terminal.

---

## 4. Automatic Live BLE Logging on your Laptop (`live_ble_receiver.py`)

You don't need to manually copy or download logs from each hub anymore! Your laptop can listen directly to the robots' BLE broadcasts during the experiment:

1. In your laptop terminal, run:
   ```bash
   ./.venv/bin/python3 live_ble_receiver.py
   ```
   *(or `source .venv/bin/activate && python3 live_ble_receiver.py`)*

2. It scans for broadcast packets emitted by the robots in real-time and logs each row:
   ```text
   ⚡ BLE START Broadcast detected on Channel 1!
   📡 Received Robot 1 | t= 1.0s | Zone 0 | State I
   📡 Received Robot 2 | t= 1.0s | Zone 0 | State S
   📡 Received Robot 1 | t= 2.0s | Zone 0 | State I
   ...
   ```

3. **Auto-save when run finishes**:
   When you stop the robots, the script detects **10 seconds of inactivity**, automatically closes the run, and saves the full consolidated dataset into:
   ```text
   logs/run_01_YYYYMMDD_HHMMSS.json
   ```
   It then resets and continues listening for the next experiment run automatically!
