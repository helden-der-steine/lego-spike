# LEGO SPIKE Prime - Agentic Robot (Pybricks Edition)

This project runs a multi-robot **SIR (Susceptible–Infected–Recovered) agent-based simulation** on LEGO SPIKE Prime hubs using **Pybricks firmware** and **100% connectionless Bluetooth Low Energy (BLE) broadcasts** (up to 10 robots, IDs `1..10`).

---

## 1. Local Environment Setup (`uv`)

This repository uses **[uv](https://docs.astral.sh/uv/)** to manage Python and dependencies ([pyproject.toml](pyproject.toml) + `uv.lock`).

### Installing `uv` (if not already installed)

- **Windows (PowerShell)**:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
  *(Or via `winget`: `winget install --id=astral-sh.uv -e`)*
- **macOS / Linux**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Official documentation**: [Astral `uv` Installation Guide](https://docs.astral.sh/uv/getting-started/installation/)

Restart your terminal after installation so `uv` is on your `PATH`, then create the `.venv` virtual environment and install all project dependencies (`bleak`, `pybricksdev`, and Pybricks API stubs):

```powershell
# Recommended on Windows (creates/syncs .venv via uv)
.\venv.ps1

# Or run uv directly
uv sync
```

---

## 2. Hub Hardware & Firmware Setup

1. **Flash Pybricks Firmware** on each SPIKE Prime hub via **[https://beta.pybricks.com/](https://beta.pybricks.com/)** (Settings $\to$ *Install Pybricks firmware*).
2. **Name each hub** `Held-1`, `Held-2`, ..., `Held-10` during firmware installation (or in Pybricks settings).
   - `agent_robot.py` reads the hub's Bluetooth name at startup and automatically maps the number (`1..10`) to its entry in `ROBOT_STATS` and its BLE telemetry channel.
3. **Hardware Ports** (configured in [agent_robot.py](agent_robot.py)):
   - `Port.A`: Ultrasonic / Distance Sensor
   - `Port.B`: Color Sensor
   - `Port.C`: Left Drive Motor
   - `Port.D`: Right Drive Motor

---

## 3. Configure Robots (Optional)

Per-robot parameters (`agent_type`, `initial_infected`, `vaccinated`) are defined centrally in the `ROBOT_STATS` table at the top of [agent_robot.py](agent_robot.py) (and mirrored in [live_ble_receiver.py](live_ble_receiver.py)):

- `agent_type`: `"A"` moves clockwise (`Yellow -> Blue -> Green -> Red`), `"B"` moves counter-clockwise (`Yellow -> Red -> Green -> Blue`).
- `initial_infected`: `True` starts as `"I"` (Red), `False` starts as `"S"` (Blue).
- `vaccinated`: `"No"` (or `"Yes"`).

---

## 4. Deploy Scripts to All Robots (`deploy_all.ps1`)

To upload and start `agent_robot.py` on the robots, make sure the hubs are **turned on** and **not connected to the browser**, then simply run [deploy_all.ps1](deploy_all.ps1) in PowerShell:

```powershell
.\deploy_all.ps1
```

What it does:
- Runs [venv.ps1](venv.ps1) to ensure `.venv` is created and synced via `uv`, then uses `.venv\Scripts\pybricksdev.exe`.
- Connects over BLE to `Held-1` through `Held-10`, uploads [agent_robot.py](agent_robot.py) with `--no-wait`, starts it in **Standby mode**, and disconnects to move on to the next hub.
- Prints a deployment summary and a ready-to-run retry command if any hub failed.

### Useful Options

```powershell
# Deploy only to specific robot IDs (e.g., 1, 2, 3)
.\deploy_all.ps1 -RobotIds 1,2,3

# Deploy a different script or custom hub name prefix
.\deploy_all.ps1 -ScriptPath color_sensor_logger.py -RobotIds 1 -HubNamePrefix "Held-"
```

Once deployed, each robot displays its centered SIR icon (`S`, `I`, `R`, or `V`), sets its status light to **Orange**, broadcasts `"STANDBY"` on its own channel (`ROBOT_ID`), and listens on **BLE Channel `0`**.

---

## 5. Run Experiments (`live_ble_receiver.py`)

No BLE GATT connections or pairing are used during experiments:
- **Laptop $\to$ Robots (Channel `0`)**: Broadcasts `START` (`1`) and `STOP` (`2`) via Windows WinRT `BluetoothLEAdvertisementPublisher` (`0x0397` LEGO Manufacturer Data).
- **Robots $\to$ Laptop (Channels `1..10`)**: Each robot broadcasts Standby heartbeats and telemetry (`5.0 s` periodic samples plus `Start`, `change_zone`, `Infection`, and `Recovery` events) on its own channel (`ROBOT_ID`).

### Start the Central Hub (Windows)

```powershell
uv run python live_ble_receiver.py
```

### Terminal Commands

| Command | Action |
| :--- | :--- |
| `s` or `ENTER` | Broadcast `START` on Channel `0` — all robots reset timers to `0.0 s`, beep, and start driving |
| `x` or `q` | Broadcast `STOP` on Channel `0` — halts all robots and saves the run |
| `status` | Show detected Standby robots and current run statistics |
| `save` | Immediately save buffered telemetry to JSON |
| `help` | Show command menu |
| `exit` | Quit Central Hub |

*(You can also start/stop an individual hub manually using its `RIGHT` / `LEFT` button.)*

Runs are automatically saved to `logs/run_XX_YYYYMMDD_HHMMSS.json` on `STOP`, when all infected robots have recovered (`5.0 s` confirmation), or after `15.0 s` of telemetry inactivity.

---

## 6. Simulation Rules, Tests & Repository Files

- **SIR Parameters** ([agent_robot.py](agent_robot.py)):
  - **Infection**: `30 s` co-location in the same valid color zone with an `"I"` robot, then `5%` probability per second.
  - **Recovery**: `"I"` $\to$ `"R"` after `120 s`.
  - **Auto-End**: Stops automatically after `3 s` with zero infected robots remaining.
- **Offline Tests**:
  ```powershell
  uv run python -m unittest test_simulation_offline.py
  ```
- **Repository Files**:
  - [pyproject.toml](pyproject.toml) — `uv` project configuration and Python dependencies.
  - [agent_robot.py](agent_robot.py) — Pybricks robot controller, zone navigation, obstacle/edge avoidance, and SIR state machine.
  - [deploy_all.ps1](deploy_all.ps1) — PowerShell BLE deployment script for hubs `Held-1`..`Held-10`.
  - [live_ble_receiver.py](live_ble_receiver.py) — Windows BLE broadcast controller and telemetry logger.
  - [test_simulation_offline.py](test_simulation_offline.py) — Offline unit tests.
  - [color_sensor_logger.py](color_sensor_logger.py) — Utility to inspect live `ColorSensor` HSV values over zones.
  - [download_log.py](download_log.py) — Utility to extract and save JSON log dumps from hub console output into `logs/`.
