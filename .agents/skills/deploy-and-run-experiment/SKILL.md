---
name: deploy-and-run-experiment
description: >-
  Use this skill when deploying Pybricks scripts to SPIKE Prime hubs
  (Held-1..Held-10), retrying failed BLE uploads, running the host Central Hub
  experiment controller (`python -m host`), or saving console JSON logs.
---

# Deploy Hubs and Run Experiments

This project uses connectionless BLE broadcasts (`START`/`STOP` from host on Channel `0`; robot telemetry on Channels `1..max_robots`). Only the host PC starts and stops simulation runs.

## Steps

1. **Prepare Python Environment & Hubs**
   - Power on the SPIKE Prime hubs (`Held-1`..`Held-10`) and make sure they are **not** connected to `beta.pybricks.com` in a browser.
   - Ensure `.venv` is synced (run automatically by `deploy_script.ps1`, or run `.\venv.ps1` manually).

2. **Sync Config and Deploy to Robots**
   - Deploy `src/run_robot.py` to all configured hubs (automatically runs `python -m host.config_sync` first to generate `src/shared/generated_config.py`):
     ```powershell
     .\deploy_script.ps1
     ```
   - To deploy to a subset or retry failed hubs:
     ```powershell
     .\deploy_script.ps1 -RobotIds 1,2,3
     ```
   - Each deployed hub displays its SIR icon, turns its status light **Orange** (Standby), broadcasts `STANDBY`, and listens on Channel `0`.

3. **Start the Host Central Hub (Windows)**
   ```powershell
   uv run python -m host
   ```
   - Wait until expected robots appear as `READY in Standby` (verify with `status`).
   - Terminal commands:
     - `s` or `ENTER`: Broadcast `START` on Channel `0` (resets hub timers and starts driving).
     - `x` or `q`: Broadcast `STOP` on Channel `0` (halts all robots and saves the run).
     - `status`: List standby robots and current run counts.
     - `save`: Force-save buffered telemetry immediately.
     - `exit`: Quit cleanly.

4. **Check Saved Logs (or Recover Console Dumps)**
   - Runs auto-save to `logs/run_XX_YYYYMMDD_HHMMSS.json` on `STOP`, when `0` infected robots remain for `[host].no_infected_end_ms` (`5000 ms`), or after `[host].inactivity_timeout_ms` (`15000 ms`) of silence.
   - To manually save a hub's `=== JSON LOG DUMP START ===` console output into `logs/`:
     ```powershell
     uv run python -m host.log_saver
     ```
