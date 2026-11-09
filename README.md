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

## 3. 100% Connectionless BLE Broadcast Workflow (`live_ble_receiver.py`)

No BLE GATT connections or pairing are used:
- **Laptop $\to$ Robots (Channel `0`)**: Your Windows laptop broadcasts `START` (`1`) and `STOP` (`2`) on **BLE Channel `0`** using `BluetoothLEAdvertisementPublisher` (`0x0397` LEGO Manufacturer Data). All robots observe **only Channel `0`**.
- **Robots $\to$ Laptop (Channels `1..10`)**: Each robot (`ROBOT_ID = 1..10`) broadcasts its Standby status and 1.0s telemetry on its own channel (`1..10`). Your laptop passively listens on **Channels `1..10`**.

### Step 1: Start Robots in Standby
1. Start [`agent_robot.py`](agent_robot.py) on each robot (`ROBOT_ID = 1, 2, 3, ...`):
   - Each robot displays its centered `"I"`, `"S"`, or `"R"` icon with an **Orange** status light.
   - It broadcasts `"STANDBY"` on its channel (`ROBOT_ID`) and listens on **Channel `0`**.

### Step 2: Launch the Central Hub on Windows
Install `bleak` (which automatically installs the Windows WinRT Bluetooth advertisement packages):
```powershell
pip install bleak
python live_ble_receiver.py
```

The Central Hub passively listens on Channels `1..10` and detects robots in Standby:
```text
📡 Passive BLE Scanner active on Channels 1..10 (waiting for robots in Standby)...
[12:15:01] 🟠 Robot 1 (Channel 1) READY in Standby | SIR State: I
[12:15:01] 🟠 Robot 2 (Channel 2) READY in Standby | SIR State: S
[12:15:02] 🟠 Robot 3 (Channel 3) READY in Standby | SIR State: S
```

---

## 4. Running Experiments

### Start All Robots (`s` or `ENTER`):
Press **`s`** (or **`ENTER`**) in the laptop terminal:
- The laptop broadcasts `START` (`1`) on **BLE Channel `0`**.
- All robots observing Channel `0` simultaneously reset their timers to $t = 0.0\text{ s}$, beep, and start driving!
- Live telemetry from Channels `1..10` is logged in real time:
  ```text
  [12:15:05] 📡 Ch  1 | Robot 1 | t=  1.0s | State: I | Zone: 0 | Type: A
  [12:15:05] 📡 Ch  2 | Robot 2 | t=  1.0s | State: S | Zone: 0 | Type: B
  [12:15:05] 📡 Ch  3 | Robot 3 | t=  1.0s | State: S | Zone: 0 | Type: A
  ```

### Stop All Robots (`x` or `q`):
Press **`x`** (or **`q`**) in the terminal:
- The laptop broadcasts `STOP` (`2`) on **BLE Channel `0`**.
- All robots observing Channel `0` immediately stop their motors and halt broadcasting.
- The run is automatically saved (or auto-saved after 10 seconds of silence) to:
  ```text
  logs/run_01_YYYYMMDD_HHMMSS.json
  ```
